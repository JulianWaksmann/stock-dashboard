"""
components/bonds_panel.py - Pestaña completa de Bonos Corporativos (ONs).

Concentra acá toda la pestaña (controles, KPIs, cuadro y documentación) en vez
de repartirla en `app.py`: la pestaña de acciones y la de bonos no comparten
estado ni filtros, y tenerlas mezcladas en un único `main()` haría que agregar
un filtro de un lado obligue a releer el otro.

Reparto entre barra lateral y cuerpo de la pestaña: la barra lateral es única
para toda la app y la dibuja la sección activa, así que ahí va lo que elige
**qué panel se carga** (el país, que determina fuente de precios, catálogo y
convenciones). Los filtros del cuadro se quedan en el cuerpo porque recortan un
panel ya descargado y son muchos: en el sidebar competirían por el espacio con
lo único que hay que decidir antes de bajar datos.
"""

from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from bonds.byma_source import BYMA_BASE_URL
from bonds.data_loader import load_bonds_data
from bonds.flows_source import COMMUNITY_FLOWS_URL
from bonds.panel import apply_bond_filters
from components.bonds_table import render_bonds_table
from components.coming_soon import render_coming_soon
from constants import (
    BOND_COUNTRY_ARGENTINA,
    BOND_COUNTRY_OPTIONS,
    BOND_LAW_FILTER_OPTIONS,
    BOND_LIQUIDITY_FILTER_OPTIONS,
    BOND_MIN_YEARS_FOR_GRADING,
    BOND_PARITY_DISCOUNT_MAX,
    BOND_PRICE_CONVENTION_OPTIONS,
    BOND_PRICE_DIRTY,
    BOND_RISK_YIELD_PREMIUM_PP,
    BOND_SCORE_ATTRACTIVE_MIN,
    BOND_SCORE_JURISDICTION,
    BOND_SCORE_LIQUIDITY,
    BOND_SCORE_MIN_COVERAGE,
    BOND_SCORE_NEUTRAL_MIN,
    BOND_SCORE_PARITY,
    BOND_SCORE_RATE_RISK,
    BOND_SCORE_VERY_ATTRACTIVE_MIN,
    BOND_SCORE_WEIGHTS,
    BOND_SCORE_YIELD,
    BOND_SETTLEMENT_FILTER_OPTIONS,
    BOND_SIGNAL_FILTER_OPTIONS,
    BOND_SOURCE_NONE,
)

# Qué mide cada dimensión del puntaje, para la tabla de la metodología.
_EXPLICACION_DIMENSION = {
    BOND_SCORE_YIELD: "Cuánto rinde frente a sus pares, con castigo por prima excesiva.",
    BOND_SCORE_LIQUIDITY: "Spread de puntas y volumen operado: si el rendimiento es ejecutable.",
    BOND_SCORE_RATE_RISK: "Duration modificada: cuánto cae el precio si suben las tasas.",
    BOND_SCORE_PARITY: "Si cotiza bajo la par, parte del retorno llega como ganancia de capital.",
    BOND_SCORE_JURISDICTION: "Ley aplicable: dónde se litiga un default.",
}

# Tope del filtro de duration. 15 años cubre con margen el tramo más largo del
# universo corporativo argentino en dólares.
_MAX_DURATION_FILTER_YEARS = 15.0


def _render_sidebar() -> str:
    """
    Barra lateral de la sección de bonos: el desplegable de país.

    La barra lateral es única para toda la app y la dibuja la sección que esté
    activa, así que lo que se ponga acá solo aparece mientras se miran bonos.
    Por eso el país va acá y los filtros del cuadro siguen dentro de la
    pestaña: el país elige **qué panel se carga** (fuente de precios, catálogo,
    convenciones), mientras que los filtros recortan un panel ya descargado.
    """
    st.sidebar.header("🌐 Mercado de bonos")

    country = st.sidebar.selectbox(
        "País:",
        BOND_COUNTRY_OPTIONS,
        help="Cada país tiene su propia fuente de precios y sus propias convenciones de cálculo. Hoy solo Argentina está implementada.",
    )

    st.sidebar.markdown("---")
    if st.sidebar.button(
        "🔄 Refrescar ONs",
        use_container_width=True,
        type="primary",
        help="Limpia la caché y vuelve a consultar precios",
    ):
        st.cache_data.clear()
        st.rerun()

    return country


def _render_controls() -> tuple[date, bool]:
    """
    Controles de cálculo de la pestaña.

    La **fecha de liquidación** no está entre los controles visibles a
    propósito. Los precios que se descargan son los de hoy, así que descontar
    ese flujo contra una fecha distinta mezcla dos momentos del mercado y
    devuelve una TIR que no corresponde a nada: el único valor coherente con
    los precios de pantalla es la fecha de hoy. Queda disponible dentro de
    "Ajustes avanzados" para verificar contra un informe de otra fecha, que es
    el único caso en que mover la fecha significa algo.
    """
    col1, col2 = st.columns([3, 2])

    with col1:
        convention = st.radio(
            "💲 Convención del precio de pantalla",
            BOND_PRICE_CONVENTION_OPTIONS,
            horizontal=True,
            help="BYMA publica precios sucios (con interés corrido incluido). Elegir mal esta opción sesga la TIR y la paridad. Solo tiene efecto sobre las ONs con condiciones de emisión cargadas: pasar de limpio a sucio exige el interés corrido, y para eso hay que saber qué parte de cada pago es renta.",
        )

    with col2:
        with st.expander("⚙️ Ajustes avanzados"):
            settlement = st.date_input(
                "📅 Fecha de liquidación",
                value=date.today(),
                help="A qué fecha se descuenta el flujo de fondos. Cambiarla mientras los precios son los de hoy produce una TIR que no corresponde a ninguna operación real: sirve solo para reproducir el cálculo de un informe de otra fecha.",
            )
            if settlement != date.today():
                st.caption(
                    "⚠️ Los precios siguen siendo los de hoy. Las métricas de abajo "
                    "no corresponden a una operación ejecutable."
                )

    return settlement, convention == BOND_PRICE_DIRTY


def _render_kpis(df: pd.DataFrame):
    """Resumen agregado del panel de ONs."""
    if df.empty:
        return

    with_yield = df["TIR (%)"].dropna()
    columns = st.columns(5)

    with columns[0]:
        st.metric(
            "ONs en Panel",
            f"{len(df)}",
            delta=f"{len(with_yield)} con TIR",
            delta_color="off",
            help="Especies que cotizan. La TIR solo se calcula para las que tienen condiciones de emisión cargadas en el catálogo.",
        )

    with columns[1]:
        st.metric(
            "Mediana TIR",
            f"{with_yield.median():.2f}%" if not with_yield.empty else "N/A",
            help="Es la referencia contra la que se mide si una ON rinde más o menos que sus pares.",
        )

    with columns[2]:
        durations = df["Duration Mod."].dropna()
        st.metric(
            "Mediana Duration",
            f"{durations.median():.2f}" if not durations.empty else "N/A",
            help="Riesgo de tasa típico del panel, en años de duration modificada.",
        )

    with columns[3]:
        parities = df["Paridad (%)"].dropna()
        below_par = (parities < BOND_PARITY_DISCOUNT_MAX).mean() * 100 if not parities.empty else np.nan
        st.metric(
            "% Bajo la Par",
            f"{below_par:.0f}%" if np.isfinite(below_par) else "N/A",
            help="Proporción de ONs cotizando por debajo de su valor técnico (paridad < 100).",
        )

    with columns[4]:
        scores = df["Puntaje"].dropna() if "Puntaje" in df.columns else pd.Series(dtype=float)
        best = int((scores >= BOND_SCORE_VERY_ATTRACTIVE_MIN).sum()) if not scores.empty else 0
        st.metric(
            "Puntaje Mediano",
            f"{scores.median():.0f}" if not scores.empty else "N/A",
            delta=f"{best} por encima de {BOND_SCORE_VERY_ATTRACTIVE_MIN:.0f}",
            delta_color="off",
            help="El puntaje es relativo al panel del día, así que la mediana ronda 50 por construcción. Lo informativo es cuántas ONs se despegan.",
        )


def _render_filters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Dibuja los filtros rápidos y devuelve el DataFrame ya filtrado.

    Esta función solo recoge lo que el usuario eligió; el filtrado en sí lo
    hace `apply_bond_filters`, que es código puro y testeado: el orden en que
    se aplican los filtros cambia el resultado y no puede vivir enterrado en
    la capa de dibujo.
    """
    col_liq, col0, col1, col2, col3, col4 = st.columns([2, 2, 2, 2, 2, 2])

    with col_liq:
        liquidity_filter = st.selectbox(
            "💧 Liquidez:",
            BOND_LIQUIDITY_FILTER_OPTIONS,
            help="El feed devuelve el panel entero, incluidas especies que no operaron hoy: su precio es el de la última rueda en que se negociaron, así que su TIR mide el mercado de otro día. El ranking se arma dentro de la moneda elegida.",
        )
    with col0:
        settlement_filter = st.selectbox(
            "💱 Especie de liquidación:",
            BOND_SETTLEMENT_FILTER_OPTIONS,
            help="Cada ON cotiza en tres especies según la última letra del ticker: O liquida en pesos, D en dólar MEP (dólares en tu cuenta local) y C en dólar cable (dólares en el exterior). Son el mismo bono. La opción por defecto trae las dos en dólares y muestra una sola fila por bono, la de la especie más operada.",
        )
    with col1:
        signal_filter = st.selectbox("🚦 Filtrar por atractivo:", BOND_SIGNAL_FILTER_OPTIONS)
    with col2:
        law_filter = st.selectbox("⚖️ Filtrar por ley aplicable:", BOND_LAW_FILTER_OPTIONS)
    with col3:
        max_duration = st.slider(
            "⏳ Duration modificada máxima (años):",
            min_value=0.0,
            max_value=_MAX_DURATION_FILTER_YEARS,
            value=_MAX_DURATION_FILTER_YEARS,
            step=0.5,
            help="Limita el riesgo de tasa: cuanto menor la duration, menos cae el precio si suben las tasas.",
        )
    with col4:
        only_with_yield = st.checkbox(
            "Solo ONs con TIR calculada",
            value=True,
            help="Oculta las especies que cotizan pero no tienen cronograma de pagos conocido.",
        )
        include_near_maturity = st.checkbox(
            f"Incluir las que vencen en < {BOND_MIN_YEARS_FOR_GRADING * 12:.0f} meses",
            value=False,
            help=(
                "Por defecto se ocultan. A semanas del vencimiento la TIR anualizada "
                "deja de medir rendimiento y pasa a ser un artefacto: anualizar el "
                "retorno de dos meses convierte un centavo de precio en decenas de "
                "puntos. Por eso tampoco reciben puntaje y se marcan ⏳ MUY CORTO. "
                "Tildá esto si lo que querés es ver qué te vence pronto."
            ),
        )

    return apply_bond_filters(
        df,
        settlement_filter=settlement_filter,
        liquidity_filter=liquidity_filter,
        signal_filter=signal_filter,
        law_filter=law_filter,
        # El tope del slider significa "sin límite", no "duration 15".
        max_duration=None if max_duration >= _MAX_DURATION_FILTER_YEARS else max_duration,
        only_with_yield=only_with_yield,
        include_near_maturity=include_near_maturity,
    )


def _render_glossary():
    """
    Glosario de las variables del cuadro.

    Va dentro de la app y no solo en el README porque es la respuesta a la
    pregunta que motiva la pestaña: qué mirar para decidir si una ON es
    interesante. Sirve de poco a tres clics de distancia del cuadro.
    """
    with st.expander("📚 Qué significa cada variable (y cómo se lee un bono)"):
        st.markdown(
            """
**Las tres que definen el retorno**

* **TIR (Tasa Interna de Retorno / *yield to maturity*)** — El rendimiento efectivo anual
  si comprás hoy, cobrás todo el flujo y lo mantenés hasta el vencimiento. Es **la** variable
  de comparación entre bonos: resume precio, cupón, plazo y cronograma de pagos en un solo
  número. Supone que reinvertís cada cupón a esa misma tasa, cosa que en la práctica rara vez
  pasa. Una TIR alta *no* es gratis: o el plazo es largo, o el emisor es riesgoso.
* **Cupón** — La tasa nominal anual que paga el bono sobre el valor nominal residual. Define
  el flujo de caja, **no** el rendimiento. Un bono con cupón 9% comprado a 120 rinde bastante
  menos del 9%.
* **Renta anual (*current yield*)** — Cupón anual dividido el precio que pagaste. Responde
  "¿cuánta caja me deja este año?", sin contar ganancia ni pérdida de capital. Útil si vivís
  de la renta; insuficiente para comparar.

**Las que miden el riesgo**

* **Duration modificada** — Cuánto cae el precio, en %, si el rendimiento exigido sube 1 punto
  porcentual. Duration 4 ⇒ +1 pp de tasa ≈ −4% de precio. Es el termómetro del riesgo de tasa:
  duration corta = precio estable; duration larga = mucho upside si las tasas bajan y mucho
  dolor si suben.
* **Vida promedio (WAL)** — En cuántos años, promedio, te devuelven el capital. En un bono con
  amortizaciones parciales puede ser mucho menor que el plazo al vencimiento: recuperás plata
  antes y quedás menos expuesto.
* **Convexidad** — El error que deja la duration sola. A igual duration, más convexidad es
  mejor: el precio sube más de lo que la duration anticipa cuando las tasas bajan, y cae menos
  cuando suben.
* **Spread vs UST** — Cuántos puntos básicos paga la ON por encima del bono del Tesoro de EE.UU.
  de duration equivalente. Es, literalmente, el precio del riesgo: riesgo argentino + riesgo
  del emisor. Compararlo entre ONs del mismo plazo es la forma más limpia de ver cuál está cara
  y cuál barata.
* **Ley aplicable** — NY o Argentina. Define en qué tribunales se litiga un default. La ley
  extranjera históricamente cotiza con menor rendimiento exigido: se paga por esa protección.

**Las que definen el precio contra el valor**

* **Valor técnico** — Capital residual + interés corrido. Es lo que el bono "vale" según el
  contrato a día de hoy.
* **Paridad** — Precio dividido valor técnico, en %. Por debajo de 100 el bono cotiza con
  descuento y parte del retorno llega como ganancia de capital al vencimiento; por encima de
  100, con premio, y el precio converge a la baja hacia el valor técnico.
* **Interés corrido** — La porción del próximo cupón ya devengada, que le pagás al vendedor
  por encima del precio limpio.
* **Capital residual** — Cuánto del valor nominal original todavía no te devolvieron. Baja con
  cada amortización, y con él baja el cupón en pesos/dólares aunque la tasa no cambie.

**Las que definen si podés operarlo de verdad**

* **Spread de puntas** — Distancia entre la punta compradora y la vendedora. Es el costo de
  entrar y salir. Un spread de 3% se come tres años de diferencia de TIR contra otra ON.
* **Volumen y operaciones** — Si casi no opera, el precio de pantalla es teórico y la TIR que
  ves puede no ser ejecutable.
* **Lámina mínima** — El valor nominal mínimo negociable. Muchas ONs bajo ley extranjera tienen
  lámina de 100.000 o 150.000 nominales: quedan fuera del alcance minorista por más atractiva
  que sea la TIR.
            """
        )


def _render_methodology():
    """Documenta cómo se arma el puntaje y con qué supuestos se calcula."""
    with st.expander("ℹ️ Cómo se calcula el Puntaje de Oportunidad"):
        pesos = "\n".join(
            f"| **{dimension}** | {peso:.0f}% | {_EXPLICACION_DIMENSION[dimension]} |"
            for dimension, peso in BOND_SCORE_WEIGHTS.items()
        )
        st.markdown(
            f"""
Cada ON recibe un puntaje de **0 a 100**. No es una nota absoluta: mide cómo se compara con **el
resto del panel del día**. Una TIR del 11% es excelente o mediocre según dónde esté cotizando todo
lo demás, así que cada dimensión se puntúa por su posición dentro del panel y no contra un umbral
fijo que diría cosas opuestas en dos momentos del ciclo.

Por construcción, **un bono promedio ronda 50**. Lo informativo es quién se despega.

| Dimensión | Peso | Qué mide |
| --- | --- | --- |
{pesos}

**Tres reglas que hacen honesto al número:**

1. **Más TIR no es siempre mejor.** Pasada una prima de {BOND_RISK_YIELD_PREMIUM_PP:.0f} puntos
   porcentuales sobre la mediana del panel, el puntaje de rendimiento empieza a caer y llega a
   cero al doble de esa prima. Ahí el mercado no regala rendimiento: le está poniendo precio a una
   probabilidad de default. Esos bonos se marcan 🚨 **ALERTA DE RIESGO** y no compiten por el
   primer puesto.
2. **Lo que no se puede medir no puntúa cero: se excluye.** Si de una ON no se conoce la ley
   aplicable, esa dimensión sale del cálculo y su peso se reparte entre las demás. Puntuar cero
   castigaría al bono por un dato que falta en nuestra fuente, no por algo que le pase al bono.
   La columna **Cobertura** dice qué fracción del peso se pudo medir de verdad.
3. **Con muy poco medido no hay puntaje.** Por debajo del {BOND_SCORE_MIN_COVERAGE:.0%} de
   cobertura no se publica número: saldría casi solo de la TIR y diría más sobre lo que falta que
   sobre la oportunidad.

**Del puntaje a la etiqueta:** ≥ {BOND_SCORE_VERY_ATTRACTIVE_MIN:.0f} 🌟 MUY ATRACTIVO ·
≥ {BOND_SCORE_ATTRACTIVE_MIN:.0f} 🟢 ATRACTIVO · ≥ {BOND_SCORE_NEUTRAL_MIN:.0f} 🟡 NEUTRAL ·
por debajo 🟠 POCO ATRACTIVO. Dos casos ganan sobre el puntaje: la alerta de riesgo de arriba, y
⏳ **MUY CORTO** para las ONs a menos de {BOND_MIN_YEARS_FOR_GRADING:.2f} años del vencimiento,
donde anualizar el retorno de unas semanas convierte un centavo de precio en decenas de puntos de
TIR.

Los pesos están en `constants.py` (`BOND_SCORE_WEIGHTS`). Son un criterio de inversión explícito,
no una verdad: si para vos la liquidez pesa más que el rendimiento, cambialos ahí.

---

**Supuestos de cálculo** (cambiarlos cambia los números, así que conviene conocerlos):

* Importes por cada **100 VN originales**, la convención de cotización local.
* **Interés corrido base 30/360**; **descuento base ACT/365** con capitalización anual, de modo
  que la TIR sea efectiva anual y comparable entre bonos de distinta frecuencia de pago.
* Solo **tasa fija**. Las ONs CER, dollar-linked, Badlar o TAMAR no se pueden modelar con este
  motor: su flujo futuro no está determinado hoy.
* El **spread vs UST** usa la curva del Tesoro de Yahoo Finance (3M, 5A, 10A, 30A) interpolada
  linealmente al plazo de duration de cada ON.
            """
        )


def _render_sources():
    """Documenta de dónde sale cada dato y qué hacer para mejorarlo."""
    with st.expander("🔌 De dónde salen los datos"):
        st.markdown(
            f"""
| Dato | Fuente | Cómo se obtiene |
| --- | --- | --- |
| Precios, puntas, volumen | [BYMA Open Data]({BYMA_BASE_URL}) | El mercado donde las ONs cotizan. API pública sin API key, pero sin documentar: es POST y valida cookie de navegador. Trae además vencimiento y moneda de cada especie. |
| Cronogramas de pago | [rendimientos-ar]({COMMUNITY_FLOWS_URL}) | Se descarga en cada carga. Es un dataset **comunitario** mantenido a mano por terceros (licencia ISC), no una fuente oficial. Publica el total de cada pago, sin separar renta de capital. |
| Condiciones de emisión | `data/ons_catalog.csv` (este repo) | Opcional y vacío por defecto. Solo hace falta para las métricas que necesitan el desglose renta/capital, o para una ON que la fuente comunitaria no cubra. |
| Curva del Tesoro de EE.UU. | Yahoo Finance (`^IRX`, `^FVX`, `^TNX`, `^TYX`) | Vía `yfinance`, igual que el panel de acciones. |

**Por qué el cronograma no sale de una fuente oficial:** las condiciones de emisión de una ON
(cupón, amortizaciones, ley) viven en su prospecto. Ni BYMA ni la CNV las publican en un formato
consultable por máquina, así que todas las alternativas son o bien datasets mantenidos a mano como
este, o bien scraping del Informe Diario del IAMC.

**Para verificar o completar el catálogo:**

* **Prospecto de emisión** — es la fuente autoritativa. Se consigue en la web del emisor o en la
  [CNV](https://www.argentina.gob.ar/cnv).
* **[IAMC](https://www.iamc.com.ar)** — el Informe Diario publica precio, TIR, paridad, duration
  y valor técnico de todas las especies listadas. Es la mejor forma de validar de una sola vez
  los datos cargados *y* el resultado del cálculo.
* **[BYMA](https://www.byma.com.ar)** — boletín diario oficial y datos de la especie.

**Por qué BYMA y no un feed alternativo:** se comparó contra data912 con
`scripts/verificar_fuentes.py`. BYMA lista 2727 especies contra 616, y sobre las 614 en común la
mitad de los precios del feed alternativo llegaba con atraso: 0,17% de diferencia mediana y hasta
2,75% en el mismo título. Sobre un bono de duration 3 eso son entre 6 y 90 puntos básicos de TIR,
que es justamente lo que el panel compara. No se dejó como respaldo porque un respaldo que
devuelve otro número no es un respaldo.

**Si necesitás precios ejecutables**, la fuente es el broker donde operás (IOL, Bull Market,
Cocos, etc. exponen API con cuenta).
            """
        )


def render_bonds_panel():
    """Dibuja la sección completa de Bonos Corporativos."""
    country = _render_sidebar()

    if country != BOND_COUNTRY_ARGENTINA:
        st.markdown(
            f'<div class="main-title">💵 Bonos Corporativos — {country}</div>',
            unsafe_allow_html=True,
        )
        render_coming_soon(
            f"Bonos corporativos — {country}",
            "Vas a poder comparar deuda corporativa de este mercado con el mismo "
            "criterio que el panel argentino: cuánto rinde cada bono frente a sus "
            "pares, cuánto riesgo de tasa tiene y si ese rendimiento es realmente "
            "ejecutable.",
        )
        return

    st.markdown(
        '<div class="main-title">💵 Bonos Corporativos Argentinos (Obligaciones Negociables)</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sub-title">Rendimiento (TIR), riesgo (duration, paridad) y liquidez de las ONs en dólares, '
        'calculados sobre el flujo de fondos contractual de cada emisión.</div>',
        unsafe_allow_html=True,
    )

    settlement, price_is_dirty = _render_controls()
    st.markdown("---")

    with st.spinner("⏳ Descargando precios de ONs y calculando TIR, duration y paridad..."):
        df_bonds, warnings = load_bonds_data(settlement=settlement, price_is_dirty=price_is_dirty)

    for message in warnings:
        st.warning(f"⚠️ {message}")

    if df_bonds.empty:
        st.error(
            "No se pudo armar el panel de ONs. Revisá la conexión a internet y volvé a intentar "
            "con **🔄 Refrescar ONs**."
        )
        _render_glossary()
        _render_sources()
        return

    without_schedule = sorted(df_bonds.loc[df_bonds["Fuente"] == BOND_SOURCE_NONE, "Ticker"])
    if without_schedule:
        st.info(
            f"📗 **{len(without_schedule)} de {len(df_bonds)} especies cotizan sin cronograma de pagos conocido.** "
            "Se les muestra precio, puntas y volumen, pero no se les puede calcular TIR ni duration. "
            "El cronograma de las ONs más operadas se descarga solo; para incorporar una que la fuente "
            "no cubra, agregá una fila en `data/ons_catalog.csv`: alcanza con cargar una especie "
            "(por ejemplo la O) y el panel la aplica también a las especies D y C del mismo bono."
        )
        with st.expander(f"Ver las {len(without_schedule)} especies sin cronograma"):
            st.write(", ".join(without_schedule))

    # El selector de convención de precio no puede aplicarse sobre las ONs que
    # solo tienen cronograma publicado. Decirlo es mejor que dejar un control
    # que no hace nada en la mayoría de las filas.
    if not price_is_dirty and "Convención Aplicada" in df_bonds.columns:
        ignoradas = int((df_bonds["Convención Aplicada"] == BOND_PRICE_DIRTY).sum())
        if ignoradas:
            st.caption(
                f"ℹ️ La convención de precio limpio no se pudo aplicar en {ignoradas} de "
                f"{len(df_bonds)} especies: su cronograma publica el total de cada pago, sin "
                "separar renta de capital, y sin ese desglose no hay interés corrido que sumarle "
                "al precio. Esas filas se calcularon con precio sucio, la convención de BYMA."
            )

    unverified = int((~df_bonds["Verificado"] & df_bonds["En Catálogo"]).sum())
    if unverified:
        st.warning(
            f"⚠️ **{unverified} ON(s) del catálogo local tienen condiciones de emisión sin verificar.** "
            "Verificalas contra el prospecto y marcá `verificado=si` en `data/ons_catalog.csv`: "
            "un cupón mal cargado devuelve una TIR mansamente incorrecta."
        )

    # Un emisor en default es lo primero que hay que saber, y no puede quedar
    # escondido detrás del interruptor de columnas completas.
    if "En Default" in df_bonds.columns and df_bonds["En Default"].any():
        en_default = sorted(df_bonds.loc[df_bonds["En Default"], "Ticker"])
        st.error(
            f"🚨 **{len(en_default)} especie(s) marcadas en default por BYMA:** "
            f"{', '.join(en_default)}. Su TIR sigue calculándose sobre el flujo contractual, "
            "que es justamente el que el emisor dejó de pagar."
        )

    _render_kpis(df_bonds)
    st.markdown("---")

    st.markdown("#### 🔍 Filtros")
    df_filtered = _render_filters(df_bonds)
    st.markdown("---")

    header_col, download_col = st.columns([3, 1])
    with header_col:
        median_ytm = df_bonds.attrs.get("median_ytm_pct", np.nan)
        median_text = f" | Mediana TIR del panel: **{median_ytm:.2f}%**" if np.isfinite(median_ytm) else ""
        st.markdown(f"### 📋 Cuadro Comparativo ({len(df_filtered)} de {len(df_bonds)} ONs){median_text}")
    with download_col:
        st.download_button(
            label="📥 Exportar a CSV",
            data=df_filtered.to_csv(index=False).encode("utf-8"),
            file_name=f"ons_argentinas_{settlement:%Y%m%d}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    vista_col, desglose_col = st.columns(2)
    with vista_col:
        vista_completa = st.checkbox(
            "Ver todas las columnas",
            value=False,
            help="Agrega puntas, convexidad, valor técnico, interés corrido, calificación y demás detalle de segundo orden.",
        )
    with desglose_col:
        ver_desglose = st.checkbox(
            "Ver desglose del puntaje",
            value=False,
            help="Muestra cuánto aporta cada dimensión al Puntaje de Oportunidad, y qué fracción del peso se pudo medir.",
        )

    render_bonds_table(df_filtered, full=vista_completa, breakdown=ver_desglose)

    _render_glossary()
    _render_methodology()
    _render_sources()
