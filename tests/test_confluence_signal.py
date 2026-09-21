"""
Tests de evaluate_confluence_signal: se construyen diccionarios tech_data
sintéticos que disparan deliberadamente cada rama del Algoritmo de
Confluencia por Sistema de Grados.

IMPORTANTE: las aserciones comparan contra las constantes importadas de
constants.py, nunca contra literales de string escritos a mano, para no
reintroducir el acoplamiento frágil (etiquetas con emojis hardcodeadas)
que ya se eliminó del código de producción.
"""

import numpy as np
import pandas as pd
import pytest

from constants import (
    BUY_RSI_MAX,
    BUY_SMA50_PROXIMITY_PCT,
    SELL_RSI_MIN,
    SIGNAL_MODERATE_BUY,
    SIGNAL_MODERATE_SELL,
    SIGNAL_NEUTRAL,
    SIGNAL_SQUEEZE,
    SIGNAL_STRONG_BUY,
    SIGNAL_STRONG_SELL,
)
from indicators import (
    STOCK_THRESHOLDS,
    ConfluenceThresholds,
    evaluate_confluence_signal,
)


@pytest.fixture
def historia_suficiente():
    """df_history con largo suficiente (>= 20) para habilitar la evaluación."""
    return pd.DataFrame({'Close': np.linspace(90.0, 100.0, 25)})


@pytest.fixture
def tech_data_base():
    """Diccionario base con todas las claves en NaN/False (no dispara nada)."""
    return dict(
        close=np.nan,
        dist_52w_high_pct=np.nan,
        rsi_14=np.nan,
        stoch_k=np.nan,
        stoch_d=np.nan,
        prev_stoch_k=np.nan,
        prev_stoch_d=np.nan,
        macd_hist=np.nan,
        prev_macd_hist=np.nan,
        macd_line=np.nan,
        signal_line=np.nan,
        sma_50=np.nan,
        sma_200=np.nan,
        bb_lower=np.nan,
        is_bb_squeeze=False,
        obv=np.nan,
        sma_obv_20=np.nan,
    )


class TestRamaCompra:

    def test_compra_fuerte_cuando_las_5_condiciones_se_cumplen(
        self, historia_suficiente, tech_data_base
    ):
        tech_data_base.update(
            close=100.0, sma_50=100.0, sma_200=90.0, rsi_14=40.0,
            stoch_k=20.0, stoch_d=25.0, prev_stoch_k=10.0, prev_stoch_d=15.0,
            obv=100.0, sma_obv_20=50.0,
        )
        resultado = evaluate_confluence_signal(historia_suficiente, tech_data_base)
        assert resultado == SIGNAL_STRONG_BUY

    def test_compra_moderada_cuando_solo_3_condiciones_se_cumplen(
        self, historia_suficiente, tech_data_base
    ):
        # c2 (soporte) y c3 (rsi) obligatorias + c1 (tendencia) true;
        # c4 (estocástico) y c5 (obv) deliberadamente false.
        tech_data_base.update(
            close=100.0, sma_50=100.0, sma_200=90.0, rsi_14=40.0,
            stoch_k=50.0, stoch_d=55.0, prev_stoch_k=60.0, prev_stoch_d=50.0,
            obv=40.0, sma_obv_20=50.0,
        )
        resultado = evaluate_confluence_signal(historia_suficiente, tech_data_base)
        assert resultado == SIGNAL_MODERATE_BUY

    def test_sin_condicion_obligatoria_de_soporte_no_hay_compra(
        self, historia_suficiente, tech_data_base
    ):
        # RSI bajo (obligatoria 3 cumplida) pero sin soporte (obligatoria 2).
        tech_data_base.update(close=100.0, sma_50=200.0, rsi_14=40.0)
        resultado = evaluate_confluence_signal(historia_suficiente, tech_data_base)
        assert resultado not in (SIGNAL_STRONG_BUY, SIGNAL_MODERATE_BUY)


class TestRamaVenta:

    def test_venta_fuerte_cuando_las_4_condiciones_se_cumplen(
        self, historia_suficiente, tech_data_base
    ):
        tech_data_base.update(
            dist_52w_high_pct=-3.0, rsi_14=70.0,
            stoch_k=85.0, stoch_d=80.0, prev_stoch_k=70.0, prev_stoch_d=75.0,
            obv=40.0, sma_obv_20=50.0,
        )
        resultado = evaluate_confluence_signal(historia_suficiente, tech_data_base)
        assert resultado == SIGNAL_STRONG_SELL

    def test_venta_moderada_cuando_solo_2_condiciones_se_cumplen(
        self, historia_suficiente, tech_data_base
    ):
        # c1 (techo) y c2 (rsi) obligatorias, c3 y c4 deliberadamente false.
        tech_data_base.update(
            dist_52w_high_pct=-3.0, rsi_14=70.0,
            stoch_k=50.0, stoch_d=55.0, prev_stoch_k=40.0, prev_stoch_d=45.0,
            macd_hist=1.0, prev_macd_hist=0.5,
            macd_line=1.0, signal_line=0.5,
            obv=60.0, sma_obv_20=50.0,
        )
        resultado = evaluate_confluence_signal(historia_suficiente, tech_data_base)
        assert resultado == SIGNAL_MODERATE_SELL

    def test_sin_condicion_obligatoria_de_techo_no_hay_venta(
        self, historia_suficiente, tech_data_base
    ):
        tech_data_base.update(dist_52w_high_pct=-20.0, rsi_14=70.0)
        resultado = evaluate_confluence_signal(historia_suficiente, tech_data_base)
        assert resultado not in (SIGNAL_STRONG_SELL, SIGNAL_MODERATE_SELL)


class TestRamaNeutralYSqueeze:

    def test_neutral_cuando_nada_se_dispara(self, historia_suficiente, tech_data_base):
        resultado = evaluate_confluence_signal(historia_suficiente, tech_data_base)
        assert resultado == SIGNAL_NEUTRAL

    def test_squeeze_cuando_is_bb_squeeze_y_sin_compra_ni_venta(
        self, historia_suficiente, tech_data_base
    ):
        tech_data_base.update(is_bb_squeeze=True)
        resultado = evaluate_confluence_signal(historia_suficiente, tech_data_base)
        assert resultado == SIGNAL_SQUEEZE


class TestCasosBorde:

    def test_historia_none_da_neutral(self, tech_data_base):
        resultado = evaluate_confluence_signal(None, tech_data_base)
        assert resultado == SIGNAL_NEUTRAL

    def test_historia_vacia_da_neutral(self, tech_data_base):
        resultado = evaluate_confluence_signal(pd.DataFrame(), tech_data_base)
        assert resultado == SIGNAL_NEUTRAL

    def test_historia_mas_corta_que_20_barras_da_neutral_aunque_condiciones_de_compra_se_cumplan(
        self, tech_data_base
    ):
        historia_corta = pd.DataFrame({'Close': np.linspace(90.0, 100.0, 10)})
        tech_data_base.update(
            close=100.0, sma_50=100.0, sma_200=90.0, rsi_14=40.0,
            stoch_k=20.0, stoch_d=25.0, prev_stoch_k=10.0, prev_stoch_d=15.0,
            obv=100.0, sma_obv_20=50.0,
        )
        resultado = evaluate_confluence_signal(historia_corta, tech_data_base)
        assert resultado == SIGNAL_NEUTRAL


class TestTechoPorExtensionSobreLaMedia:
    """
    El camino alternativo de la condición obligatoria del lado venta.

    Existe porque la condición clásica —estar a menos de 6% del máximo de 52
    semanas— asume un activo que cotiza cerca de sus máximos. Una cripto que
    cayó 70% y rebotó puede estar con RSI 80, muy estirada sobre su media, y
    a 60% de su máximo anual: sin este camino el semáforo no dice nada justo
    cuando el activo está más extendido.
    """

    @pytest.fixture
    def estirada_y_lejos_del_maximo(self, tech_data_base):
        """Muy por encima de su media, con sobrecompra, pero sin máximo cerca."""
        return {
            **tech_data_base,
            "close": 150.0,
            "dist_52w_high_pct": -60.0,   # lejísimos del máximo anual
            "rsi_14": 80.0,               # sobrecompra
            "diff_sma_50_pct": 45.0,      # 45% por encima de su media
            "sma50_dispersion_pct": 15.0, # su dispersión típica es 15% -> 3 sigmas
            "macd_hist": 1.0,
            "prev_macd_hist": 2.0,        # momento debilitándose (punto extra)
        }

    def test_con_el_camino_apagado_no_dispara(self, historia_suficiente, estirada_y_lejos_del_maximo):
        # Es el comportamiento de acciones, que no debe cambiar.
        assert evaluate_confluence_signal(
            historia_suficiente, estirada_y_lejos_del_maximo
        ) == SIGNAL_NEUTRAL

    def test_con_el_camino_encendido_marca_el_techo(self, historia_suficiente, estirada_y_lejos_del_maximo):
        umbrales = ConfluenceThresholds(stretch_sigmas=2.0)
        assert evaluate_confluence_signal(
            historia_suficiente, estirada_y_lejos_del_maximo, umbrales
        ) in (SIGNAL_STRONG_SELL, SIGNAL_MODERATE_SELL)

    def test_no_alcanza_con_estar_arriba_de_la_media(self, historia_suficiente, estirada_y_lejos_del_maximo):
        # 20% sobre una media que típicamente se separa 15% es 1,3 desvíos:
        # movimiento corriente para ese activo, no un extremo.
        moderada = {**estirada_y_lejos_del_maximo, "diff_sma_50_pct": 20.0}
        assert evaluate_confluence_signal(
            historia_suficiente, moderada, ConfluenceThresholds(stretch_sigmas=2.0)
        ) == SIGNAL_NEUTRAL

    def test_la_extension_se_mide_contra_la_dispersion_propia(self, historia_suficiente, estirada_y_lejos_del_maximo):
        # La misma distancia porcentual (45%) es un extremo para un activo
        # tranquilo y rutina para uno volátil: lo que decide es el cociente.
        volatil = {**estirada_y_lejos_del_maximo, "sma50_dispersion_pct": 40.0}
        assert evaluate_confluence_signal(
            historia_suficiente, volatil, ConfluenceThresholds(stretch_sigmas=2.0)
        ) == SIGNAL_NEUTRAL

    def test_sin_dispersion_conocida_no_inventa_un_techo(self, historia_suficiente, estirada_y_lejos_del_maximo):
        sin_dato = {**estirada_y_lejos_del_maximo, "sma50_dispersion_pct": np.nan}
        assert evaluate_confluence_signal(
            historia_suficiente, sin_dato, ConfluenceThresholds(stretch_sigmas=2.0)
        ) == SIGNAL_NEUTRAL

    def test_el_camino_clasico_sigue_funcionando(self, historia_suficiente, tech_data_base):
        # Cerca del máximo anual, sin extensión declarada: la condición de
        # siempre alcanza por sí sola.
        cerca_del_maximo = {
            **tech_data_base,
            "close": 100.0,
            "dist_52w_high_pct": -1.0,
            "rsi_14": 80.0,
            "macd_hist": 1.0,
            "prev_macd_hist": 2.0,
        }
        assert evaluate_confluence_signal(
            historia_suficiente, cerca_del_maximo, ConfluenceThresholds(stretch_sigmas=2.0)
        ) in (SIGNAL_STRONG_SELL, SIGNAL_MODERATE_SELL)


class TestCalibracionPorClaseDeActivo:
    def test_los_umbrales_por_omision_son_los_de_acciones(self):
        # Todo el tablero de acciones depende de que el valor por omisión no
        # cambie de comportamiento al parametrizar los umbrales.
        assert STOCK_THRESHOLDS.stretch_sigmas is None
        assert STOCK_THRESHOLDS.sma50_proximity_pct == BUY_SMA50_PROXIMITY_PCT
        assert STOCK_THRESHOLDS.buy_rsi_max == BUY_RSI_MAX
        assert STOCK_THRESHOLDS.sell_rsi_min == SELL_RSI_MIN

    def test_un_umbral_mas_exigente_calla_una_senal(self, historia_suficiente, tech_data_base):
        # Mismo activo, misma foto: lo único que cambia es la calibración.
        sobrecomprada = {
            **tech_data_base,
            "close": 100.0,
            "dist_52w_high_pct": -1.0,
            "rsi_14": 70.0,
            "macd_hist": 1.0,
            "prev_macd_hist": 2.0,
        }
        assert evaluate_confluence_signal(historia_suficiente, sobrecomprada) in (
            SIGNAL_STRONG_SELL,
            SIGNAL_MODERATE_SELL,
        )
        exigente = ConfluenceThresholds(sell_rsi_min=85.0)
        assert evaluate_confluence_signal(
            historia_suficiente, sobrecomprada, exigente
        ) == SIGNAL_NEUTRAL
