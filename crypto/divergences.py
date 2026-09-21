"""
crypto/divergences.py - Divergencias entre el precio y el oscilador.

Capa pura, como `crypto/levels.py`, y apoyada en los mismos pivotes: una
divergencia es una comparación entre dos giros del precio, así que detectarla
es comparar qué hizo el oscilador en esos mismos dos momentos.

**Qué es.** Que el precio y su impulso digan cosas distintas. El precio marca
un máximo más alto que el anterior pero el RSI marca uno más bajo: el
movimiento sigue, pero con menos fuerza detrás. El espejo del lado comprador
es un mínimo más bajo en el precio contra un mínimo más alto en el RSI.

**Qué no es.** Una señal de entrada. Una divergencia puede sostenerse meses
antes de que el precio gire, y puede no girar nunca —en una tendencia fuerte
el RSI se satura y divergir es lo normal, no la excepción—. Por eso esto
alimenta el gráfico, que las marca para que se vean, y no el semáforo, que
tendría que decidir algo con ellas.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from constants import (
    CRYPTO_DIVERGENCE_BEARISH,
    CRYPTO_DIVERGENCE_BULLISH,
    CRYPTO_DIVERGENCE_MAX_GAP_BARS,
    CRYPTO_DIVERGENCE_MAX_SHOWN,
    CRYPTO_DIVERGENCE_MIN_PRICE_GAP_PCT,
    CRYPTO_DIVERGENCE_MIN_RSI_GAP,
)
from crypto.levels import find_pivots

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Divergence:
    """
    Una divergencia, con los dos puntos que la forman.

    Guarda las dos fechas y los dos valores (precio y oscilador) porque el
    gráfico dibuja el segmento que los une: una divergencia se entiende
    viendo las dos líneas ir en direcciones opuestas, no leyendo que existe.
    """

    kind: str
    first_date: pd.Timestamp
    second_date: pd.Timestamp
    first_price: float
    second_price: float
    first_osc: float
    second_osc: float

    @property
    def is_bearish(self) -> bool:
        return self.kind == CRYPTO_DIVERGENCE_BEARISH


def _valor_en(serie: pd.Series, fecha) -> float:
    """Valor del oscilador en esa barra, o NaN si no hay dato."""
    try:
        valor = float(serie.loc[fecha])
    except (KeyError, TypeError, ValueError):
        return np.nan
    return valor if np.isfinite(valor) else np.nan


def _comparar_giros(
    pivotes: list[tuple[pd.Timestamp, float]],
    oscilador: pd.Series,
    indice: pd.Index,
    buscar_bajista: bool,
    max_gap_bars: int,
) -> list[Divergence]:
    """
    Compara cada giro con el siguiente y se queda con los que divergen.

    Se comparan giros **consecutivos** y no todos contra todos: dos máximos
    con otros tres máximos en el medio no forman un par que alguien lea como
    divergencia, forman una tendencia.
    """
    encontradas = []

    for (fecha_1, precio_1), (fecha_2, precio_2) in zip(pivotes, pivotes[1:], strict=False):
        try:
            separacion = indice.get_loc(fecha_2) - indice.get_loc(fecha_1)
        except KeyError:
            continue
        if separacion <= 0 or separacion > max_gap_bars:
            continue

        if precio_1 <= 0:
            continue
        salto_precio = (precio_2 - precio_1) / precio_1 * 100.0
        if abs(salto_precio) < CRYPTO_DIVERGENCE_MIN_PRICE_GAP_PCT:
            continue

        osc_1 = _valor_en(oscilador, fecha_1)
        osc_2 = _valor_en(oscilador, fecha_2)
        if np.isnan(osc_1) or np.isnan(osc_2):
            continue
        if abs(osc_2 - osc_1) < CRYPTO_DIVERGENCE_MIN_RSI_GAP:
            continue

        if buscar_bajista:
            divergen = salto_precio > 0 and osc_2 < osc_1
            tipo = CRYPTO_DIVERGENCE_BEARISH
        else:
            divergen = salto_precio < 0 and osc_2 > osc_1
            tipo = CRYPTO_DIVERGENCE_BULLISH

        if divergen:
            encontradas.append(
                Divergence(
                    kind=tipo,
                    first_date=fecha_1,
                    second_date=fecha_2,
                    first_price=float(precio_1),
                    second_price=float(precio_2),
                    first_osc=osc_1,
                    second_osc=osc_2,
                )
            )

    return encontradas


def detect_divergences(
    df: pd.DataFrame,
    oscilador: pd.Series,
    lookaround: int,
    max_gap_bars: int = CRYPTO_DIVERGENCE_MAX_GAP_BARS,
    max_shown: int = CRYPTO_DIVERGENCE_MAX_SHOWN,
) -> list[Divergence]:
    """
    Divergencias entre el precio y el oscilador, de la más reciente hacia
    atrás.

    `lookaround` es el mismo entorno con el que se buscan los soportes y las
    resistencias, y usarlo de nuevo acá no es una economía: si un giro es lo
    bastante importante como para dejar un nivel en el gráfico, es el mismo
    giro que tiene sentido comparar contra el siguiente. Dos detectores de
    giros distintos marcarían niveles en un lado y divergencias en otro.
    """
    if df is None or df.empty or oscilador is None or oscilador.dropna().empty:
        return []

    maximos, minimos = find_pivots(df, lookaround=lookaround)
    indice = df.index

    encontradas = _comparar_giros(maximos, oscilador, indice, True, max_gap_bars)
    encontradas += _comparar_giros(minimos, oscilador, indice, False, max_gap_bars)

    encontradas.sort(key=lambda d: d.second_date, reverse=True)
    return encontradas[:max_shown]
