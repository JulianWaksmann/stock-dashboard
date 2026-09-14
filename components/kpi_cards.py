"""
components/kpi_cards.py - Tarjetas resumen de métricas clave del mercado
"""

import pandas as pd
import streamlit as st


def _kpi_total_stocks(df: pd.DataFrame, timeframe_label: str) -> dict:
    """1. Total de acciones analizadas."""
    return dict(
        label="Total Acciones",
        value=f"{len(df)}",
        help=f"Empresas analizadas en temporalidad {timeframe_label}"
    )


def _kpi_market_breadth(df: pd.DataFrame, timeframe_label: str) -> dict:
    """2. Amplitud de Mercado (% de acciones por encima de su SMA 200)."""
    valid_sma200 = df["DIFF_SMA_200_VAL"].dropna() if "DIFF_SMA_200_VAL" in df.columns else pd.Series(dtype=float)
    if valid_sma200.empty:
        return dict(label=f"% > SMA 200 ({timeframe_label})", value="N/A")

    pct_above_200 = (valid_sma200 > 0).mean() * 100
    delta_label = "Fuerte" if pct_above_200 >= 60 else ("Débil" if pct_above_200 < 40 else "Neutral")
    return dict(
        label=f"% > SMA 200 ({timeframe_label})",
        value=f"{pct_above_200:.1f}%",
        delta=delta_label,
        help=f"Porcentaje de acciones cotizando por encima de su Media Móvil de 200 períodos ({timeframe_label})"
    )


def _kpi_rsi_extremes(df: pd.DataFrame, timeframe_label: str) -> dict:
    """3. Acciones en Sobreventa (RSI < 30) y Sobrecompra (RSI > 70)."""
    valid_rsi = df["RSI_VAL"].dropna() if "RSI_VAL" in df.columns else pd.Series(dtype=float)
    if valid_rsi.empty:
        return dict(label=f"Extremos RSI ({timeframe_label})", value="N/A")

    oversold_count = int((valid_rsi < 30).sum())
    overbought_count = int((valid_rsi > 70).sum())
    return dict(
        label=f"Extremos RSI ({timeframe_label})",
        value=f"🟢 {oversold_count} | 🔴 {overbought_count}",
        delta=f"{oversold_count} Sobreventa / {overbought_count} Sobrecompra",
        delta_color="off",
        help=f"🟢 Sobreventa (RSI < 30) | 🔴 Sobrecompra (RSI > 70) en {timeframe_label}"
    )


def _kpi_trailing_pe_median(df: pd.DataFrame, timeframe_label: str) -> dict:
    """4. Mediana del PER Pasado (Trailing P/E)."""
    valid_trailing_pe = df["PER Pasado (Trailing)"].dropna() if "PER Pasado (Trailing)" in df.columns else pd.Series(dtype=float)
    if valid_trailing_pe.empty:
        return dict(label="Mediana PER Pasado", value="N/A")

    return dict(
        label="Mediana PER Pasado",
        value=f"{valid_trailing_pe.median():.1f}x",
        help="Mediana del PER Pasado (Trailing P/E) de los últimos 12 meses"
    )


def _kpi_forward_pe_median(df: pd.DataFrame, timeframe_label: str) -> dict:
    """5. Mediana del PER Futuro (Forward P/E), con delta vs la mediana del PER Pasado."""
    valid_forward_pe = df["PER Futuro (Forward)"].dropna() if "PER Futuro (Forward)" in df.columns else pd.Series(dtype=float)
    if valid_forward_pe.empty:
        return dict(label="Mediana PER Futuro", value="N/A")

    valid_trailing_pe = df["PER Pasado (Trailing)"].dropna() if "PER Pasado (Trailing)" in df.columns else pd.Series(dtype=float)
    avg_forward = valid_forward_pe.median()
    delta_pe = None
    diff_pe = None
    if not valid_trailing_pe.empty:
        diff_pe = avg_forward - valid_trailing_pe.median()
        delta_pe = f"{diff_pe:+.1f}x vs Pasado"

    return dict(
        label="Mediana PER Futuro",
        value=f"{avg_forward:.1f}x",
        delta=delta_pe,
        delta_color="inverse" if delta_pe and diff_pe < 0 else "normal",
        help="Mediana del PER Futuro (Forward P/E estimado para los próximos 12 meses)"
    )


# Una entrada por tarjeta, en el orden exacto en que deben mostrarse.
_KPI_BUILDERS = (
    _kpi_total_stocks,
    _kpi_market_breadth,
    _kpi_rsi_extremes,
    _kpi_trailing_pe_median,
    _kpi_forward_pe_median,
)


def render_kpi_cards(df: pd.DataFrame, timeframe_label: str = "Diario"):
    """
    Renderiza las tarjetas superiores con estadísticas agregadas del universo de acciones.
    Cada tarjeta se construye con su propio builder (_kpi_*) para no repetir el
    patrón "columna + validar vacío + st.metric" cinco veces.
    """
    if df.empty:
        return

    columns = st.columns(len(_KPI_BUILDERS))
    for col, build_kpi in zip(columns, _KPI_BUILDERS, strict=True):
        with col:
            st.metric(**build_kpi(df, timeframe_label))
