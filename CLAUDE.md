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

# Verificar el pipeline de bonos sin levantar Streamlit
python3 scripts/panel_ons.py --top 20 --desglose
python3 scripts/verificar_fuentes.py    # diagnóstico de las fuentes de datos
```

El `.venv/` del repo **no** trae `pytest` ni `ruff` instalados: corré `pip install -r requirements-dev.txt` antes de testear o lintear.

CI (`.github/workflows/ci.yml`) corre `ruff check .` y `pytest` en **Python 3.11 y 3.14** en cada push/PR contra `main`. Los dos extremos se testean a propósito: un techo de dependencia sin wheel para el Python desplegado ya rompió producción una vez (ver el comentario de política de pinning en `requirements.txt` — no ajustes techos sin leerlo).

## Arquitectura

Son **dos motores independientes** que comparten el dashboard pero no el modelo de datos: acciones (osciladores de precio) y bonos corporativos argentinos (valor presente del flujo de fondos contractual). `app.py` los reparte con un selector.

### Regla de capas (se respeta en los dos motores)

```
I/O con red + Streamlit  →  cálculo puro  →  dibujo
```

* **Puro (sin red, sin `streamlit`)**: `indicators.py`, `bonds/bond_math.py`, `bonds/panel.py`, `bonds/scoring.py`, `bonds/catalog.py`, y el *parseo* de `bonds/byma_source.py` / `bonds/flows_source.py`. Esto es lo que la suite de tests verifica con datos fijos, sin mocks de red.
* **I/O**: `data_loader.py` (acciones) y `bonds/data_loader.py` (bonos) — los únicos que tocan `st.cache_data` y la red.
* **Dibujo**: `components/`.

No metas lógica de negocio en `components/` ni `streamlit` en los módulos puros: `scripts/panel_ons.py` corre exactamente la misma cadena desde la terminal y se rompe si esa separación se pierde.

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

### Por qué selector y no `st.tabs`

Streamlit ejecuta el cuerpo de **todas** las pestañas en cada corrida. Con `st.tabs`, mirar acciones dispararía igual la descarga de precios de ONs y de la curva del Tesoro. El `st.radio` de `app.main()` dibuja solo la sección elegida. No lo cambies a pestañas nativas.

## Estado actual (no dar por terminado)

* **País de bonos: el desplegable existe, EEUU no.** `BOND_COUNTRY_OPTIONS` en `constants.py` y la rama en `render_bonds_panel()` son el punto de extensión; hoy EEUU muestra "en desarrollo". Lo que falta para sumar un país es fuente de precios + catálogo de emisiones, no matemática: `bonds/bond_math.py` ya es agnóstico. Evitá esparcir `if país` por el módulo — la rama vive en el panel.
* **La cobertura del cuadro argentino es el problema abierto**, y no es BYMA: el feed devuelve ~2700 especies sin problemas. El embudo medido es cronograma de pagos (≈140 especies) → TIR calculable (≈85) → que además operaron hoy (≈13). El catálogo local `data/ons_catalog.csv` está **vacío** (solo comentarios), y por eso paridad, valor técnico, interés corrido, vida promedio y ley salen sin datos para todo el panel: el cronograma comunitario publica el total de cada pago sin separar renta de capital. Cargar el catálogo es la única palanca, y es data entry contra prospectos.
* **El scraping de BYMA sigue sin pulir** (`bonds/byma_source.py`): API no documentada, sin contrato de estabilidad, campos de precio y volumen elegidos por orden de preferencia porque BYMA no aclara cuál es cuál.
* **Sin conectar**: `components/ticker_detail.py` y `components/charts.py` están escritos y testeados, pero `app.py` todavía no los usa.

## Trampas conocidas

* **Streamlit dibuja un `NaN` numérico como el texto "None"**, no como celda vacía. Pasa con y sin `column_config`, y es de la librería (verificado en 1.62). Por eso `render_bonds_table` oculta las columnas que vienen 100% vacías: si no, una columna sin datos no se ve vacía, se ve rota.
* **El puntaje se rankea contra el subconjunto comparable, no contra el panel entero.** `compute_opportunity_scores` recibe `comparable` y **hay que pasárselo**. Omitirlo no falla ni avisa: como TIR y duration solo existen en una fracción mínima de las ~2700 especies, esas dimensiones caen bajo `BOND_SCORE_MIN_DIMENSION_COVERAGE`, se descartan para todos, y el cuadro entero sale "⚪ SIN DATOS". Cubierto por `TestPuntajeSobreUnPanelRealista`.
* **El `.venv/` del repo tiene rutas viejas** (se creó cuando el proyecto vivía en `~/Documents/stock-dashboard`, sin `finanzas/`). `.venv/bin/pip` falla con "bad interpreter"; usá `.venv/bin/python -m pip`. Recrearlo desde cero lo arregla.
