"""
Tests de compute_rsi: regresión de los bugs de calentamiento / división
por cero, y propiedades generales del indicador.
"""

import numpy as np
import pandas as pd
import pytest

from indicators import compute_rsi


class TestRegresionCalentamiento:
    """
    Bug corregido: durante las primeras `period` barras, avg_gain/avg_loss
    todavía no tienen suficientes datos (min_periods=period) y el RSI debía
    quedar en NaN. La versión con el bug rellenaba esas barras con 0 o 100
    según el signo del último cambio, lo que generaba señales falsas desde
    el primer día de cotización.
    """

    def test_primeras_period_barras_son_nan(self, rising_series):
        period = 14
        rsi = compute_rsi(rising_series, period)
        # Las primeras `period` posiciones no tienen suficiente historial:
        # deben ser NaN, nunca 0 ni 100.
        assert rsi.iloc[:period].isna().all()

    def test_calentamiento_no_contiene_ceros_ni_cienes_espurios(self, rising_series):
        period = 14
        rsi = compute_rsi(rising_series, period)
        calentamiento = rsi.iloc[:period]
        # Ninguna barra de calentamiento debe tomar el valor 0 o 100: si el
        # bug reapareciera, el relleno por signo produciría exactamente eso.
        assert not (calentamiento == 0.0).any()
        assert not (calentamiento == 100.0).any()


class TestRegresionDivisionPorCero:
    """
    Bug corregido: cuando avg_loss == 0 (todas las variaciones fueron al
    alza), rs = avg_gain / 0 explotaba y el manejo naive de división por
    cero devolvía 0 en lugar de 100, invirtiendo la señal (parecía
    sobreventa cuando en realidad es la sobrecompra máxima posible).
    """

    def test_serie_estrictamente_creciente_da_rsi_100(self, rising_series):
        rsi = compute_rsi(rising_series, 14)
        valores_validos = rsi.dropna()
        assert len(valores_validos) > 0
        assert (valores_validos == 100.0).all()

    def test_serie_estrictamente_decreciente_da_rsi_0(self, falling_series):
        rsi = compute_rsi(falling_series, 14)
        valores_validos = rsi.dropna()
        assert len(valores_validos) > 0
        assert (valores_validos == 0.0).all()

    def test_serie_plana_da_rsi_50(self, flat_series):
        rsi = compute_rsi(flat_series, 14)
        valores_validos = rsi.dropna()
        assert len(valores_validos) > 0
        assert (valores_validos == 50.0).all()


class TestPropiedadesGenerales:

    def test_rsi_siempre_entre_0_y_100_cuando_no_es_nan(self, random_walk_series):
        rsi = compute_rsi(random_walk_series, 14)
        validos = rsi.dropna()
        assert len(validos) > 0
        assert (validos >= 0.0).all()
        assert (validos <= 100.0).all()

    @pytest.mark.parametrize("period", [2, 7, 14, 21])
    def test_rsi_respeta_calentamiento_para_distintos_periodos(self, random_walk_series, period):
        rsi = compute_rsi(random_walk_series, period)
        assert rsi.iloc[:period].isna().all()
        assert rsi.iloc[period:].notna().any()


class TestCasosBorde:

    def test_serie_vacia_no_lanza_excepcion(self):
        vacia = pd.Series([], dtype=float)
        rsi = compute_rsi(vacia, 14)
        assert len(rsi) == 0

    def test_serie_mas_corta_que_periodo_da_todo_nan(self):
        corta = pd.Series([1.0, 2.0, 3.0])
        rsi = compute_rsi(corta, 14)
        assert rsi.isna().all()
        assert len(rsi) == len(corta)

    def test_serie_de_un_solo_elemento_no_lanza_excepcion(self):
        rsi = compute_rsi(pd.Series([42.0]), 14)
        assert len(rsi) == 1
        assert rsi.isna().all()

    def test_serie_con_nan_intercalados_no_lanza_excepcion(self):
        con_nan = pd.Series([1.0, 2.0, np.nan, 4.0, 5.0, np.nan, 7.0, 8.0, 9.0, 10.0] * 3)
        rsi = compute_rsi(con_nan, 14)
        assert len(rsi) == len(con_nan)
        # No debe explotar; puede haber NaN pero ningún valor fuera de rango.
        validos = rsi.dropna()
        if len(validos) > 0:
            assert (validos >= 0.0).all() and (validos <= 100.0).all()
