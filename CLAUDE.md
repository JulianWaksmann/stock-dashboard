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
python3 scripts/panel_merval.py --ccl   # dólar implícito par por par: verifica los ratios de ADR
python3 scripts/medir_semaforo.py --horizonte 20 60       # ¿funcionó el semáforo?
python3 scripts/medir_semaforo.py --mercado cripto
python3 scripts/verificar_fuentes.py    # diagnóstico de las fuentes de datos
```

El `.venv/` del repo **no** trae `pytest` ni `ruff` instalados: corré `pip install -r requirements-dev.txt` antes de testear o lintear.

CI (`.github/workflows/ci.yml`) corre `ruff check .` y `pytest` en **Python 3.11 y 3.14** en cada push/PR contra `main`. Los dos extremos se testean a propósito: un techo de dependencia sin wheel para el Python desplegado ya rompió producción una vez (ver el comentario de política de pinning en `requirements.txt` — no ajustes techos sin leerlo).

## Arquitectura

Arriba de todo se elige entre **Confluencia** (el tablero de mercado) y **Mi cartera** (ver más abajo). Confluencia son **tres motores independientes** que comparten el dashboard pero no el modelo de datos: acciones (osciladores de precio), bonos corporativos argentinos (valor presente del flujo de fondos contractual) y criptomonedas (los mismos osciladores, otro calendario y otra referencia). `app.py` los reparte con un selector.

El motor de acciones sirve **dos mercados**: Estados Unidos (`data_loader.py`) y Argentina (`merval/`). Comparten todo lo que se dibuja —`components/stocks_body.py`— y todo lo que se filtra —`stock_screener.py`—; lo único propio del argentino es de dónde salen los precios y en qué moneda están medidos.

Cripto y acciones comparten `indicators.py` —la lectura técnica es la misma— pero no el modelo de datos: una cripto no tiene balances, así que no hay PER ni sector, y opera los siete días, así que las ventanas de calendario se miden en otra cantidad de barras.

### Regla de capas (se respeta en los dos motores)

```
I/O con red + Streamlit  →  cálculo puro  →  dibujo
```

* **Puro (sin red, sin `streamlit`)**: `indicators.py`, `stock_screener.py`, `signal_stats.py`, `levels.py`, `divergences.py`, `merval/catalog.py`, `merval/ccl.py`, `merval/splits.py`, `bonds/curve.py`, `bonds/bond_math.py`, `bonds/panel.py`, `bonds/scoring.py`, `bonds/catalog.py`, `crypto/panel.py`, `crypto/catalog.py`, `cartera/modelo.py`, `cartera/balanz.py`, `cartera/cocos.py`, `cartera/lectura.py`, `cartera/informe.py`, y el *parseo* de `bonds/byma_source.py` / `bonds/flows_source.py`. Esto es lo que la suite de tests verifica con datos fijos, sin mocks de red.
* **I/O**: `data_loader.py` (acciones), `merval/data_loader.py` (acciones argentinas), `bonds/data_loader.py` (bonos) y `crypto/data_loader.py` (cripto) — los únicos que tocan `st.cache_data`. `crypto/prices_source.py` toca la red pero no Streamlit, igual que `bonds/byma_source.py`.
* **Dibujo**: `components/`.

No metas lógica de negocio en `components/` ni `streamlit` en los módulos puros: `scripts/panel_ons.py`, `scripts/panel_cripto.py`, `scripts/panel_merval.py` y `scripts/medir_semaforo.py` corren exactamente la misma cadena desde la terminal y se rompen si esa separación se pierde.

### `constants.py` es la única fuente de verdad

Etiquetas de señal, umbrales numéricos y **textos de las opciones de cada selector** viven todos ahí, para ambos motores. Los selectores de Streamlit comparan la opción elegida contra su propio texto en un `if/elif`: si ese literal se escribe suelto en dos lugares, editás uno y el filtro deja de funcionar en silencio, sin error. Ajustar una regla de trading significa editar `constants.py`, no `indicators.py` ni `app.py`.

`theme.py` cumple el mismo rol para los colores (el par positivo/negativo es `#26a69a` / `#ef5350`, unificado entre tabla y gráficos).

`theme.py` también tiene los tokens de **marca** (`COLOR_BRAND*`, superficies, radios, tipografía) y `components/branding.py` es la única hoja de estilos global: la inyecta `app.main()` una vez por corrida y de ahí salen la cabecera, el selector de secciones como control segmentado y las métricas en tarjeta. La carcasa es violeta sobre lavanda, tomada de la landing del producto. Dos reglas: el violeta de marca (`COLOR_BRAND`) es de la carcasa y nunca representa el signo de un número —para eso están `COLOR_POSITIVE` / `COLOR_NEGATIVE`—, y el CSS suelto no vuelve a `app.py` ni a los paneles. Elegir un violeta es parte de la regla: ningún número de una tabla de precios es violeta, así que la carcasa y el dato no compiten. Cuando la marca era verde sí competían, y por eso `COLOR_SMA_200` dejó de ser violeta (`#9333ea`): dentro del mismo gráfico se confundía con el chrome.

**No hay barra lateral.** La escondía entera el CSS de `branding.py` y los controles que vivían ahí se dibujan en el cuerpo, dentro de un `st.container(border=True)` arriba del título de cada sección: mercado y temporalidad en acciones (`app._render_controles_acciones`), país en bonos y universo + temporalidad en cripto (`_render_controles` de cada panel). El reparto que antes separaba barra lateral de cuerpo sigue valiendo, pero ahora es arriba contra abajo: arriba lo que dispara una descarga, abajo el tamiz que recorta un panel ya bajado. Los controles van **antes** del título porque el mercado elegido es el que decide qué título se dibuja. **El tablero se dibuja sobre fondo claro**, y eso condiciona tres archivos a la vez: `.streamlit/config.toml` fija el modo claro de Streamlit, `theme.py` elige cada color contra blanco (un cian neón o un amarillo pálido, legibles sobre negro, ahí desaparecen) y los gráficos usan `PLOTLY_TEMPLATE` —otro token de `theme.py`— en vez de escribir el template suelto. Los tres se mueven juntos o no se mueve ninguno. Los valores de `config.toml` duplican tokens de `theme.py` porque Streamlit lee ese archivo antes de importar el código.

### Acciones

`data_loader.load_all_stocks_data(tickers, timeframe)` → `(df_summary, dict_history)`, cacheado 5 min. Descarga precios en bloque con `yf.download` y fundamentales en paralelo con `ThreadPoolExecutor`; los tickers que fallan no cortan la carga, se acumulan en `df_summary.attrs["failed_tickers"]`.

`df_summary` tiene **columnas duplicadas a propósito**: las de nombre en castellano con sufijo de temporalidad (`"Dif. % SMA 50 (Día)"` / `" (Sem)"`) son para mostrar, y las de nombre estable en mayúsculas (`RSI_VAL`, `DIFF_SMA_200_VAL`, `DIST_52W_HIGH_PCT`, `BB_BANDWIDTH`) son las que usan filtros y KPIs, para no tener que reconstruir el nombre según la temporalidad elegida.

Esa fila la arma `data_loader.build_summary_row`, que es **pura** y es el contrato entre la descarga y todo lo que dibuja (cuadro, KPIs, alertas, ficha de detalle y gráficos, que la indexan por nombre). Un nombre que cambia y nadie actualiza no falla en el cálculo: falla en pantalla, con un `KeyError` o con un `row.get()` que devuelve el valor por omisión y parece un dato. Por eso tiene su propio test (`tests/test_stock_summary_contract.py`), que además dibuja los gráficos sobre un panel sintético — es la única forma de verificar las columnas que viven dentro de un `customdata` de Plotly.

`indicators.evaluate_confluence_signal` es el semáforo: condiciones **obligatorias** (soporte + RSI del lado compra; techo + RSI del lado venta) que habilitan el conteo, y opcionales que suman puntos hasta decidir FUERTE vs MODERADA. Squeeze y NEUTRAL son los estados de descarte.

### Bonos (ONs argentinas)

Dos fuentes de conocimiento sobre cada bono, y hacen falta las dos:

* **Precios en vivo**: BYMA Open Data (`bonds/byma_source.py`). Es **POST**, no GET, y valida cookie de sesión del propio sitio. El feed alternativo (data912) se descartó tras medirlo; está documentado en el docstring del módulo.
* **Condiciones de emisión** (cupón, amortizaciones, ley): `data/ons_catalog.csv`, cargado a mano, con marca `verificado` por fila. Es **dato editable, no código**. Un cupón mal cargado no rompe nada: devuelve una TIR mansamente incorrecta.
* **Cronogramas de pago resueltos**: dataset comunitario (`bonds/flows_source.py`). Da cobertura sin mantenimiento manual, pero no separa renta de amortización, así que paridad, valor técnico y vida promedio quedan en blanco salvo que el bono también esté en el catálogo local.

La **curva de rendimientos** (`bonds/curve.py`, puro, dibujada por `components/bonds_chart.py`) es lo que el cuadro no puede mostrar: una tabla ordena por TIR, y la TIR de un bono a un año y la de uno a cinco no son comparables. Ajusta `TIR ≈ a + b·ln(1 + duration)` por moneda y mide el residuo de cada especie contra la curva de sus pares. El ajuste excluye lo que lo distorsionaría —emisores en default, que cotizan a precio de recupero— pero igual les calcula el residuo, y el corte para llamar barato o caro es relativo a la dispersión del propio panel, como todo el resto del puntaje.

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
6. **Divergencias**: `divergences.py`, puro, y se apoya en los **mismos pivotes** que los niveles (`find_pivots`). No es una economía: si un giro merece una línea en el gráfico, es el mismo giro que tiene sentido comparar contra el siguiente; dos detectores distintos marcarían niveles en un lado y divergencias en otro. Alimentan el gráfico y **no** el semáforo a propósito: una divergencia puede sostenerse meses sin que el precio gire.
7. **Niveles del gráfico**: `levels.py`, también puro. Pivotes agrupados por cercanía porcentual; lo que distingue un nivel fuerte es la **cantidad de toques**. La escala (mensual/semanal/diaria) tiene sus propios parámetros en `CRYPTO_CHART_SCALE_PARAMS`, **medidos** sobre el historial de BTC: en mensual hay 145 barras en doce años, así que con entorno ±2 meses los niveles salían todos con un solo toque y con ±1 mes y 8% de tolerancia salen seis zonas de dos toques. Si cambiás esos valores, medí antes.

El cuadro duplica columnas con el mismo criterio que el de acciones: nombre en castellano con sufijo de temporalidad para mostrar, nombre estable en mayúsculas (`RSI_VAL`, `DIFF_SMA_200_VAL`, `RS_BTC_PP`, `VOL_ANN_PCT`, `PRECIO_VAL`, `EXTENSION_SIGMAS`, `MARKET_CAP_VAL`) para filtros, KPIs y alertas.

### Acciones argentinas (Merval), en dólares

El precio en pesos mezcla lo que vale la empresa con lo que dejó de valer el peso: una media de 200 ruedas sube sola y el RSI marca sobrecompra en cada salto devaluatorio. Por eso el panel argentino **convierte a dólares antes de calcular nada**.

El tipo de cambio sale del propio panel: trece empresas cotizan también en Nueva York, y cada par da un dólar implícito (`precio local × acciones por ADR ÷ precio del ADR`). Se usa la **mediana** de los pares, no el promedio: así un ratio mal cargado en `merval/catalog.py` queda como valor extremo y no mueve el resultado. `merval/ccl.py` publica además un diagnóstico por par con el ratio que lo volvería consistente, y `scripts/panel_merval.py --ccl` es la forma práctica de verificar la tabla contra precios reales (medido el 2026-10-18: los trece pares coinciden dentro de 0,9%).

Dos trampas propias de este mercado:

1. **Los ratios de ADR cambian** con cada split o reestructuración, y ninguno está verificado contra el programa del emisor: están verificados contra la consistencia del panel, que detecta un ratio absurdo pero no distingue entre dos plausibles. El de YPF estaba en 1 y la medición mostró que es 10.
2. **Yahoo no ajusta todos los splits de las especies locales.** `MIRG.BA` pasa de 16.350 a 1.640 pesos el 2026-08-03 con `auto_adjust` activado, y con ese salto adentro la acción mostraba un precio 89% por debajo de su media de 200 ruedas: no cayó, se partió en diez. Lo corrige `merval/splits.py`, solo cuando el salto corresponde a un factor simple dentro de 3% (una caída real no se puede "corregir"), y el panel informa qué series tocó.

### Mi cartera (Balanz + Cocos)

La segunda opción del selector de arriba de todo de `app.main()` —**Confluencia / Mi cartera**— (`components/cartera_panel.py`): no es una sección más al lado de Acciones o Bonos, porque mira lo que uno operó y no el mercado. Quien la abre sube los exports de sus brokers y ve **un solo informe en dólares MEP**, con un filtro por broker cuando hay más de uno. No tiene controles de temporalidad: la tarjeta de arriba es la carga de archivos.

* **Cada broker exporta otra cosa** y cada uno tiene su lector, que devuelve la misma `Cartera` (`cartera/modelo.py`): operaciones cerradas y lotes abiertos en USD, con columna `broker`. El formato se reconoce por el contenido (`cartera/lectura.py`), no por el nombre del archivo.
  * `cartera/balanz.py`: el reporte "resultados por info completa" ya trae cada lote vendido con su costo y el MEP de cada fecha. Es acumulado: si suben dos, se usa el más reciente. Trampas medidas sobre un export real (cubiertas por `tests/test_cartera_balanz.py`): en el export medido los cupones dicen "Dólares" pero vienen en pesos —por eso la moneda de un cupón se decide por el monto: el pago por nominal tenido, leído en pesos al MEP de ese día o en dólares, se compara contra uno típico en escala logarítmica (un corte fijo fallaba con el MEP de 2018); sin nominales del bono el cupón va a `no_reconocidos`—, `Gastos` está siempre en pesos, y el vencimiento de una ON llega con precio de venta negativo.
  * `cartera/cocos.py`: el CSV de movimientos (uno por año) es el libro crudo, sin costos ni tipo de cambio. Arma lotes por orden de llegada **dentro de Cocos**, empareja cada término de caución con su contado del mismo día (uno a uno, nunca sumando el día), saca las filas repetidas **entre** archivos comparando la fila entera (no `nroTicket`, que puede venir vacío o compartido), y pasa a USD con la serie del MEP. El CSV se lee campo por campo: una fila con más campos que el encabezado es un error para mostrar, porque `pd.read_csv` corría o descartaba columnas sin avisar. Un monto ilegible es NaN y la fila se lista; nunca cero. Una venta sin compra en los archivos va a `no_reconocidos`, agrupada por activo y sin suponer la causa (compra anterior al primer archivo o transferencia desde otro broker): no se le inventa costo. "Dividendos en especie" son dólares solo si la especie es el dólar; si son acciones, entran como lote a costo cero.
* **Nada de una cuenta en particular va en el código.** La sección es pública: lo que se midió sobre los exports del autor queda como regla verificable con datos de cualquiera (moneda del cupón por monto, fechas y cantidades leídas del archivo), nunca como un valor fijo.
* **El activo se une por ticker de BYMA**, el mismo en todos los brokers: MSFT de Balanz y de Cocos son una fila del informe. Los lotes no se mezclan entre brokers. Cocos trae el ticker en el último paréntesis de `instrumento`; la especie en dólares (MSFTD) se junta con la de pesos solo si el nombre coincide, porque YPFD es la acción clase D de YPF, no YPF en dólares.
* **MEP de Cocos**: `cartera/mep_source.py` (red, sin Streamlit) baja la serie entera de ArgentinaDatos en un pedido; `cartera/data_loader.py` la cachea seis horas, con el error atrapado fuera de la función cacheada para que un corte no quede guardado. Sin MEP, Cocos queda afuera con un aviso y Balanz sigue con el suyo.
* **Cada broker se mide hasta su propio corte** (`Cartera.cortes`): al filtrar por uno se usa su fecha, no la del más reciente. Los dividendos se proyectan sobre la tenencia del mismo broker.
* **Capital de las cauciones.** Una caución no tiene lote: si el broker informa lo colocado (Cocos), entra como capital al rendimiento anual y a la TIR; si no (Balanz), su interés cuenta en los totales pero queda fuera del rendimiento y la TIR, con una nota en pantalla. Sin esto, doce cauciones daban 361% anual.
* `cartera/informe.py` (puro) arma todo el informe. **Ningún precio de mercado sale de afuera**: lo abierto cuenta al costo, el resultado de cada venta se reparte entre los años que se tuvo el activo en proporción a los días, y la renta cuenta el año del cobro. Es una decisión del usuario, no una limitación a resolver: buscar precios de cierre afuera hacía frágil el rendimiento anual.
* `components/cartera_report.py` dibuja con `st.components.v2` (HTML/CSS/JS en `components/cartera_report/`), no con widgets de Streamlit: es lo que permite el diseño del informe. El JS solo da formato; los colores salen de `theme.py` por marcadores `$nombre` en el CSS. "Ocultar montos" tapa todo importe en dólares con `****` y deja visibles los porcentajes.
* Archivos que puede subir cualquiera: tope de 20 MB (`.streamlit/config.toml`), un xlsx que se infla más de 100 MB al descomprimirse se rechaza antes de abrirlo, y `defusedxml` protege del XML malicioso. Un archivo que falla no frena a los demás, y el aviso no repite el detalle del error (podría traer valores del archivo).
* Privacidad: los archivos no se cachean (`st.cache_data` los dejaría vivos y compartidos en el servidor), no se escriben a disco y no se muestra nombre ni número de cuenta. Los datos de los archivos van al DOM siempre por `textContent`.

### Medición del semáforo

`signal_stats.py` replaya el semáforo barra por barra sobre el historial ya descargado y lo cruza con el retorno de las barras siguientes. Reusa `evaluate_confluence_signal` sin tocarlo —una copia de las reglas mediría otro sistema— y arma la entrada vectorizada en vez de rehacer `compute_stock_technicals` sobre una ventana creciente, que es cuadrático.

Lo primero que hay que leer de la tabla es la **fila de base**: un "+3% a veinte ruedas" no dice nada hasta saber qué hizo una barra cualquiera del mismo período. La tasa de acierto es direccional (una venta acierta cuando el precio cae) y el squeeze no tiene: afirma magnitud, no dirección, así que se lee en la columna de movimiento absoluto.

Dos tests fijan lo que la vuelve creíble: paridad con el semáforo del tablero, y que truncar el historial en una barra no cambie la señal de esa barra. Los límites —muestras solapadas, un solo régimen de mercado, mide la señal y no una estrategia— están en el docstring del módulo y en pantalla.

En la interfaz va detrás de un interruptor apagado: Streamlit ejecuta el cuerpo de los expanders en cada corrida, igual que el de las pestañas, así que medir sin pedirlo le cobraría un par de segundos a cada cambio de filtro.

### Registro diario

`snapshots.py` guarda una foto por día de cada panel en `data/snapshots/<motor>/<fecha>.csv` (gitignored: es un log local, no fuente) y la compara contra la anterior. Dos reglas que no conviene cambiar: **una foto por día, la primera** —si cada recarga pisara el archivo, "lo que cambió desde ayer" dependería de a qué hora miró cada uno— y la comparación es contra la **última foto anterior**, no contra ayer, informando siempre contra qué fecha se compara.

### Por qué selector y no `st.tabs`

Streamlit ejecuta el cuerpo de **todas** las pestañas en cada corrida. Con `st.tabs`, mirar acciones dispararía igual la descarga de precios de ONs y de la curva del Tesoro. El `st.radio` de `app.main()` dibuja solo la sección elegida. No lo cambies a pestañas nativas.

## Estado actual (no dar por terminado)

* **País de bonos: el desplegable existe, EEUU no.** `BOND_COUNTRY_OPTIONS` en `constants.py` y la rama en `render_bonds_panel()` son el punto de extensión; hoy EEUU muestra "en desarrollo". Lo que falta para sumar un país es fuente de precios + catálogo de emisiones, no matemática: `bonds/bond_math.py` ya es agnóstico. Evitá esparcir `if país` por el módulo — la rama vive en el panel.
* **Los ratios de ADR del panel argentino no están verificados contra los programas de los emisores**, solo contra la consistencia del panel: `ratio_verificado` es `False` en los trece. Verificarlos es data entry contra las fichas de cada ADR, igual que el catálogo de ONs.
* **La cobertura del cuadro argentino es el problema abierto**, y no es BYMA: el feed devuelve ~2700 especies sin problemas. El embudo medido es cronograma de pagos (≈140 especies) → TIR calculable (≈85) → que además operaron hoy (≈13). El catálogo local `data/ons_catalog.csv` está **vacío** (solo comentarios), y por eso paridad, valor técnico, interés corrido, vida promedio y ley salen sin datos para todo el panel: el cronograma comunitario publica el total de cada pago sin separar renta de capital. Cargar el catálogo es la única palanca, y es data entry contra prospectos.
* **El scraping de BYMA sigue sin pulir** (`bonds/byma_source.py`): API no documentada, sin contrato de estabilidad, campos de precio y volumen elegidos por orden de preferencia porque BYMA no aclara cuál es cuál.
* **Acciones semanales usan ventanas de acciones diarias.** `load_all_stocks_data` llama a `compute_stock_technicals` con los valores por omisión (252 barras / 126), así que en temporalidad semanal el "máximo de 52 semanas" es en realidad el de 252 semanas y el squeeze se mide contra dos años y medio. El motor ya recibe las dos ventanas por parámetro —`merval/data_loader.py` y `crypto/panel.py` las pasan—; falta pasarlas acá.
* **El registro diario no cubre bonos.** `snapshots.py` es genérico (la columna de señal se parametriza, y el panel de ONs llama `"Atractivo"` a lo que acciones llama `"Semáforo"`), pero la sección de bonos todavía no lo llama.
* **La dominancia del panel no es la dominancia global, y se muestran las dos.** La global viene de CoinGecko (un pedido, sin clave); la del panel se reconstruye acá con `precio × oferta circulante` y por eso da más alto (el panel tiene decenas de monedas, el mercado tiene miles). De la del panel se informa la **variación**, no el nivel. La reconstrucción usa la oferta de hoy para todo el período: vale para leer rotación de un mes, no para reconstruir capitalizaciones históricas, y por eso la serie se corta en un año.
* **El volumen de cripto es un agregado de exchanges.** Sirve para ver si un movimiento viene acompañado o está vacío; no para deducir quién está del otro lado. Por eso la columna se llama "Flujo de Volumen (OBV)" y no "Smart Money", aunque la cuenta sea la misma.

## Trampas conocidas

* **Streamlit dibuja un `NaN` numérico como el texto "None"**, no como celda vacía. Pasa con y sin `column_config`, y es de la librería (verificado en 1.62). Por eso `render_bonds_table` oculta las columnas que vienen 100% vacías: si no, una columna sin datos no se ve vacía, se ve rota.
* **El puntaje se rankea contra el subconjunto comparable, no contra el panel entero.** `compute_opportunity_scores` recibe `comparable` y **hay que pasárselo**. Omitirlo no falla ni avisa: como TIR y duration solo existen en una fracción mínima de las ~2700 especies, esas dimensiones caen bajo `BOND_SCORE_MIN_DIMENSION_COVERAGE`, se descartan para todos, y el cuadro entero sale "⚪ SIN DATOS". Cubierto por `TestPuntajeSobreUnPanelRealista`.
* **Precio de cripto: ningún formato fijo sirve para toda la tabla.** Conviven Bitcoin en decenas de miles de dólares y monedas de cinco millonésimos; con dos decimales media tabla muestra "$0.00". Por eso precio y volumen pasan por `format_crypto_price` / `format_usd_compact` y se muestran como texto, a costa de que esas dos columnas ordenen alfabéticamente. Es un costo aceptado: comparar el precio nominal de dos criptos no significa nada (depende de cuántas unidades se emitieron).
* **Los dos caminos de descarga de cripto devolvían el índice con distinta zona horaria.** `yf.download` lo trae sin zona y el reintento individual (`Ticker.history`) con zona; alinear uno contra otro revienta con "Cannot join tz-naive with tz-aware", y solo los días en que alguna moneda cae al reintento. Se normaliza en `crypto/prices_source._normalizar_indice`, en la frontera de I/O. No quites esa normalización.
* **Yahoo redondea el precio de las monedas muy chicas a un decimal significativo.** SHIB tiene 31 precios distintos en 731 ruedas. Dos consecuencias, las dos verificadas en pantalla: columnas de variación de ventanas distintas que dan el mismo número (no es un error de cálculo), y mesetas planas donde *toda* barra es máximo local — eso inflaba el conteo de toques de un nivel a 117. Lo resuelve `crypto/levels._colapsar_eventos`, que reduce a un pivote las barras contiguas del mismo giro; no lo quites.
* **Las series locales argentinas traen splits sin ajustar.** No es un caso raro ni viejo: `MIRG.BA`, agosto de 2026, con `auto_adjust=True`. Lo corrige `merval/splits.py` antes de cualquier cálculo —también antes del dólar implícito, porque el salto arruina el tipo de cambio que ese par aporta en las fechas anteriores—. Si alguna vez hay que ampliar la tolerancia, medí: cuanto más ancha, más probable es "corregir" una caída real.
* **El HTML de `st.radio` cambia entre versiones de Streamlit.** La 1.66 envuelve cada opción en un `div` más que la 1.62, y el CSS de los selectores de navegación que se enganchaba por posición (`label > div > div`, `nth-child`) se rompió en producción: las dos píldoras salían con el logo de Confluencia y volvieron los puntitos del radio. Ahora `branding.py` solo usa atributos estables (`stRadioOption`, `stMarkdownContainer`, `input:checked`, `input[value=…]`). Streamlit Cloud instala la última versión que permite `requirements.txt`: un cambio de CSS sobre widgets nativos se prueba también con esa (`uv run --with streamlit==X`).
* **El `.venv/` del repo tiene rutas viejas** (se creó cuando el proyecto vivía en `~/Documents/stock-dashboard`, sin `finanzas/`). `.venv/bin/pip` falla con "bad interpreter"; usá `.venv/bin/python -m pip`. Recrearlo desde cero lo arregla.
