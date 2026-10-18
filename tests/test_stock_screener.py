"""
Tests del tamiz del panel de acciones (`stock_screener.py`).

El filtrado vivía dentro del cuerpo de la pestaña, mezclado con los widgets: un
filtro que deja pasar lo que debería recortar solo se veía mirando la pantalla.
Ahora es una función pura y esto es lo que fija su comportamiento, incluida la
decisión de que las filas sin RSI **pasen** el filtro de RSI.
"""

import numpy as np
import pandas as pd

from constants import (
    FILTER_FLOW_ACCUMULATION,
    FILTER_FLOW_DISTRIBUTION,
    FILTER_SIGNAL_BUY,
    FILTER_SIGNAL_SELL,
    FILTER_SIGNAL_SQUEEZE,
    FILTER_SIGNAL_STRONG_BUY,
    FILTER_SMA200_BEARISH,
    FILTER_SMA200_BULLISH,
    FLOW_ACCUMULATION,
    FLOW_DISTRIBUTION,
    SIGNAL_MODERATE_BUY,
    SIGNAL_MODERATE_SELL,
    SIGNAL_NEUTRAL,
    SIGNAL_SQUEEZE,
    SIGNAL_STRONG_BUY,
    SIGNAL_STRONG_SELL,
)
from stock_screener import StockFilters, apply_stock_filters

PANEL = pd.DataFrame({
    "Ticker": ["FUERTE", "MODERADA", "NEUTRA", "SQZ", "VENTA", "VENTAMOD", "SINRSI"],
    "Semáforo": [
        SIGNAL_STRONG_BUY,
        SIGNAL_MODERATE_BUY,
        SIGNAL_NEUTRAL,
        SIGNAL_SQUEEZE,
        SIGNAL_STRONG_SELL,
        SIGNAL_MODERATE_SELL,
        SIGNAL_NEUTRAL,
    ],
    "Flujo Institucional": [
        FLOW_ACCUMULATION,
        FLOW_DISTRIBUTION,
        FLOW_ACCUMULATION,
        FLOW_DISTRIBUTION,
        FLOW_DISTRIBUTION,
        FLOW_ACCUMULATION,
        FLOW_ACCUMULATION,
    ],
    "RSI_VAL": [30.0, 44.0, 50.0, 55.0, 72.0, 68.0, np.nan],
    "DIFF_SMA_200_VAL": [5.0, -3.0, 1.0, -2.0, 12.0, 8.0, np.nan],
})


def _tickers(df):
    return set(df["Ticker"])


class TestSinFiltros:
    def test_los_valores_por_omision_no_recortan_nada(self):
        resultado = apply_stock_filters(PANEL, StockFilters())
        assert len(resultado) == len(PANEL)

    def test_un_panel_vacio_devuelve_un_panel_vacio(self):
        assert apply_stock_filters(pd.DataFrame(), StockFilters()).empty
        assert apply_stock_filters(None, StockFilters()).empty

    def test_devuelve_una_copia_y_no_toca_el_original(self):
        resultado = apply_stock_filters(PANEL, StockFilters(signal=FILTER_SIGNAL_BUY))
        resultado["Ticker"] = "PISADO"

        assert "FUERTE" in _tickers(PANEL)


class TestFiltroDeSemaforo:
    def test_solo_compra_fuerte(self):
        resultado = apply_stock_filters(PANEL, StockFilters(signal=FILTER_SIGNAL_STRONG_BUY))
        assert _tickers(resultado) == {"FUERTE"}

    def test_compras_incluye_los_dos_grados(self):
        resultado = apply_stock_filters(PANEL, StockFilters(signal=FILTER_SIGNAL_BUY))
        assert _tickers(resultado) == {"FUERTE", "MODERADA"}

    def test_ventas_incluye_los_dos_grados(self):
        resultado = apply_stock_filters(PANEL, StockFilters(signal=FILTER_SIGNAL_SELL))
        assert _tickers(resultado) == {"VENTA", "VENTAMOD"}

    def test_squeeze(self):
        resultado = apply_stock_filters(PANEL, StockFilters(signal=FILTER_SIGNAL_SQUEEZE))
        assert _tickers(resultado) == {"SQZ"}


class TestFiltroDeFlujo:
    def test_acumulacion(self):
        resultado = apply_stock_filters(PANEL, StockFilters(flow=FILTER_FLOW_ACCUMULATION))
        assert _tickers(resultado) == {"FUERTE", "NEUTRA", "VENTAMOD", "SINRSI"}

    def test_distribucion(self):
        resultado = apply_stock_filters(PANEL, StockFilters(flow=FILTER_FLOW_DISTRIBUTION))
        assert _tickers(resultado) == {"MODERADA", "SQZ", "VENTA"}


class TestFiltroDeRsi:
    def test_recorta_por_rango(self):
        resultado = apply_stock_filters(PANEL, StockFilters(rsi_range=(45.0, 70.0)))
        assert _tickers(resultado) == {"NEUTRA", "SQZ", "VENTAMOD", "SINRSI"}

    def test_las_filas_sin_rsi_pasan(self):
        """
        Un ticker cuyos indicadores no se pudieron calcular no es un ticker
        fuera de rango: esconderlo disimularía una falla de datos.
        """
        resultado = apply_stock_filters(PANEL, StockFilters(rsi_range=(0.0, 1.0)))
        assert _tickers(resultado) == {"SINRSI"}


class TestFiltroDeTendencia:
    def test_solo_alcistas(self):
        resultado = apply_stock_filters(PANEL, StockFilters(sma200=FILTER_SMA200_BULLISH))
        assert _tickers(resultado) == {"FUERTE", "NEUTRA", "VENTA", "VENTAMOD"}

    def test_solo_bajistas(self):
        resultado = apply_stock_filters(PANEL, StockFilters(sma200=FILTER_SMA200_BEARISH))
        assert _tickers(resultado) == {"MODERADA", "SQZ"}


class TestFiltrosCombinados:
    def test_se_aplican_todos_a_la_vez(self):
        resultado = apply_stock_filters(
            PANEL,
            StockFilters(
                signal=FILTER_SIGNAL_BUY,
                flow=FILTER_FLOW_ACCUMULATION,
                rsi_range=(0.0, 40.0),
                sma200=FILTER_SMA200_BULLISH,
            ),
        )
        assert _tickers(resultado) == {"FUERTE"}

    def test_una_combinacion_sin_resultados_no_estalla(self):
        resultado = apply_stock_filters(
            PANEL,
            StockFilters(signal=FILTER_SIGNAL_STRONG_BUY, flow=FILTER_FLOW_DISTRIBUTION),
        )
        assert resultado.empty
