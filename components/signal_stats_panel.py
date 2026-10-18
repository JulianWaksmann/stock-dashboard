"""
components/signal_stats_panel.py - "¿Funcionó el semáforo?", en el propio tablero.

Lo dibuja igual para acciones y para cripto: el semáforo es el mismo algoritmo
calibrado distinto (ver `indicators.ConfluenceThresholds`), así que su medición
también tiene que ser la misma o los dos números no serían comparables.

Dos decisiones de la interfaz:

  * **La medición no corre sola.** Replayar el semáforo sobre decenas de
    historiales cuesta un par de segundos, y Streamlit ejecuta el cuerpo de los
    expanders en cada corrida, igual que el de las pestañas: si se midiera sin
    pedirlo, cada vez que alguien mueve un filtro pagaría ese costo. Va detrás
    de un interruptor que arranca apagado.
  * **La fila de base va arriba y resaltada.** Es la única referencia que hace
    legible al resto: lo que convierte a una señal en buena no es su retorno,
    es el exceso sobre una barra cualquiera del mismo período.

Es capa de dibujo: la medición vive en `signal_stats.py`, que es puro.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from constants import (
    SIGNAL_STATS_BASELINE,
    SIGNAL_STATS_HORIZONS_DAILY,
    SIGNAL_STATS_HORIZONS_WEEKLY,
    SIGNAL_STATS_MIN_CASES,
    SQUEEZE_LOOKBACK_BARS,
)
from indicators import STOCK_THRESHOLDS, ConfluenceThresholds
from signal_stats import (
    COL_ABS_MOVE,
    COL_BEST,
    COL_CASES,
    COL_EXCESS,
    COL_HIT_RATE,
    COL_MEAN,
    COL_MEDIAN,
    COL_SIGNAL,
    COL_WORST,
    measure_signal_quality,
)


def _etiqueta_horizonte(barras: int, es_semanal: bool) -> str:
    unidad = "semanas" if es_semanal else "ruedas"
    return f"{barras} {unidad}"


def _render_tabla(resumen: pd.DataFrame):
    estilo = resumen.style.format({
        COL_MEAN: "{:+.2f}%",
        COL_EXCESS: "{:+.2f}",
        COL_MEDIAN: "{:+.2f}%",
        COL_HIT_RATE: "{:.0f}%",
        COL_ABS_MOVE: "{:.2f}%",
        COL_WORST: "{:+.1f}%",
        COL_BEST: "{:+.1f}%",
    }, na_rep="—")

    st.dataframe(
        estilo,
        use_container_width=True,
        hide_index=True,
        column_config={
            COL_SIGNAL: st.column_config.TextColumn("Señal", width="medium"),
            COL_CASES: st.column_config.NumberColumn(
                "Casos",
                format="%d",
                help=(
                    f"Barras en las que apareció la señal. Menos de {SIGNAL_STATS_MIN_CASES} "
                    "es anecdótico. Ojo: las muestras se solapan, así que son menos "
                    "episodios independientes de los que parece."
                ),
            ),
            COL_MEAN: st.column_config.TextColumn(
                "Retorno medio",
                help="Retorno promedio del activo en el horizonte elegido, después de la señal.",
            ),
            COL_EXCESS: st.column_config.TextColumn(
                "Exceso vs base",
                help="Lo único que importa: cuántos puntos porcentuales más que una barra cualquiera del mismo período.",
            ),
            COL_MEDIAN: st.column_config.TextColumn("Mediana"),
            COL_HIT_RATE: st.column_config.TextColumn(
                "Acierto",
                help="Compras: cuántas veces subió. Ventas: cuántas veces bajó. Squeeze y neutral no afirman dirección, así que no se mide.",
            ),
            COL_ABS_MOVE: st.column_config.TextColumn(
                "Movimiento",
                help="Movimiento promedio sin importar el signo. Es la columna que valida al SQUEEZE, que anticipa magnitud y no dirección.",
            ),
            COL_WORST: st.column_config.TextColumn("Peor caso"),
            COL_BEST: st.column_config.TextColumn("Mejor caso"),
        },
    )


def render_signal_stats(
    historiales: dict[str, pd.DataFrame],
    timeframe_label: str = "Diario",
    window_52w: int = 252,
    squeeze_lookback: int = SQUEEZE_LOOKBACK_BARS,
    thresholds: ConfluenceThresholds = STOCK_THRESHOLDS,
    key_prefix: str = "acciones",
):
    """
    Sección "¿funcionó el semáforo?" sobre los historiales ya descargados.

    `window_52w`, `squeeze_lookback` y `thresholds` tienen que ser **los mismos**
    que usó el panel que se está mirando: medir con la calibración de acciones
    un panel de cripto daría el número de otro sistema.
    """
    with st.expander("🧪 ¿Funcionó el semáforo? (medición sobre el historial descargado)"):
        st.markdown(
            "El semáforo afirma algo verificable: que cuando varias señales coinciden, lo que "
            "sigue es distinto de un día cualquiera. Acá se replaya el semáforo barra por barra "
            "sobre el mismo historial que el tablero ya bajó y se mira qué pasó después."
        )

        if not historiales:
            st.info("No hay historiales descargados para medir.")
            return

        es_semanal = str(timeframe_label).lower().startswith("sem")
        horizontes = SIGNAL_STATS_HORIZONS_WEEKLY if es_semanal else SIGNAL_STATS_HORIZONS_DAILY
        etiquetas = {_etiqueta_horizonte(b, es_semanal): b for b in horizontes}

        col_horizonte, col_correr = st.columns([3, 1])
        with col_horizonte:
            elegido = st.radio(
                "Horizonte de medición",
                list(etiquetas),
                horizontal=True,
                key=f"{key_prefix}_horizonte_medicion",
                help="Cuántas barras después de la señal se mide el retorno.",
            )
        with col_correr:
            correr = st.checkbox(
                "Medir",
                value=False,
                key=f"{key_prefix}_correr_medicion",
                help="Replayar el semáforo sobre todo el historial cuesta unos segundos, así que no corre solo.",
            )

        if not correr:
            st.caption(
                f"Marcá **Medir** para replayar el semáforo sobre {len(historiales)} "
                "historial(es). No descarga nada nuevo: usa los datos que ya están en pantalla."
            )
            return

        horizonte = etiquetas[elegido]
        with st.spinner("⏳ Replayando el semáforo barra por barra..."):
            resumen, casos = measure_signal_quality(
                historiales,
                horizon=horizonte,
                window_52w=window_52w,
                squeeze_lookback=squeeze_lookback,
                thresholds=thresholds,
            )

        if resumen.empty:
            st.info(
                "El historial descargado no alcanza para medir este horizonte: hacen falta al "
                "menos unas cuantas barras más que el horizonte elegido."
            )
            return

        _render_tabla(resumen)

        base = resumen[resumen[COL_SIGNAL] == SIGNAL_STATS_BASELINE]
        base_media = float(base[COL_MEAN].iloc[0]) if not base.empty else float("nan")
        st.caption(
            f"Base del período: **{base_media:+.2f}%** a {elegido} para una barra cualquiera, "
            f"sobre {len(casos):,} barras de {len(historiales)} activo(s). "
            "Una señal solo aporta si su exceso sobre esa base es claramente positivo "
            "(negativo, en las de venta)."
        )

        st.warning(
            "⚠️ **Qué no es esto.** Las muestras se solapan (el retorno a 20 barras del lunes y "
            "del martes comparten 19 días), así que hay muchos menos episodios independientes "
            "que casos; es el período que se descargó, que entra casi entero en un mismo "
            "régimen de mercado; y mide la señal, no una estrategia: no hay costos, ni "
            "deslizamiento, ni stop, ni tamaño de posición."
        )
