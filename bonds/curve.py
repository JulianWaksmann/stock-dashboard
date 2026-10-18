"""
bonds/curve.py - Curva de rendimientos del panel y valor relativo contra ella.

Qué agrega sobre el cuadro: una tabla puede ordenar por TIR, pero la TIR sola
no es comparable entre bonos de plazo distinto. Un bono que rinde 11% a cinco
años y otro que rinde 11% a un año no están igual de caros: el segundo paga lo
mismo por mucho menos riesgo de tasa. Lo que se compara es **cada bono contra
sus pares de plazo parecido**, y eso es una curva.

El criterio es el mismo que usa `bonds/scoring.py` y por la misma razón: es
**relativo al panel de ese día**, no contra una curva teórica ni contra
umbrales fijos. La curva argentina se mueve entera con el riesgo país, así que
"TIR mayor a 9%" diría cosas opuestas en dos momentos del ciclo; "más TIR que
sus pares de igual duración", en cambio, significa lo mismo siempre.

Forma funcional: `TIR ≈ a + b · ln(1 + duration)`. Es una recta en escala
logarítmica de plazo, que es como se ve una curva de crédito normal: la prima
por alargar el plazo crece rápido en el tramo corto y se achata en el largo.
Con la decena de especies que suele tener TIR calculable, cualquier cosa con
más parámetros ajustaría ruido.

Dos decisiones que conviene conocer antes de tocar los números:

  * **El ajuste excluye lo que lo distorsionaría, el residuo se calcula para
    todos.** Un emisor en default cotiza a precio de recupero y su TIR
    contractual sale en decenas o cientos por ciento: una sola fila así
    inclina la recta y vuelve "caros" a todos los demás. Esas filas quedan
    afuera del ajuste, pero igual reciben su residuo, que es justamente el
    número que muestra lo lejos que están del resto.
  * **Una curva por moneda.** Un flujo en dólares y uno en pesos no pertenecen
    a la misma curva: no son dos precios del mismo riesgo, son dos monedas
    distintas. El panel ya calcula TIR solo cuando la especie liquida en la
    moneda de emisión (ver CLAUDE.md); acá se agrupa por esa moneda y cada
    grupo ajusta la suya.

Es puro: sin red y sin Streamlit. Lo dibuja `components/bonds_chart.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from constants import (
    BOND_CURVE_CHEAP,
    BOND_CURVE_FAIR,
    BOND_CURVE_FIT_MAX_YTM_MULTIPLE,
    BOND_CURVE_MIN_BONDS,
    BOND_CURVE_MIN_DURATION_SPREAD,
    BOND_CURVE_MIN_RESIDUAL_PP,
    BOND_CURVE_RESIDUAL_SIGMAS,
    BOND_CURVE_RICH,
)

COL_DURATION = "Duration Mod."
COL_YTM = "TIR (%)"
COL_CURRENCY = "Moneda"
COL_IN_DEFAULT = "En Default"

COL_THEORETICAL_YTM = "TIR Teórica (%)"
COL_RESIDUAL = "Residuo TIR (pp)"
COL_RELATIVE_VALUE = "Valor Relativo"


@dataclass(frozen=True)
class CurveFit:
    """
    Una curva ajustada sobre un grupo de bonos de la misma moneda.

    `intercepto` es la TIR teórica a duration 0 (el tramo más corto imaginable)
    y `pendiente` cuánto sube la TIR, en puntos porcentuales, por cada unidad
    de `ln(1 + duration)`. El `r2` no se usa para decidir nada: se muestra,
    para que quien lea el gráfico sepa si la nube tiene forma de curva o si la
    recta es un dibujo sobre puntos dispersos.
    """

    moneda: str
    n: int
    intercepto: float
    pendiente: float
    r2: float
    residual_sigma_pp: float

    def tir_teorica(self, duracion) -> np.ndarray:
        """TIR que le correspondería a esa duration según la curva del panel."""
        d = np.asarray(duracion, dtype=float)
        with np.errstate(invalid="ignore"):
            return self.intercepto + self.pendiente * np.log1p(d)


def _ajustable(df: pd.DataFrame) -> pd.DataFrame:
    """Filas que pueden entrar al ajuste (ver el docstring del módulo)."""
    if df.empty or COL_DURATION not in df.columns or COL_YTM not in df.columns:
        return df.iloc[0:0]

    duracion = pd.to_numeric(df[COL_DURATION], errors="coerce")
    tir = pd.to_numeric(df[COL_YTM], errors="coerce")

    mask = duracion.notna() & tir.notna() & (duracion > 0)
    if COL_IN_DEFAULT in df.columns:
        mask &= ~df[COL_IN_DEFAULT].fillna(False).astype(bool)

    # El tope se mide contra la mediana del propio grupo, ya sin los emisores
    # en default: en pesos la curva entera vive arriba del 50% y un tope fijo
    # la dejaría afuera completa.
    mediana = tir[mask].median()
    if np.isfinite(mediana) and mediana > 0:
        mask &= tir.abs() <= BOND_CURVE_FIT_MAX_YTM_MULTIPLE * mediana

    return df.loc[mask]


def fit_currency_curve(df: pd.DataFrame, moneda: str = "") -> CurveFit | None:
    """
    Ajusta una curva sobre un grupo ya filtrado por moneda.

    Devuelve `None` —y no una curva mala— cuando el grupo no alcanza para
    sostener una: pocos bonos, o todos con plazos casi iguales. En el segundo
    caso la recta quedaría definida por una nube vertical y su pendiente sería
    cualquier número con tal de pasar por el medio.
    """
    base = _ajustable(df)
    if len(base) < BOND_CURVE_MIN_BONDS:
        return None

    duraciones = pd.to_numeric(base[COL_DURATION], errors="coerce").to_numpy(dtype=float)
    tires = pd.to_numeric(base[COL_YTM], errors="coerce").to_numpy(dtype=float)

    if duraciones.max() - duraciones.min() < BOND_CURVE_MIN_DURATION_SPREAD:
        return None

    x = np.log1p(duraciones)
    pendiente, intercepto = np.polyfit(x, tires, deg=1)

    ajustado = intercepto + pendiente * x
    residuos = tires - ajustado
    varianza_total = float(np.var(tires))
    r2 = 1.0 - float(np.var(residuos)) / varianza_total if varianza_total > 0 else 0.0

    return CurveFit(
        moneda=moneda,
        n=len(base),
        intercepto=float(intercepto),
        pendiente=float(pendiente),
        r2=r2,
        # Desvío de los residuos del propio ajuste: es la unidad con la que se
        # mide si un bono está realmente fuera de la curva o apenas disperso.
        residual_sigma_pp=float(np.std(residuos)),
    )


def fit_yield_curves(df: pd.DataFrame) -> dict[str, CurveFit]:
    """Una curva por moneda, para los grupos que alcanzan a sostener una."""
    if df.empty or COL_CURRENCY not in df.columns:
        return {}

    curvas: dict[str, CurveFit] = {}
    for moneda, grupo in df.groupby(COL_CURRENCY, dropna=True):
        ajuste = fit_currency_curve(grupo, moneda=str(moneda))
        if ajuste is not None:
            curvas[str(moneda)] = ajuste
    return curvas


def add_curve_residuals(df: pd.DataFrame, curvas: dict[str, CurveFit]) -> pd.DataFrame:
    """
    Agrega TIR teórica, residuo y etiqueta de valor relativo.

    El residuo se mide en puntos porcentuales y se etiqueta contra el desvío
    de los residuos de **su propia curva**, no contra un umbral fijo: en un
    panel apretado medio punto de diferencia ya es mucho, y en uno disperso no
    es nada. El corte es el mayor entre ese desvío y `BOND_CURVE_MIN_RESIDUAL_PP`,
    así que un panel que ajusta casi perfecto no reparte etiquetas por
    diferencias de centésimas, y un bono realmente lejos de la curva igual
    queda marcado.

    Devuelve una copia: no toca el DataFrame que recibe.
    """
    out = df.copy()
    out[COL_THEORETICAL_YTM] = np.nan
    out[COL_RESIDUAL] = np.nan
    out[COL_RELATIVE_VALUE] = BOND_CURVE_FAIR

    if out.empty or not curvas or COL_CURRENCY not in out.columns:
        return out

    for moneda, ajuste in curvas.items():
        filas = out[COL_CURRENCY].astype(str) == moneda
        if not filas.any():
            continue

        duracion = pd.to_numeric(out.loc[filas, COL_DURATION], errors="coerce")
        tir = pd.to_numeric(out.loc[filas, COL_YTM], errors="coerce")

        teorica = pd.Series(ajuste.tir_teorica(duracion.to_numpy()), index=duracion.index)
        teorica = teorica.where(duracion.notna())
        residuo = tir - teorica

        out.loc[filas, COL_THEORETICAL_YTM] = teorica
        out.loc[filas, COL_RESIDUAL] = residuo

        # El mayor entre un desvío de residuo y el piso absoluto: el desvío
        # calibra contra la dispersión real del panel, el piso evita etiquetar
        # medio punto básico en un panel que ajusta casi perfecto.
        corte = max(
            BOND_CURVE_RESIDUAL_SIGMAS * ajuste.residual_sigma_pp,
            BOND_CURVE_MIN_RESIDUAL_PP,
        )
        etiquetas = pd.Series(BOND_CURVE_FAIR, index=residuo.index)
        etiquetas[residuo >= corte] = BOND_CURVE_CHEAP
        etiquetas[residuo <= -corte] = BOND_CURVE_RICH
        etiquetas[residuo.isna()] = BOND_CURVE_FAIR
        out.loc[filas, COL_RELATIVE_VALUE] = etiquetas

    return out


def curve_points(ajuste: CurveFit, duraciones, puntos: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """
    Puntos (duration, TIR teórica) para dibujar la curva, sin extrapolar.

    Se queda dentro del rango de duraciones observadas a propósito: la curva es
    una descripción del panel de hoy, no un modelo del que se pueda pedir la
    TIR de un plazo que nadie opera.
    """
    d = pd.to_numeric(pd.Series(duraciones), errors="coerce").dropna()
    d = d[d > 0]
    if d.empty:
        return np.array([]), np.array([])

    xs = np.linspace(float(d.min()), float(d.max()), puntos)
    return xs, ajuste.tir_teorica(xs)
