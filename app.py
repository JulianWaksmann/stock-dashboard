"""
app.py - Tablero de Control Cuantitativo Top 50 Acciones (Confluencia por Sistema de Grados & Smart Money)
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from data_loader import (
    load_all_stocks_data,
    TOP_50_DEFAULT
)
from components.alerts_panel import render_alerts_panel
from components.kpi_cards import render_kpi_cards
from components.screener_table import render_screener_table

# 1. Configuración de página
st.set_page_config(
    page_title="Tablero Cuantitativo | Confluencia & Smart Money",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS
st.markdown("""
<style>
    .main-title {
        font-size: 2.1rem;
        font-weight: 700;
        margin-bottom: 0.1rem;
    }
    .sub-title {
        font-size: 0.95rem;
        color: #9ca3af;
        margin-bottom: 0.8rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


def main():
    # ----------------------------------------------------
    # CABECERA SUPERIOR CON BOTÓN DE REFRESH GENERAL
    # ----------------------------------------------------
    header_col1, header_col2 = st.columns([4, 1])

    with header_col1:
        st.markdown('<div class="main-title">🚦 Tablero Cuantitativo: Confluencia & Smart Money</div>', unsafe_allow_html=True)
        current_time_str = datetime.now().strftime("%H:%M:%S")
        st.markdown(f'<div class="sub-title">Algoritmo de Confluencia por Sistema de Grados (Fuerte vs Moderada) + Smart Money (OBV) | 🕒 <i>Última recarga: {current_time_str}</i></div>', unsafe_allow_html=True)

    with header_col2:
        st.markdown("<div style='padding-top: 10px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Refrescar Todo", use_container_width=True, type="primary", help="Limpia la memoria caché y consulta las cotizaciones más recientes de Yahoo Finance"):
            st.cache_data.clear()
            st.rerun()

    # ----------------------------------------------------
    # SIDEBAR: Selección de Mercado, Temporalidad y Filtros
    # ----------------------------------------------------
    st.sidebar.header("🌐 Mercados")

    market_option = st.sidebar.selectbox(
        "Seleccionar Mercado (Dashboard):",
        ["Acciones USA (S&P 500)", "Criptomonedas", "Acciones Argentinas (Merval)"]
    )

    if market_option != "Acciones USA (S&P 500)":
        st.sidebar.markdown("---")
        st.info(f"🚧 **{market_option}**: Módulo en desarrollo. Próximamente disponible.")
        return

    tickers_list = TOP_50_DEFAULT

    # Selector de Temporalidad (Daily vs Weekly)
    timeframe_choice = st.sidebar.radio(
        "⏱️ Temporalidad Técnica (RSI, Medias, OBV):",
        ["☀️ Diario (1D)", "📅 Semanal (1W)"],
        help="Elige si deseas calcular los indicadores en velas diarias o semanales"
    )
    timeframe = "1wk" if "Semanal" in timeframe_choice else "1d"
    timeframe_label = "Semanal" if "Semanal" in timeframe_choice else "Diario"

    # Cargar datos
    with st.spinner(f"⏳ Extrayendo datos en vivo ({timeframe_label}) y evaluando grados de confluencia..."):
        df_summary, _ = load_all_stocks_data(tickers_list, timeframe=timeframe)

    if df_summary.empty:
        st.error("No se pudieron cargar los datos de las acciones. Verifica tu conexión a internet.")
        return

    # ----------------------------------------------------
    # FILTROS EN SIDEBAR
    # ----------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Filtros Rápidos")

    # Filtro por Semáforo Grados
    signal_filter = st.sidebar.selectbox(
        "Filtrar por Semáforo:",
        [
            "Todas las Acciones",
            "🌟 Solo Compra Fuerte",
            "🟢 Solo Compras (Fuerte + Moderada)",
            "🚨 Solo Venta / Rotar (Fuerte + Moderada)",
            "⚡ Solo Squeezes"
        ]
    )

    # Filtro por Flujo Institucional
    flow_filter = st.sidebar.selectbox(
        "Filtrar por Smart Money (OBV):",
        ["Todos los Flujos", "🐳 Solo Acumulación (OBV > SMA 20)", "📉 Solo Distribución (OBV < SMA 20)"]
    )

    # Filtro por RSI (14)
    rsi_range = st.sidebar.slider(
        f"Rango de RSI 14 ({timeframe_label}):",
        min_value=0.0,
        max_value=100.0,
        value=(0.0, 100.0),
        step=1.0
    )

    # Filtro por Tendencia vs SMA 200
    sma200_filter = st.sidebar.radio(
        f"Tendencia vs SMA 200 ({timeframe_label}):",
        ["Todos", "Solo Alcistas (> SMA 200)", "Solo Bajistas (< SMA 200)"]
    )

    # Aplicar Filtros
    df_filtered = df_summary.copy()

    # Semáforo
    if signal_filter == "🌟 Solo Compra Fuerte":
        df_filtered = df_filtered[df_filtered["Semáforo"] == "🌟 COMPRA FUERTE"]
    elif signal_filter == "🟢 Solo Compras (Fuerte + Moderada)":
        df_filtered = df_filtered[df_filtered["Semáforo"].isin(["🌟 COMPRA FUERTE", "🟢 COMPRA MODERADA"])]
    elif signal_filter == "🚨 Solo Venta / Rotar (Fuerte + Moderada)":
        df_filtered = df_filtered[df_filtered["Semáforo"].isin(["🚨 VENTA FUERTE / ROTAR", "🟠 VENTA MODERADA"])]
    elif signal_filter == "⚡ Solo Squeezes":
        df_filtered = df_filtered[df_filtered["Semáforo"].str.contains("SQUEEZE", na=False)]

    # Flujo Institucional
    if flow_filter == "🐳 Solo Acumulación (OBV > SMA 20)":
        df_filtered = df_filtered[df_filtered["Flujo Institucional"] == "🐳 Acumulación"]
    elif flow_filter == "📉 Solo Distribución (OBV < SMA 20)":
        df_filtered = df_filtered[df_filtered["Flujo Institucional"] == "📉 Distribución"]

    # RSI
    df_filtered = df_filtered[
        (df_filtered["RSI_VAL"].isna()) | 
        ((df_filtered["RSI_VAL"] >= rsi_range[0]) & (df_filtered["RSI_VAL"] <= rsi_range[1]))
    ]

    # SMA 200
    if "Solo Alcistas" in sma200_filter:
        df_filtered = df_filtered[df_filtered["DIFF_SMA_200_VAL"] > 0]
    elif "Solo Bajistas" in sma200_filter:
        df_filtered = df_filtered[df_filtered["DIFF_SMA_200_VAL"] < 0]

    # ----------------------------------------------------
    # 1. PANEL SUPERIOR: ALERTAS RÁPIDAS (3 COLUMNAS)
    # ----------------------------------------------------
    st.subheader("⚡ Alertas de Confluencia del Día")
    render_alerts_panel(df_summary)
    st.markdown("---")

    # ----------------------------------------------------
    # 2. KPI RESUMEN DE MERCADO
    # ----------------------------------------------------
    render_kpi_cards(df_filtered, timeframe_label=timeframe_label)
    st.markdown("---")

    # ----------------------------------------------------
    # 3. TABLA SCREENER PRINCIPAL (LIMPIA, SIN EMPRESA NI SECTOR)
    # ----------------------------------------------------
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.markdown(f"### 📋 Matriz Cuantitativa ({len(df_filtered)} de {len(df_summary)} acciones | Base: **{timeframe_label}**)")
    with col_t2:
        csv_data = df_filtered.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Exportar a CSV",
            data=csv_data,
            file_name=f"screener_confluencia_{timeframe}.csv",
            mime="text/csv",
            use_container_width=True
        )

    render_screener_table(df_filtered, timeframe_label=timeframe_label)

    with st.expander("ℹ️ Sistema de Grados del Algoritmo de Confluencia"):
        st.markdown("""
        **Lógica de Compra (Swing):**
        * Exige **obligatoriamente**: Proximidad a Soporte (+/- 4% de SMA 50 o debajo de Banda Inferior) Y RSI < 45.
        * Suma puntos por: Tendencia alcista (SMA 50 > SMA 200), Estocástico alcista (%K < 30) y Acumulación OBV.
        * **🌟 COMPRA FUERTE**: 4 o 5 puntos cumplidos.
        * **🟢 COMPRA MODERADA**: 3 puntos cumplidos.

        **Lógica de Venta / Rotación:**
        * Exige **obligatoriamente**: Proximidad a Techo (< 6% del Máx 52S) Y RSI > 65.
        * Suma puntos por: Pérdida de momento (Estocástico bajista o MACD débil) y Distribución OBV.
        * **🚨 VENTA FUERTE / ROTAR**: 3 o 4 puntos cumplidos.
        * **🟠 VENTA MODERADA**: 2 puntos cumplidos.

        **Otros Estados:**
        * **🚨 SQUEEZE**: Ancho de Bandas de Bollinger en mínimos de 6 meses.
        * **🟡 NEUTRAL**: No alcanza los umbrales de confluencia.
        """)


if __name__ == "__main__":
    main()
