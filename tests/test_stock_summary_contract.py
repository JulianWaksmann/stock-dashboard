"""
Contrato entre la descarga de acciones y lo que dibuja el tablero.

`data_loader.build_summary_row` arma las columnas de `df_summary`, y la ficha
de detalle, el screener y los gráficos las leen **por nombre**. Ese acoplamiento
no lo detecta ningún cálculo: renombrar una columna deja un `KeyError` en
pantalla (o, peor, un `row.get()` que devuelve el valor por defecto y parece un
dato). Los tests de acá fijan los nombres y, además, hacen pasar los gráficos
por un panel sintético, que es la única forma de verificar las columnas que
viven dentro de un `customdata` de Plotly.

Ya pasó una vez: `components/charts.py` y `components/ticker_detail.py` pedían
`"Señal Confluencia"` y `"Empresa"`, columnas que `df_summary` no tenía.
"""

import re

import numpy as np
import pandas as pd
import pytest

from components.charts import (
    compute_chart_indicators,
    plot_pe_comparison_bar,
    plot_sma_distances_bar,
    plot_stock_detail,
    plot_valuation_vs_technicals,
)
from constants import SIGNAL_NEUTRAL
from data_loader import build_summary_row
from indicators import compute_stock_technicals

# Columnas que lee cada consumidor. Si una desaparece de build_summary_row,
# acá se cae un test en vez de caerse el tablero.
COLUMNAS_FICHA_DETALLE = (
    "Ticker",
    "Empresa",
    "Sector",
    "Semáforo",
    "Precio Actual",
    "Var. Período (%)",
    "PER Pasado (Trailing)",
    "PER Futuro (Forward)",
    "PER Prom. Hist. (5A)",
    "RSI_VAL",
    "SMA_50_VAL",
    "SMA_200_VAL",
    "DIFF_SMA_50_VAL",
    "DIFF_SMA_200_VAL",
    "BB_BANDWIDTH",
    "STOCH_K",
    "STOCH_D",
    "DIST_52W_HIGH_PCT",
)

COLUMNAS_GRAFICOS_AGREGADOS = (
    "Ticker",
    "Empresa",
    "Sector",
    "Semáforo",
    "Precio Actual",
    "Var. Período (%)",
    "PER Pasado (Trailing)",
    "PER Futuro (Forward)",
    "PER Prom. Hist. (5A)",
    "RSI_VAL",
    "DIFF_SMA_200_VAL",
    "Market Cap ($B)",
)

COLUMNAS_FILTROS_Y_KPIS = (
    "Semáforo",
    "Flujo Institucional",
    "RSI_VAL",
    "DIFF_SMA_200_VAL",
    "DIST_52W_HIGH_PCT",
    "BB_BANDWIDTH",
)


def _fundamentales(nombre="Apple Inc.", forward_pe=25.0, market_cap=3.0e12):
    return {
        "ticker": "AAPL",
        "name": nombre,
        "sector": "Tecnología",
        "industry": "Hardware",
        "trailing_pe": 30.0,
        "forward_pe": forward_pe,
        "hist_avg_pe": 22.0,
        "peg_ratio": 2.0,
        "market_cap": market_cap,
        "dividend_yield": 0.5,
        "fifty_two_week_high": 200.0,
        "fifty_two_week_low": 120.0,
        "currency": "USD",
    }


def _panel_sintetico(random_ohlcv_df, n=6):
    """Panel de n acciones construido con la misma cadena que la descarga real."""
    tech = compute_stock_technicals(random_ohlcv_df)
    filas = []
    for i in range(n):
        fund = _fundamentales(
            nombre=f"Empresa {i}",
            forward_pe=15.0 + i,
            market_cap=(50 + i * 30) * 1e9,
        )
        fila = build_summary_row(f"TKR{i}", fund, tech, " (Día)")
        fila["Ticker"] = f"TKR{i}"
        filas.append(fila)
    return pd.DataFrame(filas)


class TestContratoDeColumnas:
    """Los nombres que los componentes indexan existen en la fila."""

    @pytest.mark.parametrize(
        "columnas",
        [COLUMNAS_FICHA_DETALLE, COLUMNAS_GRAFICOS_AGREGADOS, COLUMNAS_FILTROS_Y_KPIS],
        ids=["ficha_detalle", "graficos_agregados", "filtros_y_kpis"],
    )
    def test_todas_las_columnas_estan_presentes(self, columnas):
        fila = build_summary_row("AAPL", _fundamentales(), {}, " (Día)")
        faltantes = [c for c in columnas if c not in fila]
        assert faltantes == [], f"columnas que el tablero lee y la fila no tiene: {faltantes}"

    def test_el_sufijo_de_temporalidad_solo_afecta_a_las_columnas_de_mostrar(self):
        dia = build_summary_row("AAPL", _fundamentales(), {}, " (Día)")
        sem = build_summary_row("AAPL", _fundamentales(), {}, " (Sem)")

        assert "RSI (14) (Día)" in dia and "RSI (14) (Sem)" in sem
        # Las de nombre estable no cambian: son las que usan filtros y gráficos.
        for columna in ("RSI_VAL", "DIFF_SMA_200_VAL", "STOCH_K"):
            assert columna in dia and columna in sem

    def test_sin_tecnicos_la_fila_igual_trae_todas_las_claves(self):
        """Un ticker que falló no deja una fila corta: deja una fila en NaN."""
        fila = build_summary_row("ZZZ", {}, {}, " (Día)")
        assert fila["Semáforo"] == SIGNAL_NEUTRAL
        assert fila["Empresa"] == "ZZZ"  # sin nombre, se cae al ticker
        assert np.isnan(fila["RSI_VAL"])

    def test_el_nombre_de_la_empresa_sale_de_los_fundamentales(self):
        fila = build_summary_row("AAPL", _fundamentales(nombre="Apple Inc."), {}, " (Día)")
        assert fila["Empresa"] == "Apple Inc."


class TestGraficosSobreUnPanelRealista:
    """
    Los gráficos se dibujan sin estallar y con datos adentro.

    `plot_valuation_vs_technicals` mete siete columnas en el `customdata` del
    scatter: es el consumidor más frágil de todos y el que ya estaba roto.
    """

    def test_scatter_de_valuacion_dibuja_los_puntos(self, random_ohlcv_df):
        df = _panel_sintetico(random_ohlcv_df)
        fig = plot_valuation_vs_technicals(df, timeframe_label="Diario")
        assert len(fig.data) == 1
        assert len(fig.data[0].x) == len(df)
        # El tooltip trae empresa, sector y semáforo por fila.
        assert fig.data[0].customdata.shape == (len(df), 7)

    def test_barras_de_per_dibujan_una_serie_por_metrica(self, random_ohlcv_df):
        df = _panel_sintetico(random_ohlcv_df)
        fig = plot_pe_comparison_bar(df)
        assert len(fig.data) == 3  # trailing, forward e histórico

    def test_ranking_vs_sma200_ordena_de_menor_a_mayor(self, random_ohlcv_df):
        df = _panel_sintetico(random_ohlcv_df)
        fig = plot_sma_distances_bar(df, timeframe_label="Diario")
        valores = list(fig.data[0].x)
        assert valores == sorted(valores)

    def test_panel_vacio_devuelve_figura_con_aviso_y_no_excepcion(self):
        vacio = pd.DataFrame(columns=["PER Futuro (Forward)", "DIFF_SMA_200_VAL", "RSI_VAL"])
        fig = plot_valuation_vs_technicals(vacio)
        assert fig.data == ()
        assert fig.layout.annotations


class TestGraficoDeDetalle:
    """El gráfico de 4 paneles de la ficha."""

    def test_cuatro_paneles_con_sus_series(self, random_ohlcv_df):
        indicadores = compute_chart_indicators(random_ohlcv_df)
        assert indicadores is not None
        fig = plot_stock_detail(random_ohlcv_df, indicadores, "TKR0", "Empresa 0", "Diario")
        # Velas + SMA 50 + SMA 200 + 3 líneas de Bollinger + volumen +
        # MACD (línea, señal, histograma) + RSI + %K + %D.
        assert len(fig.data) >= 10
        assert fig.layout.yaxis4.range == (0, 100)  # el panel de osciladores

    def test_dibuja_soportes_y_resistencias(self, random_ohlcv_df):
        """
        Los niveles salen del mismo detector que el gráfico de cripto, con
        parámetros medidos sobre acciones: lo que se fija acá es que lleguen al
        gráfico y que la etiqueta diga cuántos toques tiene cada zona, que es
        lo que distingue un nivel fuerte de una línea sobre un máximo casual.

        La cuenta se escribe "×3" y no "(3 toques)" porque la etiqueta se
        dibuja fuera del área de trazado y la versión larga quedaba cortada;
        lo que el test fija es que el número esté, no cómo se escribe.
        """
        indicadores = compute_chart_indicators(random_ohlcv_df)
        fig = plot_stock_detail(random_ohlcv_df, indicadores, "TKR0", "Empresa 0", "Diario")

        etiquetas = [
            a.text for a in fig.layout.annotations
            if a.text and ("Soporte" in a.text or "Resistencia" in a.text)
        ]
        assert etiquetas, "el gráfico no dibujó ningún nivel"
        assert all(re.search(r"×\d+$", texto) for texto in etiquetas)

    def test_sin_historial_devuelve_figura_con_aviso(self):
        fig = plot_stock_detail(pd.DataFrame(), None, "TKR0")
        assert fig.data == ()
        assert fig.layout.annotations
