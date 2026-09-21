"""
crypto/data_loader.py - Entrada/salida de la sección de criptomonedas.

Capa de I/O y nada más: baja precios (`crypto/prices_source.py`) y tamaños de
mercado (`crypto/market_source.py`), los cachea, y se los pasa a los módulos
puros —`crypto/panel.py` y `crypto/dominance.py`— que son los que calculan.
Es el único módulo de `crypto/` que importa `streamlit`.

Devuelve las tres cosas juntas —cuadro, historiales y lectura de rotación— en
vez de exponer una función por cada una. Las tres salen de la misma descarga:
partirlas en tres funciones cacheadas por separado significaría bajar los
mismos precios tres veces, o pasarse diccionarios de DataFrames entre cachés,
que es peor.

Bitcoin se descarga **siempre**, esté o no en el universo elegido: es la
referencia de la fuerza relativa y el numerador de la dominancia. Si se mira
solo el grupo de memecoins, no bajarlo dejaría en blanco las dos métricas que
justamente ahí más importan.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from constants import CRYPTO_BENCHMARK_TICKER
from crypto.catalog import assets_for_universe
from crypto.dominance import RotationReading, build_rotation_reading
from crypto.market_source import fetch_coin_sizes, fetch_global_market
from crypto.panel import build_crypto_panel, spec_for_timeframe
from crypto.prices_source import fetch_crypto_history

logger = logging.getLogger(__name__)


@st.cache_data(ttl=300, show_spinner=False)
def load_crypto_data(
    universe: str,
    timeframe: str = "1d",
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], RotationReading]:
    """
    Devuelve `(cuadro, historiales, rotación)` listos para dibujar.

    Cacheado cinco minutos, el mismo plazo que el tablero de acciones. Es un
    mercado que opera las 24 horas, así que no hay cierre a partir del cual
    los datos dejen de moverse, pero refrescar en cada interacción gastaría el
    límite de consultas del proveedor sin que el precio cambie lo suficiente
    como para mover una media de 200 barras.

    Ninguna fuente secundaria puede tumbar la sección: si fallan los tamaños
    de mercado o la dominancia global, el cuadro se arma igual y las columnas
    que dependían de ellos quedan vacías. Las criptos cuyo precio no responde
    quedan en `df.attrs['failed_tickers']`.
    """
    assets = assets_for_universe(universe)
    tickers = [a.ticker for a in assets]
    spec = spec_for_timeframe(timeframe)

    a_descargar = list(dict.fromkeys([*tickers, CRYPTO_BENCHMARK_TICKER]))
    historiales, fallidas = fetch_crypto_history(a_descargar, timeframe=timeframe)

    tamanios = fetch_coin_sizes(list(historiales))
    capitalizaciones = {t: c.market_cap for t, c in tamanios.items()}
    ofertas = {t: c.circulating_supply for t, c in tamanios.items()}

    df = build_crypto_panel(
        history=historiales,
        benchmark_history=historiales.get(CRYPTO_BENCHMARK_TICKER),
        timeframe=timeframe,
        # Solo las del universo: si Bitcoin no estaba entre ellas se bajó
        # igual como referencia, pero no corresponde agregarlo al cuadro.
        assets=tuple(a for a in assets if a.ticker in historiales),
        market_caps=capitalizaciones,
    )

    df.attrs["failed_tickers"] = [t for t in fallidas if t in tickers]
    df.attrs["benchmark_missing"] = CRYPTO_BENCHMARK_TICKER not in historiales

    mercado_global, error_global = fetch_global_market()
    rotacion = build_rotation_reading(
        history=historiales,
        supplies=ofertas,
        excess_vs_btc=df["RS_BTC_PP"] if "RS_BTC_PP" in df.columns else pd.Series(dtype=float),
        benchmark_ticker=CRYPTO_BENCHMARK_TICKER,
        window_bars=spec.ventana_dominancia,
        global_btc_dominance_pct=mercado_global.btc_dominance_pct if mercado_global else None,
        global_eth_dominance_pct=mercado_global.eth_dominance_pct if mercado_global else None,
        total_market_cap_usd=mercado_global.total_market_cap_usd if mercado_global else None,
        global_error=error_global,
    )

    return df, historiales, rotacion


@st.cache_data(ttl=900, show_spinner=False)
def load_chart_history(ticker: str, interval: str) -> pd.DataFrame:
    """
    Historial de una sola moneda en la escala que pide el gráfico.

    Va aparte de `load_crypto_data` porque responde a otra pregunta y tiene
    otro ritmo: el cuadro necesita las veinte monedas en la temporalidad de
    análisis, y el gráfico necesita **una** moneda con toda la historia que
    haya. Una vela mensual cambia una vez por mes, así que se cachea quince
    minutos y no cinco.
    """
    historiales, _ = fetch_crypto_history([ticker], timeframe=interval)
    return historiales.get(ticker, pd.DataFrame())
