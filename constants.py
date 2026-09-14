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

# ======================================================================
# BONOS CORPORATIVOS ARGENTINOS (OBLIGACIONES NEGOCIABLES)
#
# Mismo criterio que arriba: las etiquetas y umbrales del panel de ONs
# viven acá para que el motor (`bonds/scoring.py`), la tabla
# (`components/bonds_table.py`) y los filtros (`components/bonds_panel.py`)
# lean siempre el mismo texto y el mismo número.
# ======================================================================

# ----------------------------------------------------------------------
# Etiquetas de atractivo de una ON (columna "Atractivo")
# ----------------------------------------------------------------------
BOND_SIGNAL_VERY_ATTRACTIVE: Final[str] = "🌟 MUY ATRACTIVO"
BOND_SIGNAL_ATTRACTIVE: Final[str] = "🟢 ATRACTIVO"
BOND_SIGNAL_NEUTRAL: Final[str] = "🟡 NEUTRAL"
BOND_SIGNAL_LOW: Final[str] = "🟠 POCO ATRACTIVO"
BOND_SIGNAL_RISK: Final[str] = "🚨 ALERTA DE RIESGO"
BOND_SIGNAL_NO_DATA: Final[str] = "⚪ SIN DATOS"

BOND_ATTRACTIVE_SIGNALS: Final[tuple[str, ...]] = (
    BOND_SIGNAL_VERY_ATTRACTIVE,
    BOND_SIGNAL_ATTRACTIVE,
)

# ----------------------------------------------------------------------
# Umbrales del scoring de ONs (evaluate_bond_attractiveness)
#
# A diferencia de las acciones, un bono no se puntúa contra su propio
# pasado sino **contra sus pares**: la referencia de todos los umbrales de
# rendimiento es la mediana de TIR del panel del día. Esa mediana se mueve
# con el riesgo argentino, así que un umbral absoluto ("TIR > 9%") diría
# cosas opuestas en dos momentos distintos del ciclo.
# ----------------------------------------------------------------------

# Premio de rendimiento: cuánta TIR por encima de la mediana del panel hay
# que ofrecer para que el bono sume el punto de "rinde más que sus pares".
BOND_YIELD_PREMIUM_PP: Final[float] = 1.0

# Alerta de riesgo: una TIR tan por encima de la mediana no es una
# oportunidad, es el mercado descontando estrés crediticio del emisor.
# Se etiqueta aparte para que no se cuele como "muy atractivo".
BOND_RISK_YIELD_PREMIUM_PP: Final[float] = 8.0

# Riesgo de tasa acotado: duration modificada por debajo de este valor
# (en años) significa que una suba de 1 pp en la tasa de descuento pega
# menos de ~3% en el precio.
BOND_SHORT_DURATION_MAX_YEARS: Final[float] = 3.0

# Cotizar bajo la par (paridad < 100) implica que parte del retorno llega
# como ganancia de capital al vencimiento y no solo vía cupón.
BOND_PARITY_DISCOUNT_MAX: Final[float] = 100.0

# Liquidez: spread entre punta compradora y vendedora, en % del punto
# medio. Por encima de este valor, entrar y salir se come el rendimiento.
BOND_LIQUID_SPREAD_MAX_PCT: Final[float] = 1.0

# ----------------------------------------------------------------------
# Opciones de los filtros de la pestaña de Bonos
# ----------------------------------------------------------------------

# --- Filtro por Atractivo ---
BOND_FILTER_SIGNAL_ALL: Final[str] = "Todas las ONs"
BOND_FILTER_SIGNAL_ATTRACTIVE: Final[str] = "🟢 Solo Atractivas (Muy + Atractivo)"
BOND_FILTER_SIGNAL_VERY_ATTRACTIVE: Final[str] = "🌟 Solo Muy Atractivas"
BOND_FILTER_SIGNAL_RISK: Final[str] = "🚨 Solo Alertas de Riesgo"

BOND_SIGNAL_FILTER_OPTIONS: Final[tuple[str, ...]] = (
    BOND_FILTER_SIGNAL_ALL,
    BOND_FILTER_SIGNAL_ATTRACTIVE,
    BOND_FILTER_SIGNAL_VERY_ATTRACTIVE,
    BOND_FILTER_SIGNAL_RISK,
)

# --- Filtro por Ley aplicable ---
BOND_FILTER_LAW_ALL: Final[str] = "Todas las leyes"
BOND_FILTER_LAW_NY: Final[str] = "🇺🇸 Solo Ley Nueva York"
BOND_FILTER_LAW_ARG: Final[str] = "🇦🇷 Solo Ley Argentina"

BOND_LAW_FILTER_OPTIONS: Final[tuple[str, ...]] = (
    BOND_FILTER_LAW_ALL,
    BOND_FILTER_LAW_NY,
    BOND_FILTER_LAW_ARG,
)

# --- Selector de convención de precio ---
# BYMA publica los precios de renta fija "sucios" (con el interés corrido
# incluido). El selector existe porque no todas las fuentes siguen esa
# convención, y confundirlas sesga la TIR y la paridad de forma silenciosa.
BOND_PRICE_DIRTY: Final[str] = "Sucio (incluye interés corrido) — BYMA"
BOND_PRICE_CLEAN: Final[str] = "Limpio (sin interés corrido)"

BOND_PRICE_CONVENTION_OPTIONS: Final[tuple[str, ...]] = (
    BOND_PRICE_DIRTY,
    BOND_PRICE_CLEAN,
)

# ----------------------------------------------------------------------
# Secciones del tablero (selector superior de app.py)
#
# Es un selector y no `st.tabs` porque Streamlit ejecuta el cuerpo de todas
# las pestañas en cada corrida: con pestañas nativas, mirar acciones
# dispararía igual la descarga de precios de ONs. Con el selector, cada
# sección consulta sus fuentes recién cuando se la elige.
# ----------------------------------------------------------------------
SECTION_STOCKS: Final[str] = "📈 Acciones (Confluencia & Smart Money)"
SECTION_BONDS: Final[str] = "💵 Bonos Corporativos Argentinos (ONs)"

SECTION_OPTIONS: Final[tuple[str, ...]] = (SECTION_STOCKS, SECTION_BONDS)

# ----------------------------------------------------------------------
# Especies de liquidación de una ON.
#
# En BYMA un mismo bono cotiza en tres especies distintas, identificadas por
# la última letra del ticker: O liquida en pesos, D en dólar MEP y C en dólar
# cable. YMCJO, YMCJD e YMCJC son la MISMA obligación negociable de YPF; lo
# que cambia es en qué moneda se paga y, por lo tanto, en qué moneda está
# expresado el precio de pantalla (YMCJO cotiza ~152.000 pesos donde YMCJD
# cotiza ~105 dólares).
#
# Esto no es cosmético: descontar el flujo en dólares de la ON contra un
# precio en pesos devuelve una TIR sin ningún sentido económico. Por eso el
# panel calcula rendimientos solo cuando la moneda de la especie coincide
# con la moneda de emisión del bono.
# ----------------------------------------------------------------------
BOND_SETTLEMENT_PESOS: Final[str] = "🇦🇷 Pesos"
BOND_SETTLEMENT_MEP: Final[str] = "💵 MEP"
BOND_SETTLEMENT_CABLE: Final[str] = "🌎 Cable"
BOND_SETTLEMENT_UNKNOWN: Final[str] = "—"

# Última letra del ticker -> especie de liquidación.
BOND_SETTLEMENT_BY_SUFFIX: Final[dict[str, str]] = {
    "O": BOND_SETTLEMENT_PESOS,
    "D": BOND_SETTLEMENT_MEP,
    "C": BOND_SETTLEMENT_CABLE,
}

# Especie de liquidación -> moneda en la que está expresado el precio.
BOND_SETTLEMENT_CURRENCY: Final[dict[str, str]] = {
    BOND_SETTLEMENT_PESOS: "ARS",
    BOND_SETTLEMENT_MEP: "USD",
    BOND_SETTLEMENT_CABLE: "USD",
}

# --- Filtro por especie de liquidación ---
BOND_FILTER_SETTLEMENT_ALL: Final[str] = "Todas las especies"
BOND_FILTER_SETTLEMENT_USD: Final[str] = "💵 Solo dólares (MEP + Cable)"
BOND_FILTER_SETTLEMENT_MEP: Final[str] = "💵 Solo MEP"
BOND_FILTER_SETTLEMENT_PESOS: Final[str] = "🇦🇷 Solo pesos"

BOND_SETTLEMENT_FILTER_OPTIONS: Final[tuple[str, ...]] = (
    BOND_FILTER_SETTLEMENT_USD,
    BOND_FILTER_SETTLEMENT_MEP,
    BOND_FILTER_SETTLEMENT_PESOS,
    BOND_FILTER_SETTLEMENT_ALL,
)
