"""
components/charts.py - Gráficos interactivos con Plotly (4 paneles apilados sincronizados según John Murphy)
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from indicators import (
    compute_bollinger_bands,
    compute_macd,
    compute_rsi,
    compute_sma,
    compute_stochastic,
)
from theme import (
    COLOR_BOLLINGER_BAND,
    COLOR_BOLLINGER_FILL,
    COLOR_BOLLINGER_MID,
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

    fig.add_hline(y=70, line_dash="dash", line_color=COLOR_NEGATIVE, row=4, col=1, annotation_text="70 (Sobrecompra)", annotation_position="top right")
    fig.add_hline(y=50, line_dash="dot", line_color=COLOR_REFERENCE_LINE, row=4, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color=COLOR_POSITIVE, row=4, col=1, annotation_text="30 (Sobreventa)", annotation_position="bottom right")


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
      1. Velas Japonesas (OHLC) + SMA 50 + SMA 200 + Bandas de Bollinger (con sombreado).
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

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.50, 0.12, 0.19, 0.19],
        subplot_titles=(
            f"{ticker} - {company_name} | {timeframe_label}: Velas, SMAs (50, 200) y Bollinger",
            "Volumen",
            "MACD (12, 26, 9)",
            f"RSI 14 y Estocástico (%K, %D) [{suffix}]"
        )
    )

    _add_price_panel(fig, df, indicators, timeframe_label, suffix)
    _add_volume_panel(fig, df)
    _add_macd_panel(fig, df, indicators)
    _add_rsi_stochastic_panel(fig, df, indicators, suffix)

    fig.update_layout(
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        height=900,
        margin=dict(l=40, r=40, t=50, b=30),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1
        )
    )
    fig.update_yaxes(title_text="Precio ($)", row=1, col=1)
    fig.update_yaxes(title_text="Volumen", row=2, col=1)
    fig.update_yaxes(title_text="MACD", row=3, col=1)
    fig.update_yaxes(title_text="RSI / Stoch", range=[0, 100], row=4, col=1)

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
            customdata=df_clean[['Empresa', 'Sector', 'Precio Actual', 'Var. Período (%)', 'PER Pasado (Trailing)', 'PER Prom. Hist. (5A)', 'Señal Confluencia']].values
        )
    )

    fig.add_hline(y=0, line_dash="dash", line_color=COLOR_SCATTER_REFERENCE_LINE)
    median_fpe = df_clean['PER Futuro (Forward)'].median()
    fig.add_vline(x=median_fpe, line_dash="dash", line_color=COLOR_SCATTER_REFERENCE_LINE)

    fig.update_layout(
        template="plotly_dark",
        title=f"<b>Valuación vs Momentum Macro ({timeframe_label})</b> (Forward P/E vs % Distancia a SMA 200)",
        xaxis_title="PER Futuro (Forward P/E) — Menor = Valuación más atractiva",
        yaxis_title=f"% Distancia a Media 200 ({timeframe_label}) — Mayor = Mayor Momentum",
        height=580,
        margin=dict(l=40, r=40, t=60, b=40)
    )
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
        template="plotly_dark",
        barmode='group',
        title="<b>Comparativa PER: Pasado vs Futuro vs Promedio Histórico (5 Años)</b>",
        xaxis_title="Acción (Ticker)",
        yaxis_title="Ratio P/E (Veces)",
        height=480,
        margin=dict(l=40, r=40, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
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
        template="plotly_dark",
        title=f"<b>Ranking: % Distancia respecto a Media Móvil de 200 ({timeframe_label})</b>",
        xaxis_title=f"% Desviación de SMA 200 ({timeframe_label})",
        yaxis_title="Ticker",
        height=max(500, len(df_clean) * 20),
        margin=dict(l=60, r=60, t=50, b=40)
    )
    return fig
