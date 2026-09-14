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

from bonds.bond_math import analyze_bond
from bonds.catalog import BondTerms
from bonds.scoring import evaluate_bond_attractiveness
from constants import BOND_SIGNAL_NO_DATA

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
) -> pd.DataFrame:
    """
    Cruza precios, condiciones de emisión y métricas en el cuadro final.

    Es una función pura (no descarga nada) para poder testearla con precios y
    catálogo fijos: toda la aritmética que la interfaz muestra pasa por acá.

    El semáforo se asigna en una segunda pasada porque depende de la mediana de
    TIR del panel, que recién se conoce cuando están calculadas todas las filas.
    """
    if prices.empty:
        return pd.DataFrame()

    treasury_curve = treasury_curve or {}
    rows: list[dict] = []

    for _, quote in prices.iterrows():
        ticker = quote["Ticker"]
        terms = catalog.get(ticker)
        price = float(quote.get("Precio", np.nan))
        bid = float(quote.get("Punta Compra", np.nan))
        ask = float(quote.get("Punta Venta", np.nan))

        row = {
            "Atractivo": BOND_SIGNAL_NO_DATA,
            "Ticker": ticker,
            "Emisor": terms.issuer if terms else "— (fuera del catálogo)",
            "Sector": terms.sector if terms else "Sin clasificar",
            "Moneda": terms.currency if terms else "—",
            "Ley": terms.law if terms else "—",
            "Cupón (%)": terms.coupon_rate if terms else np.nan,
            "Vencimiento": terms.maturity if terms else pd.NaT,
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

        if terms is not None and np.isfinite(price) and price > 0:
            metrics = _metrics_for_bond(terms, price, settlement, price_is_dirty)
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
    known_yields = df["TIR (%)"].dropna()
    median_ytm = known_yields.median() if not known_yields.empty else np.nan
    df["Atractivo"] = [
        evaluate_bond_attractiveness(
            ytm_pct=record["TIR (%)"],
            median_ytm_pct=median_ytm,
            modified_duration=record["Duration Mod."],
            parity_pct=record["Paridad (%)"],
            bid_ask_spread_pct=record["Spread (%)"],
            law=record["Ley"],
        )
        for record in df.to_dict("records")
    ]
    df.attrs["median_ytm_pct"] = median_ytm
    return df.sort_values(["TIR (%)"], ascending=False, na_position="last").reset_index(drop=True)
