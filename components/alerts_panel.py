"""
components/alerts_panel.py - Panel superior de alertas rápidas por Sistema de Grados
"""

import pandas as pd
import streamlit as st

from components.formatting import format_signed_pct
from constants import (
    SIGNAL_MODERATE_BUY,
    SIGNAL_MODERATE_SELL,
    SIGNAL_SQUEEZE,
    SIGNAL_STRONG_BUY,
    SIGNAL_STRONG_SELL,
)


def render_alerts_panel(df: pd.DataFrame):
    """
    Renderiza 3 columnas con alertas de confluencia categorizadas por grado de convicción:
      1. 🔴 Venta / Rotar (Fuerte 🚨 y Moderada 🟠)
      2. 🟢 Compra / Swing (Fuerte 🌟 y Moderada 🟢)
      3. 🚨 Squeezes (Compresión de volatilidad)
    """
    if df.empty or "Semáforo" not in df.columns:
        return

    # Filtros por Grados
    all_sales = df[df["Semáforo"].isin([SIGNAL_STRONG_SELL, SIGNAL_MODERATE_SELL])]
    all_buys = df[df["Semáforo"].isin([SIGNAL_STRONG_BUY, SIGNAL_MODERATE_BUY])]
    squeeze_stocks = df[df["Semáforo"] == SIGNAL_SQUEEZE]

    col1, col2, col3 = st.columns(3)

    # 1. 🔴 Venta / Rotación
    with col1:
        st.markdown("#### 🔴 Venta / Rotación")
        if not all_sales.empty:
            for _, r in all_sales.iterrows():
                tag = "🚨 Fuerte" if r["Semáforo"] == SIGNAL_STRONG_SELL else "🟠 Moderada"
                dist_52w = format_signed_pct(r['DIST_52W_HIGH_PCT'], decimals=1)
                st.markdown(f"- **`{r['Ticker']}`** [{tag}] — ${r['Precio Actual']:.2f} *(RSI: {r['RSI_VAL']:.1f}, Máx 52S: {dist_52w})*")
        else:
            st.caption("Ninguno hoy *(Sin sobrecompras extremas)*")

    # 2. 🟢 Compra / Swing
    with col2:
        st.markdown("#### 🟢 Compra / Swing")
        if not all_buys.empty:
            for _, r in all_buys.iterrows():
                tag = "🌟 Fuerte" if r["Semáforo"] == SIGNAL_STRONG_BUY else "🟢 Moderada"
                dist_sma50 = format_signed_pct(r['DIFF_SMA_50_VAL'], decimals=1)
                st.markdown(f"- **`{r['Ticker']}`** [{tag}] — ${r['Precio Actual']:.2f} *(RSI: {r['RSI_VAL']:.1f}, vs SMA50: {dist_sma50})*")
        else:
            st.caption("Ninguno hoy *(Esperando retrocesos a soporte)*")

    # 3. 🚨 Squeezes
    with col3:
        st.markdown("#### 🚨 Squeezes (Compresión)")
        if not squeeze_stocks.empty:
            for _, r in squeeze_stocks.iterrows():
                st.markdown(f"- **`{r['Ticker']}`** — ${r['Precio Actual']:.2f} *(Bandwidth: {r['BB_BANDWIDTH']:.1f}%)*")
        else:
            st.caption("Ninguno hoy *(Volatilidad en rango estándar)*")
