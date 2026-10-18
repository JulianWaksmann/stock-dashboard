"""
stock_screener.py - Filtros del panel de acciones, separados de la interfaz.

Es el equivalente de `bonds.panel.apply_bond_filters` para acciones, y está
acá por dos razones:

  * **Para poder testearlo.** El filtrado vivía dentro del cuerpo de la
    pestaña, mezclado con los widgets: cualquier error de comparación —un
    filtro que deja pasar lo que debería recortar— solo se veía mirando la
    pantalla con atención.
  * **Para que dos mercados compartan el mismo tamiz.** El panel de acciones
    de Estados Unidos y el de Argentina se filtran igual; lo que cambia es de
    dónde salen los precios, no qué significa "solo compras".

Las comparaciones son contra los literales de `constants.py`, nunca contra
texto escrito acá: el selector de Streamlit devuelve la opción elegida como
string, y si ese texto se duplica, el día que cambie una opción el filtro deja
de recortar en silencio, sin error.

Es puro: sin red y sin Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from constants import (
    BUY_SIGNALS,
    FILTER_FLOW_ACCUMULATION,
    FILTER_FLOW_ALL,
    FILTER_FLOW_DISTRIBUTION,
    FILTER_SIGNAL_ALL,
    FILTER_SIGNAL_BUY,
    FILTER_SIGNAL_SELL,
    FILTER_SIGNAL_SQUEEZE,
    FILTER_SIGNAL_STRONG_BUY,
    FILTER_SMA200_ALL,
    FILTER_SMA200_BEARISH,
    FILTER_SMA200_BULLISH,
    FLOW_ACCUMULATION,
    FLOW_DISTRIBUTION,
    SELL_SIGNALS,
    SIGNAL_STRONG_BUY,
)


@dataclass(frozen=True)
class StockFilters:
    """
    Lo que eligió quien mira, sin saber nada de widgets.

    Los valores por omisión son "no filtrar nada", así que construirla vacía
    devuelve el panel entero: un filtro que no se tocó nunca recorta.
    """

    signal: str = FILTER_SIGNAL_ALL
    flow: str = FILTER_FLOW_ALL
    rsi_range: tuple[float, float] = (0.0, 100.0)
    sma200: str = FILTER_SMA200_ALL


def apply_stock_filters(df: pd.DataFrame, filters: StockFilters) -> pd.DataFrame:
    """
    Recorta el panel según los filtros elegidos.

    Las filas sin RSI **pasan** el filtro de RSI a propósito: un ticker cuyos
    indicadores no se pudieron calcular no es un ticker fuera de rango, y
    esconderlo haría que el panel disimule una falla de datos en vez de
    mostrarla.

    Devuelve una copia, nunca una vista: quien reciba el resultado puede
    agregarle columnas sin que pandas avise de escrituras sobre una vista.
    """
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df.copy()

    if filters.signal == FILTER_SIGNAL_STRONG_BUY:
        out = out[out["Semáforo"] == SIGNAL_STRONG_BUY]
    elif filters.signal == FILTER_SIGNAL_BUY:
        out = out[out["Semáforo"].isin(BUY_SIGNALS)]
    elif filters.signal == FILTER_SIGNAL_SELL:
        out = out[out["Semáforo"].isin(SELL_SIGNALS)]
    elif filters.signal == FILTER_SIGNAL_SQUEEZE:
        out = out[out["Semáforo"].str.contains("SQUEEZE", na=False)]

    if filters.flow == FILTER_FLOW_ACCUMULATION:
        out = out[out["Flujo Institucional"] == FLOW_ACCUMULATION]
    elif filters.flow == FILTER_FLOW_DISTRIBUTION:
        out = out[out["Flujo Institucional"] == FLOW_DISTRIBUTION]

    minimo, maximo = filters.rsi_range
    out = out[
        out["RSI_VAL"].isna()
        | ((out["RSI_VAL"] >= minimo) & (out["RSI_VAL"] <= maximo))
    ]

    if filters.sma200 == FILTER_SMA200_BULLISH:
        out = out[out["DIFF_SMA_200_VAL"] > 0]
    elif filters.sma200 == FILTER_SMA200_BEARISH:
        out = out[out["DIFF_SMA_200_VAL"] < 0]

    return out.copy()
