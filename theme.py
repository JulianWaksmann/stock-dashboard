"""
theme.py - Paleta de colores y helpers visuales centralizados del dashboard.

Antes de este archivo, el concepto "positivo/negativo" se representaba con
TRES pares de verde/rojo distintos y sin relación entre sí:
  - #22c55e / #ef4444  en components/screener_table.py (estilos de tabla)
  - #26a69a / #ef5350  en components/charts.py (velas y volumen)
  - #66BB6A / #EF5350  en components/charts.py (barras de ranking)

Se unifica todo en el par #26a69a (verde) / #ef5350 (rojo), el de los gráficos
de velas: es la convención estándar de plataformas de trading (TradingView,
etc.) para subas/bajas, y la misma señal se lee con la misma intensidad en la
tabla y en el gráfico.

**El tablero se dibuja sobre fondo claro.** No es una preferencia estética
suelta: condiciona cada valor de este archivo. Un color pensado para fondo
oscuro (un amarillo pálido, un cian neón) desaparece sobre blanco, así que las
líneas de los indicadores y los fondos de celda resaltada se eligieron contra
#ffffff, no contra #0b0f14. Si alguna vez se vuelve al modo oscuro hay que
revisar este archivo entero, `PLOTLY_TEMPLATE` y `.streamlit/config.toml`
juntos: ninguno de los tres se sostiene solo.

La carcasa es **violeta sobre lavanda**, tomada de la landing del producto. El
cambio desde el verde anterior no es cosmético: cuando la marca era verde
compartía familia con `COLOR_POSITIVE`, y una pestaña activa o un botón se
leían como "suba". Un violeta no significa nada en una tabla de precios, así
que la carcasa y el dato dejaron de competir.
"""

from typing import Final

# ----------------------------------------------------------------------
# Paleta semántica positivo/negativo/neutro (única fuente de verdad visual)
# ----------------------------------------------------------------------
COLOR_POSITIVE: Final[str] = "#26a69a"
COLOR_NEGATIVE: Final[str] = "#ef5350"
COLOR_NEUTRAL: Final[str] = "#6b7280"

# Variantes para fondos/textos de celdas resaltadas (tablas).
# Fondo tenue + texto saturado: sobre blanco, el resaltado tiene que ser un
# tinte, no un bloque de color, o la tabla se vuelve ilegible de lejos.
COLOR_POSITIVE_BG: Final[str] = "#d9f2e6"
COLOR_POSITIVE_TEXT_STRONG: Final[str] = "#0b6b4a"
COLOR_POSITIVE_BG_MODERATE: Final[str] = "#edf8f2"
COLOR_POSITIVE_TEXT_MODERATE: Final[str] = "#15855a"
COLOR_NEGATIVE_BG: Final[str] = "#fde2e1"
COLOR_NEGATIVE_TEXT_STRONG: Final[str] = "#b42318"
COLOR_NEGATIVE_BG_MODERATE: Final[str] = "#fef0e6"
COLOR_NEGATIVE_TEXT_MODERATE: Final[str] = "#b54708"
COLOR_SQUEEZE_BG: Final[str] = "#fdf3d4"
COLOR_SQUEEZE_TEXT: Final[str] = "#8a6100"

# ----------------------------------------------------------------------
# Colores puntuales de los gráficos (indicadores, líneas de referencia, etc.)
# No representan positivo/negativo, así que no forman parte del par arriba.
# ----------------------------------------------------------------------
PLOTLY_TEMPLATE: Final[str] = "plotly_white"

# La SMA 200 era violeta (#9333ea) desde antes de que la marca lo fuera. Con
# la carcasa en #5b3fe4 las dos se confundían dentro del mismo gráfico, así que
# pasó a magenta: sigue siendo la línea lenta y ya no parece parte del chrome.
COLOR_PRICE_LINE: Final[str] = "#2962FF"
COLOR_SMA_50: Final[str] = "#0284c7"
COLOR_SMA_200: Final[str] = "#be185d"
COLOR_BOLLINGER_BAND: Final[str] = "rgba(100, 116, 139, 0.35)"
COLOR_BOLLINGER_FILL: Final[str] = "rgba(100, 116, 139, 0.06)"
COLOR_BOLLINGER_MID: Final[str] = "rgba(217, 119, 6, 0.65)"
COLOR_MACD_LINE: Final[str] = "#2962FF"
COLOR_MACD_SIGNAL: Final[str] = "#ea580c"
COLOR_MACD_ZERO_LINE: Final[str] = "#94a3b8"
COLOR_RSI_LINE: Final[str] = "#b45309"
COLOR_STOCH_K: Final[str] = "#0891b2"
COLOR_STOCH_D: Final[str] = "#c026d3"
COLOR_REFERENCE_LINE: Final[str] = "#94a3b8"

# Grilla de los gráficos. Lleva el tinte lavanda de la carcasa en vez del gris
# neutro de `plotly_white`: sobre el fondo del tablero, un gris puro se ve
# sucio, y la grilla tiene que quedar por detrás de las velas, no competir.
COLOR_CHART_GRID: Final[str] = "rgba(91, 63, 228, 0.10)"
COLOR_PE_TRAILING: Final[str] = "#2563eb"
COLOR_PE_FORWARD: Final[str] = "#16a34a"
COLOR_PE_HISTORICAL_AVG: Final[str] = "#ea580c"

# Dispersión Valuación vs Momentum (plot_valuation_vs_technicals).
# La etiqueta iba en blanco porque el lienzo era negro; sobre blanco tiene que
# ser el texto el oscuro y el borde del punto el claro, o el nombre del ticker
# se pierde contra el fondo.
COLOR_SCATTER_LABEL_TEXT: Final[str] = "#1f2937"
COLOR_SCATTER_MARKER_BORDER: Final[str] = "#ffffff"
COLOR_SCATTER_REFERENCE_LINE: Final[str] = "#94a3b8"

# ----------------------------------------------------------------------
# Identidad visual del tablero (chrome: cabecera, tarjetas, navegación)
# ----------------------------------------------------------------------
# El violeta de marca no pertenece a ninguna escala de dato: ningún número de
# una tabla de precios es violeta. Esa es exactamente la razón de elegirlo.
# Regla: `COLOR_BRAND*` solo en la carcasa (cabecera, botones, navegación,
# bordes); nunca para representar el signo de un número, que es trabajo de
# `COLOR_POSITIVE` / `COLOR_NEGATIVE`.
COLOR_BRAND: Final[str] = "#5b3fe4"
COLOR_BRAND_STRONG: Final[str] = "#4328cd"
COLOR_BRAND_LIGHT: Final[str] = "#8b6dff"
COLOR_BRAND_SOFT: Final[str] = "rgba(91, 63, 228, 0.10)"
COLOR_BRAND_BORDER: Final[str] = "rgba(91, 63, 228, 0.26)"

# Superficies y texto. Blanco de lienzo y un lavanda muy tenue para las zonas
# que tienen que separarse (barra de controles, cabeceras de tabla); sombra
# suave en vez de borde marcado, porque sobre claro el borde duro ensucia y la
# sombra ordena. La sombra lleva el tinte de la marca: una sombra gris neutra
# sobre lavanda se ve sucia, una violeta se ve apoyada.
COLOR_BACKGROUND: Final[str] = "#ffffff"
COLOR_SURFACE: Final[str] = "#ffffff"
COLOR_SURFACE_ALT: Final[str] = "#f5f3ff"
COLOR_BORDER: Final[str] = "rgba(91, 63, 228, 0.14)"
COLOR_SHADOW: Final[str] = "rgba(49, 27, 140, 0.10)"
COLOR_TEXT: Final[str] = "#15132b"
COLOR_TEXT_MUTED: Final[str] = "#5a5775"

# Radio de esquina y tipografía, para que tarjetas, botones y controles no
# redondeen cada uno por su cuenta. Los controles son pastillas completas
# (999px) y no rectángulos apenas redondeados: es lo que distingue la carcasa
# de la landing del aspecto por omisión de Streamlit.
RADIUS_CARD: Final[str] = "22px"
RADIUS_CONTROL: Final[str] = "999px"

# Dos familias con trabajos distintos: la de display titula y la de texto se
# lee. Mezclarlas en un solo token obligaba a cada panel a elegir, y elegían
# distinto. Ninguna de las dos se usa para números en columna: para eso están
# las cifras tabulares, que el CSS global activa en tablas y métricas.
FONT_FAMILY: Final[str] = (
    "'Plus Jakarta Sans', 'Segoe UI', system-ui, -apple-system, sans-serif"
)
FONT_FAMILY_DISPLAY: Final[str] = (
    "'Outfit', 'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif"
)
