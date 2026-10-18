"""
merval/ccl.py - Dólar implícito del panel argentino y conversión a dólares.

Por qué existe: el precio de una acción argentina en pesos mezcla dos cosas, lo
que la empresa vale y lo que el peso dejó de valer. Un RSI calculado sobre
pesos nominales marca sobrecompra en cualquier salto devaluatorio, y una media
de 200 ruedas en pesos sube sola. El semáforo del tablero asume una serie de
precios donde una suba es una suba: para eso hay que medir en dólares.

De dónde sale el dólar. Trece empresas del panel cotizan también en Nueva York.
Para cada par, el tipo de cambio implícito es

    CCL = precio local en pesos × acciones locales por ADR ÷ precio del ADR

y, como es el mismo dólar para todas, lo que se usa es la **mediana** de los
pares, no el promedio ni el de un par en particular. Tres razones, en orden de
importancia:

  1. Un ratio mal cargado en `merval/catalog.py` da un CCL absurdo para ese
     par; con mediana queda como valor extremo y no mueve el resultado.
  2. Una acción que no operó en Buenos Aires o en Nueva York ese día arrastra
     un precio viejo.
  3. Cada par tiene su propio costo de arbitraje, así que ni con datos
     perfectos los trece coinciden al centavo.

Qué NO es: no es el CCL que publican los medios, que se calcula contra bonos
(GD30, AL30). El implícito por acciones cotiza unas décimas distinto y se mueve
igual. Para medir el precio de una acción en dólares, el implícito por acciones
es además el más consistente: es el mismo arbitraje que fija el precio local.

Es puro: sin red y sin Streamlit. La descarga vive en `merval/data_loader.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from constants import (
    MERVAL_CCL_MAX_STALE_BARS,
    MERVAL_CCL_PAIR_OUTLIER_PCT,
)
from merval.catalog import MervalStock

# Ratios que usan efectivamente los programas de ADR: al sugerir una corrección
# se redondea a uno de éstos en vez de a un número arbitrario, porque un ratio
# de 7,3 acciones por ADR no existe.
_RATIOS_PLAUSIBLES = (1, 2, 3, 4, 5, 8, 10, 15, 20, 25, 50, 100)


@dataclass(frozen=True)
class CclEstimate:
    """
    El dólar implícito del panel y qué tan de acuerdo están los pares.

    `dispersion_pct` es el rango entre el par más alto y el más bajo del último
    día, en porcentaje de la mediana. Es el número que dice si la tabla de
    ratios está bien: con ratios correctos los pares coinciden dentro de pocos
    puntos, y un ratio equivocado lo manda a varios cientos.
    """

    serie: pd.Series
    pares_usados: tuple[str, ...] = ()
    dispersion_pct: float = np.nan
    detalle: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def ultimo(self) -> float:
        serie = self.serie.dropna()
        return float(serie.iloc[-1]) if not serie.empty else np.nan

    @property
    def disponible(self) -> bool:
        return not self.serie.dropna().empty


def _cierres(historial: pd.DataFrame | None) -> pd.Series:
    if historial is None or historial.empty or "Close" not in historial.columns:
        return pd.Series(dtype=float)
    serie = pd.to_numeric(historial["Close"], errors="coerce").dropna()
    return serie[serie > 0]


def _ratio_sugerido(ratio_actual: int, ccl_par: float, ccl_mediana: float) -> int | None:
    """
    Ratio que volvería consistente a este par, redondeado a uno plausible.

    Sirve para arreglar la tabla: si el par da un CCL diez veces más alto que
    la mediana, el ratio cargado es diez veces más grande de lo que debería.
    """
    if not np.isfinite(ccl_par) or not np.isfinite(ccl_mediana) or ccl_par <= 0:
        return None

    exacto = ratio_actual * ccl_mediana / ccl_par
    candidato = min(_RATIOS_PLAUSIBLES, key=lambda r: abs(r - exacto))
    return candidato if candidato != ratio_actual else None


def implied_ccl_series(
    historiales_locales: dict[str, pd.DataFrame],
    historiales_adr: dict[str, pd.DataFrame],
    pares: tuple[MervalStock, ...],
) -> CclEstimate:
    """
    Serie diaria del dólar implícito, como mediana de los pares disponibles.

    Cada par aporta solo las fechas en que **las dos** puntas operaron: el
    precio local de un feriado norteamericano contra el ADR del día anterior
    daría un salto de tipo de cambio que no existió.
    """
    series_por_par: dict[str, pd.Series] = {}

    for activo in pares:
        local = _cierres(historiales_locales.get(activo.ticker))
        adr = _cierres(historiales_adr.get(activo.adr))
        if local.empty or adr.empty:
            continue

        # Solo las fechas donde las dos puntas tienen precio propio.
        comunes = local.index.intersection(adr.index)
        if len(comunes) == 0:
            continue

        series_por_par[activo.ticker] = (
            local.loc[comunes] * float(activo.adr_ratio) / adr.loc[comunes]
        )

    if not series_por_par:
        return CclEstimate(serie=pd.Series(dtype=float))

    matriz = pd.DataFrame(series_por_par).sort_index()
    serie = matriz.median(axis=1, skipna=True)

    ultimos = matriz.ffill(limit=MERVAL_CCL_MAX_STALE_BARS).iloc[-1]
    mediana_final = float(serie.dropna().iloc[-1]) if not serie.dropna().empty else np.nan

    filas = []
    por_ticker = {a.ticker: a for a in pares}
    for ticker, valor in ultimos.items():
        activo = por_ticker[ticker]
        desvio = (
            (valor / mediana_final - 1.0) * 100.0
            if np.isfinite(valor) and np.isfinite(mediana_final) and mediana_final
            else np.nan
        )
        filas.append({
            "Ticker": ticker,
            "ADR": activo.adr,
            "Ratio": activo.adr_ratio,
            "Verificado": activo.ratio_verificado,
            "CCL del par": float(valor) if np.isfinite(valor) else np.nan,
            "Desvío (%)": desvio,
            "Sospechoso": bool(np.isfinite(desvio) and abs(desvio) > MERVAL_CCL_PAIR_OUTLIER_PCT),
            "Ratio sugerido": _ratio_sugerido(activo.adr_ratio, float(valor), mediana_final),
        })

    detalle = pd.DataFrame(filas).sort_values("Desvío (%)", key=abs, ascending=False)

    validos = ultimos.dropna()
    dispersion = (
        float((validos.max() - validos.min()) / mediana_final * 100.0)
        if len(validos) > 1 and np.isfinite(mediana_final) and mediana_final
        else np.nan
    )

    return CclEstimate(
        serie=serie,
        pares_usados=tuple(series_por_par),
        dispersion_pct=dispersion,
        detalle=detalle.reset_index(drop=True),
    )


def to_usd(ohlcv: pd.DataFrame, ccl: pd.Series) -> pd.DataFrame:
    """
    Pasa un OHLCV en pesos a dólares, dividiendo por el CCL de cada fecha.

    El volumen **no** se convierte: está en cantidad de acciones, no en pesos,
    y es lo que necesita el OBV. Convertirlo cambiaría la lectura de flujo sin
    que nada lo avise.

    Las fechas sin CCL propio (el ADR no operó) se completan con el último
    disponible, hasta `MERVAL_CCL_MAX_STALE_BARS` barras: un feriado se puede
    puentear, una semana sin datos no, porque sería inventar un tipo de cambio.
    Las barras que quedan sin CCL se descartan, que es lo honesto: no hay forma
    de saber a cuánto cotizaba el dólar ese día.
    """
    if ohlcv is None or ohlcv.empty or ccl is None or ccl.dropna().empty:
        return pd.DataFrame()

    df = ohlcv.sort_index().copy()
    tipo_cambio = (
        ccl.sort_index()
        .reindex(df.index.union(ccl.index))
        .ffill(limit=MERVAL_CCL_MAX_STALE_BARS)
        .reindex(df.index)
    )

    utilizables = tipo_cambio.notna() & (tipo_cambio > 0)
    df = df.loc[utilizables]
    tipo_cambio = tipo_cambio.loc[utilizables]
    if df.empty:
        return pd.DataFrame()

    for columna in ("Open", "High", "Low", "Close", "Adj Close"):
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce") / tipo_cambio

    return df
