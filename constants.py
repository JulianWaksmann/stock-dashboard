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
