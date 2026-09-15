"""
bonds/panel.py - Armado del cuadro de ONs a partir de precios y condiciones.

Es la capa pura entre la descarga (`bonds/data_loader.py`) y el dibujo
(`components/bonds_table.py`): recibe precios y catálogo ya resueltos y
devuelve el DataFrame final con todas las métricas calculadas.

Está separada de `data_loader` a propósito: sin `streamlit` ni `requests` de por
medio, toda la aritmética que el usuario termina viendo en pantalla se puede
testear pasándole un puñado de filas fijas, sin red y sin mocks.
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd

from bonds.bond_math import analyze_bond, analyze_cashflows, year_fraction
from bonds.byma_terms import ASSUMED_COUPON_FREQUENCY, BondReference
from bonds.catalog import BondTerms, base_ticker_of, find_terms, quote_currency_of, settlement_of
from bonds.flows_source import BondFlows
from bonds.scoring import compute_opportunity_scores, evaluate_bond_attractiveness, label_from_score
from constants import (
    BOND_ATTRACTIVE_SIGNALS,
    BOND_FILTER_LAW_ARG,
    BOND_FILTER_LAW_NY,
    BOND_FILTER_LIQUIDITY_ALL,
    BOND_FILTER_SETTLEMENT_MEP,
    BOND_FILTER_SETTLEMENT_PESOS,
    BOND_FILTER_SETTLEMENT_USD,
    BOND_FILTER_SIGNAL_ATTRACTIVE,
    BOND_FILTER_SIGNAL_RISK,
    BOND_FILTER_SIGNAL_VERY_ATTRACTIVE,
    BOND_LAW_INFERRED_SUFFIX,
    BOND_MIN_YEARS_FOR_GRADING,
    BOND_PRICE_CLEAN,
    BOND_PRICE_DIRTY,
    BOND_SETTLEMENT_MEP,
    BOND_SETTLEMENT_PESOS,
    BOND_SETTLEMENT_UNKNOWN,
    BOND_SIGNAL_NO_DATA,
    BOND_SIGNAL_RISK,
    BOND_SIGNAL_VERY_ATTRACTIVE,
    BOND_SIGNAL_VERY_SHORT,
    BOND_SOURCE_BYMA,
    BOND_SOURCE_CATALOG,
    BOND_SOURCE_NONE,
    BOND_TOP_VOLUME_SIZES,
)

logger = logging.getLogger(__name__)


def interpolate_treasury_yield(curve: dict[float, float], tenor_years: float | None) -> float | None:
    """
    Rendimiento del Tesoro para un plazo arbitrario, por interpolación lineal
    entre los tramos disponibles.

    Fuera del rango publicado se extiende con el tramo más cercano en vez de
    extrapolar: extrapolar una curva de tasas más allá de 30 años (o por debajo
    de 3 meses) genera números que no existen en ningún mercado.
    """
    if not curve or tenor_years is None or not np.isfinite(float(tenor_years)):
        return None

    tenors = sorted(curve)
    if tenor_years <= tenors[0]:
        return curve[tenors[0]]
    if tenor_years >= tenors[-1]:
        return curve[tenors[-1]]

    for lower, upper in zip(tenors, tenors[1:], strict=False):
        if lower <= tenor_years <= upper:
            weight = (tenor_years - lower) / (upper - lower)
            return curve[lower] + weight * (curve[upper] - curve[lower])
    return None


def _num(value) -> float:
    """
    Normaliza a float los resultados de `bond_math`, que usa `None` para
    "no calculable". Pandas trabaja con NaN, no con None: mezclar ambos
    convierte una columna numérica en columna de objetos y rompe el formato
    y las comparaciones de la tabla.
    """
    if value is None:
        return np.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _can_rebuild_from_reference(reference: BondReference | None, quote_currency: str | None) -> bool:
    """
    True si el flujo de un bono se puede reconstruir desde su ficha técnica.

    Exige las cuatro cosas sin las cuales el flujo no queda determinado: tasa
    fija (una variable no se puede descontar, su cupón futuro no existe
    todavía), amortización bullet, fechas de emisión y vencimiento, y que la
    moneda de la especie coincida con la del bono.
    """
    if reference is None or quote_currency is None:
        return False
    if reference.coupon_rate is None or not reference.is_bullet:
        return False
    if reference.issue_date is None or reference.maturity is None:
        return False
    if reference.maturity <= reference.issue_date:
        return False
    return _reference_currency(reference) == quote_currency


def _inferred_law_label(reference: BondReference | None) -> str | None:
    """Ley deducida del ISIN, marcada como inferencia y no como dato declarado."""
    if reference is None or not reference.inferred_law:
        return None
    return f"{reference.inferred_law}{BOND_LAW_INFERRED_SUFFIX}"


def _reference_currency(reference: BondReference) -> str | None:
    """
    Moneda de emisión según la ficha técnica, que la escribe en castellano.

    BYMA devuelve "Dólares" o "Pesos" acá, y los códigos ISO en el panel de
    precios. Se traduce en un solo lugar para que la comparación con la moneda
    de la especie sea entre iguales.
    """
    text = (reference.currency or "").strip().upper()
    if text.startswith("DOLAR") or text.startswith("DÓLAR") or text == "USD":
        return "USD"
    if text.startswith("PESO") or text == "ARS":
        return "ARS"
    return None


def _metrics_from_reference(
    reference: BondReference,
    price: float,
    settlement: date,
    price_is_dirty: bool,
) -> dict:
    """Corre el análisis completo sobre el flujo reconstruido de un bullet."""
    try:
        return analyze_bond(
            issue_date=reference.issue_date,
            maturity=reference.maturity,
            coupon_rate=reference.coupon_rate,
            frequency=ASSUMED_COUPON_FREQUENCY,
            settlement=settlement,
            price=price,
            amortizations=(),
            price_is_dirty=price_is_dirty,
        )
    except (ValueError, ZeroDivisionError, OverflowError):
        logger.warning("No se pudo reconstruir el flujo de %s", reference.ticker, exc_info=True)
        return {}


def _first_known(*values, default=None):
    """
    Primer valor no vacío de la lista, en orden de confiabilidad de la fuente.

    El orden con que se llama no es casual: primero el catálogo cargado a mano,
    después la ficha técnica del mercado, y al final el dataset comunitario.
    Cada fuente es más autoritativa que la siguiente, y la única forma de que
    eso quede claro es que el orden de los argumentos lo diga.
    """
    for value in values:
        if value is None:
            continue
        if isinstance(value, float) and np.isnan(value):
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return default


def _bid_ask_spread_pct(bid: float, ask: float) -> float:
    """
    Spread punta compradora / punta vendedora, en % del punto medio.

    Es la medida práctica de liquidez de una ON: lo que cuesta entrar y salir
    en el acto. Sin las dos puntas no hay spread que medir y devuelve NaN.
    """
    if not np.isfinite(bid) or not np.isfinite(ask) or bid <= 0 or ask <= 0 or ask < bid:
        return np.nan
    midpoint = (bid + ask) / 2.0
    return (ask - bid) / midpoint * 100.0


def _metrics_for_bond(
    terms: BondTerms,
    price: float,
    settlement: date,
    price_is_dirty: bool,
) -> dict:
    """Corre el análisis financiero de una ON, tolerando datos inconsistentes."""
    try:
        return analyze_bond(
            issue_date=terms.issue_date,
            maturity=terms.maturity,
            coupon_rate=terms.coupon_rate,
            frequency=terms.frequency,
            settlement=settlement,
            price=price,
            amortizations=terms.amortizations,
            price_is_dirty=price_is_dirty,
        )
    except (ValueError, ZeroDivisionError, OverflowError):
        logger.warning("No se pudieron calcular las métricas de %s", terms.ticker, exc_info=True)
        return {}


def build_bonds_panel(
    prices: pd.DataFrame,
    catalog: dict[str, BondTerms],
    settlement: date,
    price_is_dirty: bool = True,
    treasury_curve: dict[float, float] | None = None,
    flows_by_base: dict[str, BondFlows] | None = None,
    references: dict[str, BondReference] | None = None,
) -> pd.DataFrame:
    """
    Cruza precios, cronogramas de pago y métricas en el cuadro final.

    Un bono puede conocerse de dos maneras, y el panel usa las dos:

      * Por sus **condiciones de emisión** (catálogo local): permite calcular
        todo, incluidas paridad, valor técnico y vida promedio, porque se sabe
        qué parte de cada pago es renta y qué parte capital. Hay que cargarlo
        a mano, así que manda cuando está: es una decisión explícita.
      * Por su **cronograma de pagos ya resuelto** (fuente comunitaria): da
        cobertura sin mantenimiento, pero solo informa el total de cada pago,
        así que alcanza para TIR, duration y convexidad y no para el resto.

    Es una función pura (no descarga nada) para poder testearla con precios,
    catálogo y cronogramas fijos: toda la aritmética que la interfaz muestra
    pasa por acá.

    El semáforo se asigna en una segunda pasada porque depende de la mediana de
    TIR del panel, que recién se conoce cuando están calculadas todas las filas.
    """
    if prices.empty:
        return pd.DataFrame()

    treasury_curve = treasury_curve or {}
    flows_by_base = flows_by_base or {}
    references = references or {}
    rows: list[dict] = []

    for _, quote in prices.iterrows():
        ticker = quote["Ticker"]
        terms = find_terms(catalog, ticker)
        flows = flows_by_base.get(base_ticker_of(ticker))
        reference = references.get(base_ticker_of(ticker))
        settlement_kind = settlement_of(ticker)
        # La moneda del precio sale del feed cuando la informa, y del sufijo del
        # ticker cuando no: el dato le gana a la convención.
        quote_currency = _first_known(
            quote.get("Moneda Precio") if "Moneda Precio" in quote.index else None,
            quote_currency_of(ticker),
        )
        price = float(quote.get("Precio", np.nan))
        bid = float(quote.get("Punta Compra", np.nan))
        ask = float(quote.get("Punta Venta", np.nan))

        row = {
            "Atractivo": BOND_SIGNAL_NO_DATA,
            "Ticker": ticker,
            "Emisor": _first_known(
                terms.issuer if terms else None,
                reference.issuer if reference else None,
                flows.issuer if flows else None,
                default="— (sin datos)",
            ),
            "Sector": terms.sector if terms else "Sin clasificar",
            "Moneda": _first_known(
                terms.currency if terms else None,
                reference.currency if reference else None,
                flows.currency if flows else None,
                default="—",
            ),
            "Liquidación": settlement_kind,
            "Moneda Precio": quote_currency or BOND_SETTLEMENT_UNKNOWN,
            # El catálogo declara la ley; BYMA no (sus campos vienen vacíos),
            # así que en su lugar se infiere del prefijo del ISIN y se marca
            # como inferida para que no se lea como dato declarado.
            "Ley": _first_known(
                terms.law if terms else None,
                _inferred_law_label(reference),
                default="—",
            ),
            "Cupón (%)": terms.coupon_rate if terms else np.nan,
            "Vencimiento": _first_known(
                terms.maturity if terms else None,
                reference.maturity if reference else None,
                flows.maturity if flows else None,
                default=pd.NaT,
            ),
            "Precio": price,
            "Var. (%)": float(quote.get("Var. (%)", np.nan)),
            "Punta Compra": bid,
            "Punta Venta": ask,
            "Spread (%)": _bid_ask_spread_pct(bid, ask),
            "Volumen": float(quote.get("Volumen", np.nan)),
            "Operaciones": float(quote.get("Operaciones", np.nan)),
            "Lámina Mínima": _first_known(
                terms.min_denomination if terms else None,
                reference.min_denomination if reference else None,
                default=np.nan,
            ),
            "ISIN": reference.isin if reference else None,
            "En Default": bool(reference.in_default) if reference else False,
            "Garantía": reference.guarantee if reference else None,
            "Calificación": terms.rating if terms else "s/c",
            "Verificado": bool(terms.verified) if terms else False,
            "En Catálogo": terms is not None,
            "Fuente": BOND_SOURCE_CATALOG if terms else (flows.source if flows else BOND_SOURCE_NONE),
            "TIR (%)": np.nan,
            "Current Yield (%)": np.nan,
            "Duration Mod.": np.nan,
            "Duration Mac.": np.nan,
            "Convexidad": np.nan,
            "Vida Prom. (años)": np.nan,
            "Paridad (%)": np.nan,
            "Valor Técnico": np.nan,
            "Interés Corrido": np.nan,
            "Capital Residual": np.nan,
            "Años al Vto.": np.nan,
            "Spread vs UST (pb)": np.nan,
            # Qué convención de precio se aplicó de verdad en esta fila.
            "Convención Aplicada": BOND_PRICE_DIRTY if price_is_dirty else BOND_PRICE_CLEAN,
        }

        # Solo se descuenta el flujo cuando la especie cotiza en la misma
        # moneda en la que paga el bono. La especie en pesos de una ON en
        # dólares cotiza ~152.000 donde la especie MEP cotiza ~105: mezclarlas
        # no da una TIR mala, da una TIR sin ningún significado.
        priceable = np.isfinite(price) and price > 0

        metrics: dict = {}
        if priceable and terms is not None and quote_currency == terms.currency:
            metrics = _metrics_for_bond(terms, price, settlement, price_is_dirty)
        elif priceable and _can_rebuild_from_reference(reference, quote_currency):
            # Bullet a tasa fija: con emisión, vencimiento, tasa y la certeza
            # de que el capital vuelve entero al final, el flujo queda
            # determinado salvo la frecuencia de pago, que BYMA no publica. Al
            # conocerse el desglose renta/capital, acá sí salen paridad, valor
            # técnico e interés corrido, que el cronograma comunitario no
            # permite calcular.
            metrics = _metrics_from_reference(reference, price, settlement, price_is_dirty)
            if metrics:
                row["Fuente"] = BOND_SOURCE_BYMA
                row["Convención Aplicada"] = BOND_PRICE_DIRTY if price_is_dirty else BOND_PRICE_CLEAN

        elif priceable and flows is not None and quote_currency == flows.currency:
            # El cronograma comunitario publica pagos totales, así que solo se
            # piden las métricas que no necesitan el desglose renta/capital.
            #
            # `price_is_dirty` no se puede honrar por este camino: pasar de
            # precio limpio a sucio exige el interés corrido, y el interés
            # corrido exige saber qué parte de cada pago es renta. El precio se
            # toma como sucio —la convención de BYMA— y la fila lo deja dicho,
            # en vez de aplicar en silencio una opción que acá no hace nada.
            metrics = analyze_cashflows(list(flows.cashflows), settlement, price)
            metrics["years_to_maturity"] = max(year_fraction(settlement, flows.maturity), 0.0)
            row["Convención Aplicada"] = BOND_PRICE_DIRTY

        if metrics:
            row.update(
                {
                    "TIR (%)": _num(metrics.get("ytm_pct")),
                    "Current Yield (%)": _num(metrics.get("current_yield_pct")),
                    "Duration Mod.": _num(metrics.get("modified_duration")),
                    "Duration Mac.": _num(metrics.get("macaulay_duration")),
                    "Convexidad": _num(metrics.get("convexity")),
                    "Vida Prom. (años)": _num(metrics.get("weighted_average_life")),
                    "Paridad (%)": _num(metrics.get("parity_pct")),
                    "Valor Técnico": _num(metrics.get("technical_value")),
                    "Interés Corrido": _num(metrics.get("accrued_interest")),
                    "Capital Residual": _num(metrics.get("residual_capital")),
                    "Años al Vto.": _num(metrics.get("years_to_maturity")),
                }
            )
            # El spread crediticio se mide contra el tramo del Tesoro de
            # duration equivalente, no contra el plazo al vencimiento: es
            # el plazo efectivo del dinero lo que hay que comparar.
            #
            # Y solo si la TIR está en dólares: restarle un rendimiento en
            # dólares a una TIR en pesos devuelve un número enorme con formato
            # de spread crediticio que en realidad mezcla riesgo de crédito con
            # expectativa de devaluación.
            if quote_currency == "USD":
                benchmark = interpolate_treasury_yield(treasury_curve, row["Duration Mod."])
                if benchmark is not None and np.isfinite(row["TIR (%)"]):
                    row["Spread vs UST (pb)"] = (row["TIR (%)"] - benchmark) * 100.0

        rows.append(row)

    df = pd.DataFrame(rows)

    # Segunda pasada: el atractivo es relativo al panel, así que necesita la
    # mediana de TIR del día ya calculada. Si ninguna ON tiene TIR (catálogo
    # vacío) no hay mediana que calcular: pedírsela a pandas sobre una columna
    # entera de NaN devuelve NaN pero emitiendo un RuntimeWarning de numpy.
    # Dos exclusiones de la mediana, por el mismo motivo: es la referencia
    # contra la que se califica todo el panel, así que no puede construirse
    # con datos que no son comparables.
    #   - Las ONs a semanas del vencimiento: su TIR anualizada es un artefacto
    #     aritmético, no una medida de rendimiento.
    #   - Las que no operaron: su precio es el de la última rueda en que se
    #     negociaron, así que su TIR mide el mercado de otro día.
    traded = ~(df["Volumen"].notna() & (df["Volumen"] <= 0))
    long_enough = df["Años al Vto."] >= BOND_MIN_YEARS_FOR_GRADING
    # Una sola máscara para las dos cosas: la mediana de TIR y la población
    # contra la que se rankea cada dimensión tienen que ser el mismo conjunto.
    #
    # Pasarla no es opcional. El panel de BYMA trae el mercado entero (~2700
    # especies) y solo unas pocas decenas tienen cronograma de pagos conocido,
    # así que TIR y duration existen en una fracción mínima de las filas. Si el
    # ranking se hace contra el panel completo, esas dos dimensiones caen por
    # debajo de BOND_SCORE_MIN_DIMENSION_COVERAGE y se descartan para todos:
    # queda solo liquidez, cuyo peso no llega a BOND_SCORE_MIN_COVERAGE, y
    # entonces NINGUNA ON recibe puntaje. El cuadro entero sale "⚪ SIN DATOS".
    is_comparable = traded & long_enough & df["TIR (%)"].notna()
    median_ytm = df.loc[is_comparable, "TIR (%)"].median() if is_comparable.any() else np.nan
    # El puntaje pondera cada dimensión contra el resto del panel, así que
    # necesita todas las filas calculadas: por eso va en esta segunda pasada.
    scores = compute_opportunity_scores(df, median_ytm, comparable=is_comparable)
    for column in scores.columns:
        df[column] = scores[column]

    # La etiqueta sale del puntaje, salvo los dos casos que el puntaje no
    # puede expresar: una prima de riesgo que delata estrés crediticio y una
    # vida residual tan corta que la TIR deja de ser comparable. Esos dos se
    # resuelven antes y ganan.
    labels = []
    for record in df.to_dict("records"):
        override = evaluate_bond_attractiveness(
            ytm_pct=record["TIR (%)"],
            median_ytm_pct=median_ytm,
            modified_duration=record["Duration Mod."],
            parity_pct=record["Paridad (%)"],
            bid_ask_spread_pct=record["Spread (%)"],
            law=record["Ley"],
            years_to_maturity=record["Años al Vto."],
        )
        if override in (BOND_SIGNAL_RISK, BOND_SIGNAL_VERY_SHORT, BOND_SIGNAL_NO_DATA):
            labels.append(override)
        else:
            labels.append(label_from_score(record["Puntaje"]))
    df["Atractivo"] = labels
    df.attrs["median_ytm_pct"] = median_ytm
    # Se ordena por puntaje y no por TIR: la pregunta del panel es cuál es la
    # mejor oportunidad, no cuál rinde más nominalmente.
    return df.sort_values(
        ["Puntaje", "TIR (%)"], ascending=False, na_position="last"
    ).reset_index(drop=True)


def _collapse_to_one_row_per_bond(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deja una sola fila por bono, la de la especie más operada.

    Se usa cuando se piden las dos especies en dólares a la vez. MEP y cable
    son el mismo bono cobrado en distinto lugar, así que mostrar las dos
    duplica cada emisión: en un recorte "top 50 por volumen" eso significa que
    la mitad de los lugares se los llevan repeticiones en vez de bonos
    distintos. Se conserva la especie con más volumen, que es la que tiene el
    precio más representativo.
    """
    if df.empty:
        return df
    ranked = df.assign(_raiz=df["Ticker"].map(base_ticker_of)).sort_values(
        "Volumen", ascending=False, na_position="last"
    )
    return ranked.drop_duplicates("_raiz", keep="first").drop(columns="_raiz")


def _top_by_volume_within_currency(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """
    Las N especies más operadas, rankeadas **dentro de cada moneda**.

    El volumen de la especie en pesos está expresado en pesos y el de la
    especie MEP en dólares. Rankeando las dos juntas, un "top 20" se llena de
    filas en pesos por tener el número más grande y no por operar más: con 30
    especies en pesos y 10 en dólares, el top 20 devolvía 30 filas y ninguna en
    dólares. Cuando el filtro de moneda ya dejó una sola, esto equivale a
    rankear el panel entero.

    Se corta en N exacto (`keep="first"`): con empates, `keep="all"` devolvía
    más filas de las pedidas, que es lo contrario de lo que significa un tope.
    """
    if "Moneda Precio" not in df.columns:
        return df.nlargest(top_n, "Volumen", keep="first")

    # Se usa un rank dentro del grupo en lugar de `groupby().apply(nlargest)`:
    # el apply reconstruye el DataFrame y puede perder la columna de agrupación,
    # mientras que el rank filtra sobre el original y conserva orden y columnas.
    position = df.groupby("Moneda Precio", dropna=False)["Volumen"].rank(
        method="first", ascending=False
    )
    return df[position <= top_n]


def apply_bond_filters(
    df: pd.DataFrame,
    *,
    settlement_filter: str,
    liquidity_filter: str,
    signal_filter: str,
    law_filter: str,
    max_duration: float | None = None,
    only_with_yield: bool = False,
) -> pd.DataFrame:
    """
    Aplica los filtros del panel. Vive acá, y no en la capa de dibujo, porque
    el ORDEN en que se aplican cambia el resultado y eso merece tests.

    El orden es:

      1. **Moneda.** Va primero porque el volumen de la especie en pesos está
         expresado en pesos y el de la especie MEP en dólares: rankear por
         volumen mezclando ambas compara unidades distintas, y ganarían las
         filas en pesos por tener el número más grande, no por operar más.
      2. **Una fila por bono**, cuando se pidieron las dos especies en dólares.
      3. **Liquidez.** El "top N" rankea contra todo el universo de esa moneda
         y no contra lo que dejen los filtros de abajo: "las 50 más operadas"
         no debe depender de si además se filtró por ley.
      4. El resto (atractivo, ley, duration, TIR calculada), que solo recortan.
    """
    filtered = df.copy()

    if settlement_filter == BOND_FILTER_SETTLEMENT_USD:
        filtered = filtered[filtered["Moneda Precio"] == "USD"]
        filtered = _collapse_to_one_row_per_bond(filtered)
    elif settlement_filter == BOND_FILTER_SETTLEMENT_MEP:
        filtered = filtered[filtered["Liquidación"] == BOND_SETTLEMENT_MEP]
    elif settlement_filter == BOND_FILTER_SETTLEMENT_PESOS:
        filtered = filtered[filtered["Liquidación"] == BOND_SETTLEMENT_PESOS]

    if liquidity_filter != BOND_FILTER_LIQUIDITY_ALL:
        filtered = filtered[filtered["Volumen"].isna() | (filtered["Volumen"] > 0)]

    top_n = BOND_TOP_VOLUME_SIZES.get(liquidity_filter)
    # `nlargest` sobre un DataFrame vacío falla si la columna quedó sin dtype
    # numérico, y quedar vacío es un resultado normal acá: alcanza con que el
    # filtro de moneda no deje ninguna fila.
    if top_n is not None and not filtered.empty:
        filtered = _top_by_volume_within_currency(filtered, top_n)

    if signal_filter == BOND_FILTER_SIGNAL_ATTRACTIVE:
        filtered = filtered[filtered["Atractivo"].isin(BOND_ATTRACTIVE_SIGNALS)]
    elif signal_filter == BOND_FILTER_SIGNAL_VERY_ATTRACTIVE:
        filtered = filtered[filtered["Atractivo"] == BOND_SIGNAL_VERY_ATTRACTIVE]
    elif signal_filter == BOND_FILTER_SIGNAL_RISK:
        filtered = filtered[filtered["Atractivo"] == BOND_SIGNAL_RISK]

    if law_filter == BOND_FILTER_LAW_NY:
        filtered = filtered[filtered["Ley"] == "NY"]
    elif law_filter == BOND_FILTER_LAW_ARG:
        filtered = filtered[filtered["Ley"] == "ARG"]

    # Una ON sin cronograma conocido no es "de duration alta", es de duration
    # desconocida. Ocultarla es decisión del filtro de al lado, no de este.
    if max_duration is not None:
        filtered = filtered[filtered["Duration Mod."].isna() | (filtered["Duration Mod."] <= max_duration)]

    if only_with_yield:
        filtered = filtered[filtered["TIR (%)"].notna()]

    # Se devuelve en el mismo orden que arma build_bonds_panel (mayor TIR
    # primero), que los pasos de ranking y deduplicación alteran.
    # Se ordena por puntaje y, a igualdad, por TIR. Se toman solo las columnas
    # presentes para que la función siga sirviendo sobre un panel recortado.
    sort_columns = [c for c in ("Puntaje", "TIR (%)") if c in filtered.columns]
    if sort_columns:
        filtered = filtered.sort_values(sort_columns, ascending=False, na_position="last")
    return filtered.reset_index(drop=True)
