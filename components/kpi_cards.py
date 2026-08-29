"""
components/kpi_cards.py - Tarjetas resumen de métricas clave del mercado
"""

import streamlit as st
import pandas as pd


def render_kpi_cards(df: pd.DataFrame, timeframe_label: str = "Diario"):
    """
    Renderiza las tarjetas superiores con estadísticas agregadas del universo de acciones.
    """
    if df.empty:
        return

    col1, col2, col3, col4, col5 = st.columns(5)

    # 1. Total acciones
    total_stocks = len(df)
    with col1:
        st.metric(
            label="Total Acciones",
            value=f"{total_stocks}",
            help=f"Empresas analizadas en temporalidad {timeframe_label}"
        )

    # 2. Amplitud de Mercado (% > SMA 200)
    valid_sma200 = df["DIFF_SMA_200_VAL"].dropna() if "DIFF_SMA_200_VAL" in df.columns else pd.Series(dtype=float)
    if not valid_sma200.empty:
        pct_above_200 = (valid_sma200 > 0).mean() * 100
        delta_label = "Fuerte" if pct_above_200 >= 60 else ("Débil" if pct_above_200 < 40 else "Neutral")
        with col2:
            st.metric(
                label=f"% > SMA 200 ({timeframe_label})",
                value=f"{pct_above_200:.1f}%",
                delta=delta_label,
                help=f"Porcentaje de acciones cotizando por encima de su Media Móvil de 200 períodos ({timeframe_label})"
            )
    else:
        with col2:
            st.metric(label=f"% > SMA 200 ({timeframe_label})", value="N/A")

    # 3. Acciones en Sobreventa (RSI < 30) y Sobrecompra (RSI > 70)
    valid_rsi = df["RSI_VAL"].dropna() if "RSI_VAL" in df.columns else pd.Series(dtype=float)
    if not valid_rsi.empty:
        oversold_count = int((valid_rsi < 30).sum())
        overbought_count = int((valid_rsi > 70).sum())
        with col3:
            st.metric(
                label=f"Extremos RSI ({timeframe_label})",
                value=f"🟢 {oversold_count} | 🔴 {overbought_count}",
                delta=f"{oversold_count} Sobreventa / {overbought_count} Sobrecompra",
                delta_color="off",
                help=f"🟢 Sobreventa (RSI < 30) | 🔴 Sobrecompra (RSI > 70) en {timeframe_label}"
            )
    else:
        with col3:
            st.metric(label=f"Extremos RSI ({timeframe_label})", value="N/A")

    # 4. PER Pasado Mediana (Trailing P/E)
    valid_trailing_pe = df["PER Pasado (Trailing)"].dropna() if "PER Pasado (Trailing)" in df.columns else pd.Series(dtype=float)
    if not valid_trailing_pe.empty:
        avg_trailing = valid_trailing_pe.median()
        with col4:
            st.metric(
                label="Mediana PER Pasado",
                value=f"{avg_trailing:.1f}x",
                help="Mediana del PER Pasado (Trailing P/E) de los últimos 12 meses"
            )
    else:
        with col4:
            st.metric(label="Mediana PER Pasado", value="N/A")

    # 5. PER Futuro Mediana (Forward P/E)
    valid_forward_pe = df["PER Futuro (Forward)"].dropna() if "PER Futuro (Forward)" in df.columns else pd.Series(dtype=float)
    if not valid_forward_pe.empty:
        avg_forward = valid_forward_pe.median()
        delta_pe = None
        if not valid_trailing_pe.empty:
            diff_pe = avg_forward - avg_trailing
            delta_pe = f"{diff_pe:+.1f}x vs Pasado"
        with col5:
            st.metric(
                label="Mediana PER Futuro",
                value=f"{avg_forward:.1f}x",
                delta=delta_pe,
                delta_color="inverse" if delta_pe and diff_pe < 0 else "normal",
                help="Mediana del PER Futuro (Forward P/E estimado para los próximos 12 meses)"
            )
    else:
        with col5:
            st.metric(label="Mediana PER Futuro", value="N/A")
