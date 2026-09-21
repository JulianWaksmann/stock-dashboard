"""
components/crypto_panel.py - Sección completa de Criptomonedas.

Igual que la de bonos, la sección es autocontenida: sus controles, sus KPIs,
su cuadro y su documentación viven acá y no en `app.py`. Las tres secciones
del tablero no comparten estado ni filtros, y tenerlas mezcladas en un único
`main()` haría que tocar un filtro de una obligue a releer las otras dos.

Reparto entre barra lateral y cuerpo: en la barra lateral va lo que decide
**qué se descarga** (el universo y la temporalidad); los filtros, que recortan
un panel ya bajado, van en el cuerpo, al lado del cuadro que recortan.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from components.crypto_chart import build_crypto_chart, build_dominance_chart
from components.crypto_table import render_crypto_table
from components.formatting import (
    format_crypto_price,
    format_month_year,
    format_signed_pct,
    format_usd_compact,
)
from constants import (
    CRYPTO_ALTSEASON_MIN_PCT,
    CRYPTO_BENCHMARK_LABEL,
    CRYPTO_BENCHMARK_TICKER,
    CRYPTO_BTCSEASON_MAX_PCT,
    CRYPTO_CHART_SCALE_OPTIONS,
    CRYPTO_HIGH_VOLATILITY_PCT,
    CRYPTO_LEVEL_BAND_RATIO,
    CRYPTO_RS_FILTER_OPTIONS,
    CRYPTO_RS_NEUTRAL_BAND_PP,
    CRYPTO_SIGNAL_FILTER_OPTIONS,
    CRYPTO_STRETCH_SIGMAS,
    CRYPTO_TREND_FILTER_OPTIONS,
    CRYPTO_UNIVERSE_OPTIONS,
    SIGNAL_MODERATE_BUY,
    SIGNAL_MODERATE_SELL,
    SIGNAL_SQUEEZE,
    SIGNAL_STRONG_BUY,
    SIGNAL_STRONG_SELL,
    TIMEFRAME_CHOICE_OPTIONS,
    TIMEFRAME_CHOICE_WEEKLY,
)
from crypto.data_loader import load_chart_history, load_crypto_data
from crypto.divergences import detect_divergences
from crypto.levels import detect_support_resistance, scale_params
from crypto.panel import apply_crypto_filters, spec_for_timeframe
from indicators import compute_rsi


def _render_sidebar() -> tuple[str, str]:
    """
    Barra lateral de la sección: universo y temporalidad.

    Las dos cosas que van acá son las que cambian **qué se descarga**. Los
    filtros del cuadro se quedan en el cuerpo porque recortan un panel ya
    bajado y no disparan tráfico.
    """
    st.sidebar.header("🪙 Universo cripto")
    st.sidebar.caption("Estos controles aplican a la sección **Criptomonedas**.")

    universe = st.sidebar.selectbox(
        "Grupo:",
        CRYPTO_UNIVERSE_OPTIONS,
        help="Qué conjunto de criptomonedas se descarga y se analiza.",
    )

    timeframe_choice = st.sidebar.radio(
        "⏱️ Temporalidad Técnica (RSI, Medias, OBV):",
        TIMEFRAME_CHOICE_OPTIONS,
        help="Velas diarias para operar el corto plazo; semanales para leer la tendencia de fondo.",
    )
    timeframe = "1wk" if timeframe_choice == TIMEFRAME_CHOICE_WEEKLY else "1d"

    st.sidebar.markdown("---")
    if st.sidebar.button(
        "🔄 Refrescar Cripto",
        use_container_width=True,
        type="primary",
        help="Limpia la caché y vuelve a consultar las cotizaciones",
    ):
        st.cache_data.clear()
        st.rerun()

    return universe, timeframe


def _render_kpis(df: pd.DataFrame, timeframe_label: str):
    """Resumen agregado del universo cripto que se está mirando."""
    if df.empty:
        return

    columnas = st.columns(5)

    with columnas[0]:
        st.metric(
            "Criptos en Panel",
            f"{len(df)}",
            help=f"Monedas analizadas en temporalidad {timeframe_label}",
        )

    with columnas[1]:
        sma200 = df["DIFF_SMA_200_VAL"].dropna()
        if sma200.empty:
            st.metric(f"% > SMA 200 ({timeframe_label})", "N/A")
        else:
            pct = (sma200 > 0).mean() * 100
            st.metric(
                f"% > SMA 200 ({timeframe_label})",
                f"{pct:.0f}%",
                delta="Fuerte" if pct >= 60 else ("Débil" if pct < 40 else "Neutral"),
                help="Porcentaje del panel cotizando por encima de su media de 200 barras. Es la lectura más simple de si el ciclo está de un lado o del otro.",
            )

    with columnas[2]:
        rsi = df["RSI_VAL"].dropna()
        if rsi.empty:
            st.metric(f"Extremos RSI ({timeframe_label})", "N/A")
        else:
            sobreventa = int((rsi < 30).sum())
            sobrecompra = int((rsi > 70).sum())
            st.metric(
                f"Extremos RSI ({timeframe_label})",
                f"🟢 {sobreventa} | 🔴 {sobrecompra}",
                delta=f"{sobreventa} Sobreventa / {sobrecompra} Sobrecompra",
                delta_color="off",
                help="🟢 Sobreventa (RSI < 30) | 🔴 Sobrecompra (RSI > 70)",
            )

    with columnas[3]:
        vol = df["VOL_ANN_PCT"].dropna()
        if vol.empty:
            st.metric("Mediana Volatilidad", "N/A")
        else:
            mediana = vol.median()
            st.metric(
                "Mediana Volatilidad",
                f"{mediana:.0f}%",
                delta="Riesgo alto" if mediana >= CRYPTO_HIGH_VOLATILITY_PCT else None,
                delta_color="inverse",
                help=f"Volatilidad anualizada típica del panel. Por encima de {CRYPTO_HIGH_VOLATILITY_PCT:.0f}% el tamaño de posición importa más que el punto de entrada.",
            )

    with columnas[4]:
        extension = df["EXTENSION_SIGMAS"].dropna()
        if extension.empty:
            st.metric("Estiradas", "N/A")
        else:
            estiradas = int((extension >= CRYPTO_STRETCH_SIGMAS).sum())
            st.metric(
                "Estiradas",
                f"{estiradas} de {len(extension)}",
                delta="Riesgo de reversión" if estiradas else None,
                delta_color="inverse",
                help=f"Cuántas cotizan a {CRYPTO_STRETCH_SIGMAS:.0f} desvíos o más por encima de su media de 50 barras. Es la condición de techo que usa el semáforo en cripto.",
            )


def _render_rotation(rotacion, timeframe_label: str, ventana: int, unidad: str):
    """
    Bloque de rotación: ¿el valor se está yendo a Bitcoin o a las altcoins?

    Son dos mediciones distintas y se muestran juntas a propósito, porque se
    contradicen seguido. La dominancia mide **dónde está el valor**; el
    termómetro de temporada mide **cuántas monedas** le ganan a Bitcoin. Que
    la dominancia suba mientras varias alts le ganan significa que la suba de
    las alts es angosta: unas pocas tirando, el resto quedándose. Con un solo
    número esa lectura no aparece.
    """
    st.markdown("### 🔀 Rotación: Bitcoin o altcoins")

    columnas = st.columns([1, 1, 1, 2.4])

    with columnas[0]:
        if rotacion.global_btc_dominance_pct is None:
            st.metric("Dominancia BTC (global)", "N/A", help=rotacion.global_error or "")
        else:
            st.metric(
                "Dominancia BTC (global)",
                f"{rotacion.global_btc_dominance_pct:.1f}%",
                delta=(
                    f"ETH {rotacion.global_eth_dominance_pct:.1f}%"
                    if rotacion.global_eth_dominance_pct == rotacion.global_eth_dominance_pct
                    else None
                ),
                delta_color="off",
                help="Porción de todo el mercado cripto que es Bitcoin, contando miles de monedas y las stablecoins. Es la referencia que se publica en todos lados.",
            )

    with columnas[1]:
        cambio = rotacion.dominance_change_pp
        if cambio != cambio:
            st.metric(f"Dominancia panel ({ventana}{unidad})", "N/A")
        else:
            st.metric(
                f"Dominancia panel ({ventana}{unidad})",
                f"{cambio:+.2f} pp",
                delta=rotacion.rotation_label,
                delta_color="off",
                help=(
                    "Cuánto se movió el peso de Bitcoin dentro de este panel. El nivel no es "
                    "comparable con la dominancia global (acá hay decenas de monedas, no miles): "
                    "lo que se lee es la dirección. Sube = Bitcoin le gana al conjunto."
                ),
            )

    with columnas[2]:
        indice = rotacion.altseason_index_pct
        if indice != indice:
            st.metric("Temporada", "N/A")
        else:
            st.metric(
                "Temporada",
                f"{indice:.0f}%",
                delta=rotacion.season_label,
                delta_color="off",
                help=(
                    f"Qué porcentaje del panel le ganó a Bitcoin en la ventana. Por encima de "
                    f"{CRYPTO_ALTSEASON_MIN_PCT:.0f}% se habla de temporada de altcoins; por debajo "
                    f"de {CRYPTO_BTCSEASON_MAX_PCT:.0f}%, de temporada de Bitcoin."
                ),
            )

    with columnas[3]:
        figura = build_dominance_chart(rotacion.dominance_series, ventana)
        if figura is None:
            st.caption("Sin historial suficiente para reconstruir la dominancia del panel.")
        else:
            st.plotly_chart(figura, use_container_width=True, config={"displayModeBar": False})

    if rotacion.total_market_cap_usd:
        st.caption(
            f"Capitalización total del mercado cripto: **{format_usd_compact(rotacion.total_market_cap_usd)}**. "
            f"La franja sombreada del gráfico es la ventana de {ventana}{unidad} sobre la que se mide el cambio de dominancia."
        )


def _render_alerts(df: pd.DataFrame):
    """Tres columnas con las criptos que el semáforo destaca hoy."""
    if df.empty or "Semáforo" not in df.columns:
        return

    ventas = df[df["Semáforo"].isin([SIGNAL_STRONG_SELL, SIGNAL_MODERATE_SELL])]
    compras = df[df["Semáforo"].isin([SIGNAL_STRONG_BUY, SIGNAL_MODERATE_BUY])]
    squeezes = df[df["Semáforo"] == SIGNAL_SQUEEZE]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### 🔴 Venta / Rotación")
        if ventas.empty:
            st.caption("Ninguna hoy *(Sin sobrecompras extremas)*")
        for _, r in ventas.iterrows():
            tag = "🚨 Fuerte" if r["Semáforo"] == SIGNAL_STRONG_SELL else "🟠 Moderada"
            st.markdown(
                f"- **`{r['Cripto']}`** [{tag}] — {format_crypto_price(r['PRECIO_VAL'])} "
                f"*(RSI: {r['RSI_VAL']:.1f}, Máx 52S: {format_signed_pct(r['DIST_52W_HIGH_PCT'], decimals=1)})*"
            )

    with col2:
        st.markdown("#### 🟢 Compra / Swing")
        if compras.empty:
            st.caption("Ninguna hoy *(Esperando retrocesos a soporte)*")
        for _, r in compras.iterrows():
            tag = "🌟 Fuerte" if r["Semáforo"] == SIGNAL_STRONG_BUY else "🟢 Moderada"
            st.markdown(
                f"- **`{r['Cripto']}`** [{tag}] — {format_crypto_price(r['PRECIO_VAL'])} "
                f"*(RSI: {r['RSI_VAL']:.1f}, vs SMA50: {format_signed_pct(r['DIFF_SMA_50_VAL'], decimals=1)})*"
            )

    with col3:
        st.markdown("#### 🚨 Squeezes (Compresión)")
        if squeezes.empty:
            st.caption("Ninguna hoy *(Volatilidad en rango habitual)*")
        for _, r in squeezes.iterrows():
            st.markdown(
                f"- **`{r['Cripto']}`** — {format_crypto_price(r['PRECIO_VAL'])} "
                f"*(Bandwidth: {r['BB_BANDWIDTH']:.1f}%)*"
            )


def _render_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Filtros del cuadro, en el cuerpo de la sección, y el recorte resultante."""
    col1, col2, col3, col4 = st.columns([1.4, 1.2, 1.1, 1.3])

    with col1:
        signal_filter = st.selectbox("Semáforo:", CRYPTO_SIGNAL_FILTER_OPTIONS)
    with col2:
        rs_filter = st.selectbox(f"Fuerza vs {CRYPTO_BENCHMARK_LABEL}:", CRYPTO_RS_FILTER_OPTIONS)
    with col3:
        trend_filter = st.selectbox("Tendencia (SMA 200):", CRYPTO_TREND_FILTER_OPTIONS)
    with col4:
        rsi_range = st.slider("Rango de RSI 14:", 0.0, 100.0, (0.0, 100.0), step=1.0)

    return apply_crypto_filters(
        df,
        signal_filter=signal_filter,
        rs_filter=rs_filter,
        trend_filter=trend_filter,
        rsi_range=rsi_range,
    )


def _describir_divergencias(divergencias):
    """
    Explica en texto las divergencias que quedaron marcadas en el gráfico.

    El dibujo muestra que existen; esto dice qué significan y, sobre todo,
    qué no: una divergencia puede sostenerse meses antes de que el precio
    gire, y en una tendencia fuerte divergir es lo normal. Sin esa aclaración
    la marca se lee como una señal de entrada, que es justamente lo que no
    es.
    """
    if not divergencias:
        st.caption(
            "**Divergencias:** ninguna en la ventana dibujada. El impulso viene acompañando "
            "al precio."
        )
        return

    lineas = []
    for div in divergencias:
        icono = "🔻" if div.is_bearish else "🔺"
        lectura = (
            "el precio hizo un máximo más alto y el RSI uno más bajo: la suba pierde fuerza"
            if div.is_bearish
            else "el precio hizo un mínimo más bajo y el RSI uno más alto: la baja pierde fuerza"
        )
        lineas.append(
            f"- {icono} **{div.kind}** ({format_month_year(div.first_date)} → "
            f"{format_month_year(div.second_date)}) — {lectura}."
        )

    st.markdown("\n".join(lineas))
    st.caption(
        "Una divergencia avisa que el impulso no acompaña al precio, **no** que el giro sea "
        "inminente: puede sostenerse meses, y en una tendencia fuerte el oscilador se satura y "
        "divergir es lo habitual. Por eso se marcan en el gráfico y no entran al semáforo."
    )


def _render_chart(df: pd.DataFrame, historiales: dict[str, pd.DataFrame]):
    """
    Gráfico de velas de una moneda del panel, con sus zonas de soporte y
    resistencia.

    La escala es un selector y arranca en **mensual** porque la escala no es
    una preferencia visual: define qué se considera un nivel. En velas
    diarias de seis meses aparecen giros de corto plazo, casi todos con uno
    o dos toques; en velas mensuales de varios años aparecen los techos y
    pisos a los que el precio vuelve, que son los que sirven para decidir
    dónde comprar o dónde salir.

    La moneda arranca en Bitcoin porque es contra quien se compara todo lo
    demás, pero se puede cambiar: los niveles de la moneda que uno está por
    comprar importan más que los de Bitcoin.
    """
    st.markdown("### 📈 Gráfico con soportes y resistencias")

    disponibles = [t for t in df["Ticker"] if t in historiales] if "Ticker" in df.columns else []
    if not disponibles:
        st.caption("Sin historial disponible para graficar.")
        return

    por_ticker = dict(zip(df["Ticker"], df["Cripto"], strict=False))
    inicial = disponibles.index(CRYPTO_BENCHMARK_TICKER) if CRYPTO_BENCHMARK_TICKER in disponibles else 0

    col1, col2, col3 = st.columns([1.2, 1.8, 2])
    with col1:
        elegido = st.selectbox(
            "Moneda:",
            disponibles,
            index=inicial,
            format_func=lambda t: f"{por_ticker.get(t, t)} — {t}",
        )
    with col2:
        escala_elegida = st.selectbox(
            "Escala de los niveles:",
            CRYPTO_CHART_SCALE_OPTIONS,
            help="En qué temporalidad se buscan los giros del precio. Mensual da los niveles que el mercado reconoce; diario, los de las últimas semanas.",
        )

    escala = scale_params(escala_elegida)

    with st.spinner("⏳ Buscando niveles..."):
        historia = load_chart_history(elegido, escala.interval)

    if historia.empty:
        st.caption("No hay historial en esta escala para esta moneda.")
        return

    soportes, resistencias = detect_support_resistance(
        historia,
        lookaround=escala.lookaround,
        cluster_pct=escala.cluster_pct,
    )
    # La ventana dibujada, no el historial entero: una divergencia de hace
    # ocho años se marcaría fuera de la vista.
    visible = historia.tail(escala.bars)
    divergencias = detect_divergences(
        visible,
        compute_rsi(visible["Close"], 14),
        lookaround=escala.lookaround,
    )
    figura = build_crypto_chart(
        historia,
        soportes=soportes,
        resistencias=resistencias,
        nombre=por_ticker.get(elegido, elegido),
        bars=escala.bars,
        band_pct=escala.cluster_pct * CRYPTO_LEVEL_BAND_RATIO,
        divergencias=divergencias,
    )

    if figura is None:
        st.caption("Historial insuficiente en esta escala para dibujar el gráfico.")
        return

    st.plotly_chart(figura, use_container_width=True, config={"displayModeBar": False})
    st.caption(
        "Cada nivel se dibuja como **zona** y no como línea, porque el precio no gira en un número "
        "exacto sino en una franja. **Relleno y línea llena** cuando el precio la respetó tres veces "
        "o más; **punteada y tenue** cuando la tocó una o dos. La etiqueta dice a qué precio está, "
        "cuántas veces se respetó y a qué distancia quedó de la cotización de hoy."
    )
    _describir_divergencias(divergencias)


def render_crypto_panel():
    """
    Dibuja la sección de criptomonedas de punta a punta.

    Es el equivalente de `render_bonds_panel()` para esta clase de activo: la
    llama `app.main()` y desde acá para abajo la sección se maneja sola.
    """
    universe, timeframe = _render_sidebar()
    spec = spec_for_timeframe(timeframe)
    timeframe_label = "Semanal" if timeframe == "1wk" else "Diario"

    st.markdown('<div class="main-title">🪙 Criptomonedas</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="sub-title">Mismo semáforo de confluencia que el tablero de acciones, '
        f'con las ventanas ajustadas a un mercado que opera los siete días | '
        f'🕒 <i>Última recarga: {datetime.now().strftime("%H:%M:%S")}</i></div>',
        unsafe_allow_html=True,
    )

    with st.spinner(f"⏳ Descargando cotizaciones ({timeframe_label}) y evaluando confluencias..."):
        df, historiales, rotacion = load_crypto_data(universe, timeframe=timeframe)

    if df.empty:
        st.error(
            "No se pudieron cargar las cotizaciones de criptomonedas. "
            "Suele ser un problema de conexión o un límite de consultas del proveedor: "
            "probá de nuevo con **🔄 Refrescar Cripto**."
        )
        return

    fallidas = df.attrs.get("failed_tickers", [])
    if fallidas:
        st.warning(
            f"⚠️ No se pudieron cargar {len(fallidas)} criptomoneda(s). "
            "Suele pasar cuando el proveedor limita las consultas o cuando una moneda "
            "cambió de símbolo."
        )
        with st.expander("Ver criptomonedas omitidas"):
            st.write(", ".join(fallidas))

    if df.attrs.get("benchmark_missing"):
        st.info(
            f"No se pudo descargar {CRYPTO_BENCHMARK_TICKER}, así que la columna de fuerza "
            "relativa queda sin datos. El resto del cuadro no se ve afectado."
        )

    st.subheader("⚡ Alertas de Confluencia del Día")
    _render_alerts(df)
    st.markdown("---")

    _render_kpis(df, timeframe_label)
    st.markdown("---")

    _render_rotation(rotacion, timeframe_label, spec.ventana_dominancia, spec.unidad)
    st.markdown("---")

    st.markdown("### 🔍 Filtros")
    df_filtrado = _render_filters(df)

    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.markdown(
            f"### 📋 Matriz Cripto ({len(df_filtrado)} de {len(df)} monedas | Base: **{timeframe_label}**)"
        )
    with col_t2:
        st.download_button(
            label="📥 Exportar a CSV",
            data=df_filtrado.to_csv(index=False).encode("utf-8"),
            file_name=f"screener_cripto_{timeframe}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    render_crypto_table(df_filtrado, timeframe_label=timeframe_label)

    st.markdown("---")
    _render_chart(df, historiales)

    with st.expander("ℹ️ Qué cambia respecto del tablero de acciones"):
        st.markdown(f"""
        El semáforo es **exactamente el mismo**: las mismas condiciones obligatorias de
        soporte y RSI para el lado compra, el mismo techo con impulso agotándose para el
        lado venta. No hay un algoritmo distinto para cripto, porque leer un retroceso
        dentro de una tendencia sana no depende de qué se esté mirando.

        Lo que sí cambia es el contexto, y son tres cosas:

        **1. El calendario.** Cripto opera los 365 días del año. Una acción cotiza unas 252
        ruedas, así que "el máximo de las últimas 52 semanas" son 252 barras allá y
        {spec.ventana_52w} acá. Usar el número de acciones haría que el máximo anual de una
        cripto fuera en realidad el de los últimos ocho meses y medio, y que un precio cerca
        de su techo pareciera más alto de lo que está.

        **2. La referencia es Bitcoin, no un índice.** En esta clase de activo casi todo se
        mueve junto, así que "subió 8% en el mes" no dice nada por sí solo: si Bitcoin subió
        12%, esa moneda perdió terreno. La columna **vs BTC** mide justamente eso, el exceso
        de retorno sobre Bitcoin en las últimas {spec.retorno_largo} barras. La banda de
        ±{CRYPTO_RS_NEUTRAL_BAND_PP:.0f} puntos alrededor de cero existe porque en un activo
        que se mueve 5% en un día, dos puntos de diferencia acumulados en un mes son ruido.

        **3. No hay balances.** No existe el PER, ni el sector, ni el dividendo: una red no
        publica resultados trimestrales. En su lugar el cuadro muestra la **volatilidad
        anualizada** del último mes, que es la medida de riesgo que efectivamente se usa acá.
        Por encima de {CRYPTO_HIGH_VOLATILITY_PCT:.0f}% anual, cuánto se compra importa más
        que a qué precio se compra.

        **Sobre el volumen.** La columna de flujo es el mismo OBV del tablero de acciones,
        pero no se llama "Smart Money": el volumen que publica el proveedor es la suma de
        decenas de exchanges minoristas, no la huella de un fondo institucional. Sirve para
        ver si un movimiento de precio viene acompañado de operaciones o está vacío; no para
        deducir quién está del otro lado.

        **Las stablecoins no están, y es a propósito.** USDT o USDC cotizan pegadas a un
        dólar por diseño: su RSI y sus bandas describen ruido de centésimas, y el semáforo
        leería ese ruido como si fuera una tendencia.
        """)
