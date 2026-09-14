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
from bonds.catalog import BondTerms, base_ticker_of, find_terms, quote_currency_of, settlement_of
from bonds.flows_source import BondFlows
from bonds.scoring import evaluate_bond_attractiveness
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
    BOND_MIN_YEARS_FOR_GRADING,
    BOND_SETTLEMENT_MEP,
    BOND_SETTLEMENT_PESOS,
    BOND_SETTLEMENT_UNKNOWN,
    BOND_SIGNAL_NO_DATA,
    BOND_SIGNAL_RISK,
    BOND_SIGNAL_VERY_ATTRACTIVE,
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
    rows: list[dict] = []

    for _, quote in prices.iterrows():
        ticker = quote["Ticker"]
        terms = find_terms(catalog, ticker)
        flows = flows_by_base.get(base_ticker_of(ticker))
        settlement_kind = settlement_of(ticker)
        quote_currency = quote_currency_of(ticker)
        price = float(quote.get("Precio", np.nan))
        bid = float(quote.get("Punta Compra", np.nan))
        ask = float(quote.get("Punta Venta", np.nan))

        row = {
            "Atractivo": BOND_SIGNAL_NO_DATA,
            "Ticker": ticker,
            "Emisor": terms.issuer if terms else (flows.issuer if flows else "— (sin cronograma)"),
            "Sector": terms.sector if terms else "Sin clasificar",
            "Moneda": terms.currency if terms else (flows.currency if flows else "—"),
            "Liquidación": settlement_kind,
            "Moneda Precio": quote_currency or BOND_SETTLEMENT_UNKNOWN,
            "Ley": terms.law if terms else "—",
            "Cupón (%)": terms.coupon_rate if terms else np.nan,
            "Vencimiento": terms.maturity if terms else (flows.maturity if flows else pd.NaT),
            "Precio": price,
            "Var. (%)": float(quote.get("Var. (%)", np.nan)),
            "Punta Compra": bid,
            "Punta Venta": ask,
            "Spread (%)": _bid_ask_spread_pct(bid, ask),
            "Volumen": float(quote.get("Volumen", np.nan)),
            "Operaciones": float(quote.get("Operaciones", np.nan)),
            "Lámina Mínima": terms.min_denomination if terms else np.nan,
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
        }

        # Solo se descuenta el flujo cuando la especie cotiza en la misma
        # moneda en la que paga el bono. La especie en pesos de una ON en
        # dólares cotiza ~152.000 donde la especie MEP cotiza ~105: mezclarlas
        # no da una TIR mala, da una TIR sin ningún significado.
        priceable = np.isfinite(price) and price > 0

        metrics: dict = {}
        if priceable and terms is not None and quote_currency == terms.currency:
            metrics = _metrics_for_bond(terms, price, settlement, price_is_dirty)
        elif priceable and flows is not None and quote_currency == flows.currency:
            # El cronograma comunitario publica pagos totales, así que solo se
            # piden las métricas que no necesitan el desglose renta/capital.
            metrics = analyze_cashflows(list(flows.cashflows), settlement, price)
            metrics["years_to_maturity"] = max(year_fraction(settlement, flows.maturity), 0.0)

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
    comparable = df.loc[traded & long_enough, "TIR (%)"].dropna()
    median_ytm = comparable.median() if not comparable.empty else np.nan
    df["Atractivo"] = [
        evaluate_bond_attractiveness(
            ytm_pct=record["TIR (%)"],
            median_ytm_pct=median_ytm,
            modified_duration=record["Duration Mod."],
            parity_pct=record["Paridad (%)"],
            bid_ask_spread_pct=record["Spread (%)"],
            law=record["Ley"],
            years_to_maturity=record["Años al Vto."],
        )
        for record in df.to_dict("records")
    ]
    df.attrs["median_ytm_pct"] = median_ytm
    return df.sort_values(["TIR (%)"], ascending=False, na_position="last").reset_index(drop=True)


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
        filtered = filtered.nlargest(top_n, "Volumen", keep="all")

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
    return filtered.sort_values("TIR (%)", ascending=False, na_position="last").reset_index(drop=True)
