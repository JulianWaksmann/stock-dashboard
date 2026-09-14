"""
Tests de compute_obv.
"""

import numpy as np
import pandas as pd

from indicators import compute_obv


class TestAcumulacionManual:

    def test_obv_acumula_correctamente_caso_a_mano(self):
        """
        Caso calculado a mano:
          día 0: close=10 (referencia, sin variación previa)      -> +0
          día 1: close=12 (sube)  volumen=100                      -> +100
          día 2: close=11 (baja)  volumen=50                       -> -50
          día 3: close=11 (igual) volumen=30                       -> +0
          día 4: close=15 (sube)  volumen=200                      -> +200
        OBV acumulado esperado: [0, 100, 50, 50, 250]
        """
        df = pd.DataFrame({
            'Close': [10.0, 12.0, 11.0, 11.0, 15.0],
            'Volume': [100.0, 100.0, 50.0, 30.0, 200.0],
        })
        df_obv = compute_obv(df, period_sma=20)
        esperado = [0.0, 100.0, 50.0, 50.0, 250.0]
        assert df_obv['obv'].tolist() == esperado

    def test_volumen_en_cero_no_lanza_excepcion_y_obv_no_cambia(self):
        df = pd.DataFrame({
            'Close': [1.0, 2.0, 3.0, 2.0, 1.0] * 5,
            'Volume': [0.0] * 25,
        })
        df_obv = compute_obv(df, period_sma=20)
        assert (df_obv['obv'] == 0.0).all()


class TestCasosBorde:

    def test_dataframe_vacio_no_lanza_excepcion(self):
        vacio = pd.DataFrame()
        df_obv = compute_obv(vacio, period_sma=20)
        assert df_obv.empty
        assert list(df_obv.columns) == ['obv', 'sma_obv_20']

    def test_dataframe_sin_columna_close_no_lanza_excepcion(self):
        sin_close = pd.DataFrame({'Volume': [1.0, 2.0, 3.0]})
        df_obv = compute_obv(sin_close, period_sma=20)
        assert df_obv.empty

    def test_sin_columna_volumen_asume_volumen_cero(self):
        df = pd.DataFrame({'Close': [1.0, 2.0, 3.0, 2.0, 1.0]})
        df_obv = compute_obv(df, period_sma=20)
        assert (df_obv['obv'] == 0.0).all()

    def test_un_solo_elemento_no_lanza_excepcion(self):
        df = pd.DataFrame({'Close': [10.0], 'Volume': [100.0]})
        df_obv = compute_obv(df, period_sma=20)
        assert len(df_obv) == 1
        assert df_obv['obv'].iloc[0] == 0.0

    def test_volumen_con_nan_se_trata_como_cero(self):
        """
        día 0: close=10 (referencia)                    -> +0
        día 1: close=12 (sube) volumen=NaN -> tratado 0  -> +0
        día 2: close=11 (baja) volumen=50                -> -50
        """
        df = pd.DataFrame({
            'Close': [10.0, 12.0, 11.0],
            'Volume': [100.0, np.nan, 50.0],
        })
        df_obv = compute_obv(df, period_sma=20)
        # El día con volumen NaN no debe aportar variación al acumulado,
        # aunque el precio haya subido ese día.
        assert df_obv['obv'].tolist() == [0.0, 0.0, -50.0]
