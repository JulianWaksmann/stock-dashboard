"""
cartera/data_loader.py - Entrada/salida de la sección "Mi cartera".

Lo único que se cachea acá es la serie pública del MEP. Los archivos que sube
cada persona **no**: `st.cache_data` los dejaría vivos en el servidor y
compartidos entre sesiones. Se leen en cada corrida, en memoria.
"""

from __future__ import annotations

import logging

import pandas as pd
import requests
import streamlit as st

from cartera.mep_source import fetch_serie_mep

logger = logging.getLogger(__name__)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _serie_mep_cacheada() -> pd.Series:
    return fetch_serie_mep()


def load_serie_mep() -> pd.Series | None:
    """
    La historia del MEP, o `None` si la fuente no responde.

    Seis horas de caché: es un dato diario, y las operaciones que importan
    son de días ya cerrados. El error se atrapa **afuera** de la función
    cacheada para que un corte de la fuente no quede guardado seis horas.
    Que falle no tumba la sección: sin MEP solo queda afuera lo que lo
    necesita (Cocos), y Balanz sigue con el suyo.
    """
    try:
        return _serie_mep_cacheada()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("No se pudo bajar la serie del MEP: %s", exc)
        return None
