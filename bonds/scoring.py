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

from bonds.catalog import LAW_NEW_YORK
from constants import (
    BOND_LIQUID_SPREAD_MAX_PCT,
    BOND_MIN_YEARS_FOR_GRADING,
    BOND_PARITY_DISCOUNT_MAX,
    BOND_RISK_YIELD_PREMIUM_PP,
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
