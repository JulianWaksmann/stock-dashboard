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

from bonds.scoring import _percentile, compute_opportunity_scores, label_from_score
from constants import (
    BOND_RISK_YIELD_PREMIUM_PP,
    BOND_SCORE_ATTRACTIVE_MIN,
    BOND_SCORE_JURISDICTION,
    BOND_SCORE_LIQUIDITY,
    BOND_SCORE_NEUTRAL_MIN,
    BOND_SCORE_RATE_RISK,
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


# El puntaje es un percentil, así que necesita un panel de referencia: por
# debajo de BOND_SCORE_MIN_PANEL_SIZE no publica nada. Los tests que comparan
# dos bonos completan el panel con relleno neutro para tener contra qué medir.
_RELLENO = 6


def panel(*filas, rellenar: bool = True) -> pd.DataFrame:
    filas = list(filas)
    if rellenar:
        filas += [bono(f"RELLENO{i}") for i in range(_RELLENO)]
    return pd.DataFrame(filas)


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

    def test_abstenerse_no_le_gana_a_tener_el_dato_bueno(self):
        # El reverso del test anterior, que es el riesgo real de renormalizar:
        # el que declara la mejor jurisdicción tiene que ganarle al que no la
        # declara, o el sistema premiaría no cargar datos.
        df = panel(bono("CON_LEY_NY", Ley="NY"), bono("SIN_LEY", Ley=None))
        resultado = puntajes(df)
        assert resultado.loc["CON_LEY_NY", "Puntaje"] > resultado.loc["SIN_LEY", "Puntaje"]

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

    def test_volumen_cero_es_la_peor_liquidez_posible_y_no_un_dato_faltante(self):
        # Por percentil, una masa de ceros empatados se reparte el rango medio:
        # una especie que no operó sacaba el mismo puntaje de liquidez que otra
        # con las puntas pegadas y medio millón operado.
        df = panel(
            bono("OPERO", **{"Spread (%)": 0.2, "Volumen": 5e6}),
            bono("NO_OPERO", **{"Spread (%)": np.nan, "Volumen": 0.0}),
        )
        resultado = puntajes(df)
        assert resultado.loc["NO_OPERO", BOND_SCORE_LIQUIDITY] == pytest.approx(0.0)
        assert resultado.loc["OPERO", BOND_SCORE_LIQUIDITY] > resultado.loc["NO_OPERO", BOND_SCORE_LIQUIDITY]

    def test_un_panel_vacio_no_rompe(self):
        assert compute_opportunity_scores(pd.DataFrame()).empty

    def test_un_panel_demasiado_chico_no_publica_puntaje(self):
        # Un percentil contra dos bonos no mide nada, y contra uno solo mide
        # que se ganó a sí mismo.
        df = panel(bono("A"), bono("B"), rellenar=False)
        assert compute_opportunity_scores(df, MEDIANA)["Puntaje"].isna().all()

    def test_una_dimension_que_casi_nadie_tiene_se_descarta_para_todos(self):
        # Si solo un bono tiene la ley cargada, el percentil lo compara consigo
        # mismo y los demás no pagan por no tenerla: cargar un dato cierto pero
        # mediocre terminaría bajando el puntaje.
        df = panel(bono("UNICO_CON_LEY", Ley="NY"), rellenar=False)
        for i in range(_RELLENO):
            df = pd.concat([df, pd.DataFrame([bono(f"R{i}", Ley=None)])], ignore_index=True)
        resultado = compute_opportunity_scores(df, MEDIANA).set_index(df["Ticker"])
        assert resultado[BOND_SCORE_JURISDICTION].isna().all()


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


class TestPercentilSimetrico:
    """
    `100 - percentil` no es el espejo del percentil: el rank porcentual de
    pandas vive en (0, 1] y su complemento en [0, 1). Usarlo sesgaba el puntaje
    a favor de las dimensiones donde más es mejor.
    """

    def test_con_todo_empatado_las_dos_direcciones_dan_lo_mismo(self):
        serie = pd.Series([5.0] * 5)
        assert _percentile(serie, True).iloc[0] == pytest.approx(_percentile(serie, False).iloc[0])

    def test_las_dos_direcciones_son_espejo_una_de_otra(self):
        serie = pd.Series([1.0, 2.0, 3.0, 4.0])
        assert list(_percentile(serie, True)) == list(reversed(list(_percentile(serie, False))))

    def test_dimensiones_iguales_no_se_sesgan_entre_si(self):
        # Panel donde todos los bonos son idénticos: ninguna dimensión puede
        # puntuar más que otra solo por la dirección en que se mide.
        df = panel(rellenar=True)
        resultado = compute_opportunity_scores(df, MEDIANA)
        assert resultado[BOND_SCORE_YIELD].iloc[0] == pytest.approx(resultado[BOND_SCORE_RATE_RISK].iloc[0])


class TestPanelComparable:
    def test_los_percentiles_se_calculan_solo_sobre_el_panel_comparable(self):
        # Si las no comparables entraran al ranking, la referencia del puntaje
        # y la de la mediana de TIR serían dos poblaciones distintas.
        df = panel(bono("EXCLUIDO", **{"TIR (%)": 99.0}))
        comparable = pd.Series([True] * len(df), index=df.index)
        comparable.iloc[0] = False
        resultado = compute_opportunity_scores(df, MEDIANA, comparable=comparable).set_index(df["Ticker"])
        assert np.isnan(resultado.loc["EXCLUIDO", BOND_SCORE_YIELD])
