"""
components/alerts_panel.py - Panel superior de alertas rápidas (John Murphy Confluencia)
"""

import streamlit as st
import pandas as pd


def render_alerts_panel(df: pd.DataFrame):
    """
    Renderiza 3 columnas en la parte superior con listas de texto claras de los tickers que activaron alertas:
      1. 🔴 Venta/Rotar (Máx 52W + RSI>70 + Estocástico bajista + MACD débil)
      2. 🟢 Compra/Swing (SMA 50>SMA 200 + Soporte + RSI<35 + Estocástico alcista)
      3. 🚨 Squeezes (Compresión extrema de Bandas de Bollinger)
    """
    if df.empty or "Semáforo" not in df.columns:
        return

    rotation_stocks = df[df["Semáforo"] == "🔴 VENTA/ROTAR"]
    swing_stocks = df[df["Semáforo"] == "🟢 COMPRA/SWING"]
    squeeze_stocks = df[df["Semáforo"] == "🚨 SQUEEZE"]

    col1, col2, col3 = st.columns(3)

    # 1. 🔴 Venta / Rotar
    with col1:
        st.markdown("#### 🔴 Venta / Rotar")
        if not rotation_stocks.empty:
            for _, r in rotation_stocks.iterrows():
                st.markdown(f"- **`{r['Ticker']}`** — ${r['Precio Actual']:.2f} *(RSI: {r['RSI_VAL']:.1f}, Máx 52S: {r['DIST_52W_HIGH_PCT']:+.1f}%)*")
        else:
            st.caption("Ninguno hoy *(Sin sobrecompras extremas en máximos)*")

    # 2. 🟢 Compra / Swing
    with col2:
        st.markdown("#### 🟢 Compra / Swing")
        if not swing_stocks.empty:
            for _, r in swing_stocks.iterrows():
                st.markdown(f"- **`{r['Ticker']}`** — ${r['Precio Actual']:.2f} *(RSI: {r['RSI_VAL']:.1f}, vs SMA50: {r['DIFF_SMA_50_VAL']:+.1f}%)*")
        else:
            st.caption("Ninguno hoy *(Esperando retrocesos a soporte)*")

    # 3. 🚨 Squeezes
    with col3:
        st.markdown("#### 🚨 Squeezes")
        if not squeeze_stocks.empty:
            for _, r in squeeze_stocks.iterrows():
                st.markdown(f"- **`{r['Ticker']}`** — ${r['Precio Actual']:.2f} *(Bandwidth: {r['BB_BANDWIDTH']:.1f}%)*")
        else:
            st.caption("Ninguno hoy *(Volatilidad en rango estándar)*")
