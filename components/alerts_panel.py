"""
components/alerts_panel.py - Panel superior de alertas rápidas por Sistema de Grados
"""

import streamlit as st
import pandas as pd


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
    strong_sales = df[df["Semáforo"] == "🚨 VENTA FUERTE / ROTAR"]
    mod_sales = df[df["Semáforo"] == "🟠 VENTA MODERADA"]
    all_sales = df[df["Semáforo"].isin(["🚨 VENTA FUERTE / ROTAR", "🟠 VENTA MODERADA"])]

    strong_buys = df[df["Semáforo"] == "🌟 COMPRA FUERTE"]
    mod_buys = df[df["Semáforo"] == "🟢 COMPRA MODERADA"]
    all_buys = df[df["Semáforo"].isin(["🌟 COMPRA FUERTE", "🟢 COMPRA MODERADA"])]

    squeeze_stocks = df[df["Semáforo"].str.contains("SQUEEZE", na=False)]

    col1, col2, col3 = st.columns(3)

    # 1. 🔴 Venta / Rotación
    with col1:
        st.markdown("#### 🔴 Venta / Rotación")
        if not all_sales.empty:
            for _, r in all_sales.iterrows():
                tag = "🚨 Fuerte" if "FUERTE" in r["Semáforo"] else "🟠 Moderada"
                st.markdown(f"- **`{r['Ticker']}`** [{tag}] — ${r['Precio Actual']:.2f} *(RSI: {r['RSI_VAL']:.1f}, Máx 52S: {r['DIST_52W_HIGH_PCT']:+.1f}%)*")
        else:
            st.caption("Ninguno hoy *(Sin sobrecompras extremas)*")

    # 2. 🟢 Compra / Swing
    with col2:
        st.markdown("#### 🟢 Compra / Swing")
        if not all_buys.empty:
            for _, r in all_buys.iterrows():
                tag = "🌟 Fuerte" if "FUERTE" in r["Semáforo"] else "🟢 Moderada"
                st.markdown(f"- **`{r['Ticker']}`** [{tag}] — ${r['Precio Actual']:.2f} *(RSI: {r['RSI_VAL']:.1f}, vs SMA50: {r['DIFF_SMA_50_VAL']:+.1f}%)*")
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
