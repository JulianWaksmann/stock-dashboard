"""
Tests de compute_52w_high_low.
"""

import numpy as np
import pandas as pd
import pytest

from indicators import compute_52w_high_low


class TestPropiedadesGenerales:

    def test_high_52w_mayor_igual_low_52w(self, random_ohlcv_df):
        df_52w = compute_52w_high_low(random_ohlcv_df, window=252)
        validos = df_52w.dropna(subset=['high_52w', 'low_52w'])
        assert len(validos) > 0
        assert (validos['high_52w'] >= validos['low_52w']).all()

    def test_dist_52w_high_pct_nunca_positiva(self, random_ohlcv_df):
        # El cierre nunca puede superar al máximo móvil que lo incluye,
        # así que la distancia porcentual al máximo debe ser <= 0.
        df_52w = compute_52w_high_low(random_ohlcv_df, window=252)
        validos = df_52w['dist_52w_high_pct'].dropna()
        assert len(validos) > 0
        assert (validos <= 1e-9).all()


class TestCasosBorde:

    def test_dataframe_sin_high_low_usa_close(self):
        df = pd.DataFrame({'Close': np.linspace(10.0, 20.0, 30)})
        df_52w = compute_52w_high_low(df, window=252)
        assert len(df_52w) == 30

    def test_un_solo_elemento_no_lanza_excepcion(self):
        df = pd.DataFrame({'High': [10.0], 'Low': [10.0], 'Close': [10.0]})
        df_52w = compute_52w_high_low(df, window=252)
        assert len(df_52w) == 1

    @pytest.mark.xfail(
        reason=(
            "BUG: compute_52w_high_low asume la columna 'Close' incluso "
            "cuando el DataFrame está completamente vacío (sin columnas). "
            "pd.DataFrame() hace explotar 'High' if 'High' in df.columns "
            "else df['Close'] con KeyError en vez de devolver vacío/NaN."
        )
    )
    def test_dataframe_completamente_vacio_no_lanza_excepcion(self):
        vacio = pd.DataFrame()
        df_52w = compute_52w_high_low(vacio, window=252)
        assert df_52w.empty
