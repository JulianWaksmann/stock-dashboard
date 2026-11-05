"""
components/cartera_report.py - Dibuja el informe de cartera.

El informe no se arma con widgets de Streamlit: `st.metric` y `st.dataframe`
no llegan a lo que pide (cabecera con degradé, tabla maestro-detalle, donut,
calendario con chips), así que es un componente propio de
`st.components.v2` con HTML, CSS y JavaScript en `components/cartera_report/`.
Se monta en la página, no en un iframe, así que toma su alto solo y usa las
fuentes que ya cargó `branding.py`; su CSS vive dentro de un shadow root, así
que la hoja global del tablero no lo toca y él no toca al tablero.

Los colores salen de `theme.py`, igual que en el resto del tablero: el CSS
tiene marcadores `$nombre` que se llenan acá. Ninguna cuenta vive en el
JavaScript: recibe el diccionario de `cartera/informe.py` y le da formato.

Es capa de dibujo: no calcula nada y no decide nada de negocio.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

import streamlit as st

from theme import (
    COLOR_BACKGROUND,
    COLOR_BRAND,
    COLOR_BRAND_LIGHT,
    COLOR_BRAND_STRONG,
    COLOR_NEGATIVE,
    COLOR_NEGATIVE_TEXT_STRONG,
    COLOR_POSITIVE,
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
)

_DIR = Path(__file__).parent / "cartera_report"


def _css() -> str:
    return Template((_DIR / "report.css").read_text(encoding="utf-8")).substitute(
        brand=COLOR_BRAND,
        brand_strong=COLOR_BRAND_STRONG,
        brand_light=COLOR_BRAND_LIGHT,
        text=COLOR_TEXT,
        muted=COLOR_TEXT_MUTED,
        surface=COLOR_SURFACE,
        surface_alt=COLOR_SURFACE_ALT,
        background=COLOR_BACKGROUND,
        shadow=COLOR_SHADOW,
        positive=COLOR_POSITIVE,
        negative=COLOR_NEGATIVE,
        positive_text=COLOR_POSITIVE_TEXT_STRONG,
        negative_text=COLOR_NEGATIVE_TEXT_STRONG,
        squeeze_bg=COLOR_SQUEEZE_BG,
        squeeze_text=COLOR_SQUEEZE_TEXT,
        font=FONT_FAMILY,
        font_display=FONT_FAMILY_DISPLAY,
        radius_card=RADIUS_CARD,
    )


# Se registra una sola vez por proceso: registrar en cada corrida reemplaza el
# componente y Streamlit avisa en el log.
_informe = st.components.v2.component(
    "informe_cartera",
    html=(_DIR / "report.html").read_text(encoding="utf-8"),
    css=_css(),
    js=(_DIR / "report.js").read_text(encoding="utf-8"),
)


def render_cartera_report(informe: dict) -> None:
    """Monta el informe. `informe` es la salida de `cartera.informe.armar_informe`."""
    _informe(data=informe, key="informe_cartera")
