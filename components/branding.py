"""
components/branding.py - Identidad visual del tablero (carcasa, no contenido).

Streamlit no tiene sistema de diseño: cada widget trae su propio redondeo, su
propio espaciado y el gris por defecto del tema. Si cada panel corrige eso por
su cuenta con un `st.markdown` suelto, el tablero termina con tres cabeceras
distintas y cuatro violetas. Este módulo concentra **toda** la cosmética global
en un solo lugar: se inyecta una vez por corrida desde `app.main()`.

Los colores no se escriben acá: salen de `theme.py`, que sigue siendo la única
fuente de verdad. Acá vive la forma (espaciado, radios, sombras, tipografía),
no la paleta.

**No hay barra lateral.** El CSS la esconde entera, incluido el botón que la
vuelve a abrir, y los controles que vivían ahí se dibujan en el cuerpo dentro
de `st.container(border=True)`. El motivo no es estético: la barra lateral es
única para toda la aplicación, así que cada sección tenía que dibujar ahí sus
propios controles y el usuario leía el tablero en dos columnas que no se
miraban entre sí. Con los controles en el cuerpo, cada sección es una página
completa. Si se vuelve a necesitar la barra, hay que sacar la regla de abajo y
devolver los controles a `st.sidebar` en los tres paneles a la vez.

Es capa de dibujo: no calcula nada y no decide nada de negocio.
"""

from string import Template
from urllib.parse import quote

import streamlit as st

from constants import APP_CARTERA, APP_CONFLUENCIA, APP_OPTIONS, APP_TAGLINES
from theme import (
    COLOR_BACKGROUND,
    COLOR_BORDER,
    COLOR_BRAND,
    COLOR_BRAND_BORDER,
    COLOR_BRAND_SOFT,
    COLOR_BRAND_STRONG,
    COLOR_NEGATIVE,
    COLOR_NEGATIVE_BG,
    COLOR_NEGATIVE_TEXT_STRONG,
    COLOR_POSITIVE,
    COLOR_POSITIVE_BG,
    COLOR_POSITIVE_TEXT_STRONG,
    COLOR_SHADOW,
    COLOR_SQUEEZE_BG,
    COLOR_SQUEEZE_TEXT,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_FAMILY,
    FONT_FAMILY_DISPLAY,
    RADIUS_CARD,
    RADIUS_CONTROL,
)

# Anclas de los dos selectores de navegación: el de producto (la firma de
# marca) y el de secciones de Confluencia. Streamlit no deja ponerle una clase
# a un widget, así que se dibuja un `<div>` vacío justo antes y se lo alcanza
# por `:has()`. Si el navegador no soporta `:has()`, el selector se ve como el
# `st.radio` de siempre: se degrada, no se rompe.
NAV_ANCHOR_CLASS = "nav-anchor"
BRAND_ANCHOR_CLASS = "brand-nav-anchor"


def _svg_data_uri(cuerpo: str) -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" '
        f'stroke="{COLOR_BRAND}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">{cuerpo}</svg>'
    )
    return "data:image/svg+xml," + quote(svg)


# Los logos de cada píldora. El de Confluencia es el de la landing: una línea
# quebrada que sube y un punto. Van como data URI dentro del CSS porque son
# 200 bytes y servir estáticos solo para esto no vale la pena.
_ICONOS_PRODUCTO = {
    APP_CONFLUENCIA: _svg_data_uri(
        f'<path d="M3 17l5-6 4 3 5-8"/><circle cx="19.5" cy="5.5" r="2" fill="{COLOR_BRAND}" stroke="none"/>'
    ),
    APP_CARTERA: _svg_data_uri(
        '<path d="M17 8V5a1 1 0 0 0-1-1H6a2 2 0 0 0 0 4h12a1 1 0 0 1 1 1v3m0 4v3a1 1 0 0 1-1 1H6a2 2 0 0 1-2-2V6"/>'
        '<path d="M20 12v4h-4a2 2 0 0 1 0-4h4"/>'
    ),
}

_GLOBAL_CSS = Template("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stApp {
    font-family: $font;
}

/* ----------------------------------------------------------------
   Sin barra lateral (ver el docstring del módulo)
   ---------------------------------------------------------------- */
section[data-testid="stSidebar"],
div[data-testid="stSidebarCollapsedControl"],
div[data-testid="collapsedControl"] {
    display: none !important;
}

/* Lienzo blanco con un lavado lavanda arriba: el mismo recurso de la landing,
   que separa la cabecera del contenido sin dibujar una línea. */
.stApp {
    background:
        radial-gradient(1200px 520px at 86% -16%, rgba(139, 109, 255, 0.18), transparent 64%),
        radial-gradient(900px 420px at 4% -8%, rgba(91, 63, 228, 0.10), transparent 70%),
        linear-gradient(180deg, $surface_alt 0%, $background 640px);
    color: $text;
}

/* La barra de Streamlit (el botón Deploy y el menú) está fija arriba y mide
   unos 3.75rem. Con 2.2rem de padding, la firma de marca arrancaba debajo de
   ella y se veía cortada por el borde de esa barra. */
.block-container {
    padding-top: 5rem;
    max-width: 1500px;
}

/* Esa barra se mimetiza con el lienzo en vez de cortar el lavanda con una
   franja blanca, y difumina lo que pasa por detrás al desplazar: el mismo
   recurso que la cabecera de la landing. */
header[data-testid="stHeader"] {
    background: color-mix(in srgb, $surface_alt 78%, transparent);
    backdrop-filter: blur(10px);
    border-bottom: none;
}

h1, h2, h3, h4 {
    font-family: $font_display;
    font-weight: 600;
    color: $text;
    letter-spacing: -0.026em;
}

/* Los números en columna se comparan de un vistazo solo si cada dígito ocupa
   lo mismo. Vale para tablas y para las métricas, que son números grandes. */
div[data-testid="stDataFrame"],
div[data-testid="stMetricValue"],
div[data-testid="stMetricDelta"] {
    font-variant-numeric: tabular-nums;
}

/* ----------------------------------------------------------------
   Firma de marca, que es también el selector de producto
   ----------------------------------------------------------------
   Las dos píldoras (Confluencia / Mi cartera) son un `st.radio`: la elegida
   es la píldora violeta de la landing con el logo en un círculo blanco; la
   otra, la misma forma en blanco con borde lavanda. El logo y la bajada no
   pueden ir en el texto de una opción de radio, así que los pone el CSS:
   `::before` es el círculo del logo y `p::after` la bajada. Qué logo y qué
   bajada lleva cada opción lo decide `render_brand_nav()`, por posición. */
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] {
    gap: 0.7rem;
    flex-wrap: wrap;
    margin-bottom: 1.15rem;
}
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] label {
    margin: 0;
    padding: 0.42rem 1.1rem 0.42rem 0.45rem;
    border-radius: 999px;
    background: $surface;
    border: 1px solid $brand_border;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] label:hover {
    border-color: $brand;
}
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] label[data-selected="true"] {
    background: $brand;
    border-color: $brand;
    box-shadow: 0 12px 26px -14px rgba(49, 27, 140, 0.75);
}
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] label > div > div {
    display: flex;
    align-items: center;
    gap: 0.6rem;
}
/* El puntito del radio sobra: la píldora entera es la opción. */
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] label > div > div > div:first-child {
    display: none;
}
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] label > div > div::before {
    content: "";
    width: 30px;
    height: 30px;
    flex: none;
    border-radius: 999px;
    background-color: $brand_soft;
    background-position: center;
    background-repeat: no-repeat;
    background-size: 17px;
}
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] label[data-selected="true"] > div > div::before {
    background-color: #ffffff;
}
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] p {
    margin: 0;
    font-family: $font_display;
    font-size: 0.95rem;
    font-weight: 600;
    letter-spacing: -0.01em;
    line-height: 1.12;
    color: $brand_strong;
}
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] p::after {
    display: block;
    margin-top: 2px;
    font-family: $font;
    font-size: 0.58rem;
    font-weight: 500;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: $muted;
}
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] label[data-selected="true"] p {
    color: #ffffff;
}
div.element-container:has(.$brand_anchor) + div div[role="radiogroup"] label[data-selected="true"] p::after {
    color: rgba(255, 255, 255, 0.72);
}

.main-title {
    font-family: $font_display;
    font-size: 2.3rem;
    font-weight: 500;
    letter-spacing: -0.03em;
    line-height: 1.14;
    color: $text;
    margin-bottom: 0.4rem;
}
.sub-title {
    font-size: 0.95rem;
    font-weight: 400;
    line-height: 1.7;
    color: $muted;
    max-width: 70ch;
    margin-bottom: 1.1rem;
}

/* ----------------------------------------------------------------
   Selector de secciones como control segmentado
   ---------------------------------------------------------------- */
div.element-container:has(.$nav_anchor) + div div[role="radiogroup"] {
    gap: 0.3rem;
    background: $surface;
    border: 1px solid $border;
    border-radius: 999px;
    padding: 0.32rem;
    display: inline-flex;
    margin-bottom: 1.5rem;
    box-shadow: 0 10px 26px -18px $shadow;
}
div.element-container:has(.$nav_anchor) + div div[role="radiogroup"] label {
    border-radius: 999px;
    padding: 0.45rem 1.15rem;
    margin: 0;
    transition: background 0.15s ease, color 0.15s ease;
}
div.element-container:has(.$nav_anchor) + div div[role="radiogroup"] label:hover {
    background: $surface_alt;
}
div.element-container:has(.$nav_anchor) + div div[role="radiogroup"] label[data-selected="true"] {
    background: $brand;
    box-shadow: 0 10px 22px -12px rgba(49, 27, 140, 0.8);
}
div.element-container:has(.$nav_anchor) + div div[role="radiogroup"] label[data-selected="true"] p {
    color: #ffffff;
    font-weight: 600;
}
/* El puntito del radio sobra cuando las opciones ya son pastillas. Va tan
   adentro porque Streamlit envuelve cada opción en tres `div` sin clase
   estable: label > wrapper > fila > [punto, texto]. */
div.element-container:has(.$nav_anchor) + div div[role="radiogroup"] label > div > div > div:first-child {
    display: none;
}

/* ----------------------------------------------------------------
   Barra de controles: el `st.container(border=True)` de cada sección
   ----------------------------------------------------------------
   Es la tarjeta blanca que reemplazó a la barra lateral. Se estiliza por el
   contenedor con borde de Streamlit y no por un ancla con `:has()`, porque
   acá el elemento sí tiene un testid propio y estable. */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: $surface;
    border: 1px solid $border;
    border-radius: $radius_card;
    box-shadow: 0 16px 38px -26px $shadow;
}

/* ----------------------------------------------------------------
   Métricas como tarjetas
   ---------------------------------------------------------------- */
div[data-testid="stMetric"] {
    background: $surface;
    border: 1px solid $border;
    border-radius: $radius_card;
    padding: 1.05rem 1.2rem;
    box-shadow: 0 14px 34px -24px $shadow;
    transition: box-shadow 0.15s ease, transform 0.15s ease;
}
div[data-testid="stMetric"]:hover {
    box-shadow: 0 20px 44px -22px $shadow;
    transform: translateY(-2px);
}
div[data-testid="stMetricLabel"] p {
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: $muted;
}
div[data-testid="stMetricValue"] {
    font-family: $font_display;
    font-size: 1.6rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    color: $text;
}

/* ----------------------------------------------------------------
   Botones, controles y contenedores
   ---------------------------------------------------------------- */
.stButton > button, .stDownloadButton > button {
    border-radius: $radius_control;
    font-weight: 600;
    border: 1px solid $brand_border;
    background: $surface;
    color: $brand_strong;
    transition: border-color 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    border-color: $brand;
    color: $brand_strong;
    background: $brand_soft;
}
.stButton > button[kind="primary"] {
    background: $brand;
    border: none;
    color: #ffffff;
    box-shadow: 0 12px 26px -14px rgba(49, 27, 140, 0.8);
}
.stButton > button[kind="primary"]:hover {
    background: $brand_strong;
    color: #ffffff;
}

/* Campos: pastillas con borde lavanda, como el buscador de la landing.
   El valor va en 0.94rem y medio peso más que el cuerpo porque un control
   con tres letras adentro tiene que leerse como un control, no como una
   franja vacía: es lo que elige de qué activo habla la ficha entera. */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
div[data-testid="stTextInput"] input {
    border-radius: $radius_control;
    border-color: $border;
    background: $surface;
    font-size: 0.94rem;
    color: $text;
}
div[data-baseweb="select"] > div {
    min-height: 44px;
    font-weight: 500;
}
div[data-baseweb="select"] > div:hover {
    border-color: $brand_border;
}
div[data-baseweb="select"] > div:focus-within {
    border-color: $brand;
    box-shadow: 0 0 0 3px $brand_soft;
}

/* La etiqueta de cada widget: chica y en mayúsculas de caja baja, para que
   el valor sea lo que se lee primero. Va por el testid del rótulo y no por
   `label`, que también envuelve cada opción de un radio. */
div[data-testid="stWidgetLabel"] p {
    font-size: 0.78rem;
    font-weight: 600;
    color: $muted;
}
div[data-testid="stSlider"] div[role="slider"] {
    border-color: $brand;
}

div[data-testid="stExpander"] {
    border: 1px solid $border;
    border-radius: $radius_card;
    background: $surface;
    box-shadow: 0 14px 34px -26px $shadow;
}
div[data-testid="stExpander"] summary {
    font-weight: 600;
}

div[data-testid="stDataFrame"] {
    border-radius: 18px;
    overflow: hidden;
    box-shadow: 0 14px 34px -24px $shadow;
}

/* Avisos: el mismo redondeo que las tarjetas, o se ven pegados con escuadra
   en medio de una página de esquinas blandas. */
div[data-testid="stAlert"] {
    border-radius: 18px;
}

/* ----------------------------------------------------------------
   Alertas del día: una tarjeta por tipo de señal
   ----------------------------------------------------------------
   Es HTML propio y no una lista de viñetas de markdown porque una viñeta no
   alinea: con una viñeta de markdown, el precio de cada fila cae en una
   posición distinta según cuánto mida el ticker, y la columna deja de poder
   leerse de un vistazo. Acá cada dato tiene su celda. (Ojo con los signos
   peso en este bloque: es un `string.Template`, y un signo peso suelto en un
   comentario también cuenta como variable. Se escribe doble para que quede
   uno solo.) El color
   de cada tarjeta es el de la señal que agrupa (`COLOR_POSITIVE` /
   `COLOR_NEGATIVE` / squeeze), que es dato y no carcasa: es la única parte
   del chrome donde el verde y el rojo son correctos. */
.alert-card {
    background: $surface;
    border: 1px solid $border;
    border-radius: $radius_card;
    padding: 1.1rem 1.15rem 0.6rem;
    box-shadow: 0 14px 34px -26px $shadow;
    height: 100%;
}
.alert-card--buy {
    --alert-accent: $positive;
    --alert-soft: $positive_bg;
    --alert-ink: $positive_text;
}
.alert-card--sell {
    --alert-accent: $negative;
    --alert-soft: $negative_bg;
    --alert-ink: $negative_text;
}
.alert-card--squeeze {
    --alert-accent: $squeeze_text;
    --alert-soft: $squeeze_bg;
    --alert-ink: $squeeze_text;
}
.alert-card__head {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid $border;
}
.alert-card__dot {
    width: 9px;
    height: 9px;
    border-radius: 999px;
    background: var(--alert-accent);
    flex: none;
}
.alert-card__title {
    font-family: $font_display;
    font-size: 1rem;
    font-weight: 600;
    letter-spacing: -0.015em;
    color: $text;
}
.alert-card__count {
    margin-left: auto;
    font-size: 0.74rem;
    font-weight: 600;
    color: var(--alert-ink);
    background: var(--alert-soft);
    border-radius: 999px;
    padding: 0.16rem 0.6rem;
    font-variant-numeric: tabular-nums;
}
.alert-row {
    display: grid;
    grid-template-columns: auto auto 1fr;
    align-items: center;
    gap: 0.3rem 0.55rem;
    padding: 0.6rem 0;
    border-bottom: 1px solid rgba(91, 63, 228, 0.07);
}
.alert-row:last-child {
    border-bottom: none;
}
.alert-row__sym {
    font-family: ui-monospace, "SF Mono", "Menlo", monospace;
    font-size: 0.84rem;
    font-weight: 600;
    letter-spacing: 0.01em;
    color: $text;
}
.alert-row__grade {
    font-size: 0.66rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    border-radius: 999px;
    padding: 0.1rem 0.5rem;
    color: var(--alert-ink);
    border: 1px solid var(--alert-accent);
}
.alert-row__grade--strong {
    background: var(--alert-soft);
}
.alert-row__price {
    /* Fija la columna en vez de dejarla fluir: la tarjeta de squeeze no tiene
       pastilla de grado, y sin esto su precio caería una celda a la izquierda
       y las tres tarjetas dejarían de alinear. */
    grid-column: 3;
    justify-self: end;
    font-size: 0.86rem;
    font-weight: 600;
    color: $text;
    font-variant-numeric: tabular-nums;
}
.alert-row__meta {
    grid-column: 1 / -1;
    font-size: 0.74rem;
    color: $muted;
    font-variant-numeric: tabular-nums;
}
.alert-card__empty {
    padding: 0.85rem 0 0.9rem;
    font-size: 0.8rem;
    color: $muted;
}

/* ----------------------------------------------------------------
   Jerarquía de sección
   ----------------------------------------------------------------
   Los encabezados venían en cuatro tamaños distintos según quién los
   escribiera (`st.subheader`, `###`, `####`). Acá se fijan dos: título de
   sección y título de bloque. La bajada es un `st.caption`, que es donde
   ahora van los conteos que antes entraban entre paréntesis en el título. */
.block-container h3 {
    font-size: 1.3rem;
    margin-top: 0.6rem;
    margin-bottom: 0.15rem;
}
.block-container h4 {
    font-size: 1.04rem;
    margin-top: 0.4rem;
    margin-bottom: 0.15rem;
}
div[data-testid="stCaptionContainer"] p {
    font-size: 0.82rem;
    color: $muted;
}

hr {
    border: none;
    border-top: 1px solid $border;
    margin: 2rem 0 1.4rem;
}
</style>
""")


def inject_global_styles() -> None:
    """
    Inyecta la hoja de estilos del tablero. Se llama una vez por corrida.

    Streamlit reejecuta el script entero en cada interacción, así que esto se
    vuelve a emitir cada vez: es idempotente y barato (una etiqueta `<style>`).
    """
    st.markdown(
        _GLOBAL_CSS.substitute(
            font=FONT_FAMILY,
            font_display=FONT_FAMILY_DISPLAY,
            background=COLOR_BACKGROUND,
            surface=COLOR_SURFACE,
            surface_alt=COLOR_SURFACE_ALT,
            border=COLOR_BORDER,
            text=COLOR_TEXT,
            muted=COLOR_TEXT_MUTED,
            brand=COLOR_BRAND,
            brand_strong=COLOR_BRAND_STRONG,
            shadow=COLOR_SHADOW,
            brand_soft=COLOR_BRAND_SOFT,
            brand_border=COLOR_BRAND_BORDER,
            radius_card=RADIUS_CARD,
            radius_control=RADIUS_CONTROL,
            positive=COLOR_POSITIVE,
            positive_bg=COLOR_POSITIVE_BG,
            positive_text=COLOR_POSITIVE_TEXT_STRONG,
            negative=COLOR_NEGATIVE,
            negative_bg=COLOR_NEGATIVE_BG,
            negative_text=COLOR_NEGATIVE_TEXT_STRONG,
            squeeze_bg=COLOR_SQUEEZE_BG,
            squeeze_text=COLOR_SQUEEZE_TEXT,
            nav_anchor=NAV_ANCHOR_CLASS,
            brand_anchor=BRAND_ANCHOR_CLASS,
        ),
        unsafe_allow_html=True,
    )


def render_brand_nav() -> str:
    """
    Dibuja la firma de marca arriba de todo, que es el selector de producto.

    Devuelve la opción elegida (`APP_CONFLUENCIA` o `APP_CARTERA`). El logo y
    la bajada de cada píldora salen de acá y de `APP_TAGLINES`; la forma, del
    CSS global.
    """
    sel = f'div.element-container:has(.{BRAND_ANCHOR_CLASS}) + div div[role="radiogroup"]'
    reglas = "".join(
        f'{sel} label:nth-child({i}) > div > div::before {{ background-image: url("{_ICONOS_PRODUCTO[op]}"); }}'
        f'{sel} label:nth-child({i}) p::after {{ content: "{APP_TAGLINES[op]}"; }}'
        for i, op in enumerate(APP_OPTIONS, start=1)
    )
    st.markdown(f'<div class="{BRAND_ANCHOR_CLASS}"></div><style>{reglas}</style>', unsafe_allow_html=True)
    return st.radio("Vista", APP_OPTIONS, horizontal=True, label_visibility="collapsed")


def render_nav_anchor() -> None:
    """
    Marca el punto del DOM desde el que se estiliza un selector de navegación.

    Va inmediatamente antes de cada `st.radio` de navegación de `app.main()`; el CSS lo alcanza
    por `:has()` sobre el contenedor hermano. Si se mueve uno de los dos, el
    selector pierde el aspecto de control segmentado (y nada más).
    """
    st.markdown(f'<div class="{NAV_ANCHOR_CLASS}"></div>', unsafe_allow_html=True)
