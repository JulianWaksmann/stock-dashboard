"""
theme.py - Paleta de colores y helpers visuales centralizados del dashboard.

Antes de este archivo, el concepto "positivo/negativo" se representaba con
TRES pares de verde/rojo distintos y sin relación entre sí:
  - #22c55e / #ef4444  en components/screener_table.py (estilos de tabla)
  - #26a69a / #ef5350  en components/charts.py (velas y volumen)
  - #66BB6A / #EF5350  en components/charts.py (barras de ranking)

Se unifica todo en el par #26a69a (verde) / #ef5350 (rojo), el usado en los
gráficos de velas: es la convención estándar de plataformas de trading
(TradingView, etc.) para subas/bajas, tiene mejor contraste que #22c55e/
#66BB6A sobre el fondo oscuro de `template="plotly_dark"` que usa todo
`charts.py`, y ya convivía con la tabla (Streamlit) sin quejas de legibilidad.
Adoptarlo como único par evita que la misma señal (positivo/negativo) se lea
con distinta intensidad de color según el componente que la muestre.
"""

from typing import Final

# ----------------------------------------------------------------------
# Paleta semántica positivo/negativo/neutro (única fuente de verdad visual)
# ----------------------------------------------------------------------
COLOR_POSITIVE: Final[str] = "#26a69a"
COLOR_NEGATIVE: Final[str] = "#ef5350"
COLOR_NEUTRAL: Final[str] = "#9ca3af"

# Variantes para fondos/textos de celdas resaltadas (tabla del screener).
# Se mantiene la intensidad ya usada en pantalla; solo se centraliza acá.
COLOR_POSITIVE_BG: Final[str] = "#052e16"
COLOR_POSITIVE_TEXT_STRONG: Final[str] = "#4ade80"
COLOR_POSITIVE_BG_MODERATE: Final[str] = "#064e3b"
COLOR_POSITIVE_TEXT_MODERATE: Final[str] = "#86efac"
COLOR_NEGATIVE_BG: Final[str] = "#450a0a"
COLOR_NEGATIVE_TEXT_STRONG: Final[str] = "#f87171"
COLOR_NEGATIVE_BG_MODERATE: Final[str] = "#431407"
COLOR_NEGATIVE_TEXT_MODERATE: Final[str] = "#fdba74"
COLOR_SQUEEZE_BG: Final[str] = "#422006"
COLOR_SQUEEZE_TEXT: Final[str] = "#fde047"

# ----------------------------------------------------------------------
# Colores puntuales de los gráficos (indicadores, líneas de referencia, etc.)
# No representan positivo/negativo, así que no forman parte del par arriba.
# ----------------------------------------------------------------------
COLOR_PRICE_LINE: Final[str] = "#2962FF"
COLOR_SMA_50: Final[str] = "#29B6F6"
COLOR_SMA_200: Final[str] = "#AB47BC"
COLOR_BOLLINGER_BAND: Final[str] = "rgba(150, 160, 180, 0.4)"
COLOR_BOLLINGER_FILL: Final[str] = "rgba(100, 120, 160, 0.05)"
COLOR_BOLLINGER_MID: Final[str] = "rgba(255, 167, 38, 0.6)"
COLOR_MACD_LINE: Final[str] = "#2962FF"
COLOR_MACD_SIGNAL: Final[str] = "#FF6D00"
COLOR_MACD_ZERO_LINE: Final[str] = "#555555"
COLOR_RSI_LINE: Final[str] = "#FFD54F"
COLOR_STOCH_K: Final[str] = "#00E5FF"
COLOR_STOCH_D: Final[str] = "#E040FB"
COLOR_REFERENCE_LINE: Final[str] = "#666666"
COLOR_PE_TRAILING: Final[str] = "#42A5F5"
COLOR_PE_FORWARD: Final[str] = "#66BB6A"
COLOR_PE_HISTORICAL_AVG: Final[str] = "#FFA726"
