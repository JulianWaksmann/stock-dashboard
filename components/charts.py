"""
components/charts.py - Gráficos interactivos con Plotly (4 paneles apilados sincronizados según John Murphy)
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from constants import (
    STOCK_LEVEL_CLUSTER_PCT,
    STOCK_LEVELS_PER_SIDE,
    STOCK_PIVOT_LOOKAROUND_BARS,
)
from indicators import (
    compute_bollinger_bands,
    compute_macd,
    compute_rsi,
    compute_sma,
    compute_stochastic,
)
from levels import PriceLevel, detect_support_resistance
from theme import (
    COLOR_BOLLINGER_BAND,
    COLOR_BOLLINGER_FILL,
    COLOR_BOLLINGER_MID,
    COLOR_CHART_GRID,
    COLOR_MACD_LINE,
    COLOR_MACD_SIGNAL,
    COLOR_MACD_ZERO_LINE,
    COLOR_NEGATIVE,
    COLOR_PE_FORWARD,
    COLOR_PE_HISTORICAL_AVG,
    COLOR_PE_TRAILING,
    COLOR_POSITIVE,
    COLOR_PRICE_LINE,
    COLOR_REFERENCE_LINE,
    COLOR_RSI_LINE,
    COLOR_SCATTER_LABEL_TEXT,
    COLOR_SCATTER_MARKER_BORDER,
    COLOR_SCATTER_REFERENCE_LINE,
    COLOR_SMA_50,
    COLOR_SMA_200,
    COLOR_STOCH_D,
    COLOR_STOCH_K,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_FAMILY,
    PLOTLY_TEMPLATE,
)


@dataclass
class ChartIndicators:
    """Contenedor de los indicadores técnicos ya calculados para el gráfico de detalle."""

    sma_50: pd.Series
    sma_200: pd.Series
    bollinger: pd.DataFrame
    macd: pd.DataFrame
    rsi_14: pd.Series
    stochastic: pd.DataFrame


def compute_chart_indicators(df_history: pd.DataFrame) -> ChartIndicators | None:
    """
    Calcula, una única vez, todos los indicadores técnicos que necesita el
    gráfico de detalle (SMA 50/200, Bollinger, MACD, RSI y Estocástico).

    Se separa deliberadamente del ploteo: así el cálculo no se repite entre
    subplots y `plot_stock_detail` se limita a recibir estos datos y dibujar.
    Devuelve None si no hay datos suficientes (sin serie de cierre).
    """
    if df_history.empty or 'Close' not in df_history.columns:
        return None

    close = df_history['Close']
    return ChartIndicators(
        sma_50=compute_sma(close, 50),
        sma_200=compute_sma(close, 200),
        bollinger=compute_bollinger_bands(close, period=20, num_std=2.0),
        macd=compute_macd(close, fast=12, slow=26, signal=9),
        rsi_14=compute_rsi(close, 14),
        stochastic=compute_stochastic(df_history, period_k=14, period_d=3),
    )


def _add_price_panel(fig: go.Figure, df: pd.DataFrame, indicators: ChartIndicators, timeframe_label: str, suffix: str) -> None:
    """Panel 1: Velas Japonesas (u línea de cierre) + SMA 50 + SMA 200 + Bandas de Bollinger."""
    has_ohlc = all(col in df.columns for col in ['Open', 'High', 'Low', 'Close'])
    if has_ohlc:
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name=f"Precio ({timeframe_label})",
                increasing_line_color=COLOR_POSITIVE,
                decreasing_line_color=COLOR_NEGATIVE
            ),
            row=1, col=1
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df['Close'],
                mode='lines', name='Precio Cierre',
                line=dict(color=COLOR_PRICE_LINE, width=2)
            ),
            row=1, col=1
        )

    df_bb = indicators.bollinger
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df_bb['bb_upper'],
            mode='lines', name='Bollinger Superior',
            line=dict(color=COLOR_BOLLINGER_BAND, width=1, dash='dash'),
            showlegend=True
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df_bb['bb_lower'],
            mode='lines', name='Bollinger Inferior',
            line=dict(color=COLOR_BOLLINGER_BAND, width=1, dash='dash'),
            fill='tonexty',
            fillcolor=COLOR_BOLLINGER_FILL,
            showlegend=True
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df_bb['bb_mid'],
            mode='lines', name='Bollinger Base (SMA 20)',
            line=dict(color=COLOR_BOLLINGER_MID, width=1.2, dash='dot'),
            showlegend=False
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=df.index, y=indicators.sma_50,
            mode='lines', name=f'SMA 50 ({suffix})',
            line=dict(color=COLOR_SMA_50, width=2)
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, y=indicators.sma_200,
            mode='lines', name=f'SMA 200 ({suffix})',
            line=dict(color=COLOR_SMA_200, width=2.4)
        ),
        row=1, col=1
    )


def _aplicar_estilo(fig: go.Figure) -> None:
    """
    Deja todos los gráficos hablando el idioma del tablero.

    Tipografía y color de texto de la carcasa, fondo del lienzo y una grilla
    con el tinte lavanda en vez del gris de `plotly_white`. Está acá y no
    repetido en cada `update_layout` porque la coherencia entre gráficos es
    justamente lo que se pierde cuando cada uno la declara por su cuenta.

    No toca `title_font`: fijarlo en una figura sin título hace que Plotly
    dibuje la palabra "undefined" arriba a la izquierda. Estos gráficos no
    llevan título propio — el encabezado de la sección ya dice qué son.
    """
    fig.update_layout(
        font=dict(family=FONT_FAMILY, size=11.5, color=COLOR_TEXT),
        paper_bgcolor=COLOR_SURFACE,
        plot_bgcolor=COLOR_SURFACE,
        hoverlabel=dict(font=dict(family=FONT_FAMILY, size=12)),
    )
    fig.update_xaxes(
        gridcolor=COLOR_CHART_GRID,
        showline=False,
        zeroline=False,
        ticks="",
        title_font=dict(size=11, color=COLOR_TEXT_MUTED),
    )
    fig.update_yaxes(
        gridcolor=COLOR_CHART_GRID,
        showline=False,
        zeroline=False,
        ticks="",
        title_font=dict(size=11, color=COLOR_TEXT_MUTED),
    )


def _add_levels(fig: go.Figure, df: pd.DataFrame) -> None:
    """
    Soportes y resistencias sobre el panel de precio.

    Usa el mismo detector que el gráfico de cripto (`levels.py`): si un giro
    merece una línea en un gráfico, merece la misma línea en el otro. Lo que
    cambia son los parámetros, medidos sobre acciones (ver
    `STOCK_PIVOT_LOOKAROUND_BARS` en `constants.py`).

    Pocas líneas y cerca del precio, por la razón de siempre: con quince
    siempre hay una cerca, así que el precio siempre parece estar "en un
    nivel" y el gráfico deja de decir nada. El grosor es información — llena
    para las zonas que el precio respetó varias veces, punteada para las de un
    solo toque — y la cantidad de toques va en la etiqueta, así que no hay que
    adivinar por qué una es más gruesa que otra.
    """
    soportes, resistencias = detect_support_resistance(
        df,
        lookaround=STOCK_PIVOT_LOOKAROUND_BARS,
        cluster_pct=STOCK_LEVEL_CLUSTER_PCT,
        per_side=STOCK_LEVELS_PER_SIDE,
    )

    def _dibujar(nivel: PriceLevel, color: str, etiqueta: str) -> None:
        # "×3" y no "(3 toques)": la etiqueta se dibuja fuera del área de
        # trazado, y la versión larga no entraba en el margen derecho sin
        # comerle ancho al gráfico.
        fig.add_hline(
            y=nivel.price,
            line_dash="solid" if nivel.is_strong else "dot",
            line_width=1.6 if nivel.is_strong else 1.0,
            line_color=color,
            opacity=0.75,
            annotation_text=f"{etiqueta} {nivel.price:,.2f} ×{nivel.touches}",
            annotation_position="right",
            annotation_font_size=10,
            annotation_font_color=color,
            row=1,
            col=1,
        )

    for nivel in soportes:
        _dibujar(nivel, COLOR_POSITIVE, "Soporte")
    for nivel in resistencias:
        _dibujar(nivel, COLOR_NEGATIVE, "Resistencia")


def _add_volume_panel(fig: go.Figure, df: pd.DataFrame) -> None:
    """Panel 2: Volumen de operaciones, coloreado según suba (Verde) o baja (Rojo) de la barra."""
    if 'Volume' not in df.columns:
        return
    opens = df['Open'] if 'Open' in df.columns else df['Close']
    colors = [COLOR_POSITIVE if c >= o else COLOR_NEGATIVE for c, o in zip(df['Close'], opens, strict=True)]
    fig.add_trace(
        go.Bar(
            x=df.index, y=df['Volume'],
            name='Volumen',
            marker_color=colors,
            opacity=0.75
        ),
        row=2, col=1
    )


def _add_macd_panel(fig: go.Figure, df: pd.DataFrame, indicators: ChartIndicators) -> None:
    """Panel 3: MACD (Línea, Señal e Histograma)."""
    df_macd = indicators.macd
    hist_colors = [COLOR_POSITIVE if h >= 0 else COLOR_NEGATIVE for h in df_macd['hist']]
    fig.add_trace(
        go.Bar(
            x=df.index, y=df_macd['hist'],
            name='Histograma MACD',
            marker_color=hist_colors,
            opacity=0.65
        ),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df_macd['macd'],
            mode='lines', name='MACD',
            line=dict(color=COLOR_MACD_LINE, width=1.8)
        ),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df_macd['signal'],
            mode='lines', name='Señal (EMA 9)',
            line=dict(color=COLOR_MACD_SIGNAL, width=1.5)
        ),
        row=3, col=1
    )
    fig.add_hline(y=0, line_dash="solid", line_color=COLOR_MACD_ZERO_LINE, line_width=1, row=3, col=1)


def _add_rsi_stochastic_panel(fig: go.Figure, df: pd.DataFrame, indicators: ChartIndicators, suffix: str) -> None:
    """Panel 4: RSI (14) y Oscilador Estocástico (%K, %D) superpuestos con líneas 30/50/70."""
    df_stoch = indicators.stochastic
    fig.add_trace(
        go.Scatter(
            x=df.index, y=indicators.rsi_14,
            mode='lines', name=f'RSI 14 ({suffix})',
            line=dict(color=COLOR_RSI_LINE, width=2.2)
        ),
        row=4, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df_stoch['stoch_k'],
            mode='lines', name='Estocástico %K (14)',
            line=dict(color=COLOR_STOCH_K, width=1.4)
        ),
        row=4, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df_stoch['stoch_d'],
            mode='lines', name='Estocástico %D (3)',
            line=dict(color=COLOR_STOCH_D, width=1.4, dash='dot')
        ),
        row=4, col=1
    )

    # Sin etiquetas sobre las líneas: en un panel de 150 px de alto, "70
    # (Sobrecompra)" se apoya justo donde pasa el estocástico, que llega a 100
    # casi todos los días. Los umbrales se leen en las marcas del eje, que
    # `plot_stock_detail` fija en 0 / 30 / 50 / 70 / 100.
    fig.add_hline(y=70, line_dash="dash", line_color=COLOR_NEGATIVE, line_width=1, row=4, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color=COLOR_REFERENCE_LINE, line_width=1, row=4, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color=COLOR_POSITIVE, line_width=1, row=4, col=1)


def plot_stock_detail(
    df_history: pd.DataFrame,
    indicators: ChartIndicators | None,
    ticker: str,
    company_name: str = "",
    timeframe_label: str = "Diario"
) -> go.Figure:
    """
    Dibuja el gráfico profesional de 4 paneles apilados y sincronizados a partir
    de indicadores YA CALCULADOS (ver `compute_chart_indicators`):
      1. Velas Japonesas (OHLC) + SMA 50 + SMA 200 + Bandas de Bollinger (con
         sombreado) + soportes y resistencias.
      2. Volumen de operaciones (Verde / Rojo).
      3. MACD (Línea, Señal e Histograma).
      4. RSI (14) y Oscilador Estocástico (%K, %D) superpuestos con líneas 30 y 70.
    """
    if indicators is None or df_history.empty or 'Close' not in df_history.columns:
        fig = go.Figure()
        fig.add_annotation(text="No hay datos históricos disponibles para este ticker", showarrow=False)
        return fig

    df = df_history.copy().sort_index()

    is_weekly = "sem" in str(timeframe_label).lower()
    suffix = "Sem" if is_weekly else "Días"

    # Sin `subplot_titles`. Plotly los dibuja como anotaciones pegadas al borde
    # superior de cada panel, así que con cuatro paneles apilados cada título
    # caía dentro del gráfico de arriba, encima de las velas o del MACD. El
    # nombre de cada panel va en el título de su eje Y, que es donde no se
    # superpone con nada; la identificación del papel ya está en la ficha, que
    # es lo que hay inmediatamente arriba de este gráfico.
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.045,
        row_heights=[0.52, 0.12, 0.18, 0.18],
    )

    _add_price_panel(fig, df, indicators, timeframe_label, suffix)
    _add_levels(fig, df)
    _add_volume_panel(fig, df)
    _add_macd_panel(fig, df, indicators)
    _add_rsi_stochastic_panel(fig, df, indicators, suffix)

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        xaxis_rangeslider_visible=False,
        height=860,
        # El izquierdo entra el título del eje (con 40 px, "Precio ($)" salía
        # cortado en "Pr"); el derecho, las etiquetas de los niveles, que se
        # dibujan fuera del área de trazado y decían "Soporte 321,4…"; el
        # inferior, la leyenda.
        margin=dict(l=66, r=128, t=28, b=86),
        # La leyenda va abajo: son once series y arriba ocupaba tres renglones
        # que empujaban los cuatro paneles hacia el fondo de la figura.
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.06,
            xanchor="left",
            x=0,
            font=dict(size=10.5),
            bgcolor="rgba(0,0,0,0)",
        ),
    )

    _aplicar_estilo(fig)
    # En el panel de precio la grilla vertical compite con las velas.
    fig.update_xaxes(showgrid=False)

    fig.update_yaxes(title_text="Precio ($)", row=1, col=1)
    fig.update_yaxes(title_text="Volumen", row=2, col=1)
    fig.update_yaxes(title_text="MACD", row=3, col=1)
    fig.update_yaxes(
        title_text="RSI / Stoch",
        range=[0, 100],
        tickvals=[0, 30, 50, 70, 100],
        row=4, col=1,
    )

    return fig


def plot_valuation_vs_technicals(df: pd.DataFrame, timeframe_label: str = "Diario") -> go.Figure:
    """
    Gráfico de dispersión: Valuación (Forward P/E) vs Momentum (% Dif. SMA 200).
    Color por RSI (14) y tamaño por Market Cap.
    """
    df_clean = df.dropna(subset=['PER Futuro (Forward)', 'DIFF_SMA_200_VAL', 'RSI_VAL']).copy()
    if df_clean.empty:
        fig = go.Figure()
        fig.add_annotation(text="No hay suficientes datos para el gráfico de dispersión", showarrow=False)
        return fig

    mcap = df_clean['Market Cap ($B)'].fillna(50)
    sizes = np.clip(np.sqrt(mcap) * 1.8, 8, 38)

    fig = go.Figure(
        data=go.Scatter(
            x=df_clean['PER Futuro (Forward)'],
            y=df_clean['DIFF_SMA_200_VAL'],
            mode='markers+text',
            text=df_clean['Ticker'],
            textposition="top center",
            textfont=dict(size=10, color=COLOR_SCATTER_LABEL_TEXT),
            marker=dict(
                size=sizes,
                color=df_clean['RSI_VAL'],
                colorscale="Spectral_r",
                showscale=True,
                colorbar=dict(title=f"RSI ({timeframe_label})", thickness=15),
                line=dict(width=1, color=COLOR_SCATTER_MARKER_BORDER)
            ),
            hovertemplate=(
                "<b>%{text}</b> - %{customdata[0]}<br>" +
                "Sector: %{customdata[1]}<br>" +
                "Precio: $%{customdata[2]:.2f} (%{customdata[3]:+.2f}%)<br>" +
                "Señal: %{customdata[6]}<br>" +
                "Forward P/E: %{x:.1f}x<br>" +
                "Trailing P/E: %{customdata[4]:.1f}x<br>" +
                "Hist. Avg P/E: %{customdata[5]:.1f}x<br>" +
                f"Dif. % vs SMA 200 ({timeframe_label}): " + "%{y:+.2f}%<br>" +
                f"RSI 14 ({timeframe_label}): " + "%{marker.color:.1f}<extra></extra>"
            ),
            customdata=df_clean[['Empresa', 'Sector', 'Precio Actual', 'Var. Período (%)', 'PER Pasado (Trailing)', 'PER Prom. Hist. (5A)', 'Semáforo']].values
        )
    )

    fig.add_hline(y=0, line_dash="dash", line_color=COLOR_SCATTER_REFERENCE_LINE)
    median_fpe = df_clean['PER Futuro (Forward)'].median()
    fig.add_vline(x=median_fpe, line_dash="dash", line_color=COLOR_SCATTER_REFERENCE_LINE)

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        xaxis_title="PER futuro — menor es más barato",
        yaxis_title=f"% vs media de 200 ({timeframe_label.lower()}) — mayor es más impulso",
        height=580,
        margin=dict(l=56, r=40, t=24, b=46)
    )
    _aplicar_estilo(fig)
    return fig


def plot_pe_comparison_bar(df: pd.DataFrame, max_items: int = 25) -> go.Figure:
    """
    Gráfico de barras comparativo: PER Pasado (Trailing) vs PER Futuro (Forward) vs PER Histórico Promedio.
    """
    df_clean = df.dropna(subset=['PER Pasado (Trailing)', 'PER Futuro (Forward)']).copy()
    if df_clean.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos suficientes de PER", showarrow=False)
        return fig

    df_clean = df_clean.sort_values(by='Market Cap ($B)', ascending=False).head(max_items)

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name='PER Pasado (Trailing)',
            x=df_clean['Ticker'],
            y=df_clean['PER Pasado (Trailing)'],
            marker_color=COLOR_PE_TRAILING
        )
    )
    fig.add_trace(
        go.Bar(
            name='PER Futuro (Forward)',
            x=df_clean['Ticker'],
            y=df_clean['PER Futuro (Forward)'],
            marker_color=COLOR_PE_FORWARD
        )
    )
    if 'PER Prom. Hist. (5A)' in df_clean.columns:
        fig.add_trace(
            go.Bar(
                name='PER Prom. Hist. (5A)',
                x=df_clean['Ticker'],
                y=df_clean['PER Prom. Hist. (5A)'],
                marker_color=COLOR_PE_HISTORICAL_AVG
            )
        )

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        barmode='group',
        xaxis_title="",
        yaxis_title="PER (veces)",
        height=480,
        margin=dict(l=56, r=40, t=36, b=40),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
            font=dict(size=10.5), bgcolor="rgba(0,0,0,0)",
        )
    )
    _aplicar_estilo(fig)
    return fig


def plot_sma_distances_bar(df: pd.DataFrame, timeframe_label: str = "Diario") -> go.Figure:
    """
    Gráfico de barras horizontal ordenado por distancia a la SMA 200.
    """
    df_clean = df.dropna(subset=['DIFF_SMA_200_VAL']).sort_values(by='DIFF_SMA_200_VAL', ascending=True)
    if df_clean.empty:
        fig = go.Figure()
        return fig

    colors = [COLOR_POSITIVE if val >= 0 else COLOR_NEGATIVE for val in df_clean['DIFF_SMA_200_VAL']]

    fig = go.Figure(
        go.Bar(
            x=df_clean['DIFF_SMA_200_VAL'],
            y=df_clean['Ticker'],
            orientation='h',
            marker_color=colors,
            text=[f"{v:+.1f}%" for v in df_clean['DIFF_SMA_200_VAL']],
            textposition="outside",
            hovertemplate=f"<b>%{{y}}</b>: %{{x:+.2f}}% vs SMA 200 ({timeframe_label})<extra></extra>"
        )
    )

    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        xaxis_title=f"% vs media de 200 ({timeframe_label.lower()})",
        yaxis_title="",
        height=max(500, len(df_clean) * 20),
        margin=dict(l=60, r=64, t=24, b=44)
    )
    _aplicar_estilo(fig)
    return fig
