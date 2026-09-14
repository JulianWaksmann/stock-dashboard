"""
components/bonds_panel.py - Pestaña completa de Bonos Corporativos (ONs).

Concentra acá toda la pestaña (controles, KPIs, cuadro y documentación) en vez
de repartirla en `app.py`: la pestaña de acciones y la de bonos no comparten
estado ni filtros, y tenerlas mezcladas en un único `main()` haría que agregar
un filtro de un lado obligue a releer el otro.

Los filtros viven **dentro** de la pestaña y no en la barra lateral a propósito:
Streamlit dibuja la barra lateral una sola vez para toda la app, así que filtros
de bonos en el sidebar aparecerían también mientras se miran acciones.
"""

from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from bonds.data_loader import DATA912_CORPORATE_BONDS_URL, load_bonds_data
from bonds.flows_source import COMMUNITY_FLOWS_URL
from components.bonds_table import render_bonds_table
from constants import (
    BOND_ATTRACTIVE_SIGNALS,
    BOND_FILTER_LAW_ARG,
    BOND_FILTER_LAW_NY,
    BOND_FILTER_SETTLEMENT_MEP,
    BOND_FILTER_SETTLEMENT_PESOS,
    BOND_FILTER_SETTLEMENT_USD,
    BOND_FILTER_SIGNAL_ATTRACTIVE,
    BOND_FILTER_SIGNAL_RISK,
    BOND_FILTER_SIGNAL_VERY_ATTRACTIVE,
    BOND_LAW_FILTER_OPTIONS,
    BOND_LIQUID_SPREAD_MAX_PCT,
    BOND_PARITY_DISCOUNT_MAX,
    BOND_PRICE_CONVENTION_OPTIONS,
    BOND_PRICE_DIRTY,
    BOND_RISK_YIELD_PREMIUM_PP,
    BOND_SETTLEMENT_FILTER_OPTIONS,
    BOND_SETTLEMENT_MEP,
    BOND_SETTLEMENT_PESOS,
    BOND_SHORT_DURATION_MAX_YEARS,
    BOND_SIGNAL_FILTER_OPTIONS,
    BOND_SIGNAL_RISK,
    BOND_SIGNAL_VERY_ATTRACTIVE,
    BOND_SOURCE_NONE,
    BOND_YIELD_PREMIUM_PP,
)

# Tope del filtro de duration. 15 años cubre con margen el tramo más largo del
# universo corporativo argentino en dólares.
_MAX_DURATION_FILTER_YEARS = 15.0


def _render_controls() -> tuple[date, bool]:
    """Controles de cálculo: fecha de liquidación y convención de precio."""
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        settlement = st.date_input(
            "📅 Fecha de liquidación",
            value=date.today(),
            help="Fecha a la que se descuenta el flujo de fondos. En BYMA la renta fija liquida habitualmente en 24 hs (T+1).",
        )

    with col2:
        convention = st.radio(
            "💲 Convención del precio de pantalla",
            BOND_PRICE_CONVENTION_OPTIONS,
            horizontal=True,
            help="BYMA publica precios sucios (con interés corrido incluido). Elegir mal esta opción sesga la TIR y la paridad.",
        )

    with col3:
        st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Refrescar ONs", use_container_width=True, help="Limpia la caché y vuelve a consultar precios"):
            st.cache_data.clear()
            st.rerun()

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
        spreads = df["Spread (%)"].dropna()
        liquid = (spreads <= BOND_LIQUID_SPREAD_MAX_PCT).sum() if not spreads.empty else 0
        st.metric(
            "ONs Líquidas",
            f"{liquid}",
            delta=f"spread ≤ {BOND_LIQUID_SPREAD_MAX_PCT:.0f}%",
            delta_color="off",
            help="Especies con las dos puntas cerca entre sí: se puede entrar y salir sin regalar rendimiento.",
        )


def _render_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Filtros rápidos del panel. Devuelve el DataFrame ya filtrado."""
    col0, col1, col2, col3, col4 = st.columns([2, 2, 2, 2, 2])

    with col0:
        settlement_filter = st.selectbox(
            "💱 Especie de liquidación:",
            BOND_SETTLEMENT_FILTER_OPTIONS,
            help="Cada ON cotiza en tres especies (O pesos, D MEP, C cable). Son el mismo bono: por defecto se muestran las que cotizan en dólares, que son las comparables por TIR.",
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
            help="Oculta las especies que cotizan pero no tienen condiciones de emisión cargadas en el catálogo.",
        )

    filtered = df.copy()

    if settlement_filter == BOND_FILTER_SETTLEMENT_USD:
        filtered = filtered[filtered["Moneda Precio"] == "USD"]
    elif settlement_filter == BOND_FILTER_SETTLEMENT_MEP:
        filtered = filtered[filtered["Liquidación"] == BOND_SETTLEMENT_MEP]
    elif settlement_filter == BOND_FILTER_SETTLEMENT_PESOS:
        filtered = filtered[filtered["Liquidación"] == BOND_SETTLEMENT_PESOS]

    if signal_filter == BOND_FILTER_SIGNAL_ATTRACTIVE:
        filtered = filtered[filtered["Atractivo"].isin(BOND_ATTRACTIVE_SIGNALS)]
    elif signal_filter == BOND_FILTER_SIGNAL_VERY_ATTRACTIVE:
        filtered = filtered[filtered["Atractivo"] == BOND_SIGNAL_VERY_ATTRACTIVE]
    elif signal_filter == BOND_FILTER_SIGNAL_RISK:
        filtered = filtered[filtered["Atractivo"] == BOND_SIGNAL_RISK]

    if law_filter == BOND_FILTER_LAW_NY:
        filtered = filtered[filtered["Ley"] == "NY"]
    elif law_filter == BOND_FILTER_LAW_ARG:
        filtered = filtered[filtered["Ley"] == "ARG"]

    # El filtro de duration no debe descartar las filas sin duration calculada
    # salvo que el usuario haya pedido explícitamente solo ONs con TIR: una ON
    # sin condiciones cargadas no es "de duration alta", es de duration
    # desconocida, y esa distinción la decide el checkbox de al lado.
    if max_duration < _MAX_DURATION_FILTER_YEARS:
        filtered = filtered[filtered["Duration Mod."].isna() | (filtered["Duration Mod."] <= max_duration)]

    if only_with_yield:
        filtered = filtered[filtered["TIR (%)"].notna()]

    return filtered


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
    """Documenta el sistema de grados y los supuestos de cálculo."""
    with st.expander("ℹ️ Cómo se calcula el Atractivo (Sistema de Grados)"):
        st.markdown(
            f"""
Un bono no se compara contra su propio pasado sino **contra sus pares del mismo día**: una TIR
del 11% es excelente o mediocre según dónde esté cotizando el resto del panel corporativo
argentino. Por eso la referencia de todos los umbrales de rendimiento es la **mediana de TIR del
panel**, no un número fijo.

**Requisito obligatorio:** tener una TIR calculable. Sin condiciones de emisión en el catálogo
no hay flujo de fondos y no hay nada que evaluar (⚪ SIN DATOS).

**Alerta excluyente:** TIR por encima de la mediana + {BOND_RISK_YIELD_PREMIUM_PP:.0f} puntos
porcentuales → **🚨 ALERTA DE RIESGO**. Una prima así sobre los pares no es un bono barato: es el
mercado poniéndole precio a una probabilidad de default o de reestructuración.

**Puntos (1 cada uno):**

1. **Premio de rendimiento** — TIR ≥ mediana del panel + {BOND_YIELD_PREMIUM_PP:.0f} pp.
2. **Riesgo de tasa acotado** — Duration modificada ≤ {BOND_SHORT_DURATION_MAX_YEARS:.0f} años.
3. **Cotiza bajo la par** — Paridad < {BOND_PARITY_DISCOUNT_MAX:.0f}%.
4. **Liquidez** — Spread de puntas ≤ {BOND_LIQUID_SPREAD_MAX_PCT:.0f}%.
5. **Jurisdicción** — Ley Nueva York.

**Resultado:** 4-5 puntos → 🌟 MUY ATRACTIVO | 3 → 🟢 ATRACTIVO | 2 → 🟡 NEUTRAL | 0-1 → 🟠 POCO ATRACTIVO.

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
| Precios, puntas, volumen | [data912]({DATA912_CORPORATE_BONDS_URL}) | API pública sin API key. Es dato educativo con caché de ~2 hs del lado del proveedor: sirve para analizar rendimientos, no para operar al segundo. |
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

**Otras fuentes de precios**, si querés reemplazar el feed: BYMA Open Data
(`open.bymadata.com.ar`, sin key pero sin documentar), la API de BYMA para socios, o el broker
donde operás (IOL, Bull Market, Cocos, etc. exponen API con cuenta).
            """
        )


def render_bonds_panel():
    """Dibuja la pestaña completa de Bonos Corporativos (ONs)."""
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

    unverified = int((~df_bonds["Verificado"] & df_bonds["En Catálogo"]).sum())
    if unverified:
        st.warning(
            f"⚠️ **{unverified} ON(s) del catálogo local tienen condiciones de emisión sin verificar.** "
            "Verificalas contra el prospecto y marcá `verificado=si` en `data/ons_catalog.csv`: "
            "un cupón mal cargado devuelve una TIR mansamente incorrecta."
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

    render_bonds_table(df_filtered)

    _render_glossary()
    _render_methodology()
    _render_sources()
