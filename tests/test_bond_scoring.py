"""
Tests del sistema de grados de atractivo de ONs (`bonds/scoring.py`).

El scoring es una regla de negocio, no una fórmula matemática: lo que se
verifica acá es que cada condición del algoritmo documentado sume (o no sume)
el punto que le corresponde, y que los casos límite caigan del lado correcto
del umbral.
"""

import pytest

from bonds.scoring import evaluate_bond_attractiveness
from constants import (
    BOND_MIN_YEARS_FOR_GRADING,
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

MEDIAN = 10.0


def evaluate(**overrides):
    """Bono base que no suma ningún punto; cada test enciende los que necesita."""
    params = dict(
        ytm_pct=MEDIAN,
        median_ytm_pct=MEDIAN,
        modified_duration=BOND_SHORT_DURATION_MAX_YEARS + 5.0,
        parity_pct=110.0,
        bid_ask_spread_pct=5.0,
        law="ARG",
        years_to_maturity=5.0,
    )
    params.update(overrides)
    return evaluate_bond_attractiveness(**params)


class TestCondicionObligatoria:
    def test_sin_tir_no_se_evalua(self):
        assert evaluate(ytm_pct=None) == BOND_SIGNAL_NO_DATA

    def test_tir_nan_no_se_evalua(self):
        assert evaluate(ytm_pct=float("nan")) == BOND_SIGNAL_NO_DATA

    def test_tir_no_numerica_no_se_evalua(self):
        assert evaluate(ytm_pct="s/d") == BOND_SIGNAL_NO_DATA


class TestAlertaDeRiesgo:
    def test_una_prima_enorme_sobre_los_pares_es_alerta_no_oportunidad(self):
        assert evaluate(ytm_pct=MEDIAN + BOND_RISK_YIELD_PREMIUM_PP) == BOND_SIGNAL_RISK

    def test_la_alerta_es_excluyente_aunque_sume_todos_los_puntos(self):
        signal = evaluate(
            ytm_pct=MEDIAN + BOND_RISK_YIELD_PREMIUM_PP + 5.0,
            modified_duration=1.0,
            parity_pct=60.0,
            bid_ask_spread_pct=0.2,
            law="NY",
        )
        assert signal == BOND_SIGNAL_RISK

    def test_justo_por_debajo_del_umbral_no_dispara_la_alerta(self):
        assert evaluate(ytm_pct=MEDIAN + BOND_RISK_YIELD_PREMIUM_PP - 0.01) != BOND_SIGNAL_RISK

    def test_sin_mediana_del_panel_no_hay_alerta(self):
        # Sin referencia de pares no se puede afirmar que la prima sea anómala.
        assert evaluate(ytm_pct=100.0, median_ytm_pct=None) != BOND_SIGNAL_RISK


class TestPuntaje:
    def test_sin_ningun_punto_es_poco_atractivo(self):
        assert evaluate() == BOND_SIGNAL_LOW

    def test_un_solo_punto_sigue_siendo_poco_atractivo(self):
        assert evaluate(law="NY") == BOND_SIGNAL_LOW

    def test_dos_puntos_es_neutral(self):
        assert evaluate(law="NY", parity_pct=95.0) == BOND_SIGNAL_NEUTRAL

    def test_tres_puntos_es_atractivo(self):
        assert evaluate(law="NY", parity_pct=95.0, bid_ask_spread_pct=0.5) == BOND_SIGNAL_ATTRACTIVE

    def test_cuatro_puntos_es_muy_atractivo(self):
        signal = evaluate(law="NY", parity_pct=95.0, bid_ask_spread_pct=0.5, modified_duration=2.0)
        assert signal == BOND_SIGNAL_VERY_ATTRACTIVE

    def test_los_cinco_puntos_es_muy_atractivo(self):
        signal = evaluate(
            ytm_pct=MEDIAN + BOND_YIELD_PREMIUM_PP,
            law="NY",
            parity_pct=95.0,
            bid_ask_spread_pct=0.5,
            modified_duration=2.0,
        )
        assert signal == BOND_SIGNAL_VERY_ATTRACTIVE


class TestCondicionesIndividuales:
    def test_premio_de_rendimiento_justo_en_el_umbral_suma(self):
        # Tres puntos ya garantizados + el premio => sube de ATRACTIVO a MUY.
        base = dict(law="NY", parity_pct=95.0, bid_ask_spread_pct=0.5)
        assert evaluate(**base) == BOND_SIGNAL_ATTRACTIVE
        assert evaluate(ytm_pct=MEDIAN + BOND_YIELD_PREMIUM_PP, **base) == BOND_SIGNAL_VERY_ATTRACTIVE

    def test_premio_de_rendimiento_por_debajo_del_umbral_no_suma(self):
        base = dict(law="NY", parity_pct=95.0, bid_ask_spread_pct=0.5)
        assert evaluate(ytm_pct=MEDIAN + BOND_YIELD_PREMIUM_PP - 0.01, **base) == BOND_SIGNAL_ATTRACTIVE

    def test_sin_mediana_el_premio_de_rendimiento_no_suma(self):
        base = dict(law="NY", parity_pct=95.0, bid_ask_spread_pct=0.5)
        assert evaluate(ytm_pct=50.0, median_ytm_pct=None, **base) == BOND_SIGNAL_ATTRACTIVE

    def test_duration_justo_en_el_umbral_suma(self):
        base = dict(law="NY", parity_pct=95.0)
        assert evaluate(modified_duration=BOND_SHORT_DURATION_MAX_YEARS, **base) == BOND_SIGNAL_ATTRACTIVE
        assert evaluate(modified_duration=BOND_SHORT_DURATION_MAX_YEARS + 0.01, **base) == BOND_SIGNAL_NEUTRAL

    def test_paridad_en_cien_no_cuenta_como_bajo_la_par(self):
        assert evaluate(law="NY", parity_pct=100.0) == BOND_SIGNAL_LOW
        assert evaluate(law="NY", parity_pct=99.99) == BOND_SIGNAL_NEUTRAL

    def test_la_ley_se_compara_sin_distinguir_mayusculas_ni_espacios(self):
        assert evaluate(law=" ny ") == evaluate(law="NY")

    def test_ley_ausente_no_suma(self):
        assert evaluate(law=None) == BOND_SIGNAL_LOW

    @pytest.mark.parametrize("valor", [None, float("nan")])
    def test_las_metricas_faltantes_simplemente_no_suman(self, valor):
        signal = evaluate(law="NY", parity_pct=95.0, modified_duration=valor, bid_ask_spread_pct=valor)
        assert signal == BOND_SIGNAL_NEUTRAL


class TestPlazoMinimo:
    """
    Anualizar el retorno de un bono al que le quedan semanas convierte un
    centavo de precio en decenas de puntos de TIR. Esas ONs se apartan en vez
    de encabezar el panel o disparar una falsa alerta de riesgo.
    """

    def test_una_on_a_semanas_del_vencimiento_no_se_califica(self):
        assert evaluate(years_to_maturity=0.05) == BOND_SIGNAL_VERY_SHORT

    def test_el_plazo_minimo_le_gana_a_la_alerta_de_riesgo(self):
        signal = evaluate(ytm_pct=MEDIAN + BOND_RISK_YIELD_PREMIUM_PP + 200.0, years_to_maturity=0.05)
        assert signal == BOND_SIGNAL_VERY_SHORT

    def test_el_plazo_minimo_le_gana_a_un_puntaje_perfecto(self):
        signal = evaluate(
            ytm_pct=MEDIAN + BOND_YIELD_PREMIUM_PP,
            modified_duration=0.1,
            parity_pct=95.0,
            bid_ask_spread_pct=0.2,
            law="NY",
            years_to_maturity=0.05,
        )
        assert signal == BOND_SIGNAL_VERY_SHORT

    def test_justo_en_el_umbral_si_se_califica(self):
        assert evaluate(years_to_maturity=BOND_MIN_YEARS_FOR_GRADING) != BOND_SIGNAL_VERY_SHORT

    def test_sin_plazo_conocido_se_califica_igual(self):
        # El plazo es un dato opcional: su ausencia no puede dejar sin
        # calificar a una ON que sí tiene TIR.
        assert evaluate(years_to_maturity=None) == BOND_SIGNAL_LOW
