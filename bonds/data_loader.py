"""
bonds/data_loader.py - Entrada/salida de la pestaña de ONs.

Este módulo es la capa de I/O y nada más: baja precios del feed público, baja
la curva del Tesoro de Yahoo Finance, lee el catálogo y le pasa todo a
`bonds.panel.build_bonds_panel`, que es quien hace las cuentas.

Separación deliberada de responsabilidades:

  * **Precios**: se descargan. Son públicos, cambian todo el tiempo y no tiene
    sentido versionarlos en el repo.
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
import requests
import streamlit as st
import yfinance as yf

from bonds.catalog import load_catalog
from bonds.panel import build_bonds_panel

logger = logging.getLogger(__name__)

# Fuente de precios por defecto: data912, un feed público y sin API key del
# panel argentino. Es dato educativo con caché de alrededor de 2 horas del
# lado del proveedor: sirve para analizar rendimientos, no para operar al
# segundo. Cambiar esta URL es todo lo que hace falta para usar otro feed que
# devuelva la misma forma de JSON.
DATA912_CORPORATE_BONDS_URL: Final[str] = "https://data912.com/live/arg_corp"

# Timeout de la llamada HTTP. Corto a propósito: si el feed no responde,
# preferimos degradar el panel a "sin precios" antes que colgar la interfaz.
REQUEST_TIMEOUT_SECONDS: Final[int] = 15

# Mapeo de los campos del feed a los nombres internos. Se declara explícito
# para que un cambio de esquema del proveedor se note al leer este diccionario
# y no como columnas vacías tres módulos más abajo.
_PRICE_FIELD_MAP: Final[dict[str, str]] = {
    "symbol": "Ticker",
    "c": "Precio",
    "px_bid": "Punta Compra",
    "px_ask": "Punta Venta",
    "q_bid": "Cant. Compra",
    "q_ask": "Cant. Venta",
    "v": "Volumen",
    "q_op": "Operaciones",
    "pct_change": "Var. (%)",
}

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
def fetch_live_bond_prices(url: str = DATA912_CORPORATE_BONDS_URL) -> pd.DataFrame:
    """
    Descarga los precios en vivo del panel de ONs.

    Nunca propaga la excepción: ante cualquier fallo (red cortada, feed caído,
    JSON con otra forma) devuelve un DataFrame vacío con el motivo en
    `df.attrs['error']`, para que la pestaña muestre un mensaje concreto en vez
    de una traza de error.
    """
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("No se pudo consultar el feed de ONs en %s: %s", url, exc)
        df = pd.DataFrame()
        df.attrs["error"] = f"No se pudo consultar el feed de precios ({exc})."
        return df
    except ValueError as exc:
        logger.warning("El feed de ONs devolvió una respuesta que no es JSON: %s", exc)
        df = pd.DataFrame()
        df.attrs["error"] = "El feed de precios devolvió una respuesta ilegible."
        return df

    if not isinstance(payload, list) or not payload:
        df = pd.DataFrame()
        df.attrs["error"] = "El feed de precios no devolvió ninguna especie."
        return df

    raw = pd.DataFrame(payload)
    missing = [field for field in ("symbol", "c") if field not in raw.columns]
    if missing:
        df = pd.DataFrame()
        df.attrs["error"] = f"El feed cambió de formato: faltan los campos {', '.join(missing)}."
        return df

    available = {src: dst for src, dst in _PRICE_FIELD_MAP.items() if src in raw.columns}
    df = raw[list(available)].rename(columns=available)
    df["Ticker"] = df["Ticker"].astype(str).str.strip().str.upper()

    for column in df.columns:
        if column != "Ticker":
            df[column] = pd.to_numeric(df[column], errors="coerce")

    # Una misma especie puede venir repetida con distintos plazos de
    # liquidación; nos quedamos con la primera aparición para no duplicar filas.
    return df.drop_duplicates(subset="Ticker", keep="first").reset_index(drop=True)


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
    inválidas, feed caído, ONs sin condiciones cargadas). La pestaña los
    muestra tal cual: acá es donde se sabe qué pasó, no en la capa de dibujo.
    """
    warnings: list[str] = []

    catalog, catalog_errors = load_catalog(catalog_path)
    warnings.extend(catalog_errors)

    prices = fetch_live_bond_prices()
    feed_error = prices.attrs.get("error") if hasattr(prices, "attrs") else None
    if feed_error:
        warnings.append(feed_error)
        return pd.DataFrame(), warnings

    panel = build_bonds_panel(
        prices=prices,
        catalog=catalog,
        settlement=settlement,
        price_is_dirty=price_is_dirty,
        treasury_curve=fetch_us_treasury_curve(),
    )

    uncatalogued = panel.loc[~panel["En Catálogo"], "Ticker"].tolist() if not panel.empty else []
    if uncatalogued:
        warnings.append(
            f"{len(uncatalogued)} ON(s) cotizan pero no tienen condiciones de emisión cargadas, "
            f"así que no se les puede calcular TIR ni duration: {', '.join(sorted(uncatalogued))}. "
            "Agregalas en data/ons_catalog.csv."
        )

    return panel, warnings
