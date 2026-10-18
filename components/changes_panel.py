"""
components/changes_panel.py - "Qué cambió desde la última vez".

El tablero es una foto del día: dice qué marca el semáforo ahora y no sabe nada
de ayer. Esta sección le da memoria, con el registro diario de `snapshots.py`.

Dos cosas que se declaran en pantalla en vez de esconderse:

  * **La foto del día es la de la primera consulta.** El registro se graba una
    vez por día y no se reescribe, porque si cada recarga lo pisara, "lo que
    cambió desde ayer" dependería de a qué hora miró cada uno.
  * **Contra qué fecha se compara.** Si el tablero no se abrió el viernes, el
    lunes compara contra el jueves, y eso se lee distinto.

Es capa de dibujo: comparar y grabar es de `snapshots.py`.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from snapshots import PanelChanges, record_and_compare
from theme import COLOR_NEUTRAL

# Cuántos movimientos de precio se listan. Son los extremos: la lista completa
# ya está en el cuadro de arriba.
_MOVIMIENTOS_VISIBLES = 5


def _render_cambios_de_señal(cambios: PanelChanges):
    st.markdown("**Cambios de semáforo**")
    if cambios.señales.empty:
        st.caption("Ninguno: el semáforo marca lo mismo que la última vez.")
        return

    for _, fila in cambios.señales.iterrows():
        st.markdown(
            f"- **`{fila['Ticker']}`** — {fila['Antes']} "
            f"<span style='color:{COLOR_NEUTRAL};'>→</span> {fila['Ahora']}",
            unsafe_allow_html=True,
        )


def _render_movimientos(cambios: PanelChanges):
    st.markdown("**Mayores movimientos de precio**")
    if cambios.movimientos.empty:
        st.caption("Sin precios comparables entre las dos fotos.")
        return

    extremos = cambios.movimientos.head(_MOVIMIENTOS_VISIBLES)
    st.dataframe(
        extremos,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", width="small"),
            "Antes": st.column_config.NumberColumn("Antes", format="%.2f"),
            "Ahora": st.column_config.NumberColumn("Ahora", format="%.2f"),
            "Var. (%)": st.column_config.NumberColumn("Variación", format="%+.2f%%"),
        },
    )


def render_changes(
    df: pd.DataFrame,
    motor: str,
    columna_senal: str = "Semáforo",
    columna_precio: str = "Precio Actual",
):
    """
    Graba la foto del día y muestra qué cambió contra la anterior.

    `motor` es el nombre de la carpeta del registro: un panel por clase de
    activo y por mercado, porque comparar acciones argentinas contra las
    estadounidenses no significaría nada.
    """
    with st.expander("Qué cambió desde la última vez"):
        if df is None or df.empty:
            st.info("No hay panel que registrar.")
            return

        cambios = record_and_compare(
            df,
            motor,
            columna_senal=columna_senal,
            columna_precio=columna_precio,
        )

        if cambios.fecha_anterior is None:
            st.info(
                "📗 **Primera foto de este panel.** Desde hoy queda registrado un estado por "
                "día, y la próxima vez que lo abras vas a ver acá qué cambió: qué activo pasó "
                "de neutral a compra, cuál salió del panel y cuáles fueron los mayores "
                "movimientos de precio."
            )
            return

        st.caption(
            f"Comparado contra la foto del **{cambios.fecha_anterior:%d/%m/%Y}**, que es la "
            "última anterior a hoy. El registro se graba una vez por día, en la primera "
            "consulta: la foto del día es la de ese momento, no la del cierre."
        )

        columna_señales, columna_movimientos = st.columns(2)
        with columna_señales:
            _render_cambios_de_señal(cambios)
        with columna_movimientos:
            _render_movimientos(cambios)

        if cambios.nuevos or cambios.salidos:
            partes = []
            if cambios.nuevos:
                partes.append(f"**entraron** {', '.join(cambios.nuevos)}")
            if cambios.salidos:
                partes.append(f"**salieron** {', '.join(cambios.salidos)}")
            st.caption(
                "Composición del panel: " + " · ".join(partes) + ". "
                "Casi siempre es un activo que el proveedor no devolvió ese día, no una "
                "novedad del mercado."
            )
