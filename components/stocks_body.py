"""
components/stocks_body.py - Cuerpo del panel de acciones, compartido por mercado.

Lo que se dibuja debajo de la cabecera y de los filtros es **lo mismo** para
las acciones de Estados Unidos y para las argentinas: alertas, KPIs, cuadro,
ficha de detalle, vistas agregadas y medición del semáforo. Lo que cambia entre
mercados es de dónde salen los precios y en qué moneda están medidos, no qué
significa una confluencia.

Estaba escrito dentro de `app.py`, atado al único mercado que existía. Pasarlo
acá es lo que permite que un mercado nuevo sea un `data_loader` y una cabecera,
en vez de una copia de doscientas líneas de interfaz que después se desfasa.

Es capa de dibujo: recibe el panel ya filtrado y no decide nada de negocio (el
tamiz vive en `stock_screener.py`, que es puro).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.alerts_panel import render_alerts_panel
from components.changes_panel import render_changes
from components.charts import (
    plot_pe_comparison_bar,
    plot_sma_distances_bar,
    plot_valuation_vs_technicals,
)
from components.kpi_cards import render_kpi_cards
from components.screener_table import render_screener_table
from components.signal_stats_panel import render_signal_stats
from components.ticker_detail import render_ticker_detail_view
from constants import (
    SQUEEZE_LOOKBACK_BARS,
    STOCK_CHART_OPTIONS,
    STOCK_CHART_PE,
    STOCK_CHART_VALUATION,
)
from indicators import STOCK_THRESHOLDS, ConfluenceThresholds

_COMO_SE_LEE = """
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
"""


def render_failed_tickers_notice(df_summary: pd.DataFrame, nombre_activo: str = "acción"):
    """
    Avisa qué tickers no se pudieron cargar, si el loader lo dejó anotado.

    Lectura defensiva: `attrs` se pierde según qué operaciones de pandas se
    hayan aplicado antes, y una advertencia que estalla es peor que una que
    falta.
    """
    try:
        fallidos = df_summary.attrs.get("failed_tickers", [])
    except Exception:
        fallidos = []

    if not fallidos:
        return

    st.warning(
        f"⚠️ No se pudieron cargar {len(fallidos)} {nombre_activo}(es). "
        "Suele pasar cuando el proveedor de datos limita las consultas, o "
        "cuando el activo dejó de cotizar. Probá de nuevo con el botón "
        "**Refrescar datos**."
    )
    with st.expander("Ver tickers omitidos"):
        st.write(", ".join(fallidos))


def render_stocks_body(
    df_summary: pd.DataFrame,
    df_filtered: pd.DataFrame,
    historiales: dict[str, pd.DataFrame],
    timeframe_label: str = "Diario",
    timeframe: str = "1d",
    nombre_archivo: str = "screener_confluencia",
    nombre_activo: str = "acciones",
    motor_registro: str = "acciones_usa",
    window_52w: int = 252,
    squeeze_lookback: int = SQUEEZE_LOOKBACK_BARS,
    thresholds: ConfluenceThresholds = STOCK_THRESHOLDS,
    key_prefix: str = "acciones",
):
    """
    Dibuja alertas, KPIs, cuadro, ficha, vistas agregadas y medición.

    `motor_registro` nombra la carpeta del registro diario: un panel por
    mercado, porque comparar acciones argentinas contra estadounidenses no
    significaría nada.

    `window_52w`, `squeeze_lookback` y `thresholds` se pasan a la medición del
    semáforo y tienen que ser los mismos con los que se calculó el panel: medir
    con otra calibración daría el número de un sistema que no está en pantalla.
    """
    # ----------------------------------------------------
    # 1. QUÉ CAMBIÓ + ALERTAS RÁPIDAS
    # ----------------------------------------------------
    # El registro va sobre el panel entero, no sobre el filtrado: lo que
    # cambió desde ayer no depende de los filtros que estén puestos hoy.
    render_changes(df_summary, motor_registro)


    st.subheader("⚡ Alertas de Confluencia del Día")
    render_alerts_panel(df_summary)
    st.markdown("---")

    # ----------------------------------------------------
    # 2. KPI RESUMEN DE MERCADO
    # ----------------------------------------------------
    render_kpi_cards(df_filtered, timeframe_label=timeframe_label)
    st.markdown("---")

    # ----------------------------------------------------
    # 3. CUADRO PRINCIPAL
    # ----------------------------------------------------
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.markdown(
            f"### 📋 Matriz Cuantitativa ({len(df_filtered)} de {len(df_summary)} "
            f"{nombre_activo} | Base: **{timeframe_label}**)"
        )
    with col_t2:
        st.download_button(
            label="📥 Exportar a CSV",
            data=df_filtered.to_csv(index=False).encode("utf-8"),
            file_name=f"{nombre_archivo}_{timeframe}.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"{key_prefix}_csv",
        )

    render_screener_table(df_filtered, timeframe_label=timeframe_label)

    # ----------------------------------------------------
    # 4. FICHA DE DETALLE
    # ----------------------------------------------------
    # El cuadro dice *qué* activo mirar; la ficha es la que permite decidir, y
    # necesita el historial completo.
    st.markdown("---")
    st.markdown("### 🔎 Ficha de detalle")

    disponibles = df_filtered["Ticker"].tolist() if "Ticker" in df_filtered.columns else []
    if not disponibles:
        st.info("Ningún activo pasa los filtros actuales, así que no hay ficha para mostrar.")
    else:
        elegido = st.selectbox(
            "Activo a examinar:",
            disponibles,
            help="La lista respeta los filtros de la barra lateral.",
            key=f"{key_prefix}_ficha",
        )
        render_ticker_detail_view(
            elegido,
            df_summary,
            historiales,
            timeframe_label=timeframe_label,
        )

    # ----------------------------------------------------
    # 5. VISTAS AGREGADAS
    # ----------------------------------------------------
    # De a una y no las tres apiladas: son tres gráficos de 500 a 900 px y
    # juntos no se comparan, se scrollean. Ninguna descarga datos nuevos.
    st.markdown("---")
    st.markdown("### 📊 Vistas agregadas del panel")

    vista = st.radio(
        "Vista agregada",
        STOCK_CHART_OPTIONS,
        horizontal=True,
        label_visibility="collapsed",
        key=f"{key_prefix}_vista",
    )

    if vista == STOCK_CHART_VALUATION:
        st.plotly_chart(
            plot_valuation_vs_technicals(df_filtered, timeframe_label=timeframe_label),
            use_container_width=True,
        )
        st.caption(
            "Abajo a la izquierda está lo barato y rezagado; arriba a la derecha, lo caro "
            "y con impulso. Las líneas punteadas son la mediana de PER futuro del panel y "
            "el cero de distancia a la media de 200: dividen el cuadrante, no son objetivos."
        )
    elif vista == STOCK_CHART_PE:
        st.plotly_chart(plot_pe_comparison_bar(df_filtered), use_container_width=True)
        st.caption(
            "Cuando el PER futuro queda por debajo del pasado, el mercado espera que las "
            "ganancias crezcan; al revés, que caigan. El promedio de cinco años dice si el "
            "múltiplo de hoy es alto o bajo **para esa empresa**, que es la única comparación "
            "que tiene sentido entre sectores distintos."
        )
    else:
        st.plotly_chart(
            plot_sma_distances_bar(df_filtered, timeframe_label=timeframe_label),
            use_container_width=True,
        )
        st.caption(
            "Distancia a la media de 200 períodos, ordenada. Los extremos de abajo son "
            "los más castigados respecto de su propia tendencia; los de arriba, los más "
            "estirados."
        )

    # ----------------------------------------------------
    # 6. MEDICIÓN DEL SEMÁFORO
    # ----------------------------------------------------
    st.markdown("---")
    render_signal_stats(
        historiales,
        timeframe_label=timeframe_label,
        window_52w=window_52w,
        squeeze_lookback=squeeze_lookback,
        thresholds=thresholds,
        key_prefix=key_prefix,
    )

    with st.expander("ℹ️ Cómo se lee el semáforo"):
        st.markdown(_COMO_SE_LEE)
