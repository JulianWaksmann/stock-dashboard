"""
components/bonds_chart.py - Curva de rendimientos del panel de ONs.

Solo dibuja: la curva y los residuos los calcula `bonds/curve.py`.

Qué muestra que el cuadro no puede mostrar: el cuadro ordena por TIR, y la TIR
de un bono a un año y la de uno a cinco no son comparables. Acá cada especie
queda ubicada por plazo (duration, el eje horizontal) contra lo que rinde, y la
línea es lo que rinden **sus pares de ese mismo plazo**. Lo que importa es la
distancia vertical a esa línea, no la altura absoluta del punto.

Criterios de lectura, los mismos que el gráfico de cripto:

  * **El color es el veredicto**, con el par verde/rojo de `theme.py`: verde
    arriba de la curva (más TIR que sus pares), rojo abajo. Gris es "en la
    curva", que es donde debería estar la mayoría.
  * **El tamaño es el volumen operado**, porque una TIR atractiva en una
    especie que operó dos láminas no es ejecutable. Un punto chico es una
    advertencia, no un dato de segundo orden.
  * **La curva no se extrapola.** Empieza y termina en las duraciones que
    realmente se operan: afuera de ese rango no hay panel que describir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from bonds.curve import (
    COL_DURATION,
    COL_RELATIVE_VALUE,
    COL_RESIDUAL,
    COL_THEORETICAL_YTM,
    COL_YTM,
    CurveFit,
    curve_points,
)
from constants import BOND_CURVE_CHEAP, BOND_CURVE_RICH
from theme import (
    COLOR_NEGATIVE,
    COLOR_NEUTRAL,
    COLOR_POSITIVE,
    COLOR_REFERENCE_LINE,
    COLOR_SCATTER_LABEL_TEXT,
    COLOR_SCATTER_MARKER_BORDER,
)

# Tamaños de marcador, en px: el mínimo tiene que seguir siendo clickeable y
# el máximo no puede tapar a sus vecinos.
_SIZE_MIN = 9.0
_SIZE_MAX = 26.0


def _colores(etiquetas: pd.Series) -> list[str]:
    mapa = {BOND_CURVE_CHEAP: COLOR_POSITIVE, BOND_CURVE_RICH: COLOR_NEGATIVE}
    return [mapa.get(e, COLOR_NEUTRAL) for e in etiquetas]


def _tamanos(volumen: pd.Series) -> np.ndarray:
    """
    Tamaño por volumen, en raíz cuadrada del monto.

    La raíz y no el monto directo porque el volumen de ONs abarca varios
    órdenes de magnitud en el mismo día: en escala lineal, la especie más
    operada deja a todas las demás como puntos de un píxel.
    """
    v = pd.to_numeric(volumen, errors="coerce").fillna(0.0).clip(lower=0.0)
    tope = float(v.max()) if len(v) else 0.0
    if tope <= 0:
        return np.full(len(v), (_SIZE_MIN + _SIZE_MAX) / 2)
    return _SIZE_MIN + (_SIZE_MAX - _SIZE_MIN) * np.sqrt(v.to_numpy() / tope)


def build_curve_chart(df: pd.DataFrame, ajuste: CurveFit | None, moneda: str) -> go.Figure:
    """
    Dibuja la nube de bonos de una moneda y la curva ajustada sobre ella.

    `df` tiene que venir ya con los residuos (`add_curve_residuals`) y filtrado
    a una sola moneda: dos monedas en el mismo par de ejes serían dos curvas
    distintas dibujadas como si fueran una.
    """
    graficables = df.dropna(subset=[COL_DURATION, COL_YTM]).copy() if not df.empty else df
    if graficables.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="Ninguna especie de este panel tiene TIR y duration calculables",
            showarrow=False,
        )
        fig.update_layout(template="plotly_dark", height=420)
        return fig

    columnas_hover = [
        graficables.get("Emisor", pd.Series([""] * len(graficables), index=graficables.index)),
        graficables.get("Calificación", pd.Series(["—"] * len(graficables), index=graficables.index)),
        graficables.get("Volumen", pd.Series([np.nan] * len(graficables), index=graficables.index)),
        graficables.get(COL_THEORETICAL_YTM, pd.Series([np.nan] * len(graficables), index=graficables.index)),
        graficables.get(COL_RESIDUAL, pd.Series([np.nan] * len(graficables), index=graficables.index)),
        graficables.get(COL_RELATIVE_VALUE, pd.Series(["—"] * len(graficables), index=graficables.index)),
    ]

    fig = go.Figure()

    if ajuste is not None:
        xs, ys = curve_points(ajuste, graficables[COL_DURATION])
        if len(xs):
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    name=f"Curva del panel ({moneda})",
                    line=dict(color=COLOR_REFERENCE_LINE, width=2, dash="dash"),
                    hovertemplate="Duration %{x:.2f} → TIR de referencia %{y:.2f}%<extra></extra>",
                )
            )

    fig.add_trace(
        go.Scatter(
            x=graficables[COL_DURATION],
            y=graficables[COL_YTM],
            mode="markers+text",
            name="Especies",
            text=graficables["Ticker"] if "Ticker" in graficables.columns else None,
            textposition="top center",
            textfont=dict(size=10, color=COLOR_SCATTER_LABEL_TEXT),
            marker=dict(
                size=_tamanos(graficables.get("Volumen", pd.Series(dtype=float))),
                color=_colores(graficables.get(COL_RELATIVE_VALUE, pd.Series(dtype=object))),
                line=dict(width=1, color=COLOR_SCATTER_MARKER_BORDER),
            ),
            customdata=np.stack([c.to_numpy() for c in columnas_hover], axis=-1),
            hovertemplate=(
                "<b>%{text}</b> — %{customdata[0]}<br>"
                "Calificación: %{customdata[1]}<br>"
                "Duration modificada: %{x:.2f} años<br>"
                "TIR: %{y:.2f}%<br>"
                "TIR de sus pares de igual plazo: %{customdata[3]:.2f}%<br>"
                "Diferencia: %{customdata[4]:+.2f} pp (%{customdata[5]})<br>"
                "Volumen operado: %{customdata[2]:,.0f}<extra></extra>"
            ),
        )
    )

    if ajuste is not None:
        subtitulo = (
            f"{ajuste.n} especies en el ajuste · pendiente {ajuste.pendiente:+.2f} pp "
            f"por unidad de ln(1+duration) · R² {ajuste.r2:.2f}"
        )
    else:
        subtitulo = (
            "Sin curva: el panel no tiene suficientes especies con TIR y duration, "
            "o todas vencen en plazos casi iguales"
        )

    fig.update_layout(
        template="plotly_dark",
        title=f"<b>Curva de rendimientos del panel — {moneda}</b><br><sup>{subtitulo}</sup>",
        xaxis_title="Duration modificada (años) — riesgo de tasa",
        yaxis_title="TIR (%)",
        height=520,
        margin=dict(l=50, r=40, t=80, b=45),
        showlegend=False,
        hovermode="closest",
    )
    return fig
