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
    BOND_FILTER_LIQUIDITY_TRADED,
    BOND_FILTER_SETTLEMENT_USD,
    BOND_FILTER_SIGNAL_ALL,
    BOND_LAW_FILTER_OPTIONS,
    BOND_MIN_YEARS_FOR_GRADING,
    BOND_PARITY_DISCOUNT_MAX,
    BOND_RISK_YIELD_PREMIUM_PP,
    BOND_SCORE_ATTRACTIVE_MIN,
    BOND_SCORE_JURISDICTION,
    BOND_SCORE_LIQUIDITY,
    BOND_SCORE_MIN_COVERAGE,
    BOND_SCORE_NEUTRAL_MIN,
    BOND_SCORE_PARITY,
    BOND_SCORE_RATE_RISK,
    BOND_SCORE_RATING,
    BOND_SCORE_VERY_ATTRACTIVE_MIN,
    BOND_SCORE_WEIGHTS,
    BOND_SCORE_YIELD,
    BOND_SOURCE_NONE,
)

# Qué mide cada dimensión del puntaje, para la tabla de la metodología.
_EXPLICACION_DIMENSION = {
    BOND_SCORE_YIELD: "Cuánto rinde frente a sus pares, con castigo por prima excesiva.",
    BOND_SCORE_LIQUIDITY: "Spread de puntas y volumen operado: si el rendimiento es ejecutable.",
    BOND_SCORE_RATE_RISK: "Duration modificada: cuánto cae el precio si suben las tasas.",
    BOND_SCORE_PARITY: "Si cotiza bajo la par, parte del retorno llega como ganancia de capital.",
    BOND_SCORE_JURISDICTION: "Ley aplicable: dónde se litiga un default.",
    BOND_SCORE_RATING: "Calidad crediticia del emisor según las calificadoras.",
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
    Dibuja los filtros y devuelve el cuadro ya filtrado.

    Son tres, a propósito. Los que había antes o repetían algo que ya se ve en
    el cuadro —el filtro por atractivo, teniendo la barra de puntaje al lado—,
    o configuraban el armado del panel en vez de recortarlo, que es una
    decisión del tablero y no del lector: qué especie mostrar por bono, qué
    hacer con las que no operaron, y si incluir las que están por vencer.
    Esas ahora son fijas.

    Esta función solo recoge lo que el usuario eligió; el filtrado en sí lo
    hace `apply_bond_filters`, que es código puro y testeado: el orden en que
    se aplican los filtros cambia el resultado y no puede vivir enterrado en
    la capa de dibujo.
    """
    col_score, col_dur, col_ley = st.columns([2, 2, 2])

    with col_score:
        score_range = st.slider(
            "🎯 Puntaje de oportunidad:",
            min_value=0,
            max_value=100,
            value=(0, 100),
            step=5,
            help=(
                "Puntaje de 0 a 100, relativo al resto del panel del día: un bono "
                "promedio ronda 50. Con el rango completo también se muestran las ONs "
                "que no tienen puntaje; apenas lo movés, quedan solo las puntuadas."
            ),
        )

    with col_dur:
        max_duration = st.slider(
            "⏳ Riesgo de tasa máximo (años):",
            min_value=0.0,
            max_value=_MAX_DURATION_FILTER_YEARS,
            value=_MAX_DURATION_FILTER_YEARS,
            step=0.5,
            help=(
                "Duration modificada: cuánto caería el precio del bono si la tasa "
                "exigida subiera un punto porcentual. Cuanto más baja, más estable "
                "es el precio."
            ),
        )

    with col_ley:
        law_filter = st.selectbox(
            "⚖️ Ley aplicable:",
            BOND_LAW_FILTER_OPTIONS,
            help=(
                "En qué tribunales se resuelve un incumplimiento. La ley extranjera "
                "históricamente se paga con menor rendimiento exigido: el mercado "
                "cobra por esa protección."
            ),
        )

    filtrado = apply_bond_filters(
        df,
        # Fijos: hacen al armado del panel, no al recorte que elige el lector.
        settlement_filter=BOND_FILTER_SETTLEMENT_USD,
        # Se muestran todas las que operaron hoy, y no un "top N por volumen".
        # El top N era él mismo un recorte por volumen, así que dejaba en
        # pantalla solo las más operadas: la columna de cuartil decía "muy
        # alto" en todas las filas y no distinguía nada. Pidiendo solo que
        # hayan operado, el precio sigue siendo del día y el cuadro pasa de
        # ~26 bonos a ~96.
        liquidity_filter=BOND_FILTER_LIQUIDITY_TRADED,
        signal_filter=BOND_FILTER_SIGNAL_ALL,
        only_with_yield=True,
        include_near_maturity=False,
        # Elegidos por el usuario.
        law_filter=law_filter,
        # El tope del slider significa "sin límite", no "duration 15".
        max_duration=None if max_duration >= _MAX_DURATION_FILTER_YEARS else max_duration,
    )

    if score_range != (0, 100) and "Puntaje" in filtrado.columns:
        puntaje = pd.to_numeric(filtrado["Puntaje"], errors="coerce")
        filtrado = filtrado[puntaje.between(score_range[0], score_range[1])]

    return filtrado


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

Los pesos son un criterio de inversión explícito, no una verdad del mercado: dicen que antes de
preguntarse cuánto rinde un bono hay que poder operarlo y saber a quién se le presta. Si tu criterio
es otro, se pueden ajustar.

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
| Dato | De dónde sale | Qué tan confiable es |
| --- | --- | --- |
| Precios, puntas y volumen | [BYMA]({BYMA_BASE_URL}) | El mercado donde estos bonos efectivamente cotizan, así que es el dato de origen y no una copia. Se actualiza durante la rueda. |
| Calendario de pagos | [Proyecto abierto rendimientos-ar]({COMMUNITY_FLOWS_URL}) | Mantenido por terceros de forma voluntaria, no es una fuente oficial. Informa el total de cada pago sin separar cuánto es interés y cuánto capital. |
| Condiciones de emisión | Carga manual, contra el prospecto | Lo más confiable cuando está verificado, porque sale del contrato del bono. Cubre pocas emisiones. |
| Calificación crediticia | Carga manual, contra el informe de la calificadora | Solo se muestra una vez verificada. |
| Rendimiento del Tesoro de EE.UU. | Yahoo Finance | Referencia de mercado, para medir cuánto paga cada bono por encima de un activo sin riesgo de crédito. |

**Por qué el cronograma no sale de una fuente oficial:** las condiciones de emisión de una ON
(cupón, amortizaciones, ley) viven en su prospecto. Ni BYMA ni la CNV las publican en un formato
consultable por máquina, así que todas las alternativas son o bien datasets mantenidos a mano como
este, o bien scraping del Informe Diario del IAMC.

**Dónde verificar o completar estos datos:**

* **Prospecto de emisión** — es el contrato del bono y manda sobre cualquier otra fuente. Se
  consigue en la web del emisor o en la [CNV](https://www.argentina.gob.ar/cnv).
* **[IAMC](https://www.iamc.com.ar)** — su Informe Diario publica precio, rendimiento, paridad y
  riesgo de tasa de todos los bonos listados. Es la forma más rápida de contrastar de una sola vez
  tanto los datos cargados como los números que devuelve este cuadro.
* **[BYMA](https://www.byma.com.ar)** — boletín diario oficial y ficha de cada bono.

**Por qué los precios salen de BYMA y no de otra fuente:** se comparó contra un proveedor
alternativo y se lo descartó midiendo. BYMA informa 2727 bonos contra 616, y sobre los que ambos
tenían, la mitad de los precios del otro proveedor llegaba con atraso. Parece poco —una diferencia
típica del 0,17%, y hasta 2,75% en un mismo título— pero sobre el rendimiento de un bono eso son
entre 6 y 90 puntos básicos, que es justamente la diferencia que el cuadro compara. Tampoco quedó
como respaldo: un respaldo que devuelve otro número no sirve de respaldo.

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

    # La fecha de liquidación es siempre hoy y el precio se toma como lo
    # publica BYMA (con el interés corrido incluido). Las dos eran controles y
    # se sacaron: con precios de hoy, descontar a otra fecha da una TIR que no
    # corresponde a ninguna operación real, y la otra convención de precio no
    # se puede aplicar sobre la mayoría de las filas.
    settlement = date.today()
    price_is_dirty = True
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
            f"📗 **De {len(df_bonds)} obligaciones negociables que cotizan, {len(without_schedule)} no "
            "publican su calendario de pagos.** De esas se muestra precio y volumen, pero sin saber "
            "cuándo y cuánto paga un bono no hay forma de calcular su rendimiento ni su riesgo de tasa. "
            "El calendario de las más operadas se obtiene automáticamente; el resto depende de que sus "
            "condiciones de emisión se carguen a mano."
        )
        with st.expander(f"Ver las {len(without_schedule)} especies sin cronograma"):
            st.write(", ".join(without_schedule))

    unverified = int((~df_bonds["Verificado"] & df_bonds["En Catálogo"]).sum())
    if unverified:
        st.warning(
            f"⚠️ **{unverified} obligación(es) negociable(s) tienen condiciones de emisión sin verificar "
            "contra el prospecto.** Su rendimiento y su riesgo de tasa son estimaciones: si la tasa de "
            "cupón o el calendario cargados no son exactos, los números salen mal sin que nada lo avise."
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
