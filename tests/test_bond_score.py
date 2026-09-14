"""
Tests del Puntaje de Oportunidad (`bonds.scoring.compute_opportunity_scores`).

El puntaje es un criterio de inversión hecho número, así que lo que se
verifica no es que "dé bien" sino que cada regla declarada se cumpla: que el
rendimiento pese más que la jurisdicción, que una prima excesiva reste en vez
de sumar, y sobre todo que un dato faltante no se cobre como un cero.
"""

import numpy as np
import pandas as pd
import pytest

from bonds.scoring import compute_opportunity_scores, label_from_score
from constants import (
    BOND_RISK_YIELD_PREMIUM_PP,
    BOND_SCORE_ATTRACTIVE_MIN,
    BOND_SCORE_JURISDICTION,
    BOND_SCORE_LIQUIDITY,
    BOND_SCORE_NEUTRAL_MIN,
    BOND_SCORE_VERY_ATTRACTIVE_MIN,
    BOND_SCORE_WEIGHTS,
    BOND_SCORE_YIELD,
    BOND_SIGNAL_ATTRACTIVE,
    BOND_SIGNAL_LOW,
    BOND_SIGNAL_NEUTRAL,
    BOND_SIGNAL_NO_DATA,
    BOND_SIGNAL_VERY_ATTRACTIVE,
)

MEDIANA = 9.0


def panel(*filas) -> pd.DataFrame:
    return pd.DataFrame(list(filas))


def bono(ticker: str, **overrides) -> dict:
    base = {
        "Ticker": ticker,
        "TIR (%)": MEDIANA,
        "Spread (%)": 1.0,
        "Volumen": 100_000.0,
        "Duration Mod.": 3.0,
        "Paridad (%)": 100.0,
        "Ley": "NY",
    }
    base.update(overrides)
    return base


def puntajes(df: pd.DataFrame, mediana: float = MEDIANA) -> pd.DataFrame:
    return compute_opportunity_scores(df, mediana).set_index(df["Ticker"])


class TestPesos:
    def test_los_pesos_declarados_suman_cien(self):
        assert sum(BOND_SCORE_WEIGHTS.values()) == pytest.approx(100.0)

    def test_el_rendimiento_pesa_mas_que_cualquier_otra_dimension(self):
        rendimiento = BOND_SCORE_WEIGHTS[BOND_SCORE_YIELD]
        assert all(rendimiento >= peso for peso in BOND_SCORE_WEIGHTS.values())


class TestComparacionRelativa:
    def test_mejor_en_todo_puntua_mas_que_peor_en_todo(self):
        df = panel(
            bono("MEJOR", **{"TIR (%)": 10.0, "Spread (%)": 0.2, "Volumen": 9e6, "Duration Mod.": 1.0, "Paridad (%)": 85.0}),
            bono("PEOR", **{"TIR (%)": 6.0, "Spread (%)": 8.0, "Volumen": 10.0, "Duration Mod.": 9.0, "Paridad (%)": 120.0}),
        )
        resultado = puntajes(df)
        assert resultado.loc["MEJOR", "Puntaje"] > resultado.loc["PEOR", "Puntaje"]

    def test_el_puntaje_queda_dentro_de_la_escala(self):
        df = panel(*[bono(f"B{i}", **{"TIR (%)": 5.0 + i}) for i in range(6)])
        valores = puntajes(df)["Puntaje"].dropna()
        assert valores.between(0, 100).all()

    def test_a_igual_todo_el_que_rinde_mas_puntua_mas(self):
        df = panel(bono("ALTO", **{"TIR (%)": 10.0}), bono("BAJO", **{"TIR (%)": 8.0}))
        resultado = puntajes(df)
        assert resultado.loc["ALTO", "Puntaje"] > resultado.loc["BAJO", "Puntaje"]

    def test_a_igual_todo_el_mas_liquido_puntua_mas(self):
        df = panel(
            bono("LIQUIDO", **{"Spread (%)": 0.2, "Volumen": 5e6}),
            bono("ILIQUIDO", **{"Spread (%)": 6.0, "Volumen": 100.0}),
        )
        resultado = puntajes(df)
        assert resultado.loc["LIQUIDO", BOND_SCORE_LIQUIDITY] > resultado.loc["ILIQUIDO", BOND_SCORE_LIQUIDITY]

    def test_a_igual_todo_la_duration_corta_puntua_mas(self):
        df = panel(bono("CORTO", **{"Duration Mod.": 1.0}), bono("LARGO", **{"Duration Mod.": 8.0}))
        resultado = puntajes(df)
        assert resultado.loc["CORTO", "Puntaje"] > resultado.loc["LARGO", "Puntaje"]


class TestCastigoPorPrimaExcesiva:
    def test_una_prima_enorme_hunde_el_puntaje_de_rendimiento(self):
        # El bono con la TIR más alta del panel tiene que quedar último en
        # rendimiento, no primero: esa prima es riesgo de crédito con precio.
        df = panel(
            bono("SANO", **{"TIR (%)": 10.0}),
            bono("ESTRESADO", **{"TIR (%)": MEDIANA + BOND_RISK_YIELD_PREMIUM_PP * 2}),
        )
        resultado = puntajes(df)
        assert resultado.loc["ESTRESADO", BOND_SCORE_YIELD] < resultado.loc["SANO", BOND_SCORE_YIELD]
        assert resultado.loc["ESTRESADO", "Puntaje"] < resultado.loc["SANO", "Puntaje"]

    def test_un_bono_sano_le_gana_a_uno_apenas_pasado_del_umbral(self):
        df = panel(
            bono("SANO", **{"TIR (%)": MEDIANA + BOND_RISK_YIELD_PREMIUM_PP - 1}),
            bono("PASADO", **{"TIR (%)": MEDIANA + BOND_RISK_YIELD_PREMIUM_PP + 1}),
        )
        resultado = puntajes(df)
        assert resultado.loc["SANO", BOND_SCORE_YIELD] > resultado.loc["PASADO", BOND_SCORE_YIELD]

    def test_el_castigo_es_gradual_y_no_un_escalon(self):
        df = panel(
            bono("A", **{"TIR (%)": MEDIANA + BOND_RISK_YIELD_PREMIUM_PP + 1}),
            bono("B", **{"TIR (%)": MEDIANA + BOND_RISK_YIELD_PREMIUM_PP + 3}),
            bono("C", **{"TIR (%)": MEDIANA + BOND_RISK_YIELD_PREMIUM_PP + 5}),
        )
        resultado = puntajes(df)[BOND_SCORE_YIELD]
        assert resultado["A"] > resultado["B"] > resultado["C"]

    def test_sin_mediana_no_se_castiga_a_nadie(self):
        df = panel(bono("A", **{"TIR (%)": 40.0}), bono("B", **{"TIR (%)": 8.0}))
        resultado = compute_opportunity_scores(df, np.nan).set_index(df["Ticker"])
        assert resultado.loc["A", BOND_SCORE_YIELD] > resultado.loc["B", BOND_SCORE_YIELD]


class TestDatosFaltantes:
    def test_una_dimension_faltante_no_se_cobra_como_cero(self):
        # Dos bonos idénticos salvo que uno no tiene ley conocida: el que no la
        # tiene no puede quedar por debajo del que la tiene mal puntuada.
        df = panel(bono("CON_LEY", Ley="ARG"), bono("SIN_LEY", Ley=None))
        resultado = puntajes(df)
        assert np.isnan(resultado.loc["SIN_LEY", BOND_SCORE_JURISDICTION])
        assert resultado.loc["SIN_LEY", "Puntaje"] >= resultado.loc["CON_LEY", "Puntaje"]

    def test_la_cobertura_baja_cuando_falta_una_dimension(self):
        df = panel(bono("COMPLETO"), bono("SIN_LEY", Ley=None))
        resultado = puntajes(df)
        assert resultado.loc["COMPLETO", "Cobertura"] == pytest.approx(100.0)
        assert resultado.loc["SIN_LEY", "Cobertura"] < 100.0

    def test_sin_suficiente_informacion_no_se_publica_puntaje(self):
        df = panel(
            bono("COMPLETO"),
            bono("PELADO", **{"Spread (%)": np.nan, "Volumen": np.nan, "Duration Mod.": np.nan, "Paridad (%)": np.nan, "Ley": None}),
        )
        resultado = puntajes(df)
        assert np.isnan(resultado.loc["PELADO", "Puntaje"])
        assert not np.isnan(resultado.loc["COMPLETO", "Puntaje"])

    def test_la_liquidez_se_sostiene_con_una_sola_de_sus_dos_medidas(self):
        df = panel(bono("A", Volumen=np.nan), bono("B"))
        assert not np.isnan(puntajes(df).loc["A", BOND_SCORE_LIQUIDITY])

    def test_un_panel_vacio_no_rompe(self):
        assert compute_opportunity_scores(pd.DataFrame()).empty


class TestEtiqueta:
    @pytest.mark.parametrize(
        "puntaje,esperado",
        [
            (95.0, BOND_SIGNAL_VERY_ATTRACTIVE),
            (BOND_SCORE_VERY_ATTRACTIVE_MIN, BOND_SIGNAL_VERY_ATTRACTIVE),
            (BOND_SCORE_ATTRACTIVE_MIN, BOND_SIGNAL_ATTRACTIVE),
            (BOND_SCORE_NEUTRAL_MIN, BOND_SIGNAL_NEUTRAL),
            (10.0, BOND_SIGNAL_LOW),
        ],
    )
    def test_los_cortes_caen_donde_se_declaran(self, puntaje, esperado):
        assert label_from_score(puntaje) == esperado

    @pytest.mark.parametrize("puntaje", [None, float("nan"), "n/d"])
    def test_sin_puntaje_no_se_afirma_nada(self, puntaje):
        assert label_from_score(puntaje) == BOND_SIGNAL_NO_DATA
