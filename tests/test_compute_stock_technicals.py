"""
Tests de compute_stock_technicals: contrato de claves que consume la UI,
e integración básica con institutional_flow / confluence_signal.
"""

import numpy as np
import pandas as pd

from constants import FLOW_ACCUMULATION, FLOW_DISTRIBUTION, FLOW_NOT_AVAILABLE, SIGNAL_NEUTRAL
from indicators import compute_stock_technicals


class TestInstitutionalFlow:

    def test_flow_not_available_cuando_no_hay_suficiente_obv(self):
        # Con pocas barras, sma_obv_20 (min_periods=10) queda en NaN y el
        # flujo institucional no debe reportar distribución por defecto.
        df = pd.DataFrame({
            'Close': [10.0, 11.0, 10.5, 11.5, 12.0],
            'Volume': [100.0, 120.0, 90.0, 110.0, 130.0],
        })
        resultado = compute_stock_technicals(df)
        assert resultado['institutional_flow'] == FLOW_NOT_AVAILABLE

    def test_flow_acumulacion_cuando_obv_supera_su_sma(self, random_ohlcv_df):
        resultado = compute_stock_technicals(random_ohlcv_df)
        assert resultado['institutional_flow'] in (
            FLOW_ACCUMULATION, FLOW_DISTRIBUTION, FLOW_NOT_AVAILABLE
        )
        if not np.isnan(resultado['obv']) and not np.isnan(resultado['sma_obv_20']):
            if resultado['obv'] >= resultado['sma_obv_20']:
                assert resultado['institutional_flow'] == FLOW_ACCUMULATION
            else:
                assert resultado['institutional_flow'] == FLOW_DISTRIBUTION


class TestContratoDeClaves:
    """
    La UI (app.py / components) consume estos diccionarios asumiendo que
    siempre tienen el mismo conjunto de claves, incluso cuando faltan datos.
    """

    def test_dataframe_none_devuelve_claves_minimas_predecibles(self):
        resultado = compute_stock_technicals(None)
        assert resultado['confluence_signal'] == SIGNAL_NEUTRAL
        assert resultado['institutional_flow'] == FLOW_NOT_AVAILABLE
        assert np.isnan(resultado['close'])

    def test_datos_insuficientes_no_lanza_excepcion(self):
        df = pd.DataFrame({'Close': [10.0, 11.0, 12.0]})
        resultado = compute_stock_technicals(df)
        assert 'confluence_signal' in resultado
        assert 'institutional_flow' in resultado

    def test_mismo_conjunto_de_claves_sin_importar_la_cantidad_de_datos(self):
        vacio = pd.DataFrame()
        pocos_datos = pd.DataFrame({'Close': [10.0, 11.0, 12.0]})
        todo_nan = pd.DataFrame({'Close': [np.nan, np.nan, np.nan]})

        claves_vacio = set(compute_stock_technicals(vacio).keys())
        claves_pocos = set(compute_stock_technicals(pocos_datos).keys())
        claves_nan = set(compute_stock_technicals(todo_nan).keys())

        assert claves_vacio == claves_pocos == claves_nan

    def test_datos_completos_incluye_todas_las_claves_esperadas(self, random_ohlcv_df):
        resultado = compute_stock_technicals(random_ohlcv_df)
        claves_esperadas = {
            'close', 'prev_close', 'day_change_pct',
            'sma_20', 'sma_50', 'sma_200',
            'diff_sma_20_pct', 'diff_sma_50_pct', 'diff_sma_200_pct',
            'rsi_14', 'macd_line', 'signal_line', 'macd_hist', 'prev_macd_hist',
            'bb_mid', 'bb_upper', 'bb_lower', 'bb_bandwidth', 'is_bb_squeeze',
            'stoch_k', 'stoch_d', 'prev_stoch_k', 'prev_stoch_d',
            'obv', 'sma_obv_20', 'institutional_flow',
            'high_52w', 'low_52w', 'dist_52w_high_pct',
            'confluence_signal', 'technical_status',
        }
        assert claves_esperadas.issubset(resultado.keys())


class TestCasosBorde:

    def test_dataframe_sin_columna_close_no_lanza_excepcion(self):
        df = pd.DataFrame({'Volume': [1.0, 2.0, 3.0]})
        resultado = compute_stock_technicals(df)
        assert resultado['confluence_signal'] == SIGNAL_NEUTRAL

    def test_un_solo_elemento_no_lanza_excepcion(self):
        df = pd.DataFrame({'Close': [10.0]})
        resultado = compute_stock_technicals(df)
        assert resultado['close'] == 10.0
        assert resultado['prev_close'] == 10.0
