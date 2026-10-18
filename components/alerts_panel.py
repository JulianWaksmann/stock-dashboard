"""
components/alerts_panel.py - Panel superior de alertas rápidas por Sistema de Grados.

Tres tarjetas, una por tipo de señal: lo que hay que vender o rotar, lo que
está en zona de compra y lo que está comprimido. Es un resumen para mirar de
arriba: el cuadro completo viene abajo.

Antes era una lista de viñetas de markdown y no se podía comparar. Con
`- **TICKER** [tag] — $precio *(RSI...)*`, el precio de cada fila arranca en
una posición distinta según cuánto mida el ticker, así que leer "cuál está más
caro" obligaba a recorrer renglón por renglón. Acá cada dato tiene su celda y
las tres tarjetas usan la misma grilla.

Lo usan acciones y cripto con el mismo aspecto. Lo que cambia entre los dos no
es la forma sino de dónde salen los datos: la columna del símbolo (`Ticker` o
`Cripto`), la del precio y cómo se formatea ese precio, porque una cripto puede
valer cinco millonésimos de dólar y `$0.00` no es un precio. Por eso las tres
cosas son parámetros y no hay dos copias de esta función.

Es capa de dibujo: arma filas y las entrega al HTML. La forma y el color viven
en `components/branding.py`, igual que el resto de la cosmética.
"""

from collections.abc import Callable
from html import escape

import pandas as pd
import streamlit as st

from components.formatting import format_signed_pct
from constants import (
    SIGNAL_MODERATE_BUY,
    SIGNAL_MODERATE_SELL,
    SIGNAL_SQUEEZE,
    SIGNAL_STRONG_BUY,
    SIGNAL_STRONG_SELL,
)

# Grado de convicción de cada fila. Es texto y no un emoji porque la tarjeta ya
# lleva el color de la señal: repetirlo con un círculo de color al lado del
# ticker no agrega información y sí ruido.
_GRADE_STRONG = "Fuerte"
_GRADE_MODERATE = "Moderada"


def _render_card(titulo: str, variante: str, filas: list[dict], vacio: str) -> None:
    """
    Dibuja una tarjeta de alertas con sus filas, o el motivo de que esté vacía.

    `variante` es el sufijo de la clase CSS (`buy`, `sell`, `squeeze`), que es
    lo que decide el color de acento. `filas` trae ya formateado todo lo que se
    muestra: esta función no calcula ni redondea nada.

    Sale como un solo bloque de HTML y no como varios `st.markdown`: Streamlit
    envuelve cada llamada en su propio contenedor, y la tarjeta se partiría en
    tantas cajas como filas tenga.
    """
    if filas:
        cuerpo = "".join(
            '<div class="alert-row">'
            f'<span class="alert-row__sym">{escape(fila["sym"])}</span>'
            + (
                f'<span class="alert-row__grade{fila["grade_class"]}">'
                f'{escape(fila["grade"])}</span>'
                if fila["grade"]
                else ""
            )
            + f'<span class="alert-row__price">{escape(fila["price"])}</span>'
            f'<span class="alert-row__meta">{escape(fila["meta"])}</span>'
            "</div>"
            for fila in filas
        )
    else:
        cuerpo = f'<div class="alert-card__empty">{escape(vacio)}</div>'

    st.markdown(
        f'<div class="alert-card alert-card--{variante}">'
        f'<div class="alert-card__head">'
        f'<span class="alert-card__dot"></span>'
        f'<span class="alert-card__title">{escape(titulo)}</span>'
        f'<span class="alert-card__count">{len(filas)}</span>'
        f"</div>{cuerpo}</div>",
        unsafe_allow_html=True,
    )


def _precio_en_dolares(valor: float) -> str:
    """Formato por omisión: el de una acción, con dos decimales."""
    return f"${valor:.2f}"


def _fila(simbolo: str, precio: str, grado: str | None, meta: str) -> dict:
    """Arma una fila ya formateada. `grado` en `None` es una tarjeta sin grados."""
    return {
        "sym": str(simbolo),
        "grade": grado or "",
        "grade_class": " alert-row__grade--strong" if grado == _GRADE_STRONG else "",
        "price": precio,
        "meta": meta,
    }


def render_alerts_panel(
    df: pd.DataFrame,
    *,
    columna_simbolo: str = "Ticker",
    columna_precio: str = "Precio Actual",
    formatear_precio: Callable[[float], str] = _precio_en_dolares,
):
    """
    Dibuja las tres tarjetas de alertas del día a partir del panel ya filtrado.

    Cada tarjeta agrupa los dos grados de su lado (fuerte y moderada) en vez de
    separarlos en columnas distintas: el grado es un matiz dentro de la misma
    decisión, no otra decisión.

    Los tres parámetros con nombre son lo único que distingue al panel de
    acciones del de cripto (ver el docstring del módulo).
    """
    if df.empty or "Semáforo" not in df.columns:
        return

    ventas = df[df["Semáforo"].isin([SIGNAL_STRONG_SELL, SIGNAL_MODERATE_SELL])]
    compras = df[df["Semáforo"].isin([SIGNAL_STRONG_BUY, SIGNAL_MODERATE_BUY])]
    squeezes = df[df["Semáforo"] == SIGNAL_SQUEEZE]

    col_venta, col_compra, col_squeeze = st.columns(3)

    with col_venta:
        _render_card(
            "Venta / rotación",
            "sell",
            [
                _fila(
                    r[columna_simbolo],
                    formatear_precio(r[columna_precio]),
                    _GRADE_STRONG if r["Semáforo"] == SIGNAL_STRONG_SELL else _GRADE_MODERATE,
                    f"RSI {r['RSI_VAL']:.1f} · máx. 52 s "
                    f"{format_signed_pct(r['DIST_52W_HIGH_PCT'], decimals=1)}",
                )
                for _, r in ventas.iterrows()
            ],
            "Ninguna hoy: no hay sobrecompras extremas en el panel.",
        )

    with col_compra:
        _render_card(
            "Compra / swing",
            "buy",
            [
                _fila(
                    r[columna_simbolo],
                    formatear_precio(r[columna_precio]),
                    _GRADE_STRONG if r["Semáforo"] == SIGNAL_STRONG_BUY else _GRADE_MODERATE,
                    f"RSI {r['RSI_VAL']:.1f} · vs SMA 50 "
                    f"{format_signed_pct(r['DIFF_SMA_50_VAL'], decimals=1)}",
                )
                for _, r in compras.iterrows()
            ],
            "Ninguna hoy: el panel está esperando retrocesos a soporte.",
        )

    with col_squeeze:
        _render_card(
            "Squeeze / compresión",
            "squeeze",
            [
                _fila(
                    r[columna_simbolo],
                    formatear_precio(r[columna_precio]),
                    None,
                    f"Ancho de bandas {r['BB_BANDWIDTH']:.1f}%",
                )
                for _, r in squeezes.iterrows()
            ],
            "Ninguno hoy: la volatilidad está en su rango habitual.",
        )
