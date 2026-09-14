"""
Tests de compute_sma, compute_ema y compute_macd.
"""

import numpy as np
import pandas as pd
import pytest

from indicators import compute_ema, compute_macd, compute_sma


class TestSMA:

    def test_serie_100_barras_periodo_200_es_todo_nan(self, series_100_bars):
        sma = compute_sma(series_100_bars, 200)
        assert sma.isna().all()
        assert len(sma) == len(series_100_bars)

    def test_serie_250_barras_periodo_200_tiene_valores_al_final(self, series_250_bars):
        sma = compute_sma(series_250_bars, 200)
        # Las primeras 199 posiciones no alcanzan el período completo.
        assert sma.iloc[:199].isna().all()
        # A partir de la barra 200 (índice 199) ya hay valores válidos.
        assert sma.iloc[199:].notna().all()

    def test_sma_de_serie_constante_es_esa_constante(self, flat_series):
        sma = compute_sma(flat_series, 10)
        validos = sma.dropna()
        assert len(validos) > 0
        assert np.allclose(validos, 100.0)

    @pytest.mark.parametrize("period", [5, 20, 50])
    def test_sma_coincide_con_promedio_manual(self, random_walk_series, period):
        sma = compute_sma(random_walk_series, period)
        # Verificamos un punto puntual contra el cálculo manual con numpy.
        idx = period + 10
        esperado = random_walk_series.iloc[idx - period + 1: idx + 1].mean()
        assert sma.iloc[idx] == pytest.approx(esperado)


class TestEMA:

    def test_ema_de_serie_constante_es_esa_constante(self, flat_series):
        ema = compute_ema(flat_series, 10)
        assert np.allclose(ema, 100.0)

    def test_ema_no_tiene_calentamiento_nan(self, random_walk_series):
        # A diferencia de la SMA, la EMA (ewm) arranca desde la primera barra.
        ema = compute_ema(random_walk_series, 20)
        assert ema.notna().all()


class TestMACD:

    def test_macd_de_serie_constante_tiende_a_cero(self, flat_series):
        df_macd = compute_macd(flat_series)
        # Con una serie sin variación, las EMAs rápida y lenta convergen al
        # mismo valor y la línea MACD (y su histograma) deben acercarse a 0.
        cola = df_macd.tail(10)
        assert np.allclose(cola['macd'], 0.0, atol=1e-6)
        assert np.allclose(cola['hist'], 0.0, atol=1e-6)

    def test_macd_devuelve_columnas_esperadas(self, random_walk_series):
        df_macd = compute_macd(random_walk_series)
        assert list(df_macd.columns) == ['macd', 'signal', 'hist']
        assert len(df_macd) == len(random_walk_series)

    def test_macd_hist_es_diferencia_entre_macd_y_signal(self, random_walk_series):
        df_macd = compute_macd(random_walk_series)
        diferencia = df_macd['macd'] - df_macd['signal']
        assert np.allclose(diferencia.dropna(), df_macd['hist'].dropna())


class TestCasosBorde:

    def test_sma_serie_vacia(self):
        vacia = pd.Series([], dtype=float)
        assert len(compute_sma(vacia, 20)) == 0

    def test_ema_serie_vacia(self):
        vacia = pd.Series([], dtype=float)
        assert len(compute_ema(vacia, 20)) == 0

    def test_macd_serie_vacia_no_lanza_excepcion(self):
        vacia = pd.Series([], dtype=float)
        df_macd = compute_macd(vacia)
        assert df_macd.empty

    def test_sma_serie_un_elemento(self):
        assert compute_sma(pd.Series([5.0]), 20).isna().all()

    def test_macd_serie_un_elemento_no_lanza_excepcion(self):
        df_macd = compute_macd(pd.Series([5.0]))
        assert len(df_macd) == 1
