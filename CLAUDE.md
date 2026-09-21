# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

El código, los docstrings, los comentarios y toda la interfaz están en **castellano**. Los mensajes de commit recientes están en inglés. Al escribir código nuevo, seguí esa convención: prosa en castellano dentro del código, commits en inglés.

## Comandos

```bash
# Entorno (la primera vez, o si faltan dependencias)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # incluye requirements.txt + pytest + ruff

# Levantar el tablero
streamlit run app.py     # o ./run.sh, que arma el venv e instala antes de arrancar

# Tests
pytest
pytest tests/test_bond_math.py                          # un archivo
pytest tests/test_rsi.py::TestRegresionCalentamiento      # una clase (los tests están agrupados en clases)
pytest tests/test_rsi.py::TestRegresionCalentamiento::test_primeras_period_barras_son_nan
pytest -k "duration"                                      # por patrón

# Linter (mismo comando que corre CI)
ruff check .
ruff check . --fix

# Verificar los pipelines sin levantar Streamlit
python3 scripts/panel_ons.py --top 20 --desglose
python3 scripts/panel_cripto.py --grupo memes
python3 scripts/verificar_fuentes.py    # diagnóstico de las fuentes de datos
```

El `.venv/` del repo **no** trae `pytest` ni `ruff` instalados: corré `pip install -r requirements-dev.txt` antes de testear o lintear.

CI (`.github/workflows/ci.yml`) corre `ruff check .` y `pytest` en **Python 3.11 y 3.14** en cada push/PR contra `main`. Los dos extremos se testean a propósito: un techo de dependencia sin wheel para el Python desplegado ya rompió producción una vez (ver el comentario de política de pinning en `requirements.txt` — no ajustes techos sin leerlo).

## Arquitectura

Son **tres motores independientes** que comparten el dashboard pero no el modelo de datos: acciones (osciladores de precio), bonos corporativos argentinos (valor presente del flujo de fondos contractual) y criptomonedas (los mismos osciladores, otro calendario y otra referencia). `app.py` los reparte con un selector.

Cripto y acciones comparten `indicators.py` —la lectura técnica es la misma— pero no el modelo de datos: una cripto no tiene balances, así que no hay PER ni sector, y opera los siete días, así que las ventanas de calendario se miden en otra cantidad de barras.

### Regla de capas (se respeta en los dos motores)

```
I/O con red + Streamlit  →  cálculo puro  →  dibujo
```

* **Puro (sin red, sin `streamlit`)**: `indicators.py`, `bonds/bond_math.py`, `bonds/panel.py`, `bonds/scoring.py`, `bonds/catalog.py`, `crypto/panel.py`, `crypto/catalog.py`, y el *parseo* de `bonds/byma_source.py` / `bonds/flows_source.py`. Esto es lo que la suite de tests verifica con datos fijos, sin mocks de red.
* **I/O**: `data_loader.py` (acciones), `bonds/data_loader.py` (bonos) y `crypto/data_loader.py` (cripto) — los únicos que tocan `st.cache_data`. `crypto/prices_source.py` toca la red pero no Streamlit, igual que `bonds/byma_source.py`.
* **Dibujo**: `components/`.

No metas lógica de negocio en `components/` ni `streamlit` en los módulos puros: `scripts/panel_ons.py` y `scripts/panel_cripto.py` corren exactamente la misma cadena desde la terminal y se rompen si esa separación se pierde.

### `constants.py` es la única fuente de verdad

Etiquetas de señal, umbrales numéricos y **textos de las opciones de cada selector** viven todos ahí, para ambos motores. Los selectores de Streamlit comparan la opción elegida contra su propio texto en un `if/elif`: si ese literal se escribe suelto en dos lugares, editás uno y el filtro deja de funcionar en silencio, sin error. Ajustar una regla de trading significa editar `constants.py`, no `indicators.py` ni `app.py`.

`theme.py` cumple el mismo rol para los colores (el par positivo/negativo es `#26a69a` / `#ef5350`, unificado entre tabla y gráficos).

### Acciones

`data_loader.load_all_stocks_data(tickers, timeframe)` → `(df_summary, dict_history)`, cacheado 5 min. Descarga precios en bloque con `yf.download` y fundamentales en paralelo con `ThreadPoolExecutor`; los tickers que fallan no cortan la carga, se acumulan en `df_summary.attrs["failed_tickers"]`.

`df_summary` tiene **columnas duplicadas a propósito**: las de nombre en castellano con sufijo de temporalidad (`"Dif. % SMA 50 (Día)"` / `" (Sem)"`) son para mostrar, y las de nombre estable en mayúsculas (`RSI_VAL`, `DIFF_SMA_200_VAL`, `DIST_52W_HIGH_PCT`, `BB_BANDWIDTH`) son las que usan filtros y KPIs, para no tener que reconstruir el nombre según la temporalidad elegida.

`indicators.evaluate_confluence_signal` es el semáforo: condiciones **obligatorias** (soporte + RSI del lado compra; techo + RSI del lado venta) que habilitan el conteo, y opcionales que suman puntos hasta decidir FUERTE vs MODERADA. Squeeze y NEUTRAL son los estados de descarte.

### Bonos (ONs argentinas)

Dos fuentes de conocimiento sobre cada bono, y hacen falta las dos:

* **Precios en vivo**: BYMA Open Data (`bonds/byma_source.py`). Es **POST**, no GET, y valida cookie de sesión del propio sitio. El feed alternativo (data912) se descartó tras medirlo; está documentado en el docstring del módulo.
* **Condiciones de emisión** (cupón, amortizaciones, ley): `data/ons_catalog.csv`, cargado a mano, con marca `verificado` por fila. Es **dato editable, no código**. Un cupón mal cargado no rompe nada: devuelve una TIR mansamente incorrecta.
* **Cronogramas de pago resueltos**: dataset comunitario (`bonds/flows_source.py`). Da cobertura sin mantenimiento manual, pero no separa renta de amortización, así que paridad, valor técnico y vida promedio quedan en blanco salvo que el bono también esté en el catálogo local.

Dos invariantes que es fácil romper:

1. **Especie de liquidación.** En BYMA el mismo bono cotiza en tres especies según la última letra del ticker (`O` pesos, `D` MEP, `C` cable). Descontar un flujo en dólares contra un precio en pesos da una TIR sin sentido económico: el panel calcula rendimiento **solo** cuando la moneda de la especie coincide con la de emisión.
2. **Puntaje relativo, no absoluto.** Un bono se puntúa contra sus pares del panel de ese día (mediana de TIR), no contra umbrales fijos. La mediana se mueve con el riesgo argentino, así que un "TIR > 9%" diría cosas opuestas en dos momentos del ciclo.

### Criptomonedas

`crypto/data_loader.load_crypto_panel(universe, timeframe)` → `df`, cacheado 5 min. Baja el OHLCV de Yahoo con `crypto/prices_source.py` y se lo pasa a `crypto/panel.build_crypto_panel`, que es quien calcula. El universo sale de `crypto/catalog.py` (código, no CSV: acá no hay condiciones contractuales que cargar a mano).

El semáforo es **el mismo** que el de acciones: se reusa `indicators.evaluate_confluence_signal` sin tocar sus umbrales. Lo que cambia es el contexto, y son tres cosas que es fácil romper:

1. **El calendario.** Cripto opera los 365 días del año. Por eso `compute_stock_technicals` recibe `window_52w` y `squeeze_lookback` como parámetros: con los 252/126 de una acción, el "máximo de 52 semanas" de una cripto sería el de los últimos ocho meses y medio, y un precio cerca del techo parecería más alto de lo que está. Las ventanas por temporalidad viven en `crypto/panel.TimeframeSpec`, no sueltas por el módulo.
2. **La referencia es Bitcoin, no un índice.** Casi todo se mueve junto con BTC, así que un retorno aislado no dice nada: la columna `vs BTC` mide el exceso sobre Bitcoin en la ventana larga, con una banda muerta de ±2 pp porque en este activo dos puntos en un mes son ruido. Bitcoin se descarga **siempre**, esté o no en el universo elegido (si no, mirar solo memecoins dejaría la columna en blanco).
3. **Las stablecoins están excluidas a propósito.** Cotizan pegadas a un dólar por diseño: su RSI y sus bandas describen ruido de centésimas y el semáforo lo leería como tendencia. Hay un test que lo fija.

Tres cosas más que conviene saber antes de tocar el módulo:

4. **El semáforo se calibra, no se duplica.** `evaluate_confluence_signal` recibe `ConfluenceThresholds`; acciones usa `STOCK_THRESHOLDS` (los valores de siempre) y cripto `CRYPTO_THRESHOLDS`, que solo cambia un número: enciende el camino de "techo por extensión sobre la media". Sin ese camino el lado venta no dispara nunca en cripto, porque exige estar a menos de 6% del máximo anual y acá los drawdowns son de 70%. Medido sobre el panel real: con la calibración de acciones, 19 de 20 monedas salían NEUTRAL con RSI entre 60 y 80. El porqué está en `indicators._sell_near_ceiling`.
5. **Dominancia**: `crypto/dominance.py` es puro y `crypto/market_source.py` trae los datos (capitalización y oferta de Yahoo; dominancia global de CoinGecko). Ninguna de las dos fuentes secundarias puede tumbar la sección: si fallan, el cuadro se arma igual sin esas columnas.
6. **Divergencias**: `crypto/divergences.py`, puro, y se apoya en los **mismos pivotes** que los niveles (`find_pivots`). No es una economía: si un giro merece una línea en el gráfico, es el mismo giro que tiene sentido comparar contra el siguiente; dos detectores distintos marcarían niveles en un lado y divergencias en otro. Alimentan el gráfico y **no** el semáforo a propósito: una divergencia puede sostenerse meses sin que el precio gire.
7. **Niveles del gráfico**: `crypto/levels.py`, también puro. Pivotes agrupados por cercanía porcentual; lo que distingue un nivel fuerte es la **cantidad de toques**. La escala (mensual/semanal/diaria) tiene sus propios parámetros en `CRYPTO_CHART_SCALE_PARAMS`, **medidos** sobre el historial de BTC: en mensual hay 145 barras en doce años, así que con entorno ±2 meses los niveles salían todos con un solo toque y con ±1 mes y 8% de tolerancia salen seis zonas de dos toques. Si cambiás esos valores, medí antes.

El cuadro duplica columnas con el mismo criterio que el de acciones: nombre en castellano con sufijo de temporalidad para mostrar, nombre estable en mayúsculas (`RSI_VAL`, `DIFF_SMA_200_VAL`, `RS_BTC_PP`, `VOL_ANN_PCT`, `PRECIO_VAL`, `EXTENSION_SIGMAS`, `MARKET_CAP_VAL`) para filtros, KPIs y alertas.

### Por qué selector y no `st.tabs`

Streamlit ejecuta el cuerpo de **todas** las pestañas en cada corrida. Con `st.tabs`, mirar acciones dispararía igual la descarga de precios de ONs y de la curva del Tesoro. El `st.radio` de `app.main()` dibuja solo la sección elegida. No lo cambies a pestañas nativas.

## Estado actual (no dar por terminado)

* **País de bonos: el desplegable existe, EEUU no.** `BOND_COUNTRY_OPTIONS` en `constants.py` y la rama en `render_bonds_panel()` son el punto de extensión; hoy EEUU muestra "en desarrollo". Lo que falta para sumar un país es fuente de precios + catálogo de emisiones, no matemática: `bonds/bond_math.py` ya es agnóstico. Evitá esparcir `if país` por el módulo — la rama vive en el panel.
* **La cobertura del cuadro argentino es el problema abierto**, y no es BYMA: el feed devuelve ~2700 especies sin problemas. El embudo medido es cronograma de pagos (≈140 especies) → TIR calculable (≈85) → que además operaron hoy (≈13). El catálogo local `data/ons_catalog.csv` está **vacío** (solo comentarios), y por eso paridad, valor técnico, interés corrido, vida promedio y ley salen sin datos para todo el panel: el cronograma comunitario publica el total de cada pago sin separar renta de capital. Cargar el catálogo es la única palanca, y es data entry contra prospectos.
* **El scraping de BYMA sigue sin pulir** (`bonds/byma_source.py`): API no documentada, sin contrato de estabilidad, campos de precio y volumen elegidos por orden de preferencia porque BYMA no aclara cuál es cuál.
* **Sin conectar**: `components/ticker_detail.py` y `components/charts.py` están escritos y testeados, pero `app.py` todavía no los usa.
* **La dominancia del panel no es la dominancia global, y se muestran las dos.** La global viene de CoinGecko (un pedido, sin clave); la del panel se reconstruye acá con `precio × oferta circulante` y por eso da más alto (el panel tiene decenas de monedas, el mercado tiene miles). De la del panel se informa la **variación**, no el nivel. La reconstrucción usa la oferta de hoy para todo el período: vale para leer rotación de un mes, no para reconstruir capitalizaciones históricas, y por eso la serie se corta en un año.
* **El volumen de cripto es un agregado de exchanges.** Sirve para ver si un movimiento viene acompañado o está vacío; no para deducir quién está del otro lado. Por eso la columna se llama "Flujo de Volumen (OBV)" y no "Smart Money", aunque la cuenta sea la misma.

## Trampas conocidas

* **Streamlit dibuja un `NaN` numérico como el texto "None"**, no como celda vacía. Pasa con y sin `column_config`, y es de la librería (verificado en 1.62). Por eso `render_bonds_table` oculta las columnas que vienen 100% vacías: si no, una columna sin datos no se ve vacía, se ve rota.
* **El puntaje se rankea contra el subconjunto comparable, no contra el panel entero.** `compute_opportunity_scores` recibe `comparable` y **hay que pasárselo**. Omitirlo no falla ni avisa: como TIR y duration solo existen en una fracción mínima de las ~2700 especies, esas dimensiones caen bajo `BOND_SCORE_MIN_DIMENSION_COVERAGE`, se descartan para todos, y el cuadro entero sale "⚪ SIN DATOS". Cubierto por `TestPuntajeSobreUnPanelRealista`.
* **Precio de cripto: ningún formato fijo sirve para toda la tabla.** Conviven Bitcoin en decenas de miles de dólares y monedas de cinco millonésimos; con dos decimales media tabla muestra "$0.00". Por eso precio y volumen pasan por `format_crypto_price` / `format_usd_compact` y se muestran como texto, a costa de que esas dos columnas ordenen alfabéticamente. Es un costo aceptado: comparar el precio nominal de dos criptos no significa nada (depende de cuántas unidades se emitieron).
* **Los dos caminos de descarga de cripto devolvían el índice con distinta zona horaria.** `yf.download` lo trae sin zona y el reintento individual (`Ticker.history`) con zona; alinear uno contra otro revienta con "Cannot join tz-naive with tz-aware", y solo los días en que alguna moneda cae al reintento. Se normaliza en `crypto/prices_source._normalizar_indice`, en la frontera de I/O. No quites esa normalización.
* **Yahoo redondea el precio de las monedas muy chicas a un decimal significativo.** SHIB tiene 31 precios distintos en 731 ruedas. Dos consecuencias, las dos verificadas en pantalla: columnas de variación de ventanas distintas que dan el mismo número (no es un error de cálculo), y mesetas planas donde *toda* barra es máximo local — eso inflaba el conteo de toques de un nivel a 117. Lo resuelve `crypto/levels._colapsar_eventos`, que reduce a un pivote las barras contiguas del mismo giro; no lo quites.
* **El `.venv/` del repo tiene rutas viejas** (se creó cuando el proyecto vivía en `~/Documents/stock-dashboard`, sin `finanzas/`). `.venv/bin/pip` falla con "bad interpreter"; usá `.venv/bin/python -m pip`. Recrearlo desde cero lo arregla.
