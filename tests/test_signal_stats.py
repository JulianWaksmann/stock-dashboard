"""
Tests de `signal_stats.py`.

Dos cosas son las que importan y las dos son fáciles de romper sin que nada
avise:

  1. **Paridad con el tablero.** La medición replaya el semáforo con series
     vectorizadas en vez de rehacer `compute_stock_technicals` barra por barra.
     Si esa reconstrucción se desalinea, el módulo mide un sistema parecido y
     no el que está en pantalla.
  2. **Que no se filtre el futuro.** La señal de una barra tiene que ser la
     misma si el historial se corta justo ahí. Un indicador calculado con una
     ventana centrada, o un mínimo tomado sobre la serie completa, inventaría
     rendimiento del aire.
"""

import numpy as np
import pandas as pd
import pytest

from constants import (
    SIGNAL_MODERATE_SELL,
    SIGNAL_NEUTRAL,
    SIGNAL_SQUEEZE,
    SIGNAL_STATS_BASELINE,
    SIGNAL_STRONG_BUY,
    SIGNAL_STRONG_SELL,
)
from indicators import compute_stock_technicals
from signal_stats import (
    COL_ABS_MOVE,
    COL_CASES,
    COL_EXCESS,
    COL_HIT_RATE,
    COL_MEAN,
    COL_SIGNAL,
    SUMMARY_COLUMNS,
    collect_signal_outcomes,
    forward_returns,
    measure_signal_quality,
    replay_confluence_signals,
    summarize_outcomes,
)


class TestRetornosForward:
    def test_mide_las_barras_siguientes(self):
        close = pd.Series([100.0, 110.0, 121.0, 133.1])
        r = forward_returns(close, horizon=1)

        assert r.iloc[0] == pytest.approx(10.0)
        assert r.iloc[1] == pytest.approx(10.0)

    def test_las_ultimas_barras_quedan_en_nan(self):
        """Su futuro todavía no pasó: rellenarlas acortaría el horizonte."""
        r = forward_returns(pd.Series(np.arange(1.0, 11.0)), horizon=3)

        assert r.iloc[-3:].isna().all()
        assert r.iloc[:-3].notna().all()

    def test_serie_vacia_devuelve_vacio(self):
        assert forward_returns(pd.Series(dtype=float), horizon=5).empty

    def test_horizonte_no_positivo_devuelve_todo_nan_sin_acortar(self):
        """Se alinea contra las señales: acortarla rompería el alineamiento."""
        r = forward_returns(pd.Series([1.0, 2.0]), horizon=0)

        assert len(r) == 2
        assert r.isna().all()


class TestReplayDelSemaforo:
    def test_la_ultima_barra_coincide_con_el_semaforo_del_tablero(self, random_ohlcv_df):
        señales = replay_confluence_signals(random_ohlcv_df)
        del_tablero = compute_stock_technicals(random_ohlcv_df)["confluence_signal"]

        assert señales.iloc[-1] == del_tablero

    @pytest.mark.parametrize("corte", [50, 120, 199, 250, 299])
    def test_no_se_filtra_el_futuro(self, random_ohlcv_df, corte):
        """
        La señal de una barra no cambia si el historial termina ahí.

        Es la propiedad que vuelve creíble a toda la medición: si cambiara,
        la señal estaría mirando barras que ese día no existían.
        """
        completo = replay_confluence_signals(random_ohlcv_df)
        truncado = replay_confluence_signals(random_ohlcv_df.iloc[: corte + 1])

        assert truncado.iloc[-1] == completo.iloc[corte]

    def test_las_primeras_barras_son_neutrales(self, random_ohlcv_df):
        """El propio semáforo se abstiene con menos de 20 barras de historia."""
        señales = replay_confluence_signals(random_ohlcv_df)
        assert set(señales.iloc[:19]) == {SIGNAL_NEUTRAL}

    def test_devuelve_una_señal_por_barra(self, random_ohlcv_df):
        señales = replay_confluence_signals(random_ohlcv_df)
        assert len(señales) == len(random_ohlcv_df)
        assert señales.index.equals(random_ohlcv_df.index)

    def test_historial_vacio_o_sin_cierre_no_estalla(self):
        assert replay_confluence_signals(pd.DataFrame()).empty
        assert replay_confluence_signals(pd.DataFrame({"Open": [1.0]})).empty
        assert replay_confluence_signals(None).empty


class TestCasosRecolectados:
    def test_una_fila_por_barra_con_futuro_conocido(self, random_ohlcv_df):
        horizonte = 10
        casos = collect_signal_outcomes({"TKR": random_ohlcv_df}, horizon=horizonte)

        assert len(casos) == len(random_ohlcv_df) - horizonte
        assert set(casos.columns) == {"Ticker", "Fecha", COL_SIGNAL, "Retorno (%)"}
        assert casos["Retorno (%)"].notna().all()

    def test_acumula_varios_activos(self, random_ohlcv_df):
        casos = collect_signal_outcomes(
            {"UNO": random_ohlcv_df, "DOS": random_ohlcv_df}, horizon=5
        )
        assert set(casos["Ticker"]) == {"UNO", "DOS"}

    def test_los_historiales_inservibles_se_saltean(self, random_ohlcv_df):
        casos = collect_signal_outcomes(
            {"BUENO": random_ohlcv_df, "VACIO": pd.DataFrame(), "NULO": None},
            horizon=5,
        )
        assert set(casos["Ticker"]) == {"BUENO"}

    def test_sin_historiales_devuelve_tabla_vacia_con_columnas(self):
        casos = collect_signal_outcomes({}, horizon=5)
        assert casos.empty
        assert COL_SIGNAL in casos.columns


class TestResumen:
    @staticmethod
    def _casos(pares):
        """pares: lista de (señal, retorno)."""
        return pd.DataFrame({
            "Ticker": ["T"] * len(pares),
            "Fecha": pd.RangeIndex(len(pares)),
            COL_SIGNAL: [s for s, _ in pares],
            "Retorno (%)": [r for _, r in pares],
        })

    def test_la_base_va_primera_y_cuenta_todas_las_barras(self):
        casos = self._casos([
            (SIGNAL_STRONG_BUY, 10.0),
            (SIGNAL_NEUTRAL, 0.0),
            (SIGNAL_NEUTRAL, 2.0),
        ])
        resumen = summarize_outcomes(casos)

        assert resumen.iloc[0][COL_SIGNAL] == SIGNAL_STATS_BASELINE
        assert resumen.iloc[0][COL_CASES] == 3
        assert resumen.iloc[0][COL_MEAN] == pytest.approx(4.0)
        assert list(resumen.columns) == list(SUMMARY_COLUMNS)

    def test_el_exceso_se_mide_contra_la_base(self):
        """Lo único que importa: cuánto más que una barra cualquiera."""
        casos = self._casos([
            (SIGNAL_STRONG_BUY, 10.0),
            (SIGNAL_NEUTRAL, 0.0),
            (SIGNAL_NEUTRAL, 2.0),
        ])
        resumen = summarize_outcomes(casos).set_index(COL_SIGNAL)

        assert resumen.loc[SIGNAL_STRONG_BUY, COL_EXCESS] == pytest.approx(10.0 - 4.0)
        assert resumen.loc[SIGNAL_STATS_BASELINE, COL_EXCESS] == pytest.approx(0.0)

    def test_el_acierto_de_compra_cuenta_subas(self):
        casos = self._casos([
            (SIGNAL_STRONG_BUY, 5.0),
            (SIGNAL_STRONG_BUY, -5.0),
            (SIGNAL_STRONG_BUY, 1.0),
            (SIGNAL_STRONG_BUY, 3.0),
        ])
        resumen = summarize_outcomes(casos).set_index(COL_SIGNAL)
        assert resumen.loc[SIGNAL_STRONG_BUY, COL_HIT_RATE] == pytest.approx(75.0)

    def test_el_acierto_de_venta_cuenta_bajas(self):
        """
        Una venta acierta cuando el precio cae. Medirla con la regla de compra
        la haría ver mal justo cuando funcionó.
        """
        casos = self._casos([
            (SIGNAL_STRONG_SELL, -5.0),
            (SIGNAL_STRONG_SELL, -2.0),
            (SIGNAL_STRONG_SELL, 4.0),
            (SIGNAL_MODERATE_SELL, -1.0),
        ])
        resumen = summarize_outcomes(casos).set_index(COL_SIGNAL)

        assert resumen.loc[SIGNAL_STRONG_SELL, COL_HIT_RATE] == pytest.approx(200 / 3)
        assert resumen.loc[SIGNAL_MODERATE_SELL, COL_HIT_RATE] == pytest.approx(100.0)

    def test_squeeze_y_neutral_no_declaran_direccion(self):
        """
        El squeeze afirma magnitud, no dirección: su acierto queda sin medir y
        lo que se lee es el movimiento absoluto.
        """
        casos = self._casos([
            (SIGNAL_SQUEEZE, 12.0),
            (SIGNAL_SQUEEZE, -14.0),
            (SIGNAL_NEUTRAL, 1.0),
        ])
        resumen = summarize_outcomes(casos).set_index(COL_SIGNAL)

        assert np.isnan(resumen.loc[SIGNAL_SQUEEZE, COL_HIT_RATE])
        assert np.isnan(resumen.loc[SIGNAL_NEUTRAL, COL_HIT_RATE])
        assert resumen.loc[SIGNAL_SQUEEZE, COL_ABS_MOVE] == pytest.approx(13.0)

    def test_el_orden_de_las_filas_se_lee_como_el_semaforo(self):
        casos = self._casos([
            (SIGNAL_STRONG_SELL, -1.0),
            (SIGNAL_STRONG_BUY, 1.0),
            (SIGNAL_NEUTRAL, 0.0),
        ])
        señales = list(summarize_outcomes(casos)[COL_SIGNAL])

        assert señales == [
            SIGNAL_STATS_BASELINE,
            SIGNAL_STRONG_BUY,
            SIGNAL_NEUTRAL,
            SIGNAL_STRONG_SELL,
        ]

    def test_sin_casos_devuelve_resumen_vacio_con_columnas(self):
        vacio = summarize_outcomes(pd.DataFrame())
        assert vacio.empty
        assert list(vacio.columns) == list(SUMMARY_COLUMNS)


class TestMedicionCompleta:
    def test_devuelve_resumen_y_casos(self, random_ohlcv_df):
        resumen, casos = measure_signal_quality({"TKR": random_ohlcv_df}, horizon=20)

        assert not resumen.empty
        assert resumen.iloc[0][COL_SIGNAL] == SIGNAL_STATS_BASELINE
        assert resumen[COL_CASES].iloc[0] == len(casos)
