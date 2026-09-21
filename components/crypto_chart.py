"""
components/crypto_chart.py - Gráfico de velas con soportes y resistencias.

Solo dibuja: los niveles se los pasa `crypto/levels.py` ya calculados.

Criterios de lectura, que son los que hacen que el gráfico sirva de un
vistazo en vez de ser una parrilla de líneas:

  * **Pocas líneas.** Tres niveles por lado. Con quince siempre hay una cerca
    del precio, así que el precio siempre parece estar "en un nivel" y el
    gráfico deja de decir nada.
  * **El grosor es información.** Línea llena para los niveles que el precio
    respetó varias veces, punteada para los tocados una o dos. La cantidad de
    toques va en la etiqueta, así que no hay que adivinar por qué uno es más
    grueso que otro.
  * **Verde abajo, rojo arriba.** El mismo par de colores que la tabla y el
    resto del tablero (`theme.py`), sin una tercera convención propia.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from components.formatting import format_crypto_price
from constants import CRYPTO_LEVEL_LABEL_GAP_PX
from crypto.divergences import Divergence
from crypto.levels import PriceLevel
from indicators import compute_rsi, compute_sma
from theme import (
    COLOR_NEGATIVE,
    COLOR_NEUTRAL,
    COLOR_POSITIVE,
    COLOR_REFERENCE_LINE,
    COLOR_RSI_LINE,
    COLOR_SMA_50,
    COLOR_SMA_200,
)

# Transparencias de las zonas de nivel. La zona fuerte se ve; la débil
# está, pero no compite con las velas.
_RELLENO_FUERTE = 0.16
_RELLENO_DEBIL = 0.07


# Alto aproximado del panel de precios, en píxeles: la altura total de la
# figura por la fracción de fila que le toca. Alcanza con la aproximación,
# porque se usa para repartir textos y no para posicionar datos.
ALTO_PANEL_PRECIO_PX = 700 * 0.64


def _rango_vertical(vista: pd.DataFrame, niveles: list[PriceLevel]) -> tuple[float, float]:
    """
    Tramo de precios que ocupa el panel.

    Arranca en el piso de lo dibujado y no en cero: con velas de varios
    años, dejar que Plotly incluya el cero aplasta toda la acción reciente
    contra el techo del gráfico. Se incluyen los niveles para que ninguna
    zona quede fuera de cuadro.
    """
    precios_nivel = [n.price for n in niveles]
    if "Low" in vista.columns and "High" in vista.columns:
        pisos, techos = [float(vista["Low"].min())], [float(vista["High"].max())]
    else:
        pisos, techos = [float(vista["Close"].min())], [float(vista["Close"].max())]
    return min(pisos + precios_nivel) * 0.93, max(techos + precios_nivel) * 1.07


def repartir_etiquetas(
    precios: list[float],
    piso: float,
    techo: float,
    alto_px: float,
    separacion_px: float = CRYPTO_LEVEL_LABEL_GAP_PX,
) -> list[float]:
    """
    Cuánto hay que correr cada etiqueta, en píxeles, para que no se pisen.

    Las zonas cercanas al precio de hoy quedan necesariamente juntas —son
    las que más importan y las que más se apelotonan—, así que escribir cada
    texto a la altura exacta de su línea hace que dos o tres queden
    superpuestos e ilegibles.

    El reparto va de arriba hacia abajo: cada etiqueta se queda en su altura
    si puede, y si no baja lo justo para despegarse de la anterior. La línea
    del nivel no se mueve nunca; lo que se corre es solo el texto.

    Devuelve un desplazamiento por precio, en el mismo orden en que se
    recibieron.
    """
    if not precios or techo <= piso or alto_px <= 0:
        return [0.0] * len(precios)

    escala = alto_px / (techo - piso)
    alturas = [(precio - piso) * escala for precio in precios]

    # Se procesan de mayor a menor altura, guardando la posición original
    # para devolver los desplazamientos en el orden en que llegaron.
    orden = sorted(range(len(alturas)), key=lambda i: alturas[i], reverse=True)

    desplazamientos = [0.0] * len(precios)
    tope_ocupado = None
    for i in orden:
        altura = alturas[i]
        if tope_ocupado is not None and altura > tope_ocupado - separacion_px:
            altura = tope_ocupado - separacion_px
        desplazamientos[i] = altura - alturas[i]
        tope_ocupado = altura

    return desplazamientos


def _dibujar_nivel(
    fig: go.Figure,
    nivel: PriceLevel,
    color: str,
    etiqueta: str,
    precio_actual: float,
    ancho_pct: float,
    yshift: int = 0,
) -> None:
    """
    Dibuja un nivel como **zona**, no como línea.

    El precio no gira en un número exacto, gira en una franja: dibujar una
    línea de un píxel sugiere una precisión que el nivel no tiene, y hace
    que el precio parezca "romperlo" cada vez que lo cruza por medio punto.
    El ancho de la franja es la misma distancia dentro de la cual dos giros
    se consideraron el mismo nivel.

    La etiqueta dice las tres cosas que hacen falta para usarlo: a qué
    precio está, cuántas veces el precio lo respetó, y a qué distancia está
    de la cotización de hoy.
    """
    margen = nivel.price * ancho_pct / 100.0
    distancia = (nivel.price - precio_actual) / precio_actual * 100.0 if precio_actual else 0.0
    toques = f"{nivel.touches} toque" + ("s" if nivel.touches != 1 else "")

    fig.add_hrect(
        y0=nivel.price - margen,
        y1=nivel.price + margen,
        fillcolor=color,
        opacity=_RELLENO_FUERTE if nivel.is_strong else _RELLENO_DEBIL,
        line_width=0,
        layer="below",
        row=1,
        col=1,
    )
    fig.add_hline(
        y=nivel.price,
        line_color=color,
        line_width=2 if nivel.is_strong else 1,
        line_dash="solid" if nivel.is_strong else "dot",
        opacity=0.85 if nivel.is_strong else 0.5,
        annotation_text=(
            f"  <b>{etiqueta} {format_crypto_price(nivel.price)}</b>"
            f"<br>  {toques} · {distancia:+.0f}%"
        ),
        annotation_position="right",
        annotation_font_size=11,
        annotation_font_color=color,
        annotation_align="left",
        annotation_yshift=yshift,
        row=1,
        col=1,
    )


def _dibujar_divergencia(fig: go.Figure, div: Divergence) -> None:
    """
    Marca una divergencia con dos segmentos: uno en el precio y otro en el
    oscilador, del mismo color.

    Se dibujan los dos porque la divergencia **es** la comparación: un
    segmento que sube sobre las velas y otro que baja sobre el RSI se
    entiende de un vistazo, mientras que una marca suelta obliga a
    reconstruir a mano qué se estaba comparando.
    """
    color = COLOR_NEGATIVE if div.is_bearish else COLOR_POSITIVE
    fechas = [div.first_date, div.second_date]

    for fila, valores in ((1, [div.first_price, div.second_price]),
                          (3, [div.first_osc, div.second_osc])):
        fig.add_trace(
            go.Scatter(
                x=fechas,
                y=valores,
                mode="lines+markers",
                line=dict(color=color, width=2, dash="dot"),
                marker=dict(size=7, symbol="circle-open", line=dict(width=2, color=color)),
                showlegend=False,
                hovertemplate=f"{div.kind}<extra></extra>",
            ),
            row=fila,
            col=1,
        )


def build_crypto_chart(
    df: pd.DataFrame,
    soportes: list[PriceLevel],
    resistencias: list[PriceLevel],
    nombre: str,
    bars: int = 72,
    band_pct: float = 3.0,
    divergencias: list[Divergence] | None = None,
) -> go.Figure | None:
    """
    Velas de las últimas `bars` barras, con medias, volumen y zonas de nivel.

    Devuelve None si no hay suficiente historial para dibujar algo con
    sentido, en vez de un gráfico vacío que parece un error de carga.

    Las medias se calculan sobre el historial **completo** y recién después
    se recorta la ventana: calcularlas sobre lo que se ve dejaría la media
    larga en blanco justo cuando más sirve saber dónde está. En escalas
    largas —una vela por mes— puede no haber 200 barras de historia, y
    entonces esa media simplemente no se dibuja.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return None

    completo = df.sort_index()
    cierres = completo["Close"].dropna()
    if len(cierres) < 12:
        return None

    precio_actual = float(cierres.iloc[-1])

    medias = [
        (compute_sma(completo["Close"], periodo).tail(bars), color, f"SMA {periodo}")
        for periodo, color in ((50, COLOR_SMA_50), (200, COLOR_SMA_200))
    ]
    vista = completo.tail(bars)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.64, 0.14, 0.22],
    )

    fig.add_trace(
        go.Candlestick(
            x=vista.index,
            open=vista["Open"] if "Open" in vista.columns else vista["Close"],
            high=vista["High"] if "High" in vista.columns else vista["Close"],
            low=vista["Low"] if "Low" in vista.columns else vista["Close"],
            close=vista["Close"],
            name=nombre,
            increasing_line_color=COLOR_POSITIVE,
            decreasing_line_color=COLOR_NEGATIVE,
            increasing_fillcolor=COLOR_POSITIVE,
            decreasing_fillcolor=COLOR_NEGATIVE,
            line_width=1,
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    for serie, color, etiqueta in medias:
        if serie.notna().any():
            fig.add_trace(
                go.Scatter(
                    x=serie.index,
                    y=serie,
                    name=etiqueta,
                    line=dict(color=color, width=1.4),
                    hovertemplate=f"{etiqueta}: %{{y}}<extra></extra>",
                ),
                row=1,
                col=1,
            )

    if "Volume" in vista.columns:
        subas = vista["Close"] >= vista["Close"].shift(1)
        fig.add_trace(
            go.Bar(
                x=vista.index,
                y=vista["Volume"],
                name="Volumen",
                marker_color=[COLOR_POSITIVE if sube else COLOR_NEGATIVE for sube in subas],
                marker_line_width=0,
                opacity=0.35,
                showlegend=False,
                hovertemplate="Volumen: %{y:.3s}<extra></extra>",
            ),
            row=2,
            col=1,
        )

    # Las etiquetas de resistencia se corren hacia arriba y las de soporte
    # hacia abajo: cuando dos zonas quedan cerca —y las cercanas al precio
    # siempre lo están— los textos se montan uno sobre otro y no se lee
    # ninguno.
    rsi = compute_rsi(completo["Close"], 14).tail(bars)
    fig.add_trace(
        go.Scatter(
            x=rsi.index,
            y=rsi,
            name="RSI 14",
            line=dict(color=COLOR_RSI_LINE, width=1.5),
            showlegend=False,
            hovertemplate="RSI: %{y:.1f}<extra></extra>",
        ),
        row=3,
        col=1,
    )
    # Las bandas de 30 y 70 son la referencia con la que se lee el RSI; sin
    # ellas la línea no dice si 58 es mucho o poco.
    for nivel_rsi in (30, 70):
        fig.add_hline(
            y=nivel_rsi,
            line_color=COLOR_REFERENCE_LINE,
            line_width=1,
            line_dash="dot",
            opacity=0.6,
            row=3,
            col=1,
        )

    for div in divergencias or []:
        _dibujar_divergencia(fig, div)

    # El rango vertical se fija acá porque el reparto de las etiquetas lo
    # necesita: sin saber qué tramo de precios ocupa el panel, no se puede
    # traducir una distancia en dólares a una distancia en píxeles.
    piso, techo = _rango_vertical(vista, soportes + resistencias)

    # Las etiquetas se reparten en un solo cálculo, incluida la del precio de
    # hoy: si cada lado se acomodara por su cuenta, la de hoy se montaría
    # sobre el primer soporte, que es justo el caso más frecuente.
    etiquetados = (
        [(nivel, COLOR_NEGATIVE, f"R{orden}") for orden, nivel in enumerate(resistencias, start=1)]
        + [(nivel, COLOR_POSITIVE, f"S{orden}") for orden, nivel in enumerate(soportes, start=1)]
    )
    precios_etiqueta = [nivel.price for nivel, _, _ in etiquetados] + [precio_actual]
    corrimientos = repartir_etiquetas(
        precios_etiqueta, piso, techo, alto_px=ALTO_PANEL_PRECIO_PX
    )

    for (nivel, color, etiqueta), corrimiento in zip(etiquetados, corrimientos, strict=False):
        _dibujar_nivel(fig, nivel, color, etiqueta, precio_actual, band_pct, yshift=corrimiento)

    # El precio de hoy, para que la distancia a cada zona se lea sola y no
    # haya que buscar dónde termina la última vela.
    fig.add_hline(
        y=precio_actual,
        line_color=COLOR_NEUTRAL,
        line_width=1,
        line_dash="dash",
        opacity=0.7,
        annotation_text=f"  Hoy {format_crypto_price(precio_actual)}",
        annotation_position="right",
        annotation_font_size=11,
        annotation_font_color=COLOR_NEUTRAL,
        annotation_yshift=corrimientos[-1],
        row=1,
        col=1,
    )

    fig.update_layout(
        template="plotly_dark",
        height=700,
        # Margen derecho amplio: las etiquetas de las zonas se escriben fuera
        # del área de las velas para no taparlas.
        margin=dict(l=10, r=200, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis_rangeslider_visible=False,
        dragmode="pan",
    )

    grilla = "rgba(150, 160, 180, 0.12)"
    fig.update_xaxes(showgrid=False, showspikes=True, spikemode="across",
                     spikethickness=1, spikecolor=COLOR_NEUTRAL, spikedash="dot")
    fig.update_yaxes(showgrid=True, gridcolor=grilla, zeroline=False)
    fig.update_yaxes(
        title_text=None,
        tickprefix="$",
        range=[piso, techo],
        row=1,
        col=1,
    )
    fig.update_yaxes(showgrid=False, showticklabels=False, row=2, col=1)
    fig.update_yaxes(
        title_text="RSI",
        title_font_size=11,
        range=[0, 100],
        tickvals=[30, 50, 70],
        row=3,
        col=1,
    )

    return fig


def build_dominance_chart(serie: pd.Series, window_bars: int) -> go.Figure | None:
    """
    Evolución de la dominancia de Bitcoin dentro del panel.

    Deliberadamente austero: una línea, sin grilla vertical y sin leyenda. Lo
    único que hay que leer acá es la pendiente —si sube, Bitcoin le está
    ganando al resto— y cualquier adorno adicional compite con eso.

    Se sombrea la ventana sobre la que se mide el cambio informado en el KPI,
    para que el número y el dibujo se refieran visiblemente al mismo tramo.
    """
    if serie is None or serie.dropna().empty or len(serie.dropna()) < 5:
        return None

    limpia = serie.dropna()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=limpia.index,
            y=limpia,
            mode="lines",
            line=dict(color=COLOR_SMA_50, width=2),
            fill="tozeroy",
            fillcolor="rgba(41, 182, 246, 0.08)",
            hovertemplate="%{x|%d %b %Y}<br>Dominancia: %{y:.2f}%<extra></extra>",
            showlegend=False,
        )
    )

    if len(limpia) > window_bars:
        fig.add_vrect(
            x0=limpia.index[-(window_bars + 1)],
            x1=limpia.index[-1],
            fillcolor="rgba(150, 160, 180, 0.10)",
            line_width=0,
        )

    # El eje no arranca en cero: la dominancia se mueve en pocos puntos
    # porcentuales y desde cero la línea sería plana y no diría nada.
    piso = float(limpia.min())
    techo = float(limpia.max())
    margen = max((techo - piso) * 0.25, 0.5)

    fig.update_layout(
        template="plotly_dark",
        height=220,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        yaxis=dict(
            ticksuffix="%",
            range=[piso - margen, techo + margen],
            gridcolor="rgba(150, 160, 180, 0.12)",
        ),
        xaxis=dict(showgrid=False),
    )
    return fig
