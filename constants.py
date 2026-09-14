"""
constants.py - Fuente única de verdad para las etiquetas del Algoritmo de
Confluencia por Sistema de Grados y para los umbrales numéricos que definen
sus reglas de negocio.

Estas constantes existen para que `indicators.py` (donde se generan las
etiquetas y se aplican los umbrales) y `app.py` (donde se filtran) nunca se
desincronicen: si el texto de una etiqueta cambia acá, cambia en todos lados
a la vez, y si un umbral se ajusta, queda documentado en un solo lugar.

IMPORTANTE: los valores de las etiquetas son literales de string EXACTOS
(incluyendo emojis y espacios) que ya se usaban en el código y en los
DataFrames existentes. No modificar su contenido sin migrar también los
datos ya generados.
"""

from typing import Final

# ----------------------------------------------------------------------
# Etiquetas de señal de confluencia (columna "Semáforo")
# ----------------------------------------------------------------------
SIGNAL_STRONG_BUY: Final[str] = "🌟 COMPRA FUERTE"
SIGNAL_MODERATE_BUY: Final[str] = "🟢 COMPRA MODERADA"
SIGNAL_MODERATE_SELL: Final[str] = "🟠 VENTA MODERADA"
SIGNAL_STRONG_SELL: Final[str] = "🚨 VENTA FUERTE / ROTAR"
SIGNAL_NEUTRAL: Final[str] = "🟡 NEUTRAL"
SIGNAL_SQUEEZE: Final[str] = "🚨 SQUEEZE"

# Agrupaciones útiles para filtros (evitan enumerar literales sueltos)
BUY_SIGNALS: Final[tuple[str, ...]] = (SIGNAL_STRONG_BUY, SIGNAL_MODERATE_BUY)
SELL_SIGNALS: Final[tuple[str, ...]] = (SIGNAL_STRONG_SELL, SIGNAL_MODERATE_SELL)

# ----------------------------------------------------------------------
# Etiquetas de flujo institucional / Smart Money (columna "Flujo Institucional")
# ----------------------------------------------------------------------
FLOW_ACCUMULATION: Final[str] = "🐳 Acumulación"
FLOW_DISTRIBUTION: Final[str] = "📉 Distribución"
FLOW_NOT_AVAILABLE: Final[str] = "N/A"

# ----------------------------------------------------------------------
# Umbrales numéricos del Algoritmo de Confluencia (evaluate_confluence_signal)
# ----------------------------------------------------------------------

# --- Lado COMPRA ---

# Condición 1: tendencia de fondo alcista. Además de SMA 50 > SMA 200, se
# tolera que el precio esté hasta un 5% por debajo de la SMA 200 (no exige
# que la supere estrictamente) para seguir contando la tendencia como sana.
BUY_SMA200_TREND_TOLERANCE: Final[float] = 0.95

# Condición 2 (obligatoria): banda de soporte alrededor de la SMA 50.
# Se considera "cerca del soporte" si el precio está a +/- 4% de la SMA 50.
BUY_SMA50_PROXIMITY_PCT: Final[float] = 4.0

# Condición 2 (obligatoria, camino alternativo): tolerancia sobre la Banda
# Inferior de Bollinger. Se admite el precio hasta un 1% por encima de la
# banda inferior (no exige que la perfore) como señal de soporte.
BUY_BB_LOWER_TOLERANCE: Final[float] = 1.01

# Condición 3 (obligatoria): sobreventa aliviada. RSI por debajo de este
# valor habilita el lado comprador.
BUY_RSI_MAX: Final[float] = 45.0

# Condición 4: gatillo de momento por Estocástico. %K por debajo de este
# valor se considera zona de sobreventa que dispara la señal de compra.
BUY_STOCH_K_OVERSOLD: Final[float] = 30.0

# --- Lado VENTA / ROTACIÓN ---

# Condición 1 (obligatoria): proximidad al techo. Se exige que la distancia
# al máximo de 52 semanas sea mayor o igual a este valor (negativo), es
# decir, que el precio esté a menos de 6% del máximo de 52 semanas.
SELL_DIST_52W_HIGH_MIN_PCT: Final[float] = -6.0

# Condición 2 (obligatoria): sobrecompra. RSI por encima de este valor
# habilita el lado vendedor.
SELL_RSI_MIN: Final[float] = 65.0

# Condición 3: pérdida de momento por Estocástico. %K en o por encima de
# este valor se considera zona de sobrecompra que aporta punto de venta.
SELL_STOCH_K_OVERBOUGHT: Final[float] = 80.0

# --- Squeeze (compresión de volatilidad) ---

# Ventana de referencia para el mínimo de Bandwidth de Bollinger: 126 ruedas
# equivalen aproximadamente a 6 meses de operatoria diaria (21 ruedas/mes).
SQUEEZE_LOOKBACK_BARS: Final[int] = 126

# Tolerancia sobre el mínimo de Bandwidth de la ventana: se considera
# squeeze si el Bandwidth actual está hasta un 8% por encima del mínimo
# de los últimos 6 meses (no exige que sea el mínimo exacto).
SQUEEZE_BANDWIDTH_TOLERANCE: Final[float] = 1.08

# ----------------------------------------------------------------------
# Opciones de los selectores de filtros en app.py.
#
# Cada selector define su lista de opciones y luego compara la opción
# elegida contra ese mismo texto en un if/elif. Si esos textos se escriben
# como literales sueltos en dos lugares distintos, alcanza con editar uno
# y olvidarse del otro para que el filtro deje de funcionar en silencio
# (sin ningún error). Centralizar el texto acá evita esa desincronización:
# la definición del selector y la comparación siempre leen la misma fuente.
# ----------------------------------------------------------------------

# --- Filtro por Semáforo (Sistema de Grados) ---
FILTER_SIGNAL_ALL: Final[str] = "Todas las Acciones"
FILTER_SIGNAL_STRONG_BUY: Final[str] = "🌟 Solo Compra Fuerte"
FILTER_SIGNAL_BUY: Final[str] = "🟢 Solo Compras (Fuerte + Moderada)"
FILTER_SIGNAL_SELL: Final[str] = "🚨 Solo Venta / Rotar (Fuerte + Moderada)"
FILTER_SIGNAL_SQUEEZE: Final[str] = "⚡ Solo Squeezes"

SIGNAL_FILTER_OPTIONS: Final[tuple[str, ...]] = (
    FILTER_SIGNAL_ALL,
    FILTER_SIGNAL_STRONG_BUY,
    FILTER_SIGNAL_BUY,
    FILTER_SIGNAL_SELL,
    FILTER_SIGNAL_SQUEEZE,
)

# --- Filtro por Flujo Institucional / Smart Money (OBV) ---
FILTER_FLOW_ALL: Final[str] = "Todos los Flujos"
FILTER_FLOW_ACCUMULATION: Final[str] = "🐳 Solo Acumulación (OBV > SMA 20)"
FILTER_FLOW_DISTRIBUTION: Final[str] = "📉 Solo Distribución (OBV < SMA 20)"

FLOW_FILTER_OPTIONS: Final[tuple[str, ...]] = (
    FILTER_FLOW_ALL,
    FILTER_FLOW_ACCUMULATION,
    FILTER_FLOW_DISTRIBUTION,
)

# --- Filtro por Tendencia vs SMA 200 ---
FILTER_SMA200_ALL: Final[str] = "Todos"
FILTER_SMA200_BULLISH: Final[str] = "Solo Alcistas (> SMA 200)"
FILTER_SMA200_BEARISH: Final[str] = "Solo Bajistas (< SMA 200)"

SMA200_FILTER_OPTIONS: Final[tuple[str, ...]] = (
    FILTER_SMA200_ALL,
    FILTER_SMA200_BULLISH,
    FILTER_SMA200_BEARISH,
)

# --- Selector de Temporalidad (Diario vs Semanal) ---
TIMEFRAME_CHOICE_DAILY: Final[str] = "☀️ Diario (1D)"
TIMEFRAME_CHOICE_WEEKLY: Final[str] = "📅 Semanal (1W)"

TIMEFRAME_CHOICE_OPTIONS: Final[tuple[str, ...]] = (
    TIMEFRAME_CHOICE_DAILY,
    TIMEFRAME_CHOICE_WEEKLY,
)

# --- Selector de Mercado ---
MARKET_USA_STOCKS: Final[str] = "Acciones USA (S&P 500)"
MARKET_CRYPTO: Final[str] = "Criptomonedas"
MARKET_ARGENTINA: Final[str] = "Acciones Argentinas (Merval)"

MARKET_OPTIONS: Final[tuple[str, ...]] = (
    MARKET_USA_STOCKS,
    MARKET_CRYPTO,
    MARKET_ARGENTINA,
)
