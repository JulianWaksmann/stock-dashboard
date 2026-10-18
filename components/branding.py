"""
components/branding.py - Identidad visual del tablero (carcasa, no contenido).

Streamlit no tiene sistema de diseño: cada widget trae su propio redondeo, su
propio espaciado y el gris por defecto del tema. Si cada panel corrige eso por
su cuenta con un `st.markdown` suelto, el tablero termina con tres cabeceras
distintas y cuatro verdes. Este módulo concentra **toda** la cosmética global
en un solo lugar: se inyecta una vez por corrida desde `app.main()`.

Los colores no se escriben acá: salen de `theme.py`, que sigue siendo la única
fuente de verdad. Acá vive la forma (espaciado, radios, sombras, tipografía),
no la paleta.

Es capa de dibujo: no calcula nada y no decide nada de negocio.
"""

from string import Template

import streamlit as st

from theme import (
    COLOR_BACKGROUND,
    COLOR_BORDER,
    COLOR_BRAND,
    COLOR_BRAND_BORDER,
    COLOR_BRAND_SOFT,
    COLOR_BRAND_STRONG,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    FONT_FAMILY,
    RADIUS_CARD,
    RADIUS_CONTROL,
)

# Ancla del selector de secciones. Streamlit no deja ponerle una clase a un
# widget, así que se dibuja un `<div>` vacío justo antes y se lo alcanza por
# `:has()`. Si el navegador no soporta `:has()`, el selector se ve como el
# `st.radio` de siempre: se degrada, no se rompe.
NAV_ANCHOR_ID = "nav-secciones"

_GLOBAL_CSS = Template("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stApp {
    font-family: $font;
}

.stApp {
    background:
        radial-gradient(1200px 520px at 12% -10%, rgba(52, 211, 153, 0.10), transparent 60%),
        radial-gradient(900px 420px at 95% 0%, rgba(16, 185, 129, 0.06), transparent 55%),
        $background;
    color: $text;
}

/* Un poco de aire arriba: el contenido no arranca pegado al borde. */
.block-container {
    padding-top: 2.2rem;
    max-width: 1500px;
}

/* ----------------------------------------------------------------
   Cabecera de sección (.main-title / .sub-title los usan los tres
   paneles: acciones, bonos y cripto).
   ---------------------------------------------------------------- */
.brand-bar {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    margin-bottom: 1.1rem;
}
.brand-mark {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    background: linear-gradient(135deg, $brand 0%, $brand_strong 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.05rem;
    box-shadow: 0 6px 18px rgba(16, 185, 129, 0.28);
}
.brand-name {
    font-size: 1.02rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: $text;
}
.brand-tag {
    font-size: 0.78rem;
    font-weight: 500;
    color: $muted;
    padding: 0.18rem 0.55rem;
    border: 1px solid $brand_border;
    border-radius: 999px;
    background: $brand_soft;
}

.main-title {
    font-size: 2.05rem;
    font-weight: 700;
    letter-spacing: -0.025em;
    line-height: 1.18;
    color: $text;
    margin-bottom: 0.3rem;
}
.sub-title {
    font-size: 0.95rem;
    font-weight: 400;
    line-height: 1.55;
    color: $muted;
    max-width: 70ch;
    margin-bottom: 1.1rem;
}

/* ----------------------------------------------------------------
   Selector de secciones como control segmentado
   ---------------------------------------------------------------- */
div.element-container:has(#$nav_anchor) + div div[role="radiogroup"] {
    gap: 0.35rem;
    background: $surface;
    border: 1px solid $border;
    border-radius: 999px;
    padding: 0.3rem;
    display: inline-flex;
    margin-bottom: 1.6rem;
}
div.element-container:has(#$nav_anchor) + div div[role="radiogroup"] label {
    border-radius: 999px;
    padding: 0.42rem 1.05rem;
    margin: 0;
    transition: background 0.15s ease, color 0.15s ease;
}
div.element-container:has(#$nav_anchor) + div div[role="radiogroup"] label:hover {
    background: $surface_alt;
}
div.element-container:has(#$nav_anchor) + div div[role="radiogroup"] label:has(input:checked) {
    background: $brand_soft;
    box-shadow: inset 0 0 0 1px $brand_border;
}
div.element-container:has(#$nav_anchor) + div div[role="radiogroup"] label:has(input:checked) p {
    color: $brand;
    font-weight: 600;
}
/* El puntito del radio sobra cuando las opciones ya son pastillas. Va tan
   adentro porque Streamlit envuelve cada opción en tres `div` sin clase
   estable: label > wrapper > fila > [punto, texto]. */
div.element-container:has(#$nav_anchor) + div div[role="radiogroup"] label > div > div > div:first-child {
    display: none;
}

/* ----------------------------------------------------------------
   Métricas como tarjetas
   ---------------------------------------------------------------- */
div[data-testid="stMetric"] {
    background: $surface;
    border: 1px solid $border;
    border-radius: $radius_card;
    padding: 1rem 1.15rem;
    transition: border-color 0.15s ease, transform 0.15s ease;
}
div[data-testid="stMetric"]:hover {
    border-color: $brand_border;
    transform: translateY(-1px);
}
div[data-testid="stMetricLabel"] p {
    font-size: 0.78rem;
    font-weight: 500;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: $muted;
}
div[data-testid="stMetricValue"] {
    font-size: 1.55rem;
    font-weight: 650;
    letter-spacing: -0.02em;
}

/* ----------------------------------------------------------------
   Botones, controles y contenedores
   ---------------------------------------------------------------- */
.stButton > button, .stDownloadButton > button {
    border-radius: $radius_control;
    font-weight: 600;
    border: 1px solid $border;
    transition: border-color 0.15s ease, background 0.15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    border-color: $brand_border;
    color: $brand;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, $brand 0%, $brand_strong 100%);
    border: none;
    color: #06231a;
}
.stButton > button[kind="primary"]:hover {
    filter: brightness(1.06);
    color: #06231a;
}

div[data-testid="stExpander"] {
    border: 1px solid $border;
    border-radius: $radius_card;
    background: $surface;
}

hr {
    border-color: $border;
    margin: 1.6rem 0;
}

/* Barra lateral: superficie propia, un poco más oscura que el lienzo. */
section[data-testid="stSidebar"] {
    background: $surface;
    border-right: 1px solid $border;
}
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    font-size: 0.98rem;
    letter-spacing: 0.01em;
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
            background=COLOR_BACKGROUND,
            surface=COLOR_SURFACE,
            surface_alt=COLOR_SURFACE_ALT,
            border=COLOR_BORDER,
            text=COLOR_TEXT,
            muted=COLOR_TEXT_MUTED,
            brand=COLOR_BRAND,
            brand_strong=COLOR_BRAND_STRONG,
            brand_soft=COLOR_BRAND_SOFT,
            brand_border=COLOR_BRAND_BORDER,
            radius_card=RADIUS_CARD,
            radius_control=RADIUS_CONTROL,
            nav_anchor=NAV_ANCHOR_ID,
        ),
        unsafe_allow_html=True,
    )


def render_brand_bar(etiqueta: str) -> None:
    """
    Dibuja la firma del producto arriba de todo: marca + sección actual.

    `etiqueta` es el nombre corto de lo que se está mirando ("Acciones",
    "Bonos", "Cripto"), para que la marca no quede como un adorno suelto.
    """
    st.markdown(
        f'<div class="brand-bar">'
        f'<div class="brand-mark">📊</div>'
        f'<div class="brand-name">Tablero Cuantitativo</div>'
        f'<div class="brand-tag">{etiqueta}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_nav_anchor() -> None:
    """
    Marca el punto del DOM desde el que se estiliza el selector de secciones.

    Va inmediatamente antes del `st.radio` de `app.main()`; el CSS lo alcanza
    por `:has()` sobre el contenedor hermano. Si se mueve uno de los dos, el
    selector pierde el aspecto de control segmentado (y nada más).
    """
    st.markdown(f'<div id="{NAV_ANCHOR_ID}"></div>', unsafe_allow_html=True)
