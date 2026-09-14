"""
Tests de compute_bollinger_bands.
"""

import numpy as np
import pandas as pd

from indicators import compute_bollinger_bands


class TestPropiedadesGenerales:

    def test_banda_superior_mayor_igual_media_mayor_igual_banda_inferior(self, random_walk_series):
        df_bb = compute_bollinger_bands(random_walk_series, period=20, num_std=2.0)
        validos = df_bb.dropna(subset=['bb_mid', 'bb_upper', 'bb_lower'])
        assert len(validos) > 0
        assert (validos['bb_upper'] >= validos['bb_mid']).all()
        assert (validos['bb_mid'] >= validos['bb_lower']).all()

    def test_serie_constante_colapsa_bandas_sobre_la_media(self, flat_series):
        df_bb = compute_bollinger_bands(flat_series, period=10, num_std=2.0)
        validos = df_bb.dropna(subset=['bb_mid'])
        assert len(validos) > 0
        # Sin desviación estándar, las tres bandas deben coincidir.
        assert np.allclose(validos['bb_upper'], validos['bb_mid'])
        assert np.allclose(validos['bb_lower'], validos['bb_mid'])
        assert np.allclose(validos['bb_mid'], 100.0)


class TestCasosBorde:

    def test_dataframe_vacio_no_lanza_excepcion(self):
        vacia = pd.Series([], dtype=float)
        df_bb = compute_bollinger_bands(vacia, period=20)
        assert df_bb.empty

    def test_serie_mas_corta_que_periodo(self):
        corta = pd.Series([1.0, 2.0, 3.0])
        df_bb = compute_bollinger_bands(corta, period=20)
        assert df_bb['bb_mid'].isna().all()

    def test_serie_un_elemento_no_lanza_excepcion(self):
        df_bb = compute_bollinger_bands(pd.Series([10.0]), period=20)
        assert len(df_bb) == 1
        assert df_bb['bb_mid'].isna().all()

    def test_serie_con_nan_intercalados_no_lanza_excepcion(self):
        con_nan = pd.Series([1.0, 2.0, np.nan, 4.0, 5.0, np.nan, 7.0, 8.0, 9.0, 10.0] * 3)
        df_bb = compute_bollinger_bands(con_nan, period=10)
        assert len(df_bb) == len(con_nan)
