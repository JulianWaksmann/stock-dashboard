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
BOND_SIGNAL_VERY_SHORT: Final[str] = "⏳ MUY CORTO"

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

# Vida residual mínima para calificar una ON, en años. Por debajo de este
# plazo la TIR sigue siendo correcta pero deja de ser comparable: anualizar
# el retorno de tres semanas convierte un centavo de diferencia de precio en
# decenas de puntos de "rendimiento". Esos bonos se etiquetan aparte y se
# excluyen de la mediana del panel, para no arrastrar la referencia contra la
# que se mide todo el resto ni disparar falsas alertas de riesgo.
BOND_MIN_YEARS_FOR_GRADING: Final[float] = 0.25

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
SECTION_BONDS: Final[str] = "💵 Bonos Corporativos"

SECTION_OPTIONS: Final[tuple[str, ...]] = (SECTION_STOCKS, SECTION_BONDS)

# ----------------------------------------------------------------------
# País del panel de bonos corporativos (desplegable de la barra lateral).
#
# El país no es una etiqueta cosmética: define la fuente de precios, las
# convenciones de cálculo y el catálogo de emisiones. Hoy solo Argentina
# está implementada (BYMA + ONs en dólares); el resto figura acá para que
# el desplegable exponga el rumbo y para que el día que se sume un país
# nuevo el punto de extensión ya esté donde corresponde: una rama por país
# en `components/bonds_panel.py`, no un `if` repartido por el módulo.
#
# `bonds/bond_math.py` es agnóstico de país a propósito (descontar un flujo
# de fondos es la misma aritmética en cualquier mercado); lo que cambia por
# país es de dónde salen los precios y las condiciones de emisión.
# ----------------------------------------------------------------------
BOND_COUNTRY_ARGENTINA: Final[str] = "🇦🇷 Argentina (ONs)"
BOND_COUNTRY_USA: Final[str] = "🇺🇸 Estados Unidos"

BOND_COUNTRY_OPTIONS: Final[tuple[str, ...]] = (
    BOND_COUNTRY_ARGENTINA,
    BOND_COUNTRY_USA,
)

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

# ----------------------------------------------------------------------
# Origen del cronograma de pagos de cada ON.
#
# El panel conoce un bono de dos maneras y no dan lo mismo: el catálogo
# local describe las condiciones de emisión y permite calcular todo
# (paridad, valor técnico, vida promedio); la fuente comunitaria publica el
# cronograma ya resuelto, que alcanza para TIR y duration pero no informa
# qué parte de cada pago es capital. Mostrar de dónde salió cada fila evita
# tener que explicar por qué a unas les faltan columnas.
# ----------------------------------------------------------------------
BOND_SOURCE_CATALOG: Final[str] = "Catálogo local"
# Flujo reconstruido de la ficha técnica de BYMA. Solo se usa en bonos
# bullet a tasa fija, donde lo único que hay que suponer es la frecuencia
# de pago —el único dato del flujo que BYMA no publica—. La etiqueta dice
# "estimada" porque esa suposición mueve la TIR unos puntos básicos.
BOND_SOURCE_BYMA: Final[str] = "BYMA (frec. estimada)"

# Etiqueta de la ley cuando se dedujo del prefijo del ISIN en lugar de venir
# declarada. El sufijo existe para que nadie lea como dato duro algo que es
# una inferencia: el ISIN dice dónde se registró la emisión, no bajo qué ley
# se litiga.
BOND_LAW_INFERRED_SUFFIX: Final[str] = " (ISIN)"
BOND_SOURCE_NONE: Final[str] = "—"

# ----------------------------------------------------------------------
# Filtro de liquidez.
#
# El feed devuelve el panel entero, que incluye especies que no operaron en
# todo el día. El precio que muestran es el de la última rueda en que se
# negociaron, así que su TIR se calcula contra un precio viejo: parece un
# dato y es un recuerdo.
#
# Los umbrales son relativos (hay volumen / top N del día) y no absolutos
# porque el feed no documenta en qué unidad expresa el volumen. Un corte
# tipo "más de 1.000.000" sería un número inventado; "las 20 que más
# operaron hoy" se sostiene sin saber la unidad.
# ----------------------------------------------------------------------
BOND_FILTER_LIQUIDITY_TRADED: Final[str] = "💧 Solo las que operaron hoy"
BOND_FILTER_LIQUIDITY_TOP_20: Final[str] = "🔝 Top 20 por volumen"
BOND_FILTER_LIQUIDITY_TOP_50: Final[str] = "🔝 Top 50 por volumen"
BOND_FILTER_LIQUIDITY_ALL: Final[str] = "Todas, incluso sin operar"

# El primero es el default del selector. Arranca en el top 50 por volumen:
# es el recorte que deja el panel operable, porque más abajo de ahí las
# especies negocian tan poco que su precio de pantalla no es ejecutable.
BOND_LIQUIDITY_FILTER_OPTIONS: Final[tuple[str, ...]] = (
    BOND_FILTER_LIQUIDITY_TOP_50,
    BOND_FILTER_LIQUIDITY_TOP_20,
    BOND_FILTER_LIQUIDITY_TRADED,
    BOND_FILTER_LIQUIDITY_ALL,
)

# Cantidad de especies que deja cada corte "top N por volumen".
BOND_TOP_VOLUME_SIZES: Final[dict[str, int]] = {
    BOND_FILTER_LIQUIDITY_TOP_20: 20,
    BOND_FILTER_LIQUIDITY_TOP_50: 50,
}

# ----------------------------------------------------------------------
# Puntaje de Oportunidad (0-100).
#
# El semáforo por puntos cuenta condiciones cumplidas, y eso empareja cosas
# que no son iguales: un bono que roza el umbral de liquidez suma lo mismo
# que uno que lo supera diez veces. El puntaje pondera cada dimensión de
# forma continua, comparando a cada ON contra el resto del panel del día.
#
# Los pesos son un criterio de inversión explícito, no una verdad: dicen
# que el rendimiento relativo pesa más que todo lo demás, que la liquidez
# importa casi tanto porque un rendimiento que no podés ejecutar no existe,
# y que la jurisdicción es un matiz y no el eje de la decisión. Se tocan
# acá, en un solo lugar, y suman 100.
# ----------------------------------------------------------------------
BOND_SCORE_YIELD: Final[str] = "Rendimiento"
BOND_SCORE_RATE_RISK: Final[str] = "Riesgo de tasa"
BOND_SCORE_LIQUIDITY: Final[str] = "Liquidez"
BOND_SCORE_PARITY: Final[str] = "Paridad"
BOND_SCORE_JURISDICTION: Final[str] = "Jurisdicción"

BOND_SCORE_WEIGHTS: Final[dict[str, float]] = {
    BOND_SCORE_YIELD: 35.0,
    BOND_SCORE_LIQUIDITY: 25.0,
    BOND_SCORE_RATE_RISK: 20.0,
    BOND_SCORE_PARITY: 10.0,
    BOND_SCORE_JURISDICTION: 10.0,
}

# Pendiente del castigo por prima excesiva. Pasado el umbral de riesgo, cada
# punto porcentual de TIR de más se cuenta como este múltiplo de puntos de
# menos, de modo que el puntaje de rendimiento baje de verdad en lugar de
# empatar con el percentil, que sigue subiendo. Con pendiente 2, un bono que
# supera el umbral por 5 pp puntúa como uno que rinde 10 pp por debajo de él.
BOND_SCORE_EXCESS_PENALTY_SLOPE: Final[float] = 2.0

# Dentro de Liquidez, cuánto pesa el spread de puntas frente al volumen.
# El spread es el costo cierto de entrar y salir; el volumen dice si ese
# spread se sostiene en tamaño. Van casi a la par.
BOND_SCORE_SPREAD_SHARE: Final[float] = 0.5

# Puntaje de jurisdicción. Ley extranjera no es garantía de cobro, pero
# históricamente cotiza con menor rendimiento exigido: el mercado paga por
# esa diferencia, así que el puntaje la refleja sin volverla decisiva.
BOND_SCORE_LAW_NY: Final[float] = 100.0
BOND_SCORE_LAW_ARG: Final[float] = 40.0

# Cobertura mínima: fracción del peso total que tiene que poder evaluarse
# para publicar un puntaje. Una ON sin liquidez ni paridad conocidas se
# estaría calificando con poco más que su TIR, y ese número diría más sobre
# lo que falta que sobre el bono.
BOND_SCORE_MIN_COVERAGE: Final[float] = 0.5

# Tamaño mínimo del panel comparable para publicar puntajes. El puntaje es
# un percentil: con dos o tres bonos, "estar en el percentil 100" significa
# ganarle a dos, y con uno solo significa nada. Por debajo de este número no
# se publica puntaje en vez de fabricar una comparación que no existe.
BOND_SCORE_MIN_PANEL_SIZE: Final[int] = 5

# Fracción mínima del panel que tiene que tener una dimensión para que esa
# dimensión se use. Si solo tres bonos de cincuenta tienen la ley cargada, el
# percentil los compara entre ellos y el mejor de esos tres se lleva 100 sobre
# una muestra que no representa nada; además, los otros cuarenta y siete no
# pagan por no tenerla, con lo cual cargar un dato cierto pero mediocre baja
# el puntaje. Por debajo de este umbral la dimensión se descarta para todos,
# que es la única forma de que todos se comparen sobre la misma base.
BOND_SCORE_MIN_DIMENSION_COVERAGE: Final[float] = 0.5

# Cortes del puntaje a etiqueta del semáforo.
BOND_SCORE_VERY_ATTRACTIVE_MIN: Final[float] = 70.0
BOND_SCORE_ATTRACTIVE_MIN: Final[float] = 55.0
BOND_SCORE_NEUTRAL_MIN: Final[float] = 40.0


# ----------------------------------------------------------------------
# Cuántas especies se enriquecen con la ficha técnica de BYMA.
#
# La ficha técnica se pide de a una especie por llamada, y el panel trae más
# de 2700: pedirlas todas serían miles de pedidos a una API pública por cada
# carga. Se piden solo las más operadas de cada moneda, que son las únicas
# que el panel muestra por defecto y las únicas cuyo precio es ejecutable.
# ----------------------------------------------------------------------
BYMA_TERMS_FETCH_LIMIT: Final[int] = 150

# ----------------------------------------------------------------------
# Cuartil de volumen operado (columna "Volumen (cuartil)").
#
# Traduce el volumen a una lectura rápida de liquidez. El número crudo no
# se puede comparar de un vistazo: 86.000 es mucho o poco según contra qué.
#
# Dos decisiones que cambian el resultado:
#
#   1. **Los cuartiles se calculan DENTRO de cada moneda.** El volumen de la
#      especie en pesos está expresado en pesos y el de la especie MEP en
#      dólares. Mezclarlas pondría a casi todas las especies en pesos en el
#      cuartil alto por tener el número más grande, no por operar más. Es el
#      mismo motivo por el que `_top_by_volume_within_currency` rankea por
#      moneda.
#
#   2. **Volumen cero no es el cuartil más bajo: es "sin operar".** Las
#      especies que no negociaron son mayoría en el panel, y dejarlas entrar
#      al cuartil las repartiría empatadas por la mitad de la escala,
#      arrastrando hacia abajo a las que sí operaron poco. Se etiquetan
#      aparte y no participan del cálculo.
#
# Se calculan sobre el panel completo de cada moneda y no sobre lo que
# dejen los filtros: "muy alto" tiene que significar muy alto en el mercado,
# no muy alto entre las treinta filas que quedaron en pantalla.
# ----------------------------------------------------------------------
BOND_VOLUME_VERY_HIGH: Final[str] = "🔵 Muy alto"
BOND_VOLUME_HIGH: Final[str] = "🟢 Alto"
BOND_VOLUME_MEDIUM: Final[str] = "🟡 Medio"
BOND_VOLUME_LOW: Final[str] = "🟠 Bajo"
BOND_VOLUME_NONE: Final[str] = "⚪ Sin operar"

# De mayor a menor, para que la interfaz no reconstruya el orden a mano.
BOND_VOLUME_QUARTILES: Final[tuple[str, ...]] = (
    BOND_VOLUME_VERY_HIGH,
    BOND_VOLUME_HIGH,
    BOND_VOLUME_MEDIUM,
    BOND_VOLUME_LOW,
    BOND_VOLUME_NONE,
)

# Nombre de la columna, junto a "Volumen".
BOND_VOLUME_QUARTILE_COLUMN: Final[str] = "Volumen (cuartil)"
