"""
components/merval_panel.py - Sección de acciones argentinas, medida en dólares.

Reusa el cuerpo del panel de acciones (`components/stocks_body.py`) porque es
el mismo semáforo sobre el mismo contrato de columnas: lo propio de esta
sección es apenas la cabecera y el cuadro del dólar implícito, que es lo que
hace creíble todo lo demás.

Por qué el CCL se muestra y no se esconde: cada precio de este panel es un
precio en pesos dividido por un tipo de cambio que el tablero **calculó**. Si
ese número está mal, todo el panel está mal, y quien mira tiene derecho a ver
de dónde salió y qué tan de acuerdo están los pares que lo forman.

Es capa de dibujo: el cálculo vive en `merval/ccl.py`, que es puro.
"""

from __future__ import annotations

import numpy as np
import streamlit as st

from components.stocks_body import render_failed_tickers_notice, render_stocks_body
from constants import MERVAL_CCL_MAX_DISPERSION_PCT
from merval.ccl import CclEstimate
from merval.data_loader import load_merval_data, universo_descripto, ventanas_para
from stock_screener import StockFilters, apply_stock_filters


def _render_ccl(ccl: CclEstimate):
    """Tarjeta del dólar implícito, con el detalle par por par detrás."""
    col_valor, col_pares, col_dispersion = st.columns(3)

    with col_valor:
        st.metric(
            "Dólar implícito del panel (CCL)",
            f"${ccl.ultimo:,.0f}" if np.isfinite(ccl.ultimo) else "N/A",
            help=(
                "Mediana del tipo de cambio que surge de cada par acción local / ADR. "
                "No es el CCL que publican los medios, que se calcula contra bonos: "
                "cotiza unas décimas distinto y se mueve igual."
            ),
        )

    with col_pares:
        st.metric(
            "Pares que lo forman",
            f"{len(ccl.pares_usados)}",
            help="Acciones con las dos puntas operadas. Se usa la mediana: un ratio mal cargado queda como valor extremo y no mueve el resultado.",
        )

    with col_dispersion:
        dispersion = ccl.dispersion_pct
        sana = np.isfinite(dispersion) and dispersion <= MERVAL_CCL_MAX_DISPERSION_PCT
        st.metric(
            "Dispersión entre pares",
            f"{dispersion:.1f}%" if np.isfinite(dispersion) else "N/A",
            delta="Consistente" if sana else "Revisar ratios",
            delta_color="normal" if sana else "inverse",
            help=(
                "Rango entre el par más alto y el más bajo, en % de la mediana. Con ratios "
                "correctos los pares coinciden dentro de pocos puntos; el resto es costo "
                "de arbitraje."
            ),
        )

    if np.isfinite(ccl.dispersion_pct) and ccl.dispersion_pct > MERVAL_CCL_MAX_DISPERSION_PCT:
        sospechosos = ccl.detalle[ccl.detalle["Sospechoso"]] if not ccl.detalle.empty else None
        tickers = ", ".join(sospechosos["Ticker"]) if sospechosos is not None and not sospechosos.empty else "—"
        st.warning(
            f"⚠️ **Los pares no coinciden ({ccl.dispersion_pct:.0f}% de rango).** Suele ser un "
            f"ratio de ADR desactualizado en el catálogo: {tickers}. El panel se calcula igual "
            "con la mediana, que no se mueve por un par equivocado, pero conviene corregir la "
            "tabla — el detalle de abajo sugiere el ratio que volvería consistente a cada uno."
        )

    with st.expander("Ver el dólar implícito par por par"):
        st.caption(
            "Cada fila es el tipo de cambio que surge de esa acción contra su ADR. La columna "
            "**Ratio sugerido** es el que volvería consistente al par con el resto del panel: "
            "si aparece un número, el ratio cargado probablemente esté desactualizado."
        )
        if ccl.detalle.empty:
            st.info("No hay pares con las dos puntas operadas.")
        else:
            st.dataframe(
                ccl.detalle,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Ticker": st.column_config.TextColumn("Local", width="small"),
                    "ADR": st.column_config.TextColumn("ADR", width="small"),
                    "Ratio": st.column_config.NumberColumn("Acciones por ADR", format="%d"),
                    "Verificado": st.column_config.CheckboxColumn(
                        "Ratio verificado",
                        help="Comprobado contra el programa del ADR, no solo contra la consistencia del panel.",
                    ),
                    "CCL del par": st.column_config.NumberColumn("CCL del par", format="$%.0f"),
                    "Desvío (%)": st.column_config.NumberColumn("Desvío vs mediana", format="%+.1f%%"),
                    "Sospechoso": st.column_config.CheckboxColumn("Sospechoso"),
                    "Ratio sugerido": st.column_config.NumberColumn("Ratio sugerido", format="%d"),
                },
            )


def _render_splits_corregidos(df_summary):
    """
    Avisa qué series se corrigieron por un split que el proveedor no ajustó.

    Se informa en vez de arreglarse en silencio porque es un dato que el
    tablero **cambió**: sin el aviso, una serie reparada y una serie correcta
    se ven igual, y la corrección es heurística (ver `merval/splits.py`).
    """
    try:
        splits = df_summary.attrs.get("splits_corregidos", {})
    except Exception:
        splits = {}

    if not splits:
        return

    detalle = " · ".join(
        f"**{ticker}** ({', '.join(str(e) for e in eventos)})"
        for ticker, eventos in sorted(splits.items())
    )
    st.info(
        f"🔧 **{len(splits)} serie(s) corregidas por splits que el proveedor no ajustó:** "
        f"{detalle}. Pasa seguido en las especies locales, y sin corregir el salto el "
        "precio parece haberse derrumbado: la acción no cayó, se partió. Los indicadores "
        "de abajo usan la serie ya continua.",
        icon="🔧",
    )


def render_merval_panel(timeframe: str, timeframe_label: str, filtros: StockFilters):
    """
    Dibuja la sección de acciones argentinas de punta a punta.

    La llama `app.py` cuando el selector de mercado elige Argentina, con los
    mismos filtros de la barra lateral que usa el panel estadounidense: el
    tamiz es el mismo (`stock_screener.apply_stock_filters`).
    """
    col_texto, col_boton = st.columns([4, 1])
    with col_texto:
        st.markdown(
            '<div class="main-title">Acciones Argentinas — en dólares</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="sub-title">El mismo semáforo de confluencia que el panel '
            f'estadounidense, sobre precios convertidos a dólares con el tipo de cambio '
            f'implícito del propio panel. {universo_descripto()}.</div>',
            unsafe_allow_html=True,
        )
    with col_boton:
        st.markdown("<div style='padding-top: 10px;'></div>", unsafe_allow_html=True)
        if st.button(
            "Refrescar datos",
            use_container_width=True,
            type="primary",
            key="merval_refrescar",
            help="Limpia la memoria caché y vuelve a pedir las cotizaciones locales y de los ADR",
        ):
            st.cache_data.clear()
            st.rerun()

    st.info(
        "📗 **Por qué en dólares y no en pesos.** El precio en pesos mezcla lo que vale la "
        "empresa con lo que dejó de valer el peso: una media de 200 ruedas sube sola y el RSI "
        "marca sobrecompra en cada salto devaluatorio. El semáforo asume una serie donde una "
        "suba es una suba, así que acá cada precio se divide por el dólar implícito del día.",
        icon="💵",
    )

    with st.spinner(f"⏳ Descargando el panel local y los ADR ({timeframe_label}) y calculando el dólar implícito..."):
        df_summary, historiales, ccl = load_merval_data(timeframe=timeframe)

    if not ccl.disponible:
        st.error(
            "No se pudo calcular el dólar implícito: hace falta que al menos un par acción "
            "local / ADR tenga precios en las dos puntas. Sin tipo de cambio no se arma el "
            "panel, porque un cuadro en pesos nominales mostraría medias que suben solas. "
            "Probá de nuevo con **Refrescar datos**."
        )
        return

    _render_ccl(ccl)
    st.markdown("---")

    if df_summary.empty:
        st.error(
            "No se pudieron cargar las cotizaciones de las acciones argentinas. "
            "Suele ser un límite de consultas del proveedor: probá de nuevo en un minuto."
        )
        return

    render_failed_tickers_notice(df_summary, nombre_activo="acción argentina")
    _render_splits_corregidos(df_summary)

    ventana_52w, squeeze_lookback = ventanas_para(timeframe)
    render_stocks_body(
        df_summary,
        apply_stock_filters(df_summary, filtros),
        historiales,
        timeframe_label=timeframe_label,
        timeframe=timeframe,
        nombre_archivo="merval_en_dolares",
        nombre_activo="acciones argentinas",
        motor_registro="acciones_merval",
        window_52w=ventana_52w,
        squeeze_lookback=squeeze_lookback,
        key_prefix="merval",
    )
