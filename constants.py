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
MARKET_ARGENTINA: Final[str] = "Acciones Argentinas (Merval)"

# Cripto NO está acá: no es una acción, es otra clase de activo, así que va
# como sección propia del tablero junto a Acciones y Bonos. Este desplegable
# es para elegir *qué mercado accionario* se mira.
MARKET_OPTIONS: Final[tuple[str, ...]] = (
    MARKET_USA_STOCKS,
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
SECTION_CRYPTO: Final[str] = "🪙 Criptomonedas"

SECTION_OPTIONS: Final[tuple[str, ...]] = (SECTION_STOCKS, SECTION_BONDS, SECTION_CRYPTO)

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
# OJO: no puede llamarse "Calificación". Ese es el nombre de la columna que
# muestra la nota del emisor, y el panel vuelca los subpuntajes al cuadro por
# nombre de columna: si coinciden, el subpuntaje pisa la nota y la nota
# desaparece de la tabla.
BOND_SCORE_RATING: Final[str] = "Calidad crediticia"

# Los tres primeros pesan igual y son el criterio de inversión del tablero:
# antes de preguntarse cuánto rinde un bono hay que poder comprarlo y venderlo
# (liquidez) y saber a quién se le presta (calificación). Rendimiento bajó de
# 35 a 20 por eso mismo: una TIR alta que no se puede ejecutar, o que paga un
# emisor al borde del default, no es una oportunidad.
#
# Riesgo de tasa pesa la mitad que los tres primeros, y no lo mismo, porque
# la duration se estaba contando dos veces. El cuadro ya tiene un filtro de
# duration: quien no quiere riesgo de tasa lo recorta ahí. Que además lo
# castigue el puntaje convertía al ranking en una lista de bonos cortos.
#
# El caso que lo mostró: una ON de Pampa con AAA(arg), el mejor spread de
# puntas del panel y medio millón operado quedaba por debajo de una AA- que
# casi no operaba, solo porque su duration de 7 años la dejaba en 0,7 sobre
# 100 en esta dimensión. Una duration larga no es un defecto, es una
# característica: un bono a siete años no es peor que uno a seis meses, es
# otra cosa.
#
# Los 10 puntos liberados se reparten entre las dos secundarias, que estaban
# parejas. OJO con jurisdicción: hoy la ley no viene declarada por el mercado
# sino deducida del prefijo del ISIN, así que ese 15% descansa sobre un
# indicio y no sobre un dato.
#
# La calificación se pondera aunque hoy no haya ninguna cargada. No hace falta
# hacer nada especial para eso: una dimensión que no se puede medir en buena
# parte del panel se descarta para todos y su peso se reparte entre las demás,
# de modo que mientras el archivo de calificaciones esté vacío el puntaje sale
# de los otros cinco criterios y aparece solo cuando haya datos.
BOND_SCORE_WEIGHTS: Final[dict[str, float]] = {
    BOND_SCORE_YIELD: 20.0,
    BOND_SCORE_LIQUIDITY: 20.0,
    BOND_SCORE_RATING: 20.0,
    BOND_SCORE_RATE_RISK: 10.0,
    BOND_SCORE_PARITY: 15.0,
    BOND_SCORE_JURISDICTION: 15.0,
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

# Puntaje de crédito de un emisor SIN calificación.
#
# Es la única dimensión donde no se aplica la regla general de "lo que no se
# puede medir se excluye y su peso se reparte". Esa regla existe para no
# castigar a un bono por un dato que falta en nuestra fuente, y es correcta
# cuando el dato es nuestro problema. Acá no lo es: con el listado de la
# calificadora cargado, la mayoría del panel tiene nota, así que no tenerla
# dice algo del emisor —no la buscó, o se la retiraron— y no de nuestra
# cobertura.
#
# Excluirla tenía además un efecto concreto y visible: un emisor sin
# calificación no perdía nada por no tenerla, y con el resto de sus números
# buenos se quedaba con el primer puesto del cuadro por encima de emisores
# AAA. Eso es lo contrario de lo que un tablero de renta fija debería premiar.
#
# El valor NO es cero: cero es lo que puntúa un emisor en default, y de uno
# sin calificar no sabemos eso. Queda por debajo de cualquier nota que hoy
# tenga el panel (la más floja es A+(arg), que puntúa 41) y por encima de
# las notas malas de verdad: un crédito que se sabe flojo tiene que quedar
# peor que uno desconocido. Es una postura de inversión explícita, no una
# medición: subilo o bajalo según cuánto te importe que un emisor esté
# calificado.
BOND_SCORE_UNRATED: Final[float] = 30.0

# Cuánto vale un escalón de calificación, como factor.
#
# La escalera NO se reparte lineal: el riesgo de crédito crece de forma
# aproximadamente exponencial al bajar de nota. Históricamente, cada escalón
# hacia abajo multiplica la probabilidad de default en vez de sumarle una
# cantidad fija, así que un escalón por debajo de AAA no significa lo mismo
# que un escalón por debajo de BBB.
#
# Con 0,8, AAA vale 100 y cada escalón conserva el 80% del anterior:
#
#     AAA 100 · AA+ 80 · AA 64 · AA- 51 · A+ 41 · A 33 · BBB 17 · BB 9
#
# Repartir lineal dejaba a todas las corporativas argentinas —que van de
# A+(arg) a AAA(arg)— apretadas entre 80 y 100, y la dimensión no distinguía
# un AAA de un AA-.
BOND_RATING_NOTCH_DECAY: Final[float] = 0.8

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
#   3. **Se calculan sobre las filas que quedan después de filtrar**, no
#      sobre el mercado entero. Es lo contrario de lo que parece razonable,
#      y la razón es que el corte de liquidez por defecto es él mismo un
#      "top N por volumen": contra todo el mercado, las filas en pantalla
#      eran por construcción las más operadas y salían todas en el cuartil
#      más alto, con lo cual la columna no distinguía nada. El costo de esta
#      decisión es que "muy alto" significa muy alto en la vista actual y
#      cambia al cambiar los filtros; a cambio, la columna siempre reparte.
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


# ======================================================================
# CRIPTOMONEDAS
#
# Mismo criterio que en las dos secciones anteriores: etiquetas, umbrales y
# textos de los selectores viven acá para que el motor (`crypto/panel.py`),
# la tabla (`components/crypto_table.py`) y los filtros
# (`components/crypto_panel.py`) lean siempre el mismo literal.
#
# El semáforo de confluencia es **el mismo que el de acciones**: se reusa
# `indicators.evaluate_confluence_signal` sin tocar sus umbrales. Lo que
# cambia en cripto no son las reglas de lectura técnica sino el calendario
# (opera los siete días) y el hecho de que no hay balances de los que salga
# un PER. Por eso acá abajo hay ventanas en barras y no umbrales de señal.
# ======================================================================

# ----------------------------------------------------------------------
# Calendario: cuántas barras entra un plazo en un mercado que no cierra
#
# Una acción cotiza ~252 ruedas al año y ~126 en seis meses; una cripto
# opera los 365 días. Estos números son los que se le pasan a
# `compute_stock_technicals` para que "máximo de 52 semanas" y "squeeze de
# seis meses" signifiquen en cripto lo mismo que significan en acciones.
# ----------------------------------------------------------------------
CRYPTO_52W_WINDOW_DAILY: Final[int] = 365
CRYPTO_52W_WINDOW_WEEKLY: Final[int] = 52
CRYPTO_SQUEEZE_LOOKBACK_DAILY: Final[int] = 182
CRYPTO_SQUEEZE_LOOKBACK_WEEKLY: Final[int] = 26

# Barras por año, para anualizar el desvío de los retornos.
CRYPTO_BARS_PER_YEAR_DAILY: Final[int] = 365
CRYPTO_BARS_PER_YEAR_WEEKLY: Final[int] = 52

# Ventana sobre la que se mide la volatilidad anualizada: un mes.
CRYPTO_VOLATILITY_WINDOW_DAILY: Final[int] = 30
CRYPTO_VOLATILITY_WINDOW_WEEKLY: Final[int] = 13

# Ventanas de las columnas de variación (corto y mediano plazo).
CRYPTO_RETURN_SHORT_DAILY: Final[int] = 7
CRYPTO_RETURN_SHORT_WEEKLY: Final[int] = 4
CRYPTO_RETURN_LONG_DAILY: Final[int] = 30
CRYPTO_RETURN_LONG_WEEKLY: Final[int] = 13

# ----------------------------------------------------------------------
# Fuerza relativa contra Bitcoin
#
# Es la métrica nativa de esta sección y no existe en acciones. En cripto
# casi todo sube y baja junto con Bitcoin, así que "subió 8% en el mes" no
# dice nada por sí solo: si Bitcoin subió 12%, esa moneda perdió terreno.
# La columna mide el exceso de retorno sobre Bitcoin en la misma ventana.
# ----------------------------------------------------------------------
CRYPTO_BENCHMARK_TICKER: Final[str] = "BTC-USD"
CRYPTO_BENCHMARK_LABEL: Final[str] = "BTC"

# Banda muerta, en puntos porcentuales: por debajo de esta diferencia el
# desempeño se considera "en línea" con Bitcoin y no una ventaja real.
CRYPTO_RS_NEUTRAL_BAND_PP: Final[float] = 2.0

CRYPTO_RS_OUTPERFORM: Final[str] = "💪 Supera a BTC"
CRYPTO_RS_INLINE: Final[str] = "➖ En línea con BTC"
CRYPTO_RS_UNDERPERFORM: Final[str] = "🐢 Rezagada vs BTC"
CRYPTO_RS_NOT_AVAILABLE: Final[str] = "N/A"

# ----------------------------------------------------------------------
# Umbral de volatilidad anualizada, en %, para el aviso de riesgo del KPI.
# Una acción grande se mueve en el orden del 20-30% anual; en cripto el
# piso del universo mayorista ronda el 40% y las monedas chicas superan
# holgadamente el 100%.
# ----------------------------------------------------------------------
CRYPTO_HIGH_VOLATILITY_PCT: Final[float] = 100.0

# ----------------------------------------------------------------------
# Textos de los selectores de la sección (mismo motivo que en acciones:
# el `if/elif` compara contra estos literales, no contra texto suelto).
# ----------------------------------------------------------------------

# --- Selector de universo ---
CRYPTO_UNIVERSE_TOP: Final[str] = "Principales por capitalización"
CRYPTO_UNIVERSE_LAYER1: Final[str] = "Capa 1 (redes base)"
CRYPTO_UNIVERSE_DEFI: Final[str] = "DeFi e infraestructura"
CRYPTO_UNIVERSE_MEME: Final[str] = "Memecoins"

CRYPTO_UNIVERSE_OPTIONS: Final[tuple[str, ...]] = (
    CRYPTO_UNIVERSE_TOP,
    CRYPTO_UNIVERSE_LAYER1,
    CRYPTO_UNIVERSE_DEFI,
    CRYPTO_UNIVERSE_MEME,
)

# --- Filtro por Semáforo ---
CRYPTO_FILTER_SIGNAL_ALL: Final[str] = "Todas las Criptos"
CRYPTO_FILTER_SIGNAL_STRONG_BUY: Final[str] = "🌟 Solo Compra Fuerte"
CRYPTO_FILTER_SIGNAL_BUY: Final[str] = "🟢 Solo Compras (Fuerte + Moderada)"
CRYPTO_FILTER_SIGNAL_SELL: Final[str] = "🚨 Solo Venta / Rotar (Fuerte + Moderada)"
CRYPTO_FILTER_SIGNAL_SQUEEZE: Final[str] = "⚡ Solo Squeezes"

CRYPTO_SIGNAL_FILTER_OPTIONS: Final[tuple[str, ...]] = (
    CRYPTO_FILTER_SIGNAL_ALL,
    CRYPTO_FILTER_SIGNAL_STRONG_BUY,
    CRYPTO_FILTER_SIGNAL_BUY,
    CRYPTO_FILTER_SIGNAL_SELL,
    CRYPTO_FILTER_SIGNAL_SQUEEZE,
)

# --- Filtro por fuerza relativa contra Bitcoin ---
CRYPTO_FILTER_RS_ALL: Final[str] = "Todas"
CRYPTO_FILTER_RS_OUTPERFORM: Final[str] = "💪 Solo las que superan a BTC"
CRYPTO_FILTER_RS_UNDERPERFORM: Final[str] = "🐢 Solo las rezagadas vs BTC"

CRYPTO_RS_FILTER_OPTIONS: Final[tuple[str, ...]] = (
    CRYPTO_FILTER_RS_ALL,
    CRYPTO_FILTER_RS_OUTPERFORM,
    CRYPTO_FILTER_RS_UNDERPERFORM,
)

# --- Filtro por Tendencia vs SMA 200 ---
CRYPTO_FILTER_TREND_ALL: Final[str] = "Todas"
CRYPTO_FILTER_TREND_BULLISH: Final[str] = "Solo Alcistas (> SMA 200)"
CRYPTO_FILTER_TREND_BEARISH: Final[str] = "Solo Bajistas (< SMA 200)"

CRYPTO_TREND_FILTER_OPTIONS: Final[tuple[str, ...]] = (
    CRYPTO_FILTER_TREND_ALL,
    CRYPTO_FILTER_TREND_BULLISH,
    CRYPTO_FILTER_TREND_BEARISH,
)

# --- Columna de flujo de volumen ---
# El OBV se calcula igual que en acciones, pero la etiqueta no puede ser
# "Smart Money": el volumen de una cripto es la suma de lo operado en
# decenas de exchanges minoristas, no la huella de un fondo institucional.
CRYPTO_FLOW_COLUMN: Final[str] = "Flujo de Volumen (OBV)"


# ----------------------------------------------------------------------
# Calibración del semáforo para cripto: extensión sobre la media
#
# El algoritmo del semáforo no cambia, pero una de sus condiciones
# obligatorias sí necesita recalibrarse. El lado venta exige "estar en un
# techo", y en acciones eso se mide como proximidad al máximo de 52
# semanas, porque una acción líder cotiza habitualmente cerca de sus
# máximos. En cripto los drawdowns son de 70-80%: medido sobre el panel,
# una moneda puede estar con RSI 80 y 50% arriba de su SMA 50 y seguir a
# 60% de su máximo anual. Con la condición de acciones, el semáforo se
# queda mudo justo cuando el activo está más estirado.
#
# El camino alternativo mide la extensión sobre la SMA 50 en **desvíos
# propios** de cada moneda (ver `indicators.compute_sma50_dispersion`), así
# que se adapta sola a la volatilidad de cada una en vez de fijar un
# porcentaje que sería arbitrario para todas.
#
# El valor está calibrado sobre el panel real: con 2 desvíos quedan
# marcadas las monedas visiblemente estiradas sin que la etiqueta pierda
# valor por repartirse a medio cuadro.
# ----------------------------------------------------------------------
CRYPTO_STRETCH_SIGMAS: Final[float] = 2.0

# ----------------------------------------------------------------------
# DOMINANCIA Y ROTACIÓN BTC / ALTCOINS
#
# La pregunta que responde este bloque es "¿conviene estar en Bitcoin o en
# altcoins?". Se mide de dos maneras, que son distintas a propósito:
#
#   * **Dominancia global**: la porción del valor de todo el mercado cripto
#     que es Bitcoin. Es el número que se publica en todos lados y sirve de
#     referencia conocida. Viene de una fuente externa.
#   * **Dominancia del panel**: la porción que es Bitcoin dentro del
#     universo que se está mirando. No coincide con la global (el panel no
#     tiene miles de monedas ni stablecoins) y por eso se informa su
#     **variación**, no su nivel: lo que importa es hacia dónde se mueve.
# ----------------------------------------------------------------------

# Ventana, en barras, sobre la que se mide el cambio de dominancia. Es la
# misma que la de la fuerza relativa contra BTC, para que las dos columnas
# hablen del mismo período.
CRYPTO_DOMINANCE_WINDOW_DAILY: Final[int] = 30
CRYPTO_DOMINANCE_WINDOW_WEEKLY: Final[int] = 13

# Cuántos puntos porcentuales de cambio de dominancia se consideran un
# movimiento real y no ruido de medición.
CRYPTO_DOMINANCE_BAND_PP: Final[float] = 0.5

CRYPTO_ROTATION_TO_BTC: Final[str] = "🟠 Rotación hacia Bitcoin"
CRYPTO_ROTATION_TO_ALTS: Final[str] = "🟢 Rotación hacia altcoins"
CRYPTO_ROTATION_STABLE: Final[str] = "⚪ Sin rotación clara"

# --- Termómetro de temporada de altcoins ---
#
# Réplica del índice de uso corriente: qué porcentaje del universo le ganó
# a Bitcoin en la ventana. El umbral clásico es 75% para declarar
# "temporada de altcoins" y 25% para "temporada de Bitcoin"; por debajo de
# 75% no hay temporada de altcoins, hay monedas sueltas que rindieron bien.
CRYPTO_ALTSEASON_MIN_PCT: Final[float] = 75.0
CRYPTO_BTCSEASON_MAX_PCT: Final[float] = 25.0

CRYPTO_SEASON_ALTS: Final[str] = "🟢 Temporada de altcoins"
CRYPTO_SEASON_BTC: Final[str] = "🟠 Temporada de Bitcoin"
CRYPTO_SEASON_MIXED: Final[str] = "⚪ Mercado mixto"

# ----------------------------------------------------------------------
# Soportes y resistencias del gráfico
#
# Los niveles se detectan como pivotes (máximos y mínimos locales) y se
# agrupan por cercanía: un nivel al que el precio volvió varias veces vale
# más que uno tocado una sola vez, y dos pivotes a medio punto porcentual
# de distancia son el mismo nivel visto dos veces, no dos niveles.
# ----------------------------------------------------------------------

# Barras a cada lado que debe superar un pivote para contar como tal.
CRYPTO_PIVOT_LOOKAROUND_BARS: Final[int] = 10

# Dos pivotes a menos de esta distancia porcentual son el mismo nivel.
CRYPTO_LEVEL_CLUSTER_PCT: Final[float] = 2.5

# Cuántos niveles se dibujan de cada lado. Más de tres convierten el
# gráfico en una parrilla donde ningún nivel se distingue del resto.
CRYPTO_LEVELS_PER_SIDE: Final[int] = 3

# Toques mínimos para que un nivel se considere fuerte (línea llena en vez
# de punteada).
CRYPTO_LEVEL_STRONG_TOUCHES: Final[int] = 3


# ----------------------------------------------------------------------
# Escala del gráfico de soportes y resistencias
#
# Un nivel es fuerte cuando el precio lo respetó varias veces a lo largo
# del tiempo, así que la escala en la que se lo busca **es** la definición
# de qué se considera un nivel. En velas diarias de seis meses salen giros
# de corto plazo, casi todos con uno o dos toques; en velas mensuales de
# varios años salen los techos y pisos que el mercado reconoce.
#
# Por eso la escala es un selector y arranca en mensual: es la que da los
# niveles estructurales, que son los que sirven para decidir dónde comprar
# o dónde salir.
#
# Cada escala necesita sus propios parámetros. Un entorno de 10 barras son
# dos semanas en diario y casi un año en mensual; una tolerancia de
# agrupamiento de 2,5% separa bien niveles diarios y parte en dos el mismo
# techo cuando se lo mira en meses.
# ----------------------------------------------------------------------
CRYPTO_CHART_SCALE_MONTHLY: Final[str] = "🗓️ Mensual (niveles estructurales)"
CRYPTO_CHART_SCALE_WEEKLY: Final[str] = "📅 Semanal (niveles intermedios)"
CRYPTO_CHART_SCALE_DAILY: Final[str] = "☀️ Diario (niveles de corto plazo)"

CRYPTO_CHART_SCALE_OPTIONS: Final[tuple[str, ...]] = (
    CRYPTO_CHART_SCALE_MONTHLY,
    CRYPTO_CHART_SCALE_WEEKLY,
    CRYPTO_CHART_SCALE_DAILY,
)

# Por escala: (intervalo de yfinance, barras a cada lado del pivote,
# tolerancia de agrupamiento en %, barras que se dibujan).
#
# Los valores están medidos sobre el historial real de Bitcoin, no elegidos
# a ojo. En mensual hay pocas barras (145 en doce años), así que un entorno
# de ±2 meses deja apenas dos o tres pivotes y casi ninguno se agrupa: los
# niveles salen todos con un solo toque. Con ±1 mes y 8% de tolerancia, en
# cambio, quedan seis zonas de dos toques cada una, que es lo que hace que
# la línea signifique algo.
CRYPTO_CHART_SCALE_PARAMS: Final[dict[str, tuple[str, int, float, int]]] = {
    CRYPTO_CHART_SCALE_MONTHLY: ("1mo", 1, 8.0, 120),
    CRYPTO_CHART_SCALE_WEEKLY: ("1wk", 4, 4.0, 220),
    CRYPTO_CHART_SCALE_DAILY: ("1d", 10, 2.5, 280),
}

# Separación mínima entre dos etiquetas de nivel, en píxeles. Las zonas
# cercanas al precio de hoy siempre quedan juntas, y sin este piso sus
# textos se montan uno sobre otro y no se lee ninguno.
CRYPTO_LEVEL_LABEL_GAP_PX: Final[int] = 30

# Un nivel se dibuja como **zona** y no como línea: el precio no gira en un
# número exacto, gira en una franja. El ancho es la mitad de la tolerancia
# de agrupamiento de la escala, que es justamente la distancia dentro de la
# cual dos giros se consideraron el mismo nivel.
CRYPTO_LEVEL_BAND_RATIO: Final[float] = 0.5


# ----------------------------------------------------------------------
# Divergencias entre el precio y el oscilador (RSI)
#
# Una divergencia es que el precio y su impulso digan cosas distintas: el
# precio marca un máximo más alto que el anterior pero el RSI marca uno más
# bajo (bajista), o el precio hace un mínimo más bajo y el RSI uno más alto
# (alcista). Se lee como que el movimiento pierde fuerza.
#
# No es una señal de entrada por sí sola —una divergencia puede sostenerse
# mucho tiempo antes de que el precio gire, o no girar nunca— y por eso el
# panel las **marca** en el gráfico en vez de convertirlas en una etiqueta
# del semáforo.
# ----------------------------------------------------------------------

# Separación máxima entre los dos giros comparados. Dos máximos separados
# por años no son una divergencia: son dos tramos distintos del mercado.
CRYPTO_DIVERGENCE_MAX_GAP_BARS: Final[int] = 60

# Diferencia mínima, en puntos de RSI, para que el segundo giro cuente como
# más débil. Sin este piso, medio punto de RSI ya dibujaría una divergencia.
CRYPTO_DIVERGENCE_MIN_RSI_GAP: Final[float] = 3.0

# Diferencia mínima de precio entre los dos giros, en %. Dos máximos
# prácticamente iguales son un doble techo, no una divergencia.
CRYPTO_DIVERGENCE_MIN_PRICE_GAP_PCT: Final[float] = 1.0

# Cuántas se dibujan, de la más reciente hacia atrás. El gráfico muestra
# las últimas: una divergencia de hace tres años ya no informa nada.
CRYPTO_DIVERGENCE_MAX_SHOWN: Final[int] = 3

CRYPTO_DIVERGENCE_BEARISH: Final[str] = "Divergencia bajista"
CRYPTO_DIVERGENCE_BULLISH: Final[str] = "Divergencia alcista"
