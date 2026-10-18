"""
Tests de `bonds/curve.py` con paneles construidos a mano.

La curva es una lectura de valor relativo, así que lo que hay que fijar no es
solo que ajuste bien una recta: es **cuándo se niega a ajustarla** (pocos
bonos, plazos sin dispersión, dispersión que es ruido) y qué filas quedan
afuera del ajuste sin quedar afuera del diagnóstico.
"""

import numpy as np
import pandas as pd
import pytest

from bonds.curve import (
    COL_RELATIVE_VALUE,
    COL_RESIDUAL,
    COL_THEORETICAL_YTM,
    add_curve_residuals,
    curve_points,
    fit_currency_curve,
    fit_yield_curves,
)
from constants import (
    BOND_CURVE_CHEAP,
    BOND_CURVE_FAIR,
    BOND_CURVE_MIN_BONDS,
    BOND_CURVE_MIN_RESIDUAL_PP,
    BOND_CURVE_RICH,
)

INTERCEPTO = 8.0
PENDIENTE = 2.0


def panel(duraciones, tires=None, moneda="USD", en_default=None, tickers=None):
    """Panel mínimo con las columnas que mira la curva."""
    duraciones = list(duraciones)
    n = len(duraciones)
    if tires is None:
        tires = [INTERCEPTO + PENDIENTE * np.log1p(d) for d in duraciones]
    return pd.DataFrame({
        "Ticker": tickers if tickers is not None else [f"ON{i}" for i in range(n)],
        "Moneda": [moneda] * n if isinstance(moneda, str) else list(moneda),
        "Duration Mod.": duraciones,
        "TIR (%)": list(tires),
        "En Default": [False] * n if en_default is None else list(en_default),
    })


class TestAjuste:
    def test_recupera_los_coeficientes_de_una_curva_exacta(self):
        ajuste = fit_currency_curve(panel([0.5, 1.0, 2.0, 3.0, 5.0]), moneda="USD")

        assert ajuste is not None
        assert ajuste.intercepto == pytest.approx(INTERCEPTO)
        assert ajuste.pendiente == pytest.approx(PENDIENTE)
        assert ajuste.r2 == pytest.approx(1.0)
        assert ajuste.residual_sigma_pp == pytest.approx(0.0, abs=1e-9)
        assert ajuste.n == 5

    def test_tir_teorica_evalua_la_curva_ajustada(self):
        ajuste = fit_currency_curve(panel([0.5, 1.0, 2.0, 3.0, 5.0]), moneda="USD")
        assert ajuste.tir_teorica([2.0])[0] == pytest.approx(INTERCEPTO + PENDIENTE * np.log1p(2.0))

    def test_con_menos_bonos_que_el_minimo_no_hay_curva(self):
        duraciones = [1.0, 2.0, 3.0][: BOND_CURVE_MIN_BONDS - 1]
        assert fit_currency_curve(panel(duraciones)) is None

    def test_sin_dispersion_de_plazo_no_hay_curva(self):
        """Todos a duration ~2: la nube es vertical y la pendiente, ruido."""
        assert fit_currency_curve(panel([2.0, 2.05, 2.1, 2.02, 2.08])) is None

    def test_las_filas_sin_tir_o_sin_duration_no_cuentan(self):
        df = panel([0.5, 1.0, 2.0, 3.0, 4.0, 5.0])
        df.loc[0, "TIR (%)"] = np.nan
        df.loc[1, "Duration Mod."] = np.nan

        ajuste = fit_currency_curve(df)
        assert ajuste is not None
        assert ajuste.n == 4

    def test_un_panel_vacio_o_sin_columnas_no_estalla(self):
        assert fit_currency_curve(pd.DataFrame()) is None
        assert fit_currency_curve(pd.DataFrame({"Ticker": ["ON1"]})) is None
        assert fit_yield_curves(pd.DataFrame()) == {}


class TestFilasQueNoDistorsionanElAjuste:
    """
    Un emisor en default cotiza a precio de recupero: su TIR contractual es de
    dos o tres dígitos y una sola fila así inclina la recta entera.
    """

    def test_un_bono_en_default_no_mueve_la_curva(self):
        sano = panel([0.5, 1.0, 2.0, 3.0, 5.0])
        con_default = pd.concat([
            sano,
            panel([2.0], tires=[180.0], en_default=[True], tickers=["DEFAULT"]),
        ], ignore_index=True)

        a_sano = fit_currency_curve(sano, moneda="USD")
        a_con = fit_currency_curve(con_default, moneda="USD")

        assert a_con.pendiente == pytest.approx(a_sano.pendiente)
        assert a_con.intercepto == pytest.approx(a_sano.intercepto)

    def test_pero_igual_recibe_su_residuo(self):
        con_default = pd.concat([
            panel([0.5, 1.0, 2.0, 3.0, 5.0]),
            panel([2.0], tires=[180.0], en_default=[True], tickers=["DEFAULT"]),
        ], ignore_index=True)

        curvas = fit_yield_curves(con_default)
        out = add_curve_residuals(con_default, curvas)
        fila = out[out["Ticker"] == "DEFAULT"].iloc[0]

        assert fila[COL_RESIDUAL] > 100
        assert fila[COL_RELATIVE_VALUE] == BOND_CURVE_CHEAP

    def test_una_tir_absurda_sin_marca_de_default_tampoco_entra(self):
        """El filtro no depende de la marca de BYMA, también mira la magnitud."""
        df = pd.concat([
            panel([0.5, 1.0, 2.0, 3.0, 5.0]),
            panel([2.0], tires=[95.0], tickers=["RARO"]),
        ], ignore_index=True)

        ajuste = fit_currency_curve(df, moneda="USD")
        assert ajuste.n == 5
        assert ajuste.pendiente == pytest.approx(PENDIENTE)


class TestUnaCurvaPorMoneda:
    def test_cada_moneda_ajusta_la_suya(self):
        usd = panel([0.5, 1.0, 2.0, 3.0, 5.0], moneda="USD")
        ars = panel(
            [0.5, 1.0, 2.0, 3.0, 5.0],
            tires=[60.0 + 5.0 * np.log1p(d) for d in [0.5, 1.0, 2.0, 3.0, 5.0]],
            moneda="ARS",
        )
        curvas = fit_yield_curves(pd.concat([usd, ars], ignore_index=True))

        assert set(curvas) == {"USD", "ARS"}
        assert curvas["USD"].intercepto == pytest.approx(INTERCEPTO)
        assert curvas["ARS"].intercepto == pytest.approx(60.0)

    def test_la_moneda_que_no_alcanza_queda_sin_curva(self):
        usd = panel([0.5, 1.0, 2.0, 3.0, 5.0], moneda="USD")
        ars = panel([1.0, 2.0], moneda="ARS")
        curvas = fit_yield_curves(pd.concat([usd, ars], ignore_index=True))

        assert set(curvas) == {"USD"}

    def test_el_residuo_se_mide_contra_la_curva_de_su_propia_moneda(self):
        """Un bono en pesos a 65% no es barato: su curva está en 60%."""
        duraciones = [0.5, 1.0, 2.0, 3.0, 5.0]
        usd = panel(duraciones, moneda="USD")
        ars = panel(
            duraciones,
            tires=[60.0 + 5.0 * np.log1p(d) for d in duraciones],
            moneda="ARS",
        )
        df = pd.concat([usd, ars], ignore_index=True)

        out = add_curve_residuals(df, fit_yield_curves(df))
        assert out[COL_RESIDUAL].abs().max() == pytest.approx(0.0, abs=1e-9)


class TestEtiquetaDeValorRelativo:
    def test_sobre_y_bajo_la_curva(self):
        duraciones = [0.5, 1.0, 2.0, 3.0, 5.0, 7.0]
        tires = [INTERCEPTO + PENDIENTE * np.log1p(d) for d in duraciones]
        tires[2] += 3.0   # rinde mucho más que sus pares de igual plazo
        tires[4] -= 3.0   # rinde mucho menos
        df = panel(duraciones, tires=tires)

        out = add_curve_residuals(df, fit_yield_curves(df))

        assert out.loc[2, COL_RELATIVE_VALUE] == BOND_CURVE_CHEAP
        assert out.loc[4, COL_RELATIVE_VALUE] == BOND_CURVE_RICH
        assert out.loc[0, COL_RELATIVE_VALUE] == BOND_CURVE_FAIR

    def test_una_diferencia_menor_al_piso_no_etiqueta(self):
        """
        Panel pegado a su curva: el desvío de residuo es de centésimas y, sin
        el piso absoluto, cualquiera quedaría "barato" o "caro".
        """
        duraciones = [0.5, 1.0, 2.0, 3.0, 5.0]
        tires = [INTERCEPTO + PENDIENTE * np.log1p(d) for d in duraciones]
        tires[1] += BOND_CURVE_MIN_RESIDUAL_PP / 5
        df = panel(duraciones, tires=tires)

        out = add_curve_residuals(df, fit_yield_curves(df))
        assert (out[COL_RELATIVE_VALUE] == BOND_CURVE_FAIR).all()

    def test_sin_curva_las_columnas_existen_pero_vienen_vacias(self):
        df = panel([1.0, 2.0])
        out = add_curve_residuals(df, {})

        assert out[COL_THEORETICAL_YTM].isna().all()
        assert out[COL_RESIDUAL].isna().all()
        assert (out[COL_RELATIVE_VALUE] == BOND_CURVE_FAIR).all()

    def test_no_muta_el_panel_que_recibe(self):
        df = panel([0.5, 1.0, 2.0, 3.0, 5.0])
        columnas_antes = list(df.columns)
        add_curve_residuals(df, fit_yield_curves(df))

        assert list(df.columns) == columnas_antes


class TestPuntosParaDibujar:
    def test_no_extrapola_fuera_de_las_duraciones_observadas(self):
        df = panel([0.5, 1.0, 2.0, 3.0, 5.0])
        ajuste = fit_currency_curve(df, moneda="USD")

        xs, ys = curve_points(ajuste, df["Duration Mod."])
        assert xs.min() == pytest.approx(0.5)
        assert xs.max() == pytest.approx(5.0)
        assert ys[0] == pytest.approx(ajuste.tir_teorica([0.5])[0])

    def test_sin_duraciones_utilizables_devuelve_vacio(self):
        ajuste = fit_currency_curve(panel([0.5, 1.0, 2.0, 3.0, 5.0]), moneda="USD")
        xs, ys = curve_points(ajuste, [np.nan, np.nan])

        assert len(xs) == 0 and len(ys) == 0
