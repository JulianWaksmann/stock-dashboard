# Tablero Cuantitativo de Acciones, Bonos Corporativos y Criptomonedas

Tablero de análisis cuantitativo construido con **Streamlit**, **Pandas** y **Yahoo Finance (`yfinance`)**, dividido en tres secciones: **Acciones** (screener de confluencia técnica), **Bonos Corporativos Argentinos** (analítica de renta fija para Obligaciones Negociables) y **Criptomonedas** (el mismo screener técnico, adaptado a un mercado que opera los siete días). Las secciones se eligen con un selector en lugar de pestañas, así cada una consulta sus fuentes recién cuando se la abre.

La sección de acciones monitorea las 50 principales líderes del mercado en tiempo real, combinando **métricas de valuación fundamental** (PER pasado, PER futuro y PER promedio de 5 años) con los **principios de confluencia técnica de John Murphy** y una lectura de flujo institucional vía **On-Balance Volume ("Smart Money")**, para identificar de un vistazo oportunidades de swing, agotamientos de rotación y compresiones de volatilidad.

---

## ⚡ Funcionalidades principales

### 1. Motor de Confluencia (semáforo por sistema de grados)
Evalúa cada ticker contra un conjunto chico de condiciones obligatorias y opcionales para producir una señal graduada:

**Lado compra (swing)**
* Obligatorio: precio a ±4% de la SMA 50, **o** en/por debajo de la Banda Inferior de Bollinger (1% de tolerancia) — **y** RSI (14) < 45.
* Opcionales, un punto cada uno: tendencia alcista confirmada (SMA 50 > SMA 200, tolerando hasta 5% por debajo de la SMA 200), cruce alcista del Estocástico o %K < 30, y OBV por encima de su SMA de 20 períodos (acumulación).
* 4-5 puntos → 🌟 **COMPRA FUERTE**. Exactamente 3 puntos → 🟢 **COMPRA MODERADA**.

**Lado venta (rotación / agotamiento)**
* Obligatorio: precio a menos de 6% de su máximo de 52 semanas — **y** RSI (14) > 65.
* Opcionales, un punto cada uno: cruce bajista del Estocástico o %K ≥ 80, MACD debilitándose (histograma cayendo o línea MACD por debajo de la señal), y OBV por debajo de su SMA de 20 períodos (distribución).
* 3-4 puntos → 🚨 **VENTA FUERTE / ROTAR**. Exactamente 2 puntos → 🟠 **VENTA MODERADA**.

**Otros estados**
* 🚨 **SQUEEZE:** el ancho de las Bandas de Bollinger está en su mínimo de 6 meses (126 ruedas) o hasta 8% por encima — señal de compresión de volatilidad y expansión direccional inminente.
* 🟡 **NEUTRAL:** modo de seguimiento cuando no se alcanza ningún umbral de confluencia.

Cada etiqueta de señal y cada umbral numérico vive en `constants.py`, que es la única fuente de verdad compartida entre el algoritmo (`indicators.py`) y los filtros de la barra lateral (`app.py`) — las reglas se ajustan ahí, no en el código que las consume.

---

### 2. Flujo institucional (OBV / Smart Money)
* Compara el On-Balance Volume contra su propia SMA de 20 períodos para marcar cada ticker como 🐳 **Acumulación** o 📉 **Distribución**. Alimenta tanto el puntaje de confluencia como su propia columna "Flujo Institucional" y su filtro en la barra lateral.

---

### 3. Matriz de valuación fundamental
* **PER pasado (trailing):** precio sobre ganancias reales de los últimos 12 meses.
* **PER futuro (forward):** precio sobre ganancias estimadas por consenso de analistas para los próximos 12 meses.
* **PER promedio histórico (5 años):** base multianual calculada a partir de los balances anuales, que permite detectar rápido expansión de múltiplos o subvaluación.

---

### 4. Indicadores técnicos
* **Medias móviles y distancias %:** SMA 20 (corto plazo), SMA 50 (mediano) y SMA 200 (tendencia de fondo), con desvío porcentual en tiempo real.
* **RSI (14):** oscilador de momento con suavizado de Wilder, graficado con marcas fijas en 30 y 70.
* **MACD (12, 26, 9):** indicador de momento seguidor de tendencia.
* **Bandas de Bollinger (20, 2):** envolventes de volatilidad y canal dinámico de soporte/resistencia, con ancho normalizado.
* **Estocástico (%K 14, %D 3):** gatillo de momento que confirma giros de micro tendencia.
* **Máximo / mínimo de 52 semanas:** extremos móviles de 252 ruedas y distancia porcentual al techo del ciclo.

---

### 5. Arquitectura y usabilidad
* **Doble temporalidad:** alterna entre cálculos **diarios (1D)** y **semanales (1W)**.
* **Selector de mercado:** la barra lateral permite elegir mercado; **Acciones USA (S&P 500)** es el default implementado, mientras que Cripto y Acciones Argentinas (Merval) figuran como "próximamente".
* **Filtros rápidos:** por grado de señal, flujo institucional (OBV), rango de RSI (14) y tendencia contra la SMA 200.
* **Panel de alertas:** categorización inmediata de los tickers que activan setups de compra, venta o squeeze.
* **Descarga en paralelo:** ingesta multihilo con `concurrent.futures` y caché vía `st.cache_data`.
* **Carga resiliente:** si algunos tickers fallan (límites de Yahoo Finance, símbolos deslistados, cortes de red), el resto del tablero sigue funcionando y un aviso lista los omitidos.
* **Exportación a CSV** de lo que se esté viendo, con un clic.

---

## 💵 Bonos Corporativos Argentinos (Obligaciones Negociables)

La segunda sección valúa el panel de ONs corporativas en dólares a partir de su **flujo de fondos
contractual**, y no de indicadores de momento de precio, que no dicen nada útil sobre un bono.

### Qué calcula

Para cada ON con cronograma conocido, por cada 100 de valor nominal original:

| Métrica | Qué responde |
| --- | --- |
| **TIR** | Rendimiento efectivo anual si se mantiene hasta el vencimiento. Es *la* variable de comparación entre bonos. |
| **Renta anual (*current yield*)** | Cupón anual sobre el precio pagado: el flujo de caja del año, sin contar ganancia ni pérdida de capital. |
| **Duration modificada** | Riesgo de tasa: caída aproximada del precio, en %, si el rendimiento exigido sube 1 punto porcentual. |
| **Duration de Macaulay / convexidad** | Plazo promedio ponderado del flujo descontado, y la curvatura que la duration sola no captura. |
| **Vida promedio (WAL)** | En cuántos años, promedio, vuelve el capital. Bastante menos que el plazo al vencimiento en bonos que amortizan. |
| **Paridad** | Precio sobre valor técnico. Por debajo de 100, parte del retorno llega como ganancia de capital. |
| **Valor técnico / interés corrido / capital residual** | Lo que el contrato dice que el bono vale hoy. |
| **Spread vs UST** | Puntos básicos por encima del Tesoro de EE.UU. de duration equivalente: el precio del riesgo argentino más el del emisor. |
| **Spread de puntas y volumen** | Si ese rendimiento es ejecutable o es teórico. |
| **Lámina mínima** | Si un minorista puede comprarlo (muchas ONs ley NY operan en láminas de 100.000 o más). |

La app incluye un glosario que explica cada una de estas variables al lado del cuadro.

### Puntaje de Oportunidad

Cada ON recibe un puntaje de **0 a 100**, y de ahí sale la etiqueta. No es una nota absoluta: cada
dimensión se puntúa por la posición del bono **dentro del panel de ese día**. Una TIR del 11% es
excelente o mediocre según dónde esté cotizando todo lo demás, así que un umbral fijo diría cosas
opuestas en dos momentos del ciclo. Por construcción un bono promedio queda cerca de 50; lo que
importa es quién se despega.

| Dimensión | Peso | Qué mide |
| --- | --- | --- |
| Rendimiento | 35% | Cuánto rinde frente a sus pares, con castigo por prima excesiva |
| Liquidez | 25% | Spread de puntas y volumen operado: si el rendimiento es ejecutable |
| Riesgo de tasa | 20% | Duration modificada |
| Paridad | 10% | Cotizar bajo la par implica retorno vía ganancia de capital |
| Jurisdicción | 10% | Ley aplicable |

Tres reglas mantienen honesto al número:

1. **Más TIR no siempre es mejor.** Pasada una prima de `BOND_RISK_YIELD_PREMIUM_PP` sobre la
   mediana del panel, el castigo se aplica a la TIR *antes* de rankear, no al percentil después.
   Multiplicar un percentil por un factor decreciente no funciona: el percentil sube con la TIR
   mientras el factor baja, los dos efectos se cancelan y entre dos bonos ya castigados puede
   puntuar más alto el más riesgoso, que es exactamente lo que la regla evita.
2. **Lo que no se puede medir no puntúa cero: se excluye.** Una dimensión faltante sale del cálculo
   y su peso se reparte entre las demás. Puntuarla cero castigaría al bono por un hueco en nuestra
   fuente y no por algo que le pase al bono. La columna `Cobertura` informa qué fracción del peso
   se midió de verdad.
3. **Con muy poco medido, no hay puntaje.** Por debajo de `BOND_SCORE_MIN_COVERAGE` el número
   saldría casi solo de la TIR y diría más sobre lo que falta que sobre la oportunidad.

Del puntaje a la etiqueta: ≥70 🌟 MUY ATRACTIVO · ≥55 🟢 ATRACTIVO · ≥40 🟡 NEUTRAL · por debajo
🟠 POCO ATRACTIVO. Dos casos ganan sobre el puntaje: 🚨 **ALERTA DE RIESGO** por la prima de
arriba, y ⏳ **MUY CORTO** para las ONs a menos de `BOND_MIN_YEARS_FOR_GRADING` del vencimiento,
donde anualizar el retorno de unas semanas convierte un centavo de precio en decenas de puntos de
TIR. Los dos casos quedan además fuera de la mediana del panel, para que un artefacto aritmético no
corra la referencia contra la que se califica todo el resto.

Los pesos viven en `constants.py` (`BOND_SCORE_WEIGHTS`). Son un criterio de inversión explícito y
no una verdad: si para vos la liquidez pesa más que el rendimiento, ese es el lugar para decirlo.

El cuadro muestra lo esencial por defecto —puntaje, TIR, duration, paridad, spread, volumen— con el
set completo de columnas y el desglose del puntaje detrás de dos interruptores. Una tabla de veinte
columnas no se lee, se escanea.

### De dónde salen los datos

| Dato | Fuente | Notas |
| --- | --- | --- |
| Precios, puntas, volumen | [BYMA Open Data](https://open.bymadata.com.ar) | El mercado donde las ONs cotizan. Pública y sin API key, pero sin documentar: es POST y valida cookie de navegador. Trae además vencimiento y moneda de cada especie. |
| Emisor, lámina mínima, tasa de cupón, estructura de amortización, garantía, ISIN | BYMA — ficha técnica (`fichatecnica/especies/general`) | Una llamada por especie, así que se piden solo las más operadas de cada moneda y se cachean por un día: esos datos se fijan en la emisión y no cambian. |
| Cronogramas de pago | [rendimientos-ar](https://github.com/arisbdar/rendimientos-ar) (`public/config.json`) | Se descarga en cada carga. Es un **dataset comunitario** mantenido a mano por terceros (licencia ISC), no una fuente oficial. Publica el total de cada pago, sin separar renta de capital. |
| Condiciones de emisión | `data/ons_catalog.csv` (este repo) | Opcional y vacío por defecto. Solo hace falta para las métricas que necesitan el desglose renta/capital, o para una ON que el dataset comunitario no cubra. |
| Curva del Tesoro de EE.UU. | Yahoo Finance (`^IRX`, `^FVX`, `^TNX`, `^TYX`) | Vía `yfinance`, igual que la sección de acciones. Interpolada linealmente al plazo de duration de cada ON. |

### Una sola fuente de precios, a propósito

Los precios salen únicamente de BYMA. Hubo un segundo feed (data912) y se descartó después de
medirlo con `scripts/verificar_fuentes.py`: BYMA lista 2727 especies contra 616, y sobre las 614
que comparten, la mitad de los precios del feed alternativo llegaban con atraso —0,17% de
diferencia mediana y hasta 2,75% sobre el mismo título—. En un bono de duration 3 eso son entre 6
y 90 puntos básicos de TIR, que es justo lo que este panel compara. Tampoco quedó como respaldo: un
respaldo que devuelve otro número no es un respaldo, es una segunda respuesta a la misma pregunta.
Si BYMA no responde, el panel lo dice en lugar de mostrar otra cosa en silencio.

### Qué NO publica BYMA

Medido sobre 40 fichas del panel operado, no sobre supuestos:

* **La ley aplicable.** Los campos `ley` y `paisLey` existen y vienen vacíos: `paisLey` en las 40,
  `ley` en 39. La jurisdicción solo puede salir del catálogo local.
* **La frecuencia de pago.** No aparece en ningún campo. Es el único dato del flujo que falta para
  los bonos bullet, y se supone semestral —la convención dominante—, lo que acota el error a unos
  15 puntos básicos de TIR para cupones típicos. Esas filas se marcan como estimadas.
* **El cronograma de los bonos que amortizan en cuotas.** Vive en `formaAmortizacion`, en prosa.

En cambio, `interes` sí es legible: llega como "FIJO 7,50%" o "TASA DE REFERENCIA + MARGEN
APLICABLE (2,50%)". Reconocer las variables importa tanto como leer las fijas — el motor descuenta
un flujo determinado hoy, y el de un bono Badlar o CER no lo está.

Y de `formaAmortizacion` se responde **una sola pregunta binaria**: ¿devuelve todo el capital al
vencimiento? No se extrae el cronograma. Sobre los 20 textos distintos que devuelve el panel
operado, la regla acierta en los 20; el veto por plural es lo que la hace segura, porque
"amortizadas en 7 cuotas semestrales ... finalizando en la Fecha de Vencimiento" nombra el
vencimiento y no es bullet. Lo que no se reconoce no es bullet, así que el modo de falla es no
calcular.

### Tres maneras de conocer un bono

Las condiciones de emisión de una ON no se descargan. El cupón, el cronograma de amortización y la
ley aplicable viven en su prospecto, y ni BYMA ni la CNV los publican en formato consultable por
máquina. Así que el panel trabaja con la fuente que tenga, y dice cuál en cada fila:

* **Cronograma de pagos** (dataset comunitario, descargado en vivo) — informa solo el total de cada
  pago. Su cobertura es su límite real: son 54 emisiones, y ninguna de las más operadas del panel.
  Tiene las series vecinas —CP36 y CP37 donde se opera CP38 y CP40, YM34 a YM40 donde se opera
  YM39 y YM43—, así que las ONs con más volumen quedan sin TIR. Alcanza para TIR, duration y
  convexidad, y no alcanza para paridad, valor técnico, interés corrido ni vida promedio, que
  necesitan saber cuánto de cada pago es capital. Esas columnas quedan vacías en vez de adivinar.
* **Ficha técnica de BYMA**, para los bullet a tasa fija — con emisión, vencimiento, tasa y la
  certeza de que el capital vuelve entero al final, el flujo queda determinado salvo la frecuencia.
  Al conocerse el desglose renta/capital, acá sí salen paridad, valor técnico e interés corrido.
* **Condiciones de emisión** (`data/ons_catalog.csv`) — permite calcular todo, y hay que cargarlas a
  mano. Una fila del catálogo siempre le gana al resto, porque cargarla es una decisión explícita.

El catálogo viene **vacío a propósito**: mandar cupones verosímiles que nadie verificó devuelve
rendimientos equivocados con apariencia autoritativa. Toda fila que se agregue queda marcada con ⚠️
hasta que se ponga `verificado=si`, y conviene contrastarla contra el prospecto del emisor (vía la
[CNV](https://www.argentina.gob.ar/cnv)), el Informe Diario del [IAMC](https://www.iamc.com.ar)
—que publica TIR, paridad y duration ya calculadas, así que valida los datos cargados *y* el
resultado— o el boletín diario de [BYMA](https://www.byma.com.ar).

### Especies de liquidación

La última letra de un ticker de BYMA es la especie de liquidación, no decoración: **O** liquida en
pesos, **D** en dólar MEP y **C** en dólar cable. `YMCJO`, `YMCJD` e `YMCJC` son el mismo bono de
YPF, pero el primero cotiza alrededor de 152.000 pesos donde los otros cotizan alrededor de 105
dólares.

Dos consecuencias, las dos contempladas:

* La TIR se calcula solo cuando la moneda de la especie coincide con la moneda de emisión del bono.
  Descontar un flujo en dólares contra un precio en pesos no da una TIR un poco equivocada: da una
  TIR sin significado. La especie en pesos muestra precio y liquidez, sin rendimiento.
* El catálogo se busca por raíz del ticker, así que una fila cargada como `YMCJO` cubre también
  `YMCJD` e `YMCJC`. Un ticker exacto le sigue ganando a la raíz, lo que deja lugar a cargar una
  especie puntual con condiciones distintas.

El panel cotiza más de 600 especies contra un catálogo que cubre unas pocas, así que el filtro de
especie arranca en las que liquidan en dólares y la lista de las que no tienen cronograma queda
detrás de un desplegable en vez de dentro del aviso.

### Liquidez

No hay ninguna lista de tickers escrita a mano: el universo sale del feed de precios. Lo que hay que
filtrar es el ruido que trae — las especies que no operaron hoy siguen cotizando el precio de la
última rueda en que sí lo hicieron, así que su rendimiento mide el mercado de otro día.

El filtro de liquidez arranca en el top 50 por volumen, y ofrece top 20 o todas las que operaron.
Sus cortes son relativos y no absolutos porque el feed no documenta en qué unidad expresa el
volumen: "más de 1.000.000" sería un número inventado, "las 20 que más operaron hoy" se sostiene sin
saber la unidad.

Pedir las dos especies en dólares colapsa cada bono a una sola fila, conservando la más operada: MEP
y cable son el mismo bono cobrado en distinto lugar, así que mostrar las dos gastaría la mitad de un
top 50 en repeticiones en vez de emisores distintos.

La moneda se filtra antes del ranking por volumen, y el orden no es cosmético: el volumen de la
especie en pesos está expresado en pesos y el de la especie MEP en dólares, así que rankear
mezclando ambas compara unidades distintas y ganan las filas en pesos por magnitud y no por
actividad.

Las especies que no operaron quedan además fuera de la mediana del panel, por el mismo motivo que
los bonos próximos a vencer: la mediana es la referencia contra la que se califica cada bono, así
que no puede construirse con precios que no son comparables. Siguen visibles en el cuadro; lo único
que se les quita es la influencia sobre la calificación.

### Límites del modelo

* **El cronograma de amortización no se toma de BYMA.** Su ficha técnica trae fecha de emisión,
  vencimiento, cupón, moneda, país de la ley, lámina mínima y monto residual — pero el cronograma
  de amortización viene en prosa libre ("amortizadas en 4 cuotas anuales, es decir el 30 de
  septiembre de 2030, ..."). Parsear eso emisor por emisor es una adivinanza disfrazada de dato, así
  que el cronograma sigue viniendo del flujo de fondos ya resuelto.
* **Solo tasa fija.** Las ONs CER, dollar-linked, Badlar y TAMAR no se pueden modelar acá: su flujo
  futuro no está determinado hoy. Cargar una devolvería una TIR sin sentido.
* Sin cupones escalonados (*step-up*) ni opciones de rescate anticipado (*call/put*).
* Interés corrido en base 30/360; descuento en base ACT/365 con capitalización anual, de modo que la
  TIR informada sea **efectiva anual** y comparable entre bonos de distinta frecuencia de pago.
* La convención de precio (sucio contra limpio) es un selector explícito, porque elegirla mal sesga
  la TIR y la paridad en silencio. BYMA publica precios sucios.

---

## 🪙 Criptomonedas

La tercera sección aplica el mismo semáforo de confluencia del tablero de acciones a un universo de
criptomonedas, agrupado en cuatro conjuntos que se eligen desde la barra lateral: principales por
capitalización, capa 1, DeFi e infraestructura, y memecoins.

### Qué comparte con la sección de acciones

El algoritmo del semáforo es **exactamente el mismo** (`indicators.evaluate_confluence_signal`), con
los mismos umbrales: las mismas condiciones obligatorias de soporte y RSI del lado compra, el mismo
techo con impulso agotándose del lado venta, el mismo squeeze de Bollinger. Leer un retroceso dentro
de una tendencia sana no depende de qué se esté mirando, así que duplicar el algoritmo sería
duplicar el mantenimiento de una sola regla.

### Qué cambia, y por qué

**1. El semáforo se calibra, no se duplica.** El algoritmo es el mismo, pero una de sus condiciones
obligatorias necesita otro número. El lado venta exige "estar en un techo", y en acciones eso se mide
como proximidad al máximo de 52 semanas, porque una acción líder cotiza cerca de sus máximos. En
cripto los drawdowns son de 70-80%: una moneda puede estar con RSI 80, un 50% por encima de su media
de 50 barras, y seguir a 60% de su máximo anual. Medido sobre el panel real, con la calibración de
acciones 19 de 20 monedas salían NEUTRAL teniendo RSI entre 60 y 80. Por eso en cripto se habilita un
camino alternativo: **extensión sobre la media medida en desvíos propios** de cada moneda, que se
adapta sola a lo volátil que sea cada una en vez de fijar un porcentaje arbitrario para todas. La
columna **Extensión** del cuadro muestra ese número.

**2. El calendario.** Cripto opera los 365 días del año; una acción cotiza unas 252 ruedas. El
"máximo de las últimas 52 semanas" son 252 barras allá y **365 acá**, y el squeeze se mide contra
182 barras en vez de 126. Con los números de acciones, el máximo anual de una cripto sería en
realidad el de los últimos ocho meses y medio, y un precio cerca de su techo parecería más alto de
lo que está.

**3. La referencia es Bitcoin, no un índice.** En esta clase de activo casi todo se mueve junto, así
que "subió 8% en el mes" no dice nada por sí solo: si Bitcoin subió 12%, esa moneda perdió terreno.
La columna **vs BTC** mide el exceso de retorno sobre Bitcoin en la ventana larga (30 barras diarias
o 13 semanales), con una banda muerta de ±2 puntos porcentuales: en un activo que se mueve 5% en un
día, dos puntos acumulados en un mes son ruido, no una ventaja. Bitcoin se descarga siempre, esté o
no en el universo elegido.

**4. No hay balances.** No existe el PER, ni el sector, ni el dividendo: una red no publica
resultados trimestrales. En su lugar el cuadro muestra la **volatilidad anualizada** del último mes
—desvío de los retornos logarítmicos, anualizado con la raíz de 365— que es la medida de riesgo que
efectivamente se usa acá. Se usan retornos logarítmicos y no simples porque sobre saltos del 20% en
una barra, corrientes en cripto, los dos dejan de ser intercambiables.

### Sobre el volumen

La columna de flujo es el mismo OBV del tablero de acciones, pero **no se llama "Smart Money"**: el
volumen que publica el proveedor es la suma de decenas de exchanges minoristas, no la huella de un
fondo institucional. Sirve para ver si un movimiento de precio viene acompañado de operaciones o
está vacío; no para deducir quién está del otro lado.

### Las stablecoins quedan afuera

USDT, USDC y DAI no están en el universo, y es una decisión, no un olvido: cotizan pegadas a un
dólar por diseño, así que su RSI, sus medias y sus bandas describen ruido de centésimas y el
semáforo leería ese ruido como si fuera una tendencia.

### Dominancia: ¿Bitcoin o altcoins?

En cripto casi todo se mueve junto, así que la pregunta útil no es cuánto subió una moneda sino si
conviene estar en ella o en Bitcoin. La sección la responde con **dos mediciones distintas, que se
muestran juntas a propósito**:

* **Dominancia**, que mide *dónde está el valor*. Se informan dos números que no son el mismo: la
  **dominancia global** (la porción de todo el mercado cripto que es Bitcoin, contando miles de
  monedas y stablecoins) viene de CoinGecko, y la **dominancia dentro del panel** se reconstruye
  acá. La del panel da más alto —tiene decenas de monedas, no miles— así que de ella se informa la
  **variación en la ventana**, no el nivel: si sube, Bitcoin le está ganando al conjunto.
* **Termómetro de temporada**, que mide *cuántas monedas* le ganan a Bitcoin. Por encima del 75% se
  habla de temporada de altcoins; por debajo del 25%, de temporada de Bitcoin.

Las dos se contradicen seguido, y ahí está lo interesante: si la dominancia sube mientras varias
altcoins le ganan a Bitcoin, la suba de las alts es **angosta** —unas pocas tirando, el resto
quedándose—. Con un solo número esa lectura no aparece.

**Cómo se reconstruye la serie de dominancia.** La capitalización de una moneda es su precio por su
oferta en circulación; con los precios diarios (que hay, por años) y la oferta de hoy se rearma cómo
se movió el reparto del valor. La aproximación es usar la oferta actual para todo el período, porque
el histórico de emisión no está en la fuente: sobre un mes el error es despreciable (Bitcoin emite
~0,1% de su oferta mensual), sobre varios años deja de valer, y por eso la serie se corta en un año.
Es una aproximación honesta para leer rotación de corto plazo, no una reconstrucción histórica.

### Gráfico con soportes y resistencias

Debajo del cuadro hay un gráfico de velas de cualquier moneda del panel (arranca en Bitcoin), con
sus medias de 50 y 200, el volumen, y los niveles donde el precio giró.

La **escala es un selector y arranca en mensual**, porque la escala no es una preferencia visual:
define qué se considera un nivel. En velas diarias de seis meses aparecen los giros de las últimas
semanas; en velas mensuales de varios años aparecen los techos y pisos a los que el precio vuelve.
Cada escala trae sus propios parámetros, medidos sobre el historial real de Bitcoin y no elegidos a
ojo: un entorno de 10 barras son dos semanas en diario y casi un año en mensual.

Los niveles se detectan como **pivotes** —una barra cuyo máximo no es superado por las de su
entorno— y después se agrupan por cercanía porcentual, porque un nivel al que el precio volvió
cuatro veces es el mismo nivel visto cuatro veces, no cuatro líneas pegadas. Lo que distingue un
nivel importante es **cuántas veces el precio lo respetó**.

Cada nivel se dibuja como **zona** y no como línea: el precio no gira en un número exacto sino en
una franja, y una línea de un píxel sugiere una precisión que el nivel no tiene. Relleno y línea
llena a partir de tres toques, punteada y tenue con uno o dos. La etiqueta dice a qué precio está,
cuántas veces se respetó y a qué distancia quedó de hoy. Se dibujan solo los tres más cercanos de
cada lado: con quince líneas siempre hay una cerca del precio y el gráfico deja de decir nada.

### Divergencias

Debajo de las velas hay un panel de **RSI 14** que marca las divergencias entre el precio y su
impulso: el precio hace un máximo más alto pero el RSI uno más bajo (bajista), o el precio hace un
mínimo más bajo y el RSI uno más alto (alcista). Cada una se dibuja con dos segmentos del mismo
color —uno sobre las velas y otro sobre el RSI— porque la divergencia *es* esa comparación, y verla
requiere ver las dos líneas ir en direcciones opuestas.

Se detectan sobre los **mismos giros** que los soportes y resistencias, y con tres filtros para que
la marca signifique algo: los dos giros no pueden estar separados por más de 60 barras (serían dos
tramos distintos del mercado), el RSI tiene que diferir al menos 3 puntos, y el precio al menos 1%
(dos máximos iguales son un doble techo, no una divergencia).

**No son una señal de entrada, y el panel lo dice en pantalla.** Una divergencia puede sostenerse
meses antes de que el precio gire, y en una tendencia fuerte el oscilador se satura y divergir es lo
normal. Por eso se marcan en el gráfico y no entran al semáforo.

### Límites conocidos

* **El universo es una lista mantenida a mano** (`crypto/catalog.py`): no se reordena solo cuando
  cambia el ranking de capitalización.
* **Yahoo redondea el precio de las monedas muy chicas** a un decimal significativo, así que dos
  columnas de variación de ventanas distintas pueden dar el mismo número para una moneda que cotiza
  en millonésimos. No es un error de cálculo del panel.
* **Los tickers de Yahoo no siempre coinciden con el símbolo del mercado**: cuando el símbolo choca
  con otro instrumento, Yahoo le agrega un número (`UNI7083-USD` es Uniswap, `PEPE24478-USD` es
  Pepe). Los del catálogo están verificados contra el feed.

---

## 📁 Estructura del repositorio

```
stock-dashboard/
├── app.py                          # Punto de entrada Streamlit: selector de secciones, filtros de la barra lateral
├── constants.py                    # Única fuente de verdad de etiquetas y umbrales de ambos motores
├── theme.py                        # Paleta de colores centralizada, compartida por el cuadro y los gráficos
├── data_loader.py                  # Descarga paralela de precios y fundamentales de acciones, caché y agregación
├── indicators.py                   # Matemática de indicadores (SMA/EMA/RSI/MACD/Bollinger/Estocástico/OBV/52S) y confluencia
├── bonds/
│   ├── __init__.py                 # Paquete de renta fija para ONs argentinas
│   ├── bond_math.py                # Flujo de fondos, TIR, duration, convexidad, paridad, interés corrido (puro, sin I/O)
│   ├── byma_source.py              # Precios de BYMA Open Data; el parseo es una función pura
│   ├── byma_terms.py               # Ficha técnica por especie: emisor, ley, lámina, garantía, default
│   ├── catalog.py                  # Lee y valida data/ons_catalog.csv; helpers de especie de liquidación
│   ├── flows_source.py             # Descarga los cronogramas de pago publicados (dataset comunitario)
│   ├── panel.py                    # Cruce puro de precios + condiciones + métricas, y los filtros del panel
│   ├── scoring.py                  # Puntaje de Oportunidad ponderado, relativo al panel del día
│   └── data_loader.py              # Solo I/O: precios, curva del Tesoro, orquestación cacheada
├── crypto/
│   ├── __init__.py                 # Paquete del motor de criptomonedas
│   ├── catalog.py                  # Universo de criptos: ticker de Yahoo, símbolo, nombre y categoría (puro)
│   ├── panel.py                    # Métricas del cuadro: calendario de 365 días, fuerza vs BTC, volatilidad (puro)
│   ├── dominance.py                # Dominancia reconstruida, rotación y termómetro de temporada (puro)
│   ├── levels.py                   # Soportes y resistencias por pivotes agrupados (puro)
│   ├── prices_source.py            # Descarga del OHLCV en Yahoo; toca red, no Streamlit
│   ├── market_source.py            # Capitalización y oferta (Yahoo) + dominancia global (CoinGecko)
│   └── data_loader.py              # Solo I/O: orquestación cacheada del panel
├── data/
│   └── ons_catalog.csv             # Condiciones de emisión opcionales por ON; vacío por defecto
├── components/
│   ├── __init__.py
│   ├── alerts_panel.py             # Tarjetas de alertas rápidas agrupadas por grado de señal
│   ├── bonds_panel.py              # La sección de Bonos completa: controles, KPIs, filtros, glosario y metodología
│   ├── bonds_table.py              # Cuadro comparativo de ONs con formato condicional y ayuda por columna
│   ├── charts.py                   # Gráfico técnico de 4 paneles y dispersión valuación vs momento
│   ├── crypto_chart.py             # Velas con soportes/resistencias y gráfico de dominancia
│   ├── crypto_panel.py             # La sección de Cripto completa: controles, alertas, KPIs, filtros y metodología
│   ├── crypto_table.py             # Cuadro de criptomonedas con formato adaptativo de precio y volumen
│   ├── formatting.py               # Helpers de formato de texto compartidos
│   ├── kpi_cards.py                # Tarjetas de KPIs de amplitud de mercado y valuación
│   ├── screener_table.py           # Tabla interactiva del screener con resaltado condicional
│   └── ticker_detail.py            # Vista de detalle por ticker; todavía no conectada a app.py
├── scripts/
│   ├── verificar_fuentes.py        # Diagnóstico de las fuentes de datos y comparación entre feeds
│   ├── panel_ons.py                # El panel de ONs en la terminal, con el mismo motor que la interfaz
│   └── panel_cripto.py             # El panel de cripto en la terminal, con el mismo motor que la interfaz
├── tests/
│   ├── conftest.py                 # Fixtures compartidas (series sintéticas deterministas)
│   ├── test_52w_high_low.py        # compute_52w_high_low
│   ├── test_bollinger.py           # compute_bollinger_bands
│   ├── test_bond_catalog.py        # Parser del catálogo de ONs y su reporte de errores
│   ├── test_bond_filters.py        # Filtros del panel y el orden en que se aplican
│   ├── test_bond_math.py           # Matemática de renta fija (flujos, TIR, duration, paridad)
│   ├── test_bond_score.py          # Puntaje de Oportunidad ponderado
│   ├── test_bond_scoring.py        # Etiquetas de atractivo y casos excluyentes
│   ├── test_bonds_panel.py         # Cruce precios/condiciones, prioridad de fuentes e interpolación de la curva
│   ├── test_byma_source.py         # Parseo de la respuesta de precios de BYMA
│   ├── test_byma_terms.py          # Parseo de la ficha técnica de BYMA
│   ├── test_flows_source.py        # Parser de los cronogramas publicados
│   ├── test_compute_stock_technicals.py
│   ├── test_confluence_signal.py   # evaluate_confluence_signal
│   ├── test_crypto_catalog.py      # Integridad del universo cripto y de sus grupos
│   ├── test_crypto_dominance.py    # Reconstrucción de la dominancia, rotación y temporada
│   ├── test_crypto_levels.py       # Pivotes, agrupamiento de niveles y soportes/resistencias
│   ├── test_crypto_panel.py        # Calendario de 365 días, fuerza vs BTC, volatilidad, filtros y formato de precio
│   ├── test_obv.py                 # compute_obv
│   ├── test_rsi.py                 # compute_rsi
│   ├── test_sma_ema_macd.py        # compute_sma / compute_ema / compute_macd
│   └── test_stochastic.py          # compute_stochastic
├── .github/workflows/ci.yml        # CI: corre ruff y pytest en push/PR contra main, en Python 3.11 y 3.14
├── requirements.txt                # Dependencias de ejecución
├── requirements-dev.txt            # Agrega pytest y ruff, para desarrollo y CI
├── ruff.toml                       # Configuración del linter
├── pytest.ini                      # Configuración de pytest
├── .python-version                 # Fija la versión de Python (3.11) para las herramientas locales
├── run.sh                          # Setup del entorno virtual y lanzamiento, en un solo paso
├── LICENSE                         # Licencia MIT
└── .gitignore
```

---

## 🚀 Puesta en marcha

### Requisitos
* Python 3.11 o superior
* Git

### 1. Clonar el repositorio
```bash
git clone https://github.com/JulianWaksmann/stock-dashboard.git
cd stock-dashboard
```

### 2. Crear el entorno virtual e instalar dependencias
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Levantar el tablero
```bash
streamlit run app.py
```
O directamente con el script de arranque:
```bash
./run.sh
```

La aplicación se abre en el navegador en `http://localhost:8501`.

### Herramientas de línea de comandos

```bash
# Diagnóstico de las fuentes: qué responde cada una, con qué campos y cuántos registros
python3 scripts/verificar_fuentes.py

# El panel de ONs en la terminal, con el mismo motor y los mismos filtros que la interfaz
python3 scripts/panel_ons.py --top 20 --desglose

# El panel de criptomonedas en la terminal, con el mismo motor que la interfaz
python3 scripts/panel_cripto.py --grupo memes --semanal
```

---

## 🛠️ Desarrollo

### Instalar dependencias de desarrollo
```bash
pip install -r requirements-dev.txt
```
Instala las dependencias de ejecución más `pytest` y `ruff`.

### Correr los tests
```bash
pytest
```

### Correr el linter
```bash
ruff check .
```

### Integración continua
Cada push y cada pull request contra `main` corre `ruff check .` y `pytest` vía GitHub Actions (ver
`.github/workflows/ci.yml`), en Python 3.11 y 3.14. Un PR no es mergeable si alguno de los dos
pasos falla.

### Dónde se cambian las cosas
* Etiquetas y umbrales de la señal de confluencia: `constants.py`.
* Etiquetas, umbrales y pesos del puntaje de bonos: `constants.py`, sección "BONOS CORPORATIVOS".
* Condiciones de emisión de una ON (cupón, vencimiento, amortizaciones, ley): `data/ons_catalog.csv`.
* El dataset de cronogramas de pago: `COMMUNITY_FLOWS_URL` en `bonds/flows_source.py`.
* La fuente de precios de bonos: `bonds/byma_source.py`. Su parseo es una función pura, así que otra
  fuente entra normalizando a las mismas columnas.
* Ventanas de calendario, referencia y textos de la sección de cripto: `constants.py`, sección
  "CRIPTOMONEDAS".
* Calibración del semáforo por clase de activo: `indicators.ConfluenceThresholds` (los números, en
  `constants.py`).
* Sensibilidad de los soportes y resistencias (ancho del pivote, agrupamiento, cuántos se dibujan):
  `constants.py`, bloque de niveles.
* Qué criptomonedas integran cada universo: `crypto/catalog.py`.
* Colores del cuadro y de los gráficos: `theme.py`.

---

## ☁️ Despliegue (Streamlit Community Cloud)

1. Subí este repositorio a tu cuenta de GitHub: `https://github.com/JulianWaksmann/stock-dashboard`.
2. Entrá a [share.streamlit.io](https://share.streamlit.io) e iniciá sesión con GitHub.
3. Hacé clic en **"New app"**, elegí el repositorio y la rama (`main`), y poné `app.py` como archivo principal.
4. Hacé clic en **"Deploy"**.

---

## 📊 Fórmulas de referencia

$$\text{Distancia a la SMA}\% = \frac{\text{Precio} - \text{SMA}}{\text{SMA}} \times 100$$

$$\text{Ancho de Bollinger}\% = \frac{\text{Banda Superior} - \text{Banda Inferior}}{\text{Banda Media}} \times 100$$

$$\text{Distancia al Máx. 52S}\% = \frac{\text{Precio} - \text{Máx}_{252}}{\text{Máx}_{252}} \times 100$$

$$\text{Paridad}\% = \frac{\text{Precio}}{\text{Capital Residual} + \text{Interés Corrido}} \times 100$$

---

## 📄 Licencia

Proyecto bajo **Licencia MIT** — ver [`LICENSE`](LICENSE) para el texto completo.

---

## ⚠️ Advertencia
*Este proyecto está construido con fines de investigación y screening cuantitativo. No constituye
asesoramiento financiero. El rendimiento pasado y los indicadores cuantitativos no garantizan
resultados futuros. Los datos provienen de fuentes públicas sin garantía de exactitud: verificá
todo contra tu broker o contra el boletín oficial de BYMA antes de operar.*
