"""
merval/data_loader.py - Descarga del panel argentino y armado del cuadro.

Capa de I/O: es el único módulo del motor argentino que toca la red y
`st.cache_data`. `merval/catalog.py` y `merval/ccl.py` son puros, y por eso
`scripts/panel_merval.py` puede correr la misma cadena desde la terminal.

Qué hace, en orden:

  1. Baja en un solo pedido los precios locales (`.BA`, en pesos) y los de los
     ADR (en dólares).
  2. Corrige los splits que el proveedor no ajustó (`merval/splits.py`). Va
     **antes** del dólar implícito a propósito: un salto de diez a uno sin
     corregir no solo arruina los indicadores de esa acción, también el tipo de
     cambio que su par aporta en las fechas anteriores al split.
  3. Calcula el dólar implícito del panel con los pares que tengan las dos
     puntas (`merval/ccl.py`).
  4. Convierte cada serie local a dólares y recién ahí calcula los indicadores,
     con `compute_stock_technicals` y los umbrales de acciones. El semáforo es
     el mismo que el de Estados Unidos: lo que cambia es la moneda en la que se
     mide el precio, no qué significa una confluencia.
  5. Arma las filas con `data_loader.build_summary_row`, el mismo contrato que
     usa el panel estadounidense, para que el cuadro, la ficha de detalle y los
     gráficos sean literalmente los mismos componentes.

Sin CCL no hay panel, y eso es a propósito: un cuadro de acciones argentinas en
pesos nominales mostraría medias móviles que suben solas y un RSI que marca
sobrecompra en cada devaluación. Antes que eso, la sección avisa que no pudo
calcular el tipo de cambio.
"""

from __future__ import annotations

import concurrent.futures
import logging

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from constants import (
    MERVAL_52W_WINDOW_DAILY,
    MERVAL_52W_WINDOW_WEEKLY,
    MERVAL_SQUEEZE_LOOKBACK_DAILY,
    MERVAL_SQUEEZE_LOOKBACK_WEEKLY,
)
from data_loader import _empty_fundamentals, build_summary_row, fetch_single_ticker_info
from indicators import compute_stock_technicals
from merval.catalog import MERVAL_UNIVERSE, adr_pairs, adr_tickers, local_tickers, stock_for
from merval.ccl import CclEstimate, implied_ccl_series, to_usd
from merval.splits import SplitEvent, adjust_for_splits

logger = logging.getLogger(__name__)


def ventanas_para(timeframe: str) -> tuple[int, int]:
    """Ventana anual y de squeeze, en barras, según la temporalidad."""
    if timeframe == "1wk":
        return MERVAL_52W_WINDOW_WEEKLY, MERVAL_SQUEEZE_LOOKBACK_WEEKLY
    return MERVAL_52W_WINDOW_DAILY, MERVAL_SQUEEZE_LOOKBACK_DAILY


def _descargar(tickers: list[str], timeframe: str) -> dict[str, pd.DataFrame]:
    """OHLCV de todos los tickers en un solo pedido, tolerante a faltantes."""
    period = "5y" if timeframe == "1wk" else "2y"
    interval = "1wk" if timeframe == "1wk" else "1d"

    try:
        descarga = yf.download(
            tickers=tickers,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )
    except Exception:
        logger.exception("Falló la descarga masiva del panel argentino: %s", tickers)
        return {}

    historiales: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            if isinstance(descarga.columns, pd.MultiIndex):
                if ticker not in descarga.columns.levels[0]:
                    continue
                df = descarga[ticker].dropna(how="all")
            else:
                df = descarga
            if df is not None and not df.empty and "Close" in df.columns:
                # Los dos mercados devuelven el índice con distinta zona
                # horaria según el camino de descarga; se normaliza acá, en la
                # frontera de I/O, porque alinear uno contra otro revienta.
                df = df.sort_index()
                if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                historiales[ticker] = df
        except (KeyError, ValueError):
            logger.warning("Formato inesperado en el historial de %s", ticker)
    return historiales


def _fundamentales(tickers: list[str]) -> dict[str, dict]:
    """Fundamentales de cada acción local, en paralelo (los que Yahoo tenga)."""
    resultado: dict[str, dict] = {}
    if not tickers:
        return resultado

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(tickers))) as pool:
        futuros = {pool.submit(fetch_single_ticker_info, t): t for t in tickers}
        for futuro in concurrent.futures.as_completed(futuros):
            ticker = futuros[futuro]
            try:
                datos = futuro.result()
            except Exception:
                logger.exception("Fallaron los fundamentales de %s", ticker)
                datos = {**_empty_fundamentals(ticker), "_fetch_ok": False}
            datos.pop("_fetch_ok", None)
            resultado[ticker] = datos
    return resultado


@st.cache_data(ttl=300, show_spinner=False)
def load_merval_data(timeframe: str = "1d") -> tuple[pd.DataFrame, dict[str, pd.DataFrame], CclEstimate]:
    """
    Devuelve `(df_summary, historiales_en_dolares, ccl)`, cacheado 5 minutos.

    `df_summary` tiene exactamente las columnas del panel estadounidense (ver
    `data_loader.build_summary_row`), con los precios ya en dólares. Los
    tickers que no se pudieron convertir quedan anotados en
    `df_summary.attrs["failed_tickers"]`, y las series a las que hubo que
    corregirles un split, en `df_summary.attrs["splits_corregidos"]`.
    """
    locales = list(local_tickers())
    adrs = list(adr_tickers())

    historiales = _descargar(locales + adrs, timeframe)

    # Splits sin ajustar, antes de cualquier cálculo: con el salto adentro, los
    # indicadores de esa acción y el tipo de cambio que aporta su par quedan
    # los dos mal (ver `merval/splits.py`).
    splits: dict[str, list[SplitEvent]] = {}
    for ticker in locales:
        historial = historiales.get(ticker)
        if historial is None or historial.empty:
            continue
        corregido, eventos = adjust_for_splits(historial)
        historiales[ticker] = corregido
        if eventos:
            splits[ticker] = eventos

    ccl = implied_ccl_series(
        {t: historiales.get(t) for t in locales},
        {t: historiales.get(t) for t in adrs},
        adr_pairs(),
    )

    if not ccl.disponible:
        vacio = pd.DataFrame()
        vacio.attrs["failed_tickers"] = sorted(locales)
        vacio.attrs["splits_corregidos"] = splits
        return vacio, {}, ccl

    ventana_52w, squeeze_lookback = ventanas_para(timeframe)
    tf_suffix = " (Sem)" if timeframe == "1wk" else " (Día)"

    historiales_usd: dict[str, pd.DataFrame] = {}
    fallidos: set[str] = set()
    for ticker in locales:
        en_pesos = historiales.get(ticker)
        if en_pesos is None or en_pesos.empty:
            fallidos.add(ticker)
            continue
        en_dolares = to_usd(en_pesos, ccl.serie)
        if en_dolares.empty:
            fallidos.add(ticker)
            continue
        historiales_usd[ticker] = en_dolares

    fundamentales = _fundamentales(list(historiales_usd))
    ultimo_ccl = ccl.ultimo

    filas = []
    for ticker in locales:
        historial = historiales_usd.get(ticker)
        tecnicos = compute_stock_technicals(
            historial if historial is not None else pd.DataFrame(),
            window_52w=ventana_52w,
            squeeze_lookback=squeeze_lookback,
        )

        fundamental = dict(fundamentales.get(ticker, _empty_fundamentals(ticker)))
        ficha = stock_for(ticker)
        if ficha is not None:
            # El nombre y el sector salen del catálogo: Yahoo devuelve nombres
            # inconsistentes para las especies locales y a veces ningún sector.
            fundamental["name"] = ficha.nombre
            fundamental["sector"] = ficha.sector

        # La capitalización de una especie local viene en pesos; en el cuadro
        # la columna está en miles de millones de dólares, como el resto.
        capitalizacion = fundamental.get("market_cap")
        if capitalizacion and np.isfinite(ultimo_ccl) and ultimo_ccl > 0:
            fundamental["market_cap"] = capitalizacion / ultimo_ccl

        filas.append(build_summary_row(ticker, fundamental, tecnicos, tf_suffix, timeframe))

    df_summary = pd.DataFrame(filas)
    df_summary.attrs["failed_tickers"] = sorted(fallidos)
    df_summary.attrs["ccl"] = ultimo_ccl
    # Se informa en pantalla: una serie corregida es un dato que el tablero
    # cambió, y eso no se hace en silencio.
    df_summary.attrs["splits_corregidos"] = splits
    return df_summary, historiales_usd, ccl


def universo_descripto() -> str:
    """Una línea con la composición del panel, para la cabecera."""
    con_adr = len(adr_pairs())
    return f"{len(MERVAL_UNIVERSE)} acciones del panel líder, {con_adr} con ADR en Nueva York"
