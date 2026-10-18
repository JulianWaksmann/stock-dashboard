"""
merval/splits.py - Splits que el proveedor no ajustó, en las series locales.

El problema, medido: `MIRG.BA` pasa de 16.350 a 1.640 pesos entre el 31 de
julio y el 3 de agosto de 2026, sin que ninguna otra cosa se mueva. No es una
caída del 90%, es un split de diez a uno que Yahoo publica con `auto_adjust`
activado y aun así no corrige en la serie local. Pasa seguido en las especies
de Buenos Aires y casi nunca en los ADR.

Por qué no se puede ignorar: una discontinuidad así envenena **todo** lo que se
calcula sobre la serie. Con ese salto adentro, Mirgor mostraba un precio 89%
por debajo de su media de 200 ruedas y 94% por debajo de su máximo anual, y el
semáforo lo leía como una acción destruida en vez de como una acción partida en
diez. Y es invisible: el número que sale es perfectamente plausible.

Cómo se distingue un split de un derrumbe real, que es la única parte
delicada. Un split cambia el precio por un factor **simple** —diez a uno, cinco
a uno— y no cambia nada más. Entonces se exige que:

  * el salto sea grande (más de `MERVAL_SPLIT_MIN_JUMP_PCT`): nadie parte una
    acción en 1,1;
  * el factor esté a menos de `MERVAL_SPLIT_FACTOR_TOLERANCE_PCT` de uno de los
    factores que se usan en la práctica (2, 3, 5, 10, 100…), en cualquiera de
    las dos direcciones.

Una caída genuina que caiga por casualidad a menos de 3% de exactamente un
décimo es posible y quedaría mal corregida. Es un riesgo aceptado y mucho menor
que el contrario: dejar el salto garantiza indicadores falsos, corregirlo de más
es un caso raro. El tablero informa qué series tocó, en vez de arreglarlas en
silencio.

Es puro: sin red y sin Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from constants import (
    MERVAL_SPLIT_FACTOR_TOLERANCE_PCT,
    MERVAL_SPLIT_MIN_JUMP_PCT,
)

# Factores de split que se usan en la práctica. Se prueban en las dos
# direcciones: un split divide el precio y un split inverso lo multiplica.
_FACTORES_PLAUSIBLES = (2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 50, 100, 1000)


@dataclass(frozen=True)
class SplitEvent:
    """Un salto de precio atribuible a un split no ajustado."""

    fecha: pd.Timestamp
    factor: float          # cuántas acciones nuevas por cada vieja (10 = diez a uno)
    precio_antes: float
    precio_despues: float

    def __str__(self) -> str:
        cuando = (
            self.fecha.date().isoformat()
            if isinstance(self.fecha, pd.Timestamp)
            else str(self.fecha)
        )
        if self.factor >= 1:
            return f"{cuando}: split {self.factor:g}×1"
        return f"{cuando}: split inverso 1×{1 / self.factor:g}"


def _factor_plausible(ratio: float) -> float | None:
    """
    Factor de split que explica el salto, o None si no hay uno simple.

    `ratio` es precio_despues / precio_antes: 0,1 en un split de diez a uno.
    """
    if not np.isfinite(ratio) or ratio <= 0:
        return None

    tolerancia = MERVAL_SPLIT_FACTOR_TOLERANCE_PCT / 100.0
    for factor in _FACTORES_PLAUSIBLES:
        # Split: el precio se divide por el factor.
        if abs(ratio * factor - 1.0) <= tolerancia:
            return float(factor)
        # Split inverso: el precio se multiplica.
        if abs(ratio / factor - 1.0) <= tolerancia:
            return 1.0 / float(factor)
    return None


def detect_unadjusted_splits(close: pd.Series) -> list[SplitEvent]:
    """Saltos de una barra que corresponden a un factor de split simple."""
    serie = pd.to_numeric(close, errors="coerce").dropna()
    serie = serie[serie > 0]
    if len(serie) < 3:
        return []

    variacion = serie.pct_change() * 100.0
    candidatas = variacion.index[variacion.abs() >= MERVAL_SPLIT_MIN_JUMP_PCT]

    eventos = []
    for fecha in candidatas:
        posicion = serie.index.get_loc(fecha)
        if posicion == 0:
            continue
        antes = float(serie.iloc[posicion - 1])
        despues = float(serie.iloc[posicion])
        factor = _factor_plausible(despues / antes)
        if factor is None:
            continue
        eventos.append(
            SplitEvent(fecha=fecha, factor=factor, precio_antes=antes, precio_despues=despues)
        )
    return eventos


def adjust_for_splits(ohlcv: pd.DataFrame) -> tuple[pd.DataFrame, list[SplitEvent]]:
    """
    Devuelve `(serie_corregida, eventos)` dejando la serie continua.

    Se corrige **hacia atrás**, como hace cualquier proveedor: en un split de
    diez a uno, los precios anteriores se dividen por diez, así que el último
    precio sigue siendo el que se ve hoy en pantalla y la serie queda expresada
    en acciones nuevas de punta a punta. El volumen anterior se multiplica por
    el mismo factor, porque esas mismas operaciones equivalen a diez veces más
    acciones nuevas.

    Sin eventos, devuelve la serie tal cual (una copia) y una lista vacía.
    """
    if ohlcv is None or ohlcv.empty or "Close" not in ohlcv.columns:
        return (ohlcv.copy() if isinstance(ohlcv, pd.DataFrame) else pd.DataFrame()), []

    df = ohlcv.sort_index().copy()
    eventos = detect_unadjusted_splits(df["Close"])
    if not eventos:
        return df, []

    # El volumen viene entero y el ajuste lo vuelve fraccionario: sin este
    # cambio de tipo, pandas rechaza la escritura con un LossySetitemError.
    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").astype(float)

    for evento in eventos:
        anteriores = df.index < evento.fecha
        if not anteriores.any():
            continue
        for columna in ("Open", "High", "Low", "Close", "Adj Close"):
            if columna in df.columns:
                df.loc[anteriores, columna] = (
                    pd.to_numeric(df.loc[anteriores, columna], errors="coerce") / evento.factor
                )
        if "Volume" in df.columns:
            df.loc[anteriores, "Volume"] = (
                pd.to_numeric(df.loc[anteriores, "Volume"], errors="coerce") * evento.factor
            )

    return df, eventos
