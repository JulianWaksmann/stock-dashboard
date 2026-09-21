"""
crypto/prices_source.py - Descarga de historiales de criptomonedas.

Toca la red pero no Streamlit, igual que `bonds/byma_source.py`: la caché y
los avisos en pantalla son problema de `crypto/data_loader.py`. Gracias a eso
`scripts/panel_cripto.py` puede bajar los mismos datos desde la terminal sin
arrastrar la interfaz.

La fuente es Yahoo Finance, la misma que la sección de acciones. No es la más
fina para cripto —el volumen que publica es un agregado de exchanges y no
siempre coincide con el de un mercado en particular— pero cubre el universo
entero con un solo pedido, tiene años de historia y ya es una dependencia del
proyecto. Para lo que hace el panel (medias, RSI, bandas, máximos anuales) la
serie de cierres alcanza y sobra.

Ninguna falla individual corta la descarga: la cripto que no responde queda
registrada y el resto del panel se arma igual.
"""

from __future__ import annotations

import logging
from typing import Final

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Cuánta historia se pide en cada temporalidad. El piso lo fija la SMA de 200
# barras más la ventana del máximo anual: en diario, 365 + 200 barras entran
# holgadas en dos años; en semanal hacen falta 200 semanas, casi cuatro años,
# así que se piden cinco.
_PERIOD_BY_INTERVAL: Final[dict[str, str]] = {
    "1d": "2y",
    "1wk": "5y",
    # Mensual se pide entero: sirve para buscar los niveles que el mercado
    # reconoce, y esos son justamente los de hace años.
    "1mo": "max",
}


def _period_for(interval: str) -> str:
    return _PERIOD_BY_INTERVAL.get(interval, _PERIOD_BY_INTERVAL["1d"])


def fetch_crypto_history(
    tickers: list[str],
    timeframe: str = "1d",
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """
    Baja el OHLCV de cada cripto y devuelve `(historiales, fallidas)`.

    Se pide todo en un único `yf.download`; si una cripto no viene en ese
    bloque se reintenta sola, porque la descarga masiva a veces omite un
    símbolo que individualmente sí responde. La que tampoco responde en el
    reintento se devuelve en la lista de fallidas, sin excepción: un panel de
    treinta criptomonedas no debe quedar en blanco porque una dejó de cotizar.
    """
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t and t.strip()))
    if not tickers:
        return {}, []

    interval = timeframe if timeframe in _PERIOD_BY_INTERVAL else "1d"
    period = _period_for(interval)

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
        logger.exception("Falló la descarga masiva de criptomonedas: %s", tickers)
        descarga = pd.DataFrame()

    historiales: dict[str, pd.DataFrame] = {}
    fallidas: list[str] = []

    for ticker in tickers:
        df_t = _extract(descarga, ticker, multiple=len(tickers) > 1)
        if df_t is None:
            df_t = _fetch_single(ticker, period, interval)

        if df_t is None or df_t.empty:
            logger.warning("Sin historial disponible para %s", ticker)
            fallidas.append(ticker)
            continue

        historiales[ticker] = _normalizar_indice(df_t.sort_index())

    return historiales, fallidas


def _normalizar_indice(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deja el índice sin zona horaria.

    Los dos caminos de descarga no devuelven lo mismo: el bloque masivo trae
    fechas sin zona y el reintento individual las trae con zona. Mientras cada
    moneda se mira sola no se nota, pero cualquier cuenta que las alinee entre
    sí —la dominancia, por ejemplo— falla con "Cannot join tz-naive with
    tz-aware" según qué monedas hayan caído en el reintento ese día. Se
    normaliza acá, en la frontera, para que el motor reciba siempre lo mismo.
    """
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)
    return df


def _extract(descarga: pd.DataFrame, ticker: str, multiple: bool) -> pd.DataFrame | None:
    """Saca el bloque de un ticker del resultado de la descarga masiva."""
    if descarga is None or descarga.empty:
        return None

    try:
        if multiple and isinstance(descarga.columns, pd.MultiIndex):
            if ticker not in descarga.columns.levels[0]:
                return None
            df_t = descarga[ticker].dropna(how="all").copy()
        else:
            df_t = descarga.copy()
    except (KeyError, ValueError) as exc:
        logger.warning("Bloque de precios con formato inesperado para %s: %s", ticker, exc)
        return None

    if df_t.empty or "Close" not in df_t.columns or df_t["Close"].dropna().empty:
        return None
    return df_t


def _fetch_single(ticker: str, period: str, interval: str) -> pd.DataFrame | None:
    """Reintento individual para una cripto que la descarga masiva no trajo."""
    try:
        df_t = yf.Ticker(ticker).history(period=period, interval=interval)
    except Exception:
        logger.exception("Error bajando el historial individual de %s", ticker)
        return None
    if df_t is None or df_t.empty or "Close" not in df_t.columns:
        return None
    return df_t
