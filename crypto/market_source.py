"""
crypto/market_source.py - Capitalización de mercado y dominancia global.

Toca la red pero no Streamlit, igual que `crypto/prices_source.py`.

Son **dos fuentes para dos preguntas distintas**, y hacen falta las dos:

  * **Capitalización y oferta circulante por moneda**: Yahoo Finance, el
    mismo proveedor que los precios. Las publica en el `info` de cada
    símbolo cripto. Sirven para dos cosas: mostrar el tamaño de cada moneda,
    y reconstruir cómo se movió la dominancia dentro del panel (ver
    `crypto/dominance.py`), que es lo que no se puede pedir hecho a ningún
    lado.
  * **Dominancia global de Bitcoin**: CoinGecko, un único pedido sin clave de
    API. Es la porción de **todo** el mercado cripto que es Bitcoin, contando
    miles de monedas y las stablecoins. El panel no puede calcular ese número
    —tiene tres docenas de monedas, no miles— y es la referencia que se
    publica en todos lados, así que se toma prestada en vez de inventar una
    aproximación y presentarla como si fuera la misma.

Ninguna falla propaga excepciones: la sección dibuja igual sin estos datos,
solo que sin las columnas y KPIs que dependen de ellos.
"""

from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass
from typing import Final

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# Endpoint público de CoinGecko. Sin clave de API y con límite de consultas
# generoso para un pedido cada diez minutos, que es lo que hace el panel.
COINGECKO_GLOBAL_URL: Final[str] = "https://api.coingecko.com/api/v3/global"

_TIMEOUT_SEGUNDOS: Final[int] = 12


@dataclass(frozen=True)
class GlobalMarket:
    """Foto del mercado cripto completo, tal como la publica CoinGecko."""

    btc_dominance_pct: float
    eth_dominance_pct: float
    total_market_cap_usd: float


@dataclass(frozen=True)
class CoinSize:
    """Tamaño de una moneda: capitalización y oferta en circulación."""

    ticker: str
    market_cap: float | None
    circulating_supply: float | None


def fetch_global_market() -> tuple[GlobalMarket | None, str | None]:
    """
    Dominancia global de Bitcoin y capitalización total del mercado.

    Devuelve `(datos, error)`; nunca lanza. El error es un texto en castellano
    listo para mostrar, porque quien lo lee en pantalla no tiene por qué
    entender un código HTTP.
    """
    try:
        respuesta = requests.get(COINGECKO_GLOBAL_URL, timeout=_TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
        datos = respuesta.json()["data"]
        porcentajes = datos["market_cap_percentage"]
        return (
            GlobalMarket(
                btc_dominance_pct=float(porcentajes["btc"]),
                eth_dominance_pct=float(porcentajes.get("eth", "nan")),
                total_market_cap_usd=float(datos["total_market_cap"]["usd"]),
            ),
            None,
        )
    except requests.RequestException as exc:
        logger.warning("No se pudo consultar la dominancia global: %s", exc)
        return None, "No se pudo consultar la dominancia global del mercado."
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Respuesta de dominancia global con formato inesperado: %s", exc)
        return None, "La fuente de dominancia global respondió en un formato inesperado."
    except Exception:
        logger.exception("Error inesperado consultando la dominancia global")
        return None, "No se pudo consultar la dominancia global del mercado."


def _fetch_one_size(ticker: str) -> CoinSize:
    """Capitalización y oferta de una moneda. Un fallo devuelve campos vacíos."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        logger.warning("No se pudo obtener el tamaño de %s", ticker)
        return CoinSize(ticker, None, None)

    def _positivo(valor) -> float | None:
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return None
        return numero if numero > 0 else None

    return CoinSize(
        ticker=ticker,
        market_cap=_positivo(info.get("marketCap")),
        circulating_supply=_positivo(info.get("circulatingSupply")),
    )


def fetch_coin_sizes(tickers: list[str]) -> dict[str, CoinSize]:
    """
    Capitalización y oferta circulante de cada moneda, en paralelo.

    Yahoo obliga a un pedido por símbolo para estos campos (no vienen en la
    descarga masiva de precios), así que se pide con un pool de hilos, igual
    que los fundamentales de acciones. Las que fallan vuelven con los campos
    en None y el resto del panel no se entera.
    """
    tickers = list(dict.fromkeys(t for t in tickers if t))
    if not tickers:
        return {}

    tamanios: dict[str, CoinSize] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(tickers))) as executor:
        futuros = {executor.submit(_fetch_one_size, t): t for t in tickers}
        for futuro in concurrent.futures.as_completed(futuros):
            ticker = futuros[futuro]
            try:
                tamanios[ticker] = futuro.result()
            except Exception:
                logger.exception("El hilo a cargo del tamaño de %s terminó con error", ticker)
                tamanios[ticker] = CoinSize(ticker, None, None)

    return tamanios
