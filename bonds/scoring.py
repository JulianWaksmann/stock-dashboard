"""
bonds/scoring.py - Sistema de grados de atractivo para ONs.

Es el equivalente, del lado de la renta fija, al Algoritmo de Confluencia de
`indicators.py`: traduce un puñado de métricas a una sola etiqueta legible, con
la misma mecánica de "condición obligatoria + puntos opcionales" para que el
criterio quede explícito y auditable en vez de escondido en una fórmula.

La diferencia conceptual con las acciones: un bono **no se compara contra su
propio pasado** sino contra sus pares del mismo día. Una TIR del 11% es
excelente o mediocre según dónde esté cotizando el resto del panel corporativo
argentino, así que la referencia de los umbrales de rendimiento es la mediana
de TIR del panel, no un número absoluto.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from bonds.catalog import LAW_ARGENTINA, LAW_NEW_YORK
from constants import (
    BOND_LIQUID_SPREAD_MAX_PCT,
    BOND_MIN_YEARS_FOR_GRADING,
    BOND_PARITY_DISCOUNT_MAX,
    BOND_RISK_YIELD_PREMIUM_PP,
    BOND_SCORE_ATTRACTIVE_MIN,
    BOND_SCORE_EXCESS_PENALTY_SLOPE,
    BOND_SCORE_JURISDICTION,
    BOND_SCORE_LAW_ARG,
    BOND_SCORE_LAW_NY,
    BOND_SCORE_LIQUIDITY,
    BOND_SCORE_MIN_COVERAGE,
    BOND_SCORE_MIN_DIMENSION_COVERAGE,
    BOND_SCORE_MIN_PANEL_SIZE,
    BOND_SCORE_NEUTRAL_MIN,
    BOND_SCORE_PARITY,
    BOND_SCORE_RATE_RISK,
    BOND_SCORE_RATING,
    BOND_SCORE_SPREAD_SHARE,
    BOND_SCORE_VERY_ATTRACTIVE_MIN,
    BOND_SCORE_WEIGHTS,
    BOND_SCORE_YIELD,
    BOND_SHORT_DURATION_MAX_YEARS,
    BOND_SIGNAL_ATTRACTIVE,
    BOND_SIGNAL_LOW,
    BOND_SIGNAL_NEUTRAL,
    BOND_SIGNAL_NO_DATA,
    BOND_SIGNAL_RISK,
    BOND_SIGNAL_VERY_ATTRACTIVE,
    BOND_SIGNAL_VERY_SHORT,
    BOND_YIELD_PREMIUM_PP,
)


def _is_number(value) -> bool:
    """True si el valor es un número real utilizable (ni None ni NaN)."""
    if value is None:
        return False
    try:
        return not math.isnan(float(value))
    except (TypeError, ValueError):
        return False


def evaluate_bond_attractiveness(
    *,
    ytm_pct: float | None,
    median_ytm_pct: float | None,
    modified_duration: float | None,
    parity_pct: float | None,
    bid_ask_spread_pct: float | None,
    law: str | None,
    years_to_maturity: float | None = None,
) -> str:
    """
    Sistema de Grados de una ON.

    PLAZO MÍNIMO (excluyente): una ON a la que le quedan semanas de vida no se
    califica. Su TIR es correcta pero no comparable: anualizar el retorno de
    tres semanas convierte un centavo de diferencia de precio en decenas de
    puntos de rendimiento, y esa ON aparecería encabezando el panel o gatillando
    una alerta de riesgo por puro artefacto aritmético.

    OBLIGATORIO: tener una TIR calculable. Sin flujo de fondos conocido (ON
    fuera del catálogo) o sin precio válido no hay nada que evaluar, y devolver
    "neutral" ahí sería afirmar algo que no se midió.

    ALERTA DE RIESGO (excluyente): TIR por encima de la mediana del panel más
    BOND_RISK_YIELD_PREMIUM_PP. Una prima tan grande sobre los pares no es un
    bono barato: es el mercado poniéndole precio a una probabilidad de default
    o de reestructuración. Se etiqueta aparte, nunca como oportunidad.

    PUNTOS (1 cada uno):
      1. Premio de rendimiento: TIR >= mediana del panel + BOND_YIELD_PREMIUM_PP.
      2. Riesgo de tasa acotado: duration modificada <= BOND_SHORT_DURATION_MAX_YEARS.
      3. Cotiza bajo la par: paridad < BOND_PARITY_DISCOUNT_MAX (parte del
         retorno llega como ganancia de capital, no solo por cupón).
      4. Liquidez: spread punta/punta <= BOND_LIQUID_SPREAD_MAX_PCT.
      5. Jurisdicción: ley Nueva York (un default se litiga fuera del país).

      --> 4-5 puntos: 🌟 MUY ATRACTIVO
      --> 3 puntos:   🟢 ATRACTIVO
      --> 2 puntos:   🟡 NEUTRAL
      --> 0-1 puntos: 🟠 POCO ATRACTIVO
    """
    if not _is_number(ytm_pct):
        return BOND_SIGNAL_NO_DATA

    ytm = float(ytm_pct)

    if _is_number(years_to_maturity) and float(years_to_maturity) < BOND_MIN_YEARS_FOR_GRADING:
        return BOND_SIGNAL_VERY_SHORT

    if _is_number(median_ytm_pct) and ytm >= float(median_ytm_pct) + BOND_RISK_YIELD_PREMIUM_PP:
        return BOND_SIGNAL_RISK

    # Punto 1: premio de rendimiento contra la mediana del panel. Sin mediana
    # (panel de un solo bono) no hay comparación posible y el punto no se suma.
    point_yield_premium = (
        _is_number(median_ytm_pct) and ytm >= float(median_ytm_pct) + BOND_YIELD_PREMIUM_PP
    )

    # Punto 2: riesgo de tasa acotado.
    point_short_duration = (
        _is_number(modified_duration) and float(modified_duration) <= BOND_SHORT_DURATION_MAX_YEARS
    )

    # Punto 3: cotiza bajo la par.
    point_below_par = _is_number(parity_pct) and float(parity_pct) < BOND_PARITY_DISCOUNT_MAX

    # Punto 4: liquidez medida por el spread punta compradora / punta vendedora.
    point_liquid = (
        _is_number(bid_ask_spread_pct) and float(bid_ask_spread_pct) <= BOND_LIQUID_SPREAD_MAX_PCT
    )

    # Punto 5: jurisdicción extranjera.
    point_foreign_law = (law or "").strip().upper() == LAW_NEW_YORK

    score = sum(
        [
            point_yield_premium,
            point_short_duration,
            point_below_par,
            point_liquid,
            point_foreign_law,
        ]
    )

    if score >= 4:
        return BOND_SIGNAL_VERY_ATTRACTIVE
    if score == 3:
        return BOND_SIGNAL_ATTRACTIVE
    if score == 2:
        return BOND_SIGNAL_NEUTRAL
    return BOND_SIGNAL_LOW


def _percentile(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """
    Convierte una métrica en un puntaje 0-100 por su posición en el panel.

    Se usa el percentil y no una escala absoluta porque no existe un "bueno"
    fijo en este mercado: una duration de 3 años es corta o larga según lo que
    haya en oferta ese día, igual que una TIR del 11%. El percentil responde
    la pregunta que importa —cómo se compara con las alternativas reales de
    hoy— y se recalibra solo cuando el mercado se mueve.
    """
    # `ascending` en el propio rank, y no `100 - percentil`: esa resta NO es
    # el espejo del percentil. El rank porcentual de pandas vive en (0, 1], así
    # que su complemento vive en [0, 1) y las dos escalas no coinciden. Con
    # todos los valores empatados daba 60 para "más es mejor" y 40 para "menos
    # es mejor" sobre el mismo dato, un sesgo estructural a favor de las
    # dimensiones que premian el valor alto.
    return series.rank(pct=True, ascending=higher_is_better, na_option="keep") * 100.0


def _yield_subscore(ytm: pd.Series, median_ytm: float) -> pd.Series:
    """
    Puntaje de rendimiento, con castigo por prima excesiva.

    Más TIR es mejor solo hasta cierto punto. Pasada la prima que separa una
    oportunidad de un problema de crédito, el mercado no está regalando
    rendimiento: está poniéndole precio a una probabilidad de default. A partir
    de ahí cada punto porcentual de más se cuenta como BOND_SCORE_EXCESS_PENALTY_SLOPE
    puntos de menos al rankear, así que el bono cae en el orden del panel en
    lugar de subir. Dónde termina depende del resto del panel —es un
    percentil—, no de un piso fijo.
    """
    if not _is_number(median_ytm):
        return _percentile(ytm, higher_is_better=True)

    # El castigo se aplica sobre la TIR ANTES de rankear, no sobre el percentil
    # después. Multiplicar el percentil por un factor decreciente no alcanza:
    # el percentil sube con la TIR al mismo tiempo que el factor baja, los dos
    # efectos se cancelan y entre dos bonos ya castigados puede puntuar más
    # alto el que rinde más, que es exactamente lo que esta regla evita.
    cap = float(median_ytm) + BOND_RISK_YIELD_PREMIUM_PP
    excess = (ytm - cap).clip(lower=0.0)
    effective = ytm - excess * (1.0 + BOND_SCORE_EXCESS_PENALTY_SLOPE)
    return _percentile(effective, higher_is_better=True)


def _liquidity_subscore(spread_pct: pd.Series, volume: pd.Series) -> pd.Series:
    """
    Puntaje de liquidez: spread de puntas y volumen operado.

    Son dos caras de lo mismo y ninguna alcanza sola. El spread es el costo
    cierto de entrar y salir; el volumen dice si ese spread se sostiene en
    tamaño o es una punta simbólica por diez nominales. Si falta uno, se usa
    el otro en vez de descartar la dimensión entera.
    """
    tightness = _percentile(spread_pct, higher_is_better=False)

    # Volumen cero no es un dato faltante: es la peor liquidez posible, y hay
    # que decirlo explícitamente. Por percentil, una masa de ceros empatados
    # se reparte el rango medio, y una especie que no operó terminaba sacando
    # el mismo puntaje de liquidez que otra con las puntas pegadas y medio
    # millón operado.
    depth = _percentile(volume.where(volume > 0), higher_is_better=True)
    depth = depth.mask(volume.notna() & (volume <= 0), 0.0)

    combined = (
        tightness * BOND_SCORE_SPREAD_SHARE + depth * (1.0 - BOND_SCORE_SPREAD_SHARE)
    )
    return combined.fillna(tightness).fillna(depth)


def _rating_subscore(ranks: pd.Series | None, scales: pd.Series | None) -> pd.Series:
    """
    Puntaje de calidad crediticia, por percentil DENTRO de cada escala.

    Una nota en escala nacional y una en escala global no significan lo mismo:
    la nacional mide contra el resto del país y la global contra el mundo, así
    que un "AAA" local convive con un "B" global sobre el mismo emisor.
    Rankearlas juntas pondría a todos los calificados localmente por encima de
    todos los calificados afuera, que es un artefacto de notación y no una
    diferencia de crédito.

    Un emisor sin calificación no puntúa cero: se abstiene, igual que en
    jurisdicción. Cero sería afirmar que es mal crédito, y lo único que se
    sabe es que no tenemos el dato.
    """
    if ranks is None or ranks.empty:
        return pd.Series(dtype=float)
    numeric = pd.to_numeric(ranks, errors="coerce")
    if scales is None:
        return _percentile(numeric, higher_is_better=True)
    grupos = scales.fillna("—").astype(str)
    return numeric.groupby(grupos).rank(pct=True, ascending=True, na_option="keep") * 100.0


def _jurisdiction_subscore(law: pd.Series) -> pd.Series:
    """Puntaje de jurisdicción. Una ley desconocida no puntúa: se abstiene."""
    # Se compara por prefijo para aceptar la ley inferida del ISIN, que llega
    # marcada como "NY (ISIN)": es la misma jurisdicción, con su origen a la
    # vista.
    normalized = law.fillna("").astype(str).str.strip().str.upper()
    scores = pd.Series(np.nan, index=law.index, dtype=float)
    scores[normalized.str.startswith(LAW_NEW_YORK)] = BOND_SCORE_LAW_NY
    scores[normalized.str.startswith(LAW_ARGENTINA)] = BOND_SCORE_LAW_ARG
    return scores


def compute_opportunity_scores(
    df: pd.DataFrame,
    median_ytm: float | None = None,
    comparable: pd.Series | None = None,
) -> pd.DataFrame:
    """
    Puntaje de Oportunidad de cada ON, de 0 a 100, con su desagregado.

    Devuelve una columna por dimensión, el puntaje total y la cobertura: qué
    fracción del peso total se pudo evaluar de verdad.

    La regla que hace honesto al número: **una dimensión que no se puede medir
    no puntúa cero, se excluye y los pesos se renormalizan sobre lo que sí se
    midió**. Puntuar cero castigaría al bono por un dato que falta en nuestra
    fuente y no por nada que le pase al bono. Y si queda demasiado poco por
    medir, no se publica puntaje: un número que sale casi solo de la TIR diría
    más sobre lo que no sabemos que sobre la oportunidad.
    """
    if df.empty:
        return pd.DataFrame(index=df.index)

    if median_ytm is None:
        median_ytm = df.attrs.get("median_ytm_pct", np.nan)

    # Los percentiles se calculan SOLO sobre el panel comparable, el mismo
    # subconjunto que define la mediana de TIR. Si las especies que no operaron
    # entraran al ranking, la referencia del puntaje y la del castigo por prima
    # serían dos poblaciones distintas, y un bono podría estar en el percentil
    # 80 contra un universo y en el 50 contra el otro.
    if comparable is None:
        comparable = pd.Series(True, index=df.index)
    comparable = comparable.reindex(df.index).fillna(False).astype(bool)

    ranked = df.where(comparable)

    subscores = pd.DataFrame(
        {
            BOND_SCORE_YIELD: _yield_subscore(ranked["TIR (%)"], median_ytm),
            BOND_SCORE_LIQUIDITY: _liquidity_subscore(ranked["Spread (%)"], ranked["Volumen"]),
            BOND_SCORE_RATE_RISK: _percentile(ranked["Duration Mod."], higher_is_better=False),
            BOND_SCORE_PARITY: _percentile(ranked["Paridad (%)"], higher_is_better=False),
            BOND_SCORE_JURISDICTION: _jurisdiction_subscore(ranked["Ley"]),
            BOND_SCORE_RATING: _rating_subscore(
                ranked.get("CALIF_RANK"), ranked.get("CALIF_ESCALA")
            ),
        },
        index=df.index,
    )

    # Una dimensión que casi nadie tiene se descarta para todos. Usarla
    # compararía a unos pocos entre sí y dejaría a la mayoría sin pagar por no
    # tenerla, de modo que cargar un dato cierto pero mediocre bajaría el
    # puntaje: exactamente el incentivo opuesto al que queremos.
    panel_size = int(comparable.sum())
    dimension_coverage = subscores.notna().sum() / max(panel_size, 1)
    unusable = dimension_coverage[dimension_coverage < BOND_SCORE_MIN_DIMENSION_COVERAGE].index
    subscores[unusable] = np.nan

    weights = pd.Series(BOND_SCORE_WEIGHTS)
    measured = subscores.notna()
    available_weight = measured.mul(weights, axis=1).sum(axis=1)
    weighted_total = subscores.fillna(0.0).mul(weights, axis=1).sum(axis=1)

    total_weight = float(weights.sum())
    coverage = available_weight / total_weight
    score = (weighted_total / available_weight.replace(0.0, np.nan)).where(
        coverage >= BOND_SCORE_MIN_COVERAGE
    )

    # Un percentil contra un puñado de bonos no mide nada: con un panel de uno,
    # "percentil 100" es ganarse a sí mismo.
    if panel_size < BOND_SCORE_MIN_PANEL_SIZE:
        score = pd.Series(np.nan, index=df.index, dtype=float)

    result = subscores.copy()
    result["Puntaje"] = score
    result["Cobertura"] = coverage * 100.0
    return result


def label_from_score(score: float | None) -> str:
    """
    Traduce el puntaje a la etiqueta del semáforo.

    Los cortes son deliberadamente exigentes del lado alto: como el puntaje es
    relativo al panel, un bono promedio da alrededor de 50, y llamar
    "atractivo" a lo promedio vaciaría la palabra.
    """
    if not _is_number(score):
        return BOND_SIGNAL_NO_DATA
    value = float(score)
    if value >= BOND_SCORE_VERY_ATTRACTIVE_MIN:
        return BOND_SIGNAL_VERY_ATTRACTIVE
    if value >= BOND_SCORE_ATTRACTIVE_MIN:
        return BOND_SIGNAL_ATTRACTIVE
    if value >= BOND_SCORE_NEUTRAL_MIN:
        return BOND_SIGNAL_NEUTRAL
    return BOND_SIGNAL_LOW
