"""
app.py - Tablero de Control Cuantitativo Top 50 Acciones (Confluencia por Sistema de Grados & Smart Money)
"""

from datetime import datetime

import streamlit as st

from components.alerts_panel import render_alerts_panel
from components.bonds_panel import render_bonds_panel
from components.coming_soon import render_coming_soon
from components.crypto_panel import render_crypto_panel
from components.kpi_cards import render_kpi_cards
from components.screener_table import render_screener_table
from constants import (
    BUY_SIGNALS,
    FILTER_FLOW_ACCUMULATION,
    FILTER_FLOW_DISTRIBUTION,
    FILTER_SIGNAL_BUY,
    FILTER_SIGNAL_SELL,
    FILTER_SIGNAL_SQUEEZE,
    FILTER_SIGNAL_STRONG_BUY,
    FILTER_SMA200_BEARISH,
    FILTER_SMA200_BULLISH,
    FLOW_ACCUMULATION,
    FLOW_DISTRIBUTION,
    FLOW_FILTER_OPTIONS,
    MARKET_OPTIONS,
    MARKET_USA_STOCKS,
    SECTION_BONDS,
    SECTION_OPTIONS,
    SECTION_STOCKS,
    SELL_SIGNALS,
    SIGNAL_FILTER_OPTIONS,
    SIGNAL_STRONG_BUY,
    SMA200_FILTER_OPTIONS,
    TIMEFRAME_CHOICE_OPTIONS,
    TIMEFRAME_CHOICE_WEEKLY,
)
from data_loader import (
    TOP_50_DEFAULT,
    load_all_stocks_data,
)

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


def _render_stocks_tab():
    """
    Pestaña de acciones: el tablero de confluencia técnica + Smart Money.

    Vive en `app.py` y no en `components/` porque es la que orquesta los
    filtros de la barra lateral, que son globales a la aplicación. La pestaña
    de bonos, en cambio, es autocontenida y vive en `components/bonds_panel.py`.
    """
    # ----------------------------------------------------
    # CABECERA CON BOTÓN DE REFRESH GENERAL
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
    st.sidebar.caption("Estos controles aplican a la pestaña **Acciones**. La pestaña de Bonos tiene sus propios filtros.")

    market_option = st.sidebar.selectbox(
        "Seleccionar Mercado (Dashboard):",
        MARKET_OPTIONS
    )

    if market_option != MARKET_USA_STOCKS:
        st.sidebar.markdown("---")
        render_coming_soon(
            market_option,
            "Vas a poder seguir las acciones líderes de este mercado con el mismo "
            "semáforo de confluencia y la misma lectura de flujo institucional que "
            "ya usás para las acciones de Estados Unidos.",
        )
        return

    tickers_list = TOP_50_DEFAULT

    # Selector de Temporalidad (Daily vs Weekly)
    timeframe_choice = st.sidebar.radio(
        "⏱️ Temporalidad Técnica (RSI, Medias, OBV):",
        TIMEFRAME_CHOICE_OPTIONS,
        help="Elige si deseas calcular los indicadores en velas diarias o semanales"
    )
    is_weekly = timeframe_choice == TIMEFRAME_CHOICE_WEEKLY
    timeframe = "1wk" if is_weekly else "1d"
    timeframe_label = "Semanal" if is_weekly else "Diario"

    # Cargar datos
    with st.spinner(f"⏳ Extrayendo datos en vivo ({timeframe_label}) y evaluando grados de confluencia..."):
        df_summary, _ = load_all_stocks_data(tickers_list, timeframe=timeframe)

    if df_summary.empty:
        st.error("No se pudieron cargar los datos de las acciones. Verifica tu conexión a internet.")
        return

    # Aviso de tickers que no se pudieron cargar (lectura defensiva: attrs
    # puede perderse según qué operaciones de pandas se hayan aplicado antes).
    try:
        failed_tickers = df_summary.attrs.get("failed_tickers", [])
    except Exception:
        failed_tickers = []

    if failed_tickers:
        st.warning(
            f"⚠️ No se pudieron cargar {len(failed_tickers)} acción(es). "
            "Suele pasar cuando el proveedor de datos limita las consultas, o "
            "cuando la acción dejó de cotizar. Probá de nuevo con el botón "
            "**🔄 Refrescar Todo**."
        )
        with st.expander("Ver tickers omitidos"):
            st.write(", ".join(failed_tickers))

    # ----------------------------------------------------
    # FILTROS EN SIDEBAR
    # ----------------------------------------------------
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Filtros Rápidos")

    # Filtro por Semáforo Grados
    signal_filter = st.sidebar.selectbox(
        "Filtrar por Semáforo:",
        SIGNAL_FILTER_OPTIONS
    )

    # Filtro por Flujo Institucional
    flow_filter = st.sidebar.selectbox(
        "Filtrar por Smart Money (OBV):",
        FLOW_FILTER_OPTIONS
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
        SMA200_FILTER_OPTIONS
    )

    # Aplicar Filtros
    df_filtered = df_summary.copy()

    # Semáforo
    if signal_filter == FILTER_SIGNAL_STRONG_BUY:
        df_filtered = df_filtered[df_filtered["Semáforo"] == SIGNAL_STRONG_BUY]
    elif signal_filter == FILTER_SIGNAL_BUY:
        df_filtered = df_filtered[df_filtered["Semáforo"].isin(BUY_SIGNALS)]
    elif signal_filter == FILTER_SIGNAL_SELL:
        df_filtered = df_filtered[df_filtered["Semáforo"].isin(SELL_SIGNALS)]
    elif signal_filter == FILTER_SIGNAL_SQUEEZE:
        df_filtered = df_filtered[df_filtered["Semáforo"].str.contains("SQUEEZE", na=False)]

    # Flujo Institucional
    if flow_filter == FILTER_FLOW_ACCUMULATION:
        df_filtered = df_filtered[df_filtered["Flujo Institucional"] == FLOW_ACCUMULATION]
    elif flow_filter == FILTER_FLOW_DISTRIBUTION:
        df_filtered = df_filtered[df_filtered["Flujo Institucional"] == FLOW_DISTRIBUTION]

    # RSI
    df_filtered = df_filtered[
        (df_filtered["RSI_VAL"].isna()) |
        ((df_filtered["RSI_VAL"] >= rsi_range[0]) & (df_filtered["RSI_VAL"] <= rsi_range[1]))
    ]

    # SMA 200
    if sma200_filter == FILTER_SMA200_BULLISH:
        df_filtered = df_filtered[df_filtered["DIFF_SMA_200_VAL"] > 0]
    elif sma200_filter == FILTER_SMA200_BEARISH:
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

    with st.expander("ℹ️ Cómo se lee el semáforo"):
        st.markdown("""
        El semáforo no busca adivinar el precio: busca **momentos en que varias señales
        independientes coinciden**. Una sola señal se equivoca seguido; tres a la vez, bastante
        menos. De ahí el nombre "confluencia", y de ahí que haya dos grados según cuántas
        coincidan.

        **Señales de compra — un retroceso dentro de una tendencia sana**

        La idea es comprar una acción que viene bien y está tomando un descanso, no una que está
        cayendo. Por eso se exigen dos cosas **sí o sí**: que el precio haya vuelto a una zona de
        soporte, y que no venga de estar sobrecomprada. Cumplidas ésas, suman puntos que la
        tendencia de fondo siga siendo alcista, que el impulso de corto plazo esté girando para
        arriba, y que el volumen muestre que hay dinero entrando en vez de saliendo.

        * 🌟 **COMPRA FUERTE** — coinciden casi todas las señales.
        * 🟢 **COMPRA MODERADA** — coinciden las justas.

        **Señales de venta o rotación — un techo con el impulso agotándose**

        El espejo del anterior. Se exige **sí o sí** que el precio esté pegado a su máximo del
        último año y que venga sobrecomprado. Suman puntos que el impulso ya esté girando para
        abajo y que el volumen muestre dinero saliendo. No dice "vendé": dice que el tramo de suba
        está maduro y conviene revisar la posición.

        * 🚨 **VENTA FUERTE / ROTAR** — el agotamiento está confirmado por varias señales.
        * 🟠 **VENTA MODERADA** — hay indicios, no confirmación.

        **Otros estados**

        * 🚨 **SQUEEZE** — la acción lleva meses moviéndose en un rango cada vez más angosto. No
          anticipa la dirección, pero esa compresión suele resolverse con un movimiento grande.
        * 🟡 **NEUTRAL** — no hay suficientes señales coincidiendo. Es el estado más común, y está
          bien que lo sea: el sistema está pensado para hablar poco.
        """)


def main():
    """
    Punto de entrada: reparte la aplicación en secciones por clase de activo.

    Es un selector y no `st.tabs` a propósito. Streamlit ejecuta el cuerpo de
    **todas** las pestañas en cada corrida, no solo el de la visible: con
    `st.tabs`, abrir el tablero de acciones dispararía también la descarga de
    precios de ONs, la curva del Tesoro y el panel de cripto sin que nadie haya
    entrado a esas secciones. Un selector dibuja únicamente la sección elegida,
    así que cada fuente de datos se consulta recién cuando se la mira.
    """
    section = st.radio(
        "Sección",
        SECTION_OPTIONS,
        horizontal=True,
        label_visibility="collapsed",
    )

    if section == SECTION_STOCKS:
        _render_stocks_tab()
    elif section == SECTION_BONDS:
        render_bonds_panel()
    else:
        render_crypto_panel()


if __name__ == "__main__":
    main()
