"""
components/cartera_panel.py - Sección "Mi cartera" del tablero.

Quien la abre sube los exports de sus brokers —el reporte de resultados de
Balanz, los CSV de movimientos de Cocos (uno por año)— y ve un solo informe en
dólares MEP. Igual que las otras secciones, la llama `app.main()` y desde acá
para abajo se maneja sola; los controles (carga de archivos y filtro por
broker) van en la tarjeta de arriba del título, como en el resto de los
paneles.

Privacidad: los archivos se procesan en memoria y no se escriben a disco, no
se cachean (`st.cache_data` los dejaría vivos en el servidor y compartidos
entre sesiones) y no pasan por `snapshots.py`. El informe no muestra nombre
ni número de cuenta. Lo único que se cachea es la serie pública del MEP.

Es capa de dibujo: lee y calcula a través de `cartera/`.
"""

import re

import streamlit as st

from cartera.cocos import es_cocos
from cartera.data_loader import load_serie_mep
from cartera.informe import armar_informe
from cartera.lectura import leer_archivos
from cartera.modelo import ExportInvalido, filtrar_broker
from components.cartera_report import render_cartera_report
from constants import CARTERA_BROKER_ALL


def _texto_plano(texto: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>~<$])", r"\\\1", texto)


def render_cartera_panel() -> None:
    with st.container(border=True):
        archivos = st.file_uploader(
            "Exports de tus brokers",
            type=["xlsx", "csv"],
            accept_multiple_files=True,
            help=(
                "Balanz: el reporte de resultados con información completa (.xlsx). "
                "Cocos: el export de movimientos de cuenta (.csv), uno por año; subí todos."
            ),
        )
        st.caption(
            "🔒 Los archivos se procesan en memoria y no se guardan. "
            "El informe no muestra tu nombre ni tu número de cuenta."
        )
        filtro = st.empty()

    st.markdown('<div class="main-title">Tu historia de inversiones, en dólares</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-title">Subí los exports de Balanz y de Cocos y te armamos un solo informe: '
        "qué ganaste con cada activo, cuánto cobraste de renta y cuánto rindió cada año.</div>",
        unsafe_allow_html=True,
    )

    if not archivos:
        return

    contenidos = [(a.name, a.getvalue()) for a in archivos]
    # El MEP solo hace falta para Cocos: Balanz trae el suyo en el Excel.
    hay_cocos = any(es_cocos(c) for _, c in contenidos)
    with st.spinner("Leyendo tus archivos..."):
        serie_mep = load_serie_mep() if hay_cocos else None
        try:
            cartera, avisos = leer_archivos(contenidos, serie_mep)
        except ExportInvalido as exc:
            st.error(str(exc))
            return

    for aviso in avisos:
        # Los avisos citan nombres de archivo, que elige quien sube: se
        # muestran como texto, sin que un "*" o un "[...]" se lea como Markdown.
        st.warning(_texto_plano(aviso))

    brokers = sorted(set(cartera.operaciones["broker"]) | set(cartera.lotes_abiertos["broker"]))
    elegido = None
    if len(brokers) > 1:
        with filtro:
            opcion = st.radio("Broker", (CARTERA_BROKER_ALL, *brokers), horizontal=True)
        elegido = None if opcion == CARTERA_BROKER_ALL else opcion

    render_cartera_report(armar_informe(filtrar_broker(cartera, elegido)))
