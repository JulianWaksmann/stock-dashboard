"""
bonds/data_loader.py - Entrada/salida de la pestaña de ONs.

Este módulo es la capa de I/O y nada más: baja precios de BYMA, baja la curva
del Tesoro de Yahoo Finance, lee el catálogo y le pasa todo a
`bonds.panel.build_bonds_panel`, que es quien hace las cuentas.

Separación deliberada de responsabilidades:

  * **Precios**: se descargan de BYMA, que es el mercado donde las ONs
    cotizan. Hubo un feed alternativo (data912) y se descartó al medirlo:
    listaba 616 especies contra 2727 y la mitad de sus precios llegaban con
    atraso, hasta 2,75% de diferencia sobre el mismo título. Un 0,17% de
    diferencia de precio ya mueve la TIR varios puntos básicos; en el extremo,
    casi un punto porcentual. Para comparar rendimientos entre bonos eso no es
    ruido tolerable.
  * **Condiciones de emisión**: se leen del catálogo (`bonds/catalog.py`). No
    existe una fuente pública y gratuita que las publique en formato
    consultable por máquina.
  * **Métricas**: las calcula `bonds/panel.py`, que no toca red ni Streamlit y
    por eso se puede testear con datos fijos.

Ninguna descarga propaga excepciones hacia arriba: los fallos se convierten en
avisos en castellano que la pestaña muestra tal cual.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Final

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from bonds.byma_source import fetch_byma_bond_prices
from bonds.byma_terms import BondReference, fetch_byma_terms
from bonds.catalog import load_catalog, quote_currency_of
from bonds.flows_source import BondFlows, fetch_community_flows
from bonds.panel import build_bonds_panel
from constants import BYMA_TERMS_FETCH_LIMIT

logger = logging.getLogger(__name__)

# Curva de referencia del Tesoro de EE.UU. para medir el spread crediticio.
# Son los cuatro tramos que Yahoo Finance publica como índice de rendimiento,
# ya expresados en % anual.
_UST_TENORS: Final[dict[str, float]] = {
    "^IRX": 0.25,
    "^FVX": 5.0,
    "^TNX": 10.0,
    "^TYX": 30.0,
}


@st.cache_data(ttl=600, show_spinner=False)
def fetch_live_bond_prices() -> pd.DataFrame:
    """
    Descarga el panel de ONs de BYMA.

    Fuente única a propósito. Hubo un feed alternativo como respaldo y se
    quitó después de medirlo contra BYMA con `scripts/verificar_fuentes.py`:
    sobre las 614 especies en común, la mitad de los precios llegaba con
    atraso —mediana de 0,17% de diferencia, máximo 2,75% sobre el mismo
    título—. Un respaldo que devuelve otro número no es un respaldo, es una
    segunda respuesta a la misma pregunta, y en un panel que compara
    rendimientos entre bonos esa diferencia se convierte en decenas de puntos
    básicos de TIR.

    Si BYMA no responde, el panel queda sin precios y lo dice. Es preferible a
    mostrar números que no son los del mercado sin que se note.

    Nunca propaga la excepción: el motivo del fallo queda en
    `df.attrs['error']`.
    """
    prices, error = fetch_byma_bond_prices()
    if error:
        prices.attrs["error"] = error
    return prices


def _feed_warnings(prices: pd.DataFrame) -> list[str]:
    """Avisos del feed que la pestaña tiene que mostrar tal cual."""
    if not hasattr(prices, "attrs"):
        return []
    return [prices.attrs[key] for key in ("volume_missing",) if prices.attrs.get(key)]


@st.cache_data(ttl=86_400, show_spinner=False)
def fetch_bond_references(tickers: tuple[str, ...]) -> tuple[dict[str, BondReference], str | None]:
    """
    Fichas técnicas de BYMA, cacheadas por un día.

    El emisor, la ley y la lámina mínima de un bono se fijan cuando se emite y
    no cambian, así que no tiene sentido volver a pedirlas con la frecuencia de
    los precios. El argumento es una tupla, y no una lista, porque
    `st.cache_data` necesita que la clave sea hasheable.
    """
    return fetch_byma_terms(list(tickers))


def _most_traded(prices: pd.DataFrame, limit: int) -> tuple[str, ...]:
    """
    Las especies más operadas de cada moneda.

    Acota cuántas fichas técnicas se piden: son una llamada por especie y el
    panel trae más de 2700. Se rankea por moneda porque el volumen de la
    especie en pesos está en pesos y el de la MEP en dólares, así que un
    ranking conjunto compara unidades distintas.
    """
    if prices.empty or "Volumen" not in prices.columns:
        return ()
    if "Moneda Precio" in prices.columns:
        position = prices.groupby("Moneda Precio", dropna=False)["Volumen"].rank(
            method="first", ascending=False
        )
        selected = prices[position <= limit]
    else:
        selected = prices.nlargest(limit, "Volumen", keep="first")
    return tuple(selected["Ticker"].astype(str))


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_bond_cashflows() -> tuple[dict[str, BondFlows], str | None]:
    """
    Cronogramas de pago publicados, cacheados por una hora.

    Se cachean mucho más tiempo que los precios porque no cambian con el
    mercado: un cronograma de pagos solo se mueve cuando la fuente incorpora
    una emisión nueva.
    """
    return fetch_community_flows()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_us_treasury_curve() -> dict[float, float]:
    """
    Rendimientos del Tesoro de EE.UU. por tramo, en % anual.

    Son la tasa libre de riesgo contra la cual se mide cuánto paga una ON por
    asumir riesgo argentino y riesgo del emisor. Si Yahoo no responde, se
    devuelve un diccionario vacío y el panel simplemente omite la columna de
    spread en vez de inventar una referencia.
    """
    curve: dict[float, float] = {}
    for symbol, tenor in _UST_TENORS.items():
        try:
            history = yf.Ticker(symbol).history(period="5d")
            if history.empty or "Close" not in history.columns:
                continue
            last = float(history["Close"].dropna().iloc[-1])
            if np.isfinite(last) and last > 0:
                curve[tenor] = last
        except Exception:
            logger.warning("No se pudo obtener el tramo %s de la curva del Tesoro", symbol)
    return curve


def load_bonds_data(
    settlement: date,
    price_is_dirty: bool = True,
    catalog_path: str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Punto de entrada de la pestaña: descarga, cruza y devuelve `(panel, avisos)`.

    Los avisos son mensajes ya redactados para el usuario (catálogo con filas
    inválidas, feed caído): acá es donde se sabe qué pasó, no en la capa de
    dibujo.

    Lo que **no** vuelve por acá es el detalle de qué ONs quedaron sin
    condiciones cargadas. El panel lista más de 600 especies y el catálogo
    cubre un puñado, así que enumerarlas en un aviso escupe una pared de
    tickers que nadie lee; la pestaña las cuenta y las ofrece dentro de un
    desplegable a partir de la columna "En Catálogo".
    """
    warnings: list[str] = []

    catalog, catalog_errors = load_catalog(catalog_path)
    warnings.extend(catalog_errors)

    flows_by_base, flows_error = fetch_bond_cashflows()
    if flows_error:
        warnings.append(flows_error)

    prices = fetch_live_bond_prices()
    feed_error = prices.attrs.get("error") if hasattr(prices, "attrs") else None
    if feed_error:
        warnings.append(feed_error)
        return pd.DataFrame(), warnings

    warnings.extend(_feed_warnings(prices))

    # La ficha técnica se pide solo para las más operadas: es una llamada por
    # especie, y el panel trae más de 2700.
    prices_with_currency = prices.assign(
        **{"Moneda Precio": prices["Ticker"].map(quote_currency_of)}
    )
    references, references_error = fetch_bond_references(
        _most_traded(prices_with_currency, BYMA_TERMS_FETCH_LIMIT)
    )
    if references_error:
        warnings.append(references_error)

    panel = build_bonds_panel(
        prices=prices,
        catalog=catalog,
        settlement=settlement,
        price_is_dirty=price_is_dirty,
        treasury_curve=fetch_us_treasury_curve(),
        flows_by_base=flows_by_base,
        references=references,
    )

    return panel, warnings
