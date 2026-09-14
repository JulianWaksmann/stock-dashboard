"""
Tests de compute_stochastic: regresión del bug de calentamiento/relleno
con 50.0 y propiedades generales del oscilador.
"""

import numpy as np
import pandas as pd

from indicators import compute_stochastic


def _ohlc_desde_close(close: pd.Series, spread: float = 1.0) -> pd.DataFrame:
    """Construye un DataFrame OHLC simple a partir de una serie de cierres."""
    return pd.DataFrame({
        'High': close + spread,
        'Low': close - spread,
        'Close': close,
    })


class TestRegresionCalentamiento:
    """
    Bug corregido: highest_high/lowest_low en NaN durante el calentamiento
    (min_periods = period_k // 2) debían dejar %K en NaN. La versión con el
    bug usaba 50.0 como relleno genérico, mezclando "sin datos suficientes"
    con "rango realmente plano".
    """

    def test_calentamiento_queda_en_nan(self, random_ohlcv_df):
        period_k = 14
        df_stoch = compute_stochastic(random_ohlcv_df, period_k=period_k, period_d=3)
        min_periods = max(1, period_k // 2)
        # Antes de alcanzar min_periods no puede haber ningún valor válido.
        assert df_stoch['stoch_k'].iloc[:min_periods - 1].isna().all()
        # Ya alcanzado min_periods, empieza a haber valores.
        assert df_stoch['stoch_k'].iloc[min_periods:].notna().any()

    def test_50_solo_aparece_con_rango_genuinamente_cero(self):
        # Rango high-low constante y sin variación: acá sí corresponde 50.0.
        df_plano = pd.DataFrame({
            'High': [10.0] * 20,
            'Low': [10.0] * 20,
            'Close': [10.0] * 20,
        })
        df_stoch = compute_stochastic(df_plano, period_k=14, period_d=3)
        validos = df_stoch['stoch_k'].dropna()
        assert len(validos) > 0
        assert (validos == 50.0).all()

    def test_50_no_aparece_durante_calentamiento_con_rango_variable(self):
        # Serie con rango variable: el calentamiento debe ser NaN, nunca 50.0
        # "porque no había otro valor para poner".
        close = pd.Series(np.linspace(10.0, 50.0, 20))
        df = _ohlc_desde_close(close, spread=2.0)
        df_stoch = compute_stochastic(df, period_k=14, period_d=3)
        calentamiento = df_stoch['stoch_k'].iloc[:6]  # min_periods = 7
        assert calentamiento.isna().all()


class TestPropiedadesGenerales:

    def test_stoch_k_y_stoch_d_en_rango_0_100(self, random_ohlcv_df):
        df_stoch = compute_stochastic(random_ohlcv_df, period_k=14, period_d=3)
        k_validos = df_stoch['stoch_k'].dropna()
        d_validos = df_stoch['stoch_d'].dropna()
        assert len(k_validos) > 0 and len(d_validos) > 0
        assert (k_validos >= 0.0).all() and (k_validos <= 100.0).all()
        assert (d_validos >= 0.0).all() and (d_validos <= 100.0).all()

    def test_stoch_d_es_media_movil_de_stoch_k(self, random_ohlcv_df):
        df_stoch = compute_stochastic(random_ohlcv_df, period_k=14, period_d=3)
        esperado = df_stoch['stoch_k'].rolling(window=3, min_periods=1).mean()
        pd.testing.assert_series_equal(
            df_stoch['stoch_d'], esperado, check_names=False
        )


class TestCasosBorde:

    def test_dataframe_sin_columna_high_low_usa_close(self):
        df = pd.DataFrame({'Close': np.linspace(10.0, 20.0, 20)})
        df_stoch = compute_stochastic(df, period_k=14, period_d=3)
        assert len(df_stoch) == len(df)

    def test_serie_mas_corta_que_periodo(self):
        df = _ohlc_desde_close(pd.Series([1.0, 2.0, 3.0]))
        df_stoch = compute_stochastic(df, period_k=14, period_d=3)
        assert len(df_stoch) == 3

    def test_un_solo_elemento_no_lanza_excepcion(self):
        df = _ohlc_desde_close(pd.Series([5.0]))
        df_stoch = compute_stochastic(df, period_k=14, period_d=3)
        assert len(df_stoch) == 1
        assert df_stoch['stoch_k'].isna().all()

    def test_dataframe_completamente_vacio_no_lanza_excepcion(self):
        vacio = pd.DataFrame()
        df_stoch = compute_stochastic(vacio, period_k=14, period_d=3)
        assert df_stoch.empty
