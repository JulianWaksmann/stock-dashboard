"""
crypto/levels.py - Detección de soportes y resistencias.

Capa pura: recibe un OHLCV y devuelve niveles. Sin red, sin Streamlit y sin
dependencia de cripto, aunque hoy solo lo use esa sección.

El método es el que usa cualquiera a mano sobre un gráfico, escrito como
código: buscar los puntos donde el precio giró (**pivotes**: un máximo que es
el más alto de su entorno, un mínimo que es el más bajo), y después juntar los
que están a la misma altura, porque un nivel al que el precio volvió cuatro
veces es el mismo nivel visto cuatro veces, no cuatro niveles pegados.

De ahí sale lo único que distingue un nivel importante de una línea cualquiera:
**cuántas veces el precio lo respetó**. Un techo tocado una sola vez es un
máximo; uno tocado cuatro veces es una zona donde hay vendedores esperando.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from constants import (
    CRYPTO_CHART_SCALE_MONTHLY,
    CRYPTO_CHART_SCALE_PARAMS,
    CRYPTO_LEVEL_CLUSTER_PCT,
    CRYPTO_LEVEL_STRONG_TOUCHES,
    CRYPTO_LEVELS_PER_SIDE,
    CRYPTO_PIVOT_LOOKAROUND_BARS,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriceLevel:
    """
    Un nivel de precio con la evidencia que lo sostiene.

    `touches` es cuántos pivotes distintos cayeron en la misma zona, y es lo
    que separa un nivel fuerte de una línea trazada sobre un máximo casual.
    """

    price: float
    touches: int
    last_touch: pd.Timestamp | None

    @property
    def is_strong(self) -> bool:
        """Si el precio volvió a este nivel las veces suficientes."""
        return self.touches >= CRYPTO_LEVEL_STRONG_TOUCHES


def find_pivots(
    df: pd.DataFrame,
    lookaround: int = CRYPTO_PIVOT_LOOKAROUND_BARS,
) -> tuple[list[tuple[pd.Timestamp, float]], list[tuple[pd.Timestamp, float]]]:
    """
    Máximos y mínimos locales del OHLCV, como `(máximos, mínimos)`.

    Un pivote es una barra cuyo máximo (o mínimo) no es superado por ninguna
    de las `lookaround` barras de cada lado. Cuanto más ancho el entorno,
    menos pivotes y más importantes: con 10 barras se ignoran los giros de
    un par de días y quedan los que se ven a simple vista en el gráfico.

    Las últimas `lookaround` barras no pueden producir pivotes —todavía no
    existe el costado derecho que los confirme— y eso es correcto: un techo
    no es un techo hasta que el precio se aleja de él.
    """
    if df is None or df.empty or lookaround < 1:
        return [], []

    high = df["High"] if "High" in df.columns else df.get("Close")
    low = df["Low"] if "Low" in df.columns else df.get("Close")
    if high is None or low is None:
        return [], []

    high = high.dropna()
    low = low.dropna()
    ventana = 2 * lookaround + 1
    if len(high) < ventana:
        return [], []

    max_movil = high.rolling(ventana, center=True).max()
    min_movil = low.rolling(ventana, center=True).min()

    maximos = _colapsar_eventos(high, high == max_movil, lookaround, quedarse_con_el_mayor=True)
    minimos = _colapsar_eventos(low, low == min_movil, lookaround, quedarse_con_el_mayor=False)
    return maximos, minimos


def _colapsar_eventos(
    serie: pd.Series,
    es_candidato: pd.Series,
    lookaround: int,
    quedarse_con_el_mayor: bool,
) -> list[tuple[pd.Timestamp, float]]:
    """
    Reduce a un solo pivote las barras contiguas que son el mismo giro.

    Hace falta porque un techo plano genera un candidato por barra: si el
    precio se queda veinte barras en el máximo, las veinte son "el máximo de
    su entorno". Sin colapsar, ese techo cuenta como veinte toques y el nivel
    aparece como fortísimo cuando en realidad el precio estuvo ahí una sola
    vez.

    No es un caso raro: el proveedor redondea el precio de las monedas muy
    chicas a un decimal significativo, así que una moneda que cotiza en
    millonésimos tiene mesetas perfectamente planas de decenas de barras
    —medido sobre dos años de SHIB: 31 precios distintos en 731 ruedas, y 181
    pivotes de máximo antes de este colapso—.

    Dos candidatos separados por más de `lookaround` barras son giros
    distintos y se conservan los dos.
    """
    # Posiciones dentro de la serie completa, no dentro del subconjunto
    # filtrado: la distancia entre dos giros se mide en barras del gráfico.
    posiciones = np.flatnonzero(es_candidato.to_numpy())
    if len(posiciones) == 0:
        return []

    grupos: list[list[int]] = [[posiciones[0]]]
    for pos in posiciones[1:]:
        if pos - grupos[-1][-1] <= lookaround:
            grupos[-1].append(pos)
        else:
            grupos.append([pos])

    elegir = max if quedarse_con_el_mayor else min
    pivotes = []
    for grupo in grupos:
        pos = elegir(grupo, key=lambda j: serie.iloc[j])
        pivotes.append((serie.index[pos], float(serie.iloc[pos])))
    return pivotes


def cluster_levels(
    pivots: list[tuple[pd.Timestamp, float]],
    cluster_pct: float = CRYPTO_LEVEL_CLUSTER_PCT,
) -> list[PriceLevel]:
    """
    Agrupa pivotes cercanos en un solo nivel.

    La cercanía se mide en porcentaje y no en dólares porque un nivel es una
    zona, y el ancho de esa zona escala con el precio: medio punto porcentual
    son $400 en Bitcoin y una millonésima en una memecoin.

    El nivel resultante es el **promedio** de los pivotes del grupo, no el
    extremo: si el precio giró tres veces en una franja, la franja es el
    nivel, y quedarse con el pico más alto dibujaría una línea por la que el
    precio casi nunca pasó.
    """
    if not pivots or cluster_pct <= 0:
        return []

    ordenados = sorted(pivots, key=lambda par: par[1])
    grupos: list[list[tuple[pd.Timestamp, float]]] = [[ordenados[0]]]

    for fecha, precio in ordenados[1:]:
        referencia = np.mean([p for _, p in grupos[-1]])
        if referencia > 0 and abs(precio - referencia) / referencia * 100.0 <= cluster_pct:
            grupos[-1].append((fecha, precio))
        else:
            grupos.append([(fecha, precio)])

    niveles = []
    for grupo in grupos:
        precios = [p for _, p in grupo]
        fechas = [f for f, _ in grupo if f is not None]
        niveles.append(
            PriceLevel(
                price=float(np.mean(precios)),
                touches=len(grupo),
                last_touch=max(fechas) if fechas else None,
            )
        )
    return niveles


def detect_support_resistance(
    df: pd.DataFrame,
    current_price: float | None = None,
    lookaround: int = CRYPTO_PIVOT_LOOKAROUND_BARS,
    cluster_pct: float = CRYPTO_LEVEL_CLUSTER_PCT,
    per_side: int = CRYPTO_LEVELS_PER_SIDE,
) -> tuple[list[PriceLevel], list[PriceLevel]]:
    """
    Soportes y resistencias alrededor del precio actual, como `(soportes,
    resistencias)`, ordenados del más cercano al más lejano.

    Se devuelven pocos y cercanos a propósito. Un gráfico con quince líneas
    no informa nada: siempre hay una cerca, así que el precio siempre parece
    estar "en un nivel". Los tres de cada lado son los que efectivamente
    pueden frenar el precio en los próximos movimientos.

    Los pivotes de máximos y de mínimos se juntan antes de agrupar porque un
    techo roto pasa a funcionar como piso: son el mismo nivel, y separarlos
    lo contaría dos veces.
    """
    if df is None or df.empty:
        return [], []

    if current_price is None:
        cierres = df["Close"].dropna() if "Close" in df.columns else pd.Series(dtype=float)
        if cierres.empty:
            return [], []
        current_price = float(cierres.iloc[-1])

    if not np.isfinite(current_price) or current_price <= 0:
        return [], []

    maximos, minimos = find_pivots(df, lookaround=lookaround)
    niveles = cluster_levels(maximos + minimos, cluster_pct=cluster_pct)

    soportes = sorted(
        [n for n in niveles if n.price < current_price],
        key=lambda n: current_price - n.price,
    )
    resistencias = sorted(
        [n for n in niveles if n.price > current_price],
        key=lambda n: n.price - current_price,
    )
    return soportes[:per_side], resistencias[:per_side]


@dataclass(frozen=True)
class ChartScale:
    """
    Cómo buscar y dibujar niveles en una escala de tiempo.

    La escala no es una preferencia visual: **es** la definición de qué se
    considera un nivel. En velas diarias de seis meses aparecen giros de
    corto plazo, casi todos con uno o dos toques; en velas mensuales de
    varios años aparecen los techos y pisos que el mercado reconoce y a los
    que el precio vuelve. Por eso cada escala trae su propio entorno de
    pivote y su propia tolerancia de agrupamiento: un entorno de 10 barras
    son dos semanas en diario y casi un año en mensual.
    """

    interval: str
    lookaround: int
    cluster_pct: float
    bars: int


def scale_params(scale: str) -> ChartScale:
    """
    Parámetros de la escala elegida en el selector del gráfico.

    Una escala desconocida cae en mensual, que es la de omisión, en vez de
    devolver un gráfico vacío.
    """
    interval, lookaround, cluster_pct, bars = CRYPTO_CHART_SCALE_PARAMS.get(
        scale, CRYPTO_CHART_SCALE_PARAMS[CRYPTO_CHART_SCALE_MONTHLY]
    )
    return ChartScale(interval=interval, lookaround=lookaround, cluster_pct=cluster_pct, bars=bars)
