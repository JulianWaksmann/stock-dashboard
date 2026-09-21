"""
crypto/dominance.py - Dominancia de Bitcoin y rotación hacia altcoins.

Capa pura: recibe precios y ofertas circulantes ya descargados y devuelve las
series y etiquetas. Sin red y sin Streamlit, como el resto del motor.

**Por qué hay que reconstruir la serie en vez de pedirla.** La dominancia
global se publica como un número de hoy, no como una serie histórica gratuita,
y es el movimiento —no el nivel— lo que responde la pregunta útil: si la
dominancia sube, Bitcoin le está ganando al conjunto y estar en altcoins costó
plata aunque hayan subido en dólares.

La reconstrucción usa una identidad simple: la capitalización de una moneda es
su precio por su oferta en circulación. Con los precios (que sí hay, diarios y
por años) y la oferta de hoy se rearma cómo se movió el reparto del valor
dentro del panel.

**La aproximación y su límite, porque importa.** Se usa la oferta de hoy para
todo el período, ya que el histórico de emisión no está disponible en la
fuente. Para una ventana de un mes el error es despreciable: Bitcoin emite
~0,1% de su oferta por mes y las monedas grandes se mueven en ese orden. Sobre
varios años el supuesto deja de valer, y por eso la serie se corta en un año.
Es una aproximación honesta para leer rotación de corto plazo, no una
reconstrucción histórica de la capitalización.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from constants import (
    CRYPTO_ALTSEASON_MIN_PCT,
    CRYPTO_BTCSEASON_MAX_PCT,
    CRYPTO_DOMINANCE_BAND_PP,
    CRYPTO_ROTATION_STABLE,
    CRYPTO_ROTATION_TO_ALTS,
    CRYPTO_ROTATION_TO_BTC,
    CRYPTO_RS_NEUTRAL_BAND_PP,
    CRYPTO_SEASON_ALTS,
    CRYPTO_SEASON_BTC,
    CRYPTO_SEASON_MIXED,
)

logger = logging.getLogger(__name__)

# Tope de la serie reconstruida, en barras. Más allá de un año el supuesto de
# oferta constante deja de ser razonable (ver el docstring del módulo).
MAX_BARRAS_SERIE = 365


def reconstruct_panel_dominance(
    history: dict[str, pd.DataFrame],
    supplies: dict[str, float | None],
    benchmark_ticker: str,
    max_bars: int = MAX_BARRAS_SERIE,
) -> pd.Series:
    """
    Serie de dominancia de Bitcoin **dentro del panel**, en %.

    No es la dominancia global y no hay que presentarla como tal: el panel
    tiene tres docenas de monedas y el mercado tiene miles. El nivel de esta
    serie es más alto que el global justamente por eso. Lo que sí es
    comparable es su movimiento, que es para lo que se usa.

    Las monedas sin oferta conocida se excluyen del total en vez de estimarse:
    una capitalización inventada mueve el reparto sin que se note. Si falta la
    del propio Bitcoin, o no queda ninguna otra moneda, devuelve una serie
    vacía.
    """
    if not history or benchmark_ticker not in history:
        return pd.Series(dtype=float)

    supply_btc = supplies.get(benchmark_ticker)
    if not supply_btc or not np.isfinite(supply_btc) or supply_btc <= 0:
        return pd.Series(dtype=float)

    capitalizaciones = {}
    for ticker, df in history.items():
        oferta = supplies.get(ticker)
        if df is None or df.empty or "Close" not in df.columns:
            continue
        if not oferta or not np.isfinite(oferta) or oferta <= 0:
            continue
        serie = df["Close"].dropna() * oferta
        # Las series pueden venir de orígenes distintos y no todas traen la
        # misma convención de zona horaria; alinear una con zona contra otra
        # sin zona es un error, no una diferencia cosmética.
        if isinstance(serie.index, pd.DatetimeIndex) and serie.index.tz is not None:
            serie.index = serie.index.tz_localize(None)
        capitalizaciones[ticker] = serie

    if len(capitalizaciones) < 2:
        return pd.Series(dtype=float)

    caps = pd.DataFrame(capitalizaciones).sort_index().tail(max_bars)

    # Un hueco suelto en una moneda no debe sacarla del total ese día: se
    # arrastra su último valor conocido. Los huecos iniciales (una moneda
    # que todavía no cotizaba) quedan en NaN y no suman, que es lo correcto.
    caps = caps.ffill()

    total = caps.sum(axis=1, skipna=True)
    dominancia = (caps[benchmark_ticker] / total.replace(0, np.nan)) * 100.0
    return dominancia.dropna()


def dominance_change_pp(series: pd.Series, bars: int) -> float:
    """
    Cuánto cambió la dominancia en las últimas `bars` barras, en puntos
    porcentuales. NaN si la serie no llega a cubrir la ventana.
    """
    if series is None or bars <= 0:
        return np.nan
    limpia = series.dropna()
    if len(limpia) < bars + 1:
        return np.nan
    return float(limpia.iloc[-1]) - float(limpia.iloc[-(bars + 1)])


def classify_rotation(change_pp: float) -> str:
    """
    Traduce el cambio de dominancia a la decisión que habilita.

    La banda muerta evita leer como rotación lo que es ruido de medición: la
    serie está reconstruida con oferta constante, así que décimas de punto no
    son señal de nada.
    """
    if change_pp is None or not np.isfinite(change_pp):
        return CRYPTO_ROTATION_STABLE
    if change_pp > CRYPTO_DOMINANCE_BAND_PP:
        return CRYPTO_ROTATION_TO_BTC
    if change_pp < -CRYPTO_DOMINANCE_BAND_PP:
        return CRYPTO_ROTATION_TO_ALTS
    return CRYPTO_ROTATION_STABLE


def altseason_index(excess_vs_btc: pd.Series) -> float:
    """
    Qué porcentaje del universo le ganó a Bitcoin en la ventana.

    Réplica del índice de uso corriente. Toma la columna de exceso de retorno
    contra Bitcoin y cuenta cuántas lo superan con margen (la misma banda
    muerta que usa la columna `vs BTC`, para que el termómetro y la tabla no
    digan cosas distintas sobre la misma moneda).

    Bitcoin no se cuenta a sí mismo: su exceso es cero por construcción y
    sumarlo al denominador haría que el índice nunca llegue al tope.
    """
    if excess_vs_btc is None:
        return np.nan

    valores = pd.Series(excess_vs_btc).dropna()
    # El exceso exactamente nulo es Bitcoin contra sí mismo.
    valores = valores[valores != 0.0]
    if valores.empty:
        return np.nan

    superan = (valores > CRYPTO_RS_NEUTRAL_BAND_PP).sum()
    return float(superan) / float(len(valores)) * 100.0


def classify_season(index_pct: float) -> str:
    """
    Etiqueta del termómetro: temporada de altcoins, de Bitcoin, o mixta.

    Los umbrales son los de uso corriente (75% y 25%). El estado mixto es el
    más frecuente y está bien que lo sea: que cinco monedas de veinte le ganen
    a Bitcoin no es una temporada, son cinco monedas.
    """
    if index_pct is None or not np.isfinite(index_pct):
        return CRYPTO_SEASON_MIXED
    if index_pct >= CRYPTO_ALTSEASON_MIN_PCT:
        return CRYPTO_SEASON_ALTS
    if index_pct <= CRYPTO_BTCSEASON_MAX_PCT:
        return CRYPTO_SEASON_BTC
    return CRYPTO_SEASON_MIXED


@dataclass(frozen=True)
class RotationReading:
    """
    Todo lo que la sección necesita saber sobre el reparto BTC / altcoins.

    Junta las dos mediciones en un solo objeto porque se leen juntas y se
    contradicen seguido: la dominancia puede subir mientras varias altcoins
    sueltas le ganan a Bitcoin. Cuando eso pasa, lo que está diciendo el par
    es que la suba de las alts es angosta, y verlo requiere tener los dos
    números a la vista.

    Los campos globales pueden venir en None: son de una fuente externa que
    puede no responder, y la sección se dibuja igual sin ellos.
    """

    dominance_series: pd.Series
    dominance_change_pp: float
    rotation_label: str
    altseason_index_pct: float
    season_label: str
    global_btc_dominance_pct: float | None = None
    global_eth_dominance_pct: float | None = None
    total_market_cap_usd: float | None = None
    global_error: str | None = None


def build_rotation_reading(
    history: dict[str, pd.DataFrame],
    supplies: dict[str, float | None],
    excess_vs_btc: pd.Series,
    benchmark_ticker: str,
    window_bars: int,
    global_btc_dominance_pct: float | None = None,
    global_eth_dominance_pct: float | None = None,
    total_market_cap_usd: float | None = None,
    global_error: str | None = None,
) -> RotationReading:
    """
    Arma la lectura completa de rotación a partir de los datos ya descargados.

    Es pura: la parte que toca la red (precios, ofertas y dominancia global)
    ya ocurrió antes de llegar acá, y por eso todo esto se testea con series
    fijas.
    """
    serie = reconstruct_panel_dominance(history, supplies, benchmark_ticker)
    cambio = dominance_change_pp(serie, window_bars)
    indice = altseason_index(excess_vs_btc)

    return RotationReading(
        dominance_series=serie,
        dominance_change_pp=cambio,
        rotation_label=classify_rotation(cambio),
        altseason_index_pct=indice,
        season_label=classify_season(indice),
        global_btc_dominance_pct=global_btc_dominance_pct,
        global_eth_dominance_pct=global_eth_dominance_pct,
        total_market_cap_usd=total_market_cap_usd,
        global_error=global_error,
    )
