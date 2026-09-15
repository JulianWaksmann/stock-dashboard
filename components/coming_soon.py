"""
components/coming_soon.py - Aviso único de "módulo en desarrollo".

Existe para que el texto de estos avisos esté en un solo lugar. Son lo que ve
alguien que entra a una sección todavía vacía, y por eso están escritos para
un lector de negocio: dicen **qué va a poder hacer ahí** y que todavía no está.

Nada de arquitectura interna. Un aviso previo explicaba que el motor de renta
fija ya era agnóstico de país y que faltaba la fuente de precios: es cierto,
es útil para quien programa, y no significa nada para quien quiere saber si
puede analizar un bono de Estados Unidos. Esa clase de detalle vive en el
código y en CLAUDE.md, no en pantalla.
"""

import streamlit as st


def render_coming_soon(titulo: str, descripcion: str) -> None:
    """
    Dibuja el aviso de una sección que todavía no está disponible.

    `descripcion` dice, en una o dos frases y sin tecnicismos, qué va a poder
    hacer el usuario cuando esté.
    """
    st.info(f"🚧 **{titulo}** — en desarrollo.\n\n{descripcion}")
