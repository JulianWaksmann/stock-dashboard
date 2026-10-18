"""
app.py - Tablero de Control Cuantitativo Top 50 Acciones (Confluencia por Sistema de Grados & Smart Money)
"""

from datetime import datetime

import streamlit as st

from components.bonds_panel import render_bonds_panel
from components.branding import (
    inject_global_styles,
    render_brand_bar,
    render_nav_anchor,
)
from components.coming_soon import render_coming_soon
from components.crypto_panel import render_crypto_panel
from components.merval_panel import render_merval_panel
from components.stocks_body import render_failed_tickers_notice, render_stocks_body
from constants import (
    FLOW_FILTER_OPTIONS,
    MARKET_ARGENTINA,
    MARKET_OPTIONS,
    MARKET_USA_STOCKS,
    SECTION_BONDS,
    SECTION_OPTIONS,
    SECTION_SHORT_LABELS,
    SECTION_STOCKS,
    SIGNAL_FILTER_OPTIONS,
    SMA200_FILTER_OPTIONS,
    TIMEFRAME_CHOICE_OPTIONS,
    TIMEFRAME_CHOICE_WEEKLY,
)
from data_loader import (
    TOP_50_DEFAULT,
    load_all_stocks_data,
)
from stock_screener import StockFilters, apply_stock_filters

# 1. Configuración de página
st.set_page_config(
    page_title="Tablero Cuantitativo | Confluencia & Smart Money",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)



def _render_market_header(titulo: str, subtitulo: str):
    """Cabecera de un mercado de acciones, con el botón de recarga."""
    col_texto, col_boton = st.columns([4, 1])

    with col_texto:
        st.markdown(f'<div class="main-title">{titulo}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="sub-title">{subtitulo} '
            f'<span style="opacity:0.7;">Última recarga: {datetime.now().strftime("%H:%M:%S")}</span></div>',
            unsafe_allow_html=True,
        )

    with col_boton:
        st.markdown("<div style='padding-top: 10px;'></div>", unsafe_allow_html=True)
        if st.button(
            "Refrescar datos",
            use_container_width=True,
            type="primary",
            help="Limpia la memoria caché y consulta las cotizaciones más recientes de Yahoo Finance",
        ):
            st.cache_data.clear()
            st.rerun()


def _render_tamiz(timeframe_label: str) -> StockFilters:
    """
    El tamiz del cuadro de acciones: recorta un panel que ya está descargado.

    Lo que hacen con el panel vive en `stock_screener.py`, que es puro y está
    testeado. Esta función solo traduce widgets a intenciones.
    """
    columnas = st.columns(4)

    with columnas[0]:
        signal = st.selectbox("Semáforo", SIGNAL_FILTER_OPTIONS)
    with columnas[1]:
        flow = st.selectbox("Flujo de volumen (OBV)", FLOW_FILTER_OPTIONS)
    with columnas[2]:
        sma200 = st.selectbox(
            f"Tendencia vs SMA 200 ({timeframe_label})",
            SMA200_FILTER_OPTIONS,
        )
    with columnas[3]:
        rsi_range = st.slider(
            f"Rango de RSI 14 ({timeframe_label})",
            min_value=0.0,
            max_value=100.0,
            value=(0.0, 100.0),
            step=1.0,
        )

    return StockFilters(signal=signal, flow=flow, rsi_range=rsi_range, sma200=sma200)


def _render_controles_acciones() -> tuple[str, str, str, StockFilters]:
    """
    Todos los controles de la sección, en una tarjeta arriba del contenido.

    La tarjeta separa dos clases de control que antes convivían en la barra
    lateral sin distinguirse: arriba, lo que decide **qué se descarga**
    (mercado y temporalidad), que dispara tráfico de red al cambiar; abajo, el
    tamiz, que solo recorta lo que ya está en memoria. Devuelve las dos cosas
    juntas porque la temporalidad etiqueta las columnas que el tamiz filtra.
    """
    with st.container(border=True):
        fuente = st.columns([1.6, 2])

        with fuente[0]:
            market_option = st.selectbox("Mercado", MARKET_OPTIONS)
        with fuente[1]:
            timeframe_choice = st.radio(
                "Temporalidad técnica (RSI, medias, OBV)",
                TIMEFRAME_CHOICE_OPTIONS,
                horizontal=True,
                help="Elegí si los indicadores se calculan en velas diarias o semanales",
            )

        is_weekly = timeframe_choice == TIMEFRAME_CHOICE_WEEKLY
        timeframe = "1wk" if is_weekly else "1d"
        timeframe_label = "Semanal" if is_weekly else "Diario"

        st.markdown("---")
        filtros = _render_tamiz(timeframe_label)

    return market_option, timeframe, timeframe_label, filtros


def _render_usa_stocks(timeframe: str, timeframe_label: str, filtros: StockFilters):
    """Las 50 acciones líderes de Estados Unidos: el panel original."""
    _render_market_header(
        "Confluencia &amp; Smart Money",
        "Semáforo de confluencia por grados (fuerte vs moderada) y lectura de flujo "
        "institucional (OBV) sobre las 50 acciones líderes.",
    )

    with st.spinner(f"⏳ Extrayendo datos en vivo ({timeframe_label}) y evaluando grados de confluencia..."):
        df_summary, historiales = load_all_stocks_data(TOP_50_DEFAULT, timeframe=timeframe)

    if df_summary.empty:
        st.error("No se pudieron cargar los datos de las acciones. Verifica tu conexión a internet.")
        return

    render_failed_tickers_notice(df_summary, nombre_activo="acción")

    render_stocks_body(
        df_summary,
        apply_stock_filters(df_summary, filtros),
        historiales,
        timeframe_label=timeframe_label,
        timeframe=timeframe,
        nombre_archivo="screener_confluencia",
        nombre_activo="acciones",
        key_prefix="acciones_usa",
    )


def _render_stocks_tab():
    """
    Sección de acciones: el tablero de confluencia técnica + Smart Money.

    Vive en `app.py` y no en `components/` porque es la que orquesta el
    selector de mercado. Lo que se dibuja debajo es el mismo para todos los
    mercados y está en `components/stocks_body.py`; lo que cambia por mercado
    es la descarga.

    Los controles van arriba del título y no debajo porque el mercado elegido
    es el que decide qué título se dibuja.
    """
    market_option, timeframe, timeframe_label, filtros = _render_controles_acciones()

    if market_option == MARKET_USA_STOCKS:
        _render_usa_stocks(timeframe, timeframe_label, filtros)
    elif market_option == MARKET_ARGENTINA:
        render_merval_panel(timeframe, timeframe_label, filtros)
    else:
        render_coming_soon(
            market_option,
            "Vas a poder seguir las acciones líderes de este mercado con el mismo "
            "semáforo de confluencia y la misma lectura de flujo institucional que "
            "ya usás para las acciones de Estados Unidos.",
        )


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
    inject_global_styles()

    # La firma de marca nombra la sección elegida, que recién se conoce
    # después de dibujar el selector: se reserva el lugar antes y se llena
    # después, para que en pantalla quede arriba.
    encabezado = st.container()

    render_nav_anchor()
    section = st.radio(
        "Sección",
        SECTION_OPTIONS,
        horizontal=True,
        label_visibility="collapsed",
    )

    with encabezado:
        render_brand_bar(SECTION_SHORT_LABELS[section])

    if section == SECTION_STOCKS:
        _render_stocks_tab()
    elif section == SECTION_BONDS:
        render_bonds_panel()
    else:
        render_crypto_panel()


if __name__ == "__main__":
    main()
