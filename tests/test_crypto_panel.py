"""
Tests del motor de criptomonedas (`crypto/panel.py`) y del formato de precios.

Todo con OHLCV fijo: el módulo no toca red ni Streamlit, así que no hace falta
ningún mock. Lo que se verifica acá es lo que distingue a esta sección de la
de acciones —el calendario de 365 días, la referencia contra Bitcoin y la
volatilidad anualizada— más los filtros del cuadro.
"""

import numpy as np
import pandas as pd
import pytest

from components.formatting import format_crypto_price, format_month_year, format_usd_compact
from constants import (
    CRYPTO_52W_WINDOW_DAILY,
    CRYPTO_52W_WINDOW_WEEKLY,
    CRYPTO_BARS_PER_YEAR_DAILY,
    CRYPTO_FILTER_RS_ALL,
    CRYPTO_FILTER_RS_OUTPERFORM,
    CRYPTO_FILTER_RS_UNDERPERFORM,
    CRYPTO_FILTER_SIGNAL_ALL,
    CRYPTO_FILTER_SIGNAL_SQUEEZE,
    CRYPTO_FILTER_TREND_ALL,
    CRYPTO_FILTER_TREND_BEARISH,
    CRYPTO_FILTER_TREND_BULLISH,
    CRYPTO_RS_INLINE,
    CRYPTO_RS_NEUTRAL_BAND_PP,
    CRYPTO_RS_NOT_AVAILABLE,
    CRYPTO_RS_OUTPERFORM,
    CRYPTO_RS_UNDERPERFORM,
    SIGNAL_SQUEEZE,
)
from crypto.panel import (
    apply_crypto_filters,
    build_crypto_panel,
    classify_relative_strength,
    compute_annualized_volatility,
    compute_return_pct,
    spec_for_timeframe,
)


def make_ohlcv(precios, volumen=1_000_000.0):
    """OHLCV mínimo pero completo a partir de una lista de cierres."""
    close = pd.Series(precios, dtype=float)
    idx = pd.date_range("2024-01-01", periods=len(close), freq="D")
    return pd.DataFrame(
        {
            "Open": close.shift(1).fillna(close.iloc[0]).to_numpy(),
            "High": (close * 1.01).to_numpy(),
            "Low": (close * 0.99).to_numpy(),
            "Close": close.to_numpy(),
            "Volume": np.full(len(close), volumen),
        },
        index=idx,
    )


class TestVariacionPorcentual:
    def test_calcula_la_variacion_de_la_ventana_pedida(self):
        # 10 barras atrás valía 100, ahora vale 110.
        close = pd.Series([100.0, *np.linspace(101, 110, 10)])
        assert compute_return_pct(close, 10) == pytest.approx(10.0)

    def test_sin_historial_suficiente_devuelve_nan(self):
        # Medir "30 días" sobre 6 barras daría un número que no es lo que dice
        # ser: preferimos NaN antes que un retorno de otra ventana.
        assert np.isnan(compute_return_pct(pd.Series([1.0] * 6), 30))

    def test_la_ventana_justa_alcanza(self):
        # Para 5 barras de retorno hacen falta 6 precios, no 5.
        assert np.isnan(compute_return_pct(pd.Series(np.arange(1, 6, dtype=float)), 5))
        assert not np.isnan(compute_return_pct(pd.Series(np.arange(1, 7, dtype=float)), 5))

    def test_precio_base_en_cero_devuelve_nan(self):
        assert np.isnan(compute_return_pct(pd.Series([0.0, 1.0, 2.0]), 2))

    def test_ignora_los_huecos_del_historial(self):
        close = pd.Series([100.0, np.nan, 110.0])
        assert compute_return_pct(close, 1) == pytest.approx(10.0)


class TestVolatilidadAnualizada:
    def test_serie_plana_no_tiene_volatilidad(self):
        assert compute_annualized_volatility(pd.Series([100.0] * 40), 30, 365) == pytest.approx(0.0)

    def test_anualiza_con_la_raiz_de_las_barras_por_anio(self):
        rng = np.random.default_rng(7)
        precios = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 200))))
        diaria = compute_annualized_volatility(precios, 30, 1)
        anual = compute_annualized_volatility(precios, 30, CRYPTO_BARS_PER_YEAR_DAILY)
        assert anual == pytest.approx(diaria * np.sqrt(CRYPTO_BARS_PER_YEAR_DAILY))

    def test_sin_historial_suficiente_devuelve_nan(self):
        assert np.isnan(compute_annualized_volatility(pd.Series([100.0] * 10), 30, 365))

    def test_una_cripto_volatil_puntua_mas_alto_que_una_tranquila(self):
        rng = np.random.default_rng(11)
        tranquila = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.005, 100))))
        volatil = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.08, 100))))
        assert compute_annualized_volatility(volatil, 30, 365) > compute_annualized_volatility(
            tranquila, 30, 365
        )


class TestFuerzaRelativaContraBitcoin:
    def test_exceso_claramente_positivo_supera_a_btc(self):
        assert classify_relative_strength(CRYPTO_RS_NEUTRAL_BAND_PP + 5) == CRYPTO_RS_OUTPERFORM

    def test_exceso_claramente_negativo_queda_rezagado(self):
        assert classify_relative_strength(-CRYPTO_RS_NEUTRAL_BAND_PP - 5) == CRYPTO_RS_UNDERPERFORM

    @pytest.mark.parametrize("exceso", [0.0, 1.0, -1.0, CRYPTO_RS_NEUTRAL_BAND_PP])
    def test_dentro_de_la_banda_muerta_esta_en_linea(self, exceso):
        # Dos puntos de diferencia en un mes, sobre un activo que se mueve 5%
        # por día, son ruido y no una ventaja.
        assert classify_relative_strength(exceso) == CRYPTO_RS_INLINE

    @pytest.mark.parametrize("valor", [np.nan, None, np.inf])
    def test_sin_dato_no_inventa_una_etiqueta(self, valor):
        assert classify_relative_strength(valor) == CRYPTO_RS_NOT_AVAILABLE


class TestCalendarioDeMercadoAbiertoTodoElAnio:
    def test_el_maximo_anual_diario_mide_365_barras(self):
        assert spec_for_timeframe("1d").ventana_52w == CRYPTO_52W_WINDOW_DAILY == 365

    def test_el_maximo_anual_semanal_mide_52_barras(self):
        assert spec_for_timeframe("1wk").ventana_52w == CRYPTO_52W_WINDOW_WEEKLY == 52

    def test_temporalidad_desconocida_cae_en_diario(self):
        assert spec_for_timeframe("1h").interval == "1d"

    def test_un_maximo_de_hace_300_dias_sigue_contando(self):
        # Regresión del punto que motiva parametrizar la ventana: con las 252
        # ruedas de una acción, un pico de hace 300 días quedaría fuera de la
        # ventana y el precio actual parecería estar en máximos.
        precios = [100.0] * 50 + [500.0] + [100.0] * 299
        df = build_crypto_panel({"X-USD": make_ohlcv(precios)}, timeframe="1d")
        # El pico está 300 barras atrás: dentro de 365, fuera de 252.
        assert df.loc[0, "Dif. % Máx 52S"] == pytest.approx(-80.0, abs=1.0)


class TestArmadoDelCuadro:
    @pytest.fixture
    def panel(self):
        rng = np.random.default_rng(42)
        btc = make_ohlcv(100 * np.exp(np.cumsum(rng.normal(0.002, 0.02, 400))))
        eth = make_ohlcv(50 * np.exp(np.cumsum(rng.normal(0.001, 0.03, 400))))
        return build_crypto_panel(
            {"BTC-USD": btc, "ETH-USD": eth},
            benchmark_history=btc,
            timeframe="1d",
        )

    def test_una_fila_por_cripto(self, panel):
        assert len(panel) == 2

    def test_resuelve_nombre_y_categoria_desde_el_catalogo(self, panel):
        fila = panel[panel["Ticker"] == "ETH-USD"].iloc[0]
        assert fila["Cripto"] == "ETH"
        assert fila["Nombre"] == "Ethereum"

    def test_bitcoin_no_puede_superarse_a_si_mismo(self, panel):
        fila = panel[panel["Ticker"] == "BTC-USD"].iloc[0]
        assert fila["Exceso vs BTC (pp)"] == pytest.approx(0.0)
        assert fila["vs BTC"] == CRYPTO_RS_INLINE

    def test_las_columnas_estables_acompanan_a_las_de_mostrar(self, panel):
        # El cuadro duplica columnas a propósito: las de castellano cambian de
        # título con la temporalidad, las de mayúsculas no. Si se desincronizan,
        # los filtros y los KPIs leen otra cosa que la tabla.
        fila = panel.iloc[0]
        assert fila["RSI_VAL"] == pytest.approx(fila["RSI (14) (Día)"], nan_ok=True)
        assert fila["DIST_52W_HIGH_PCT"] == pytest.approx(fila["Dif. % Máx 52S"], nan_ok=True)

    def test_los_titulos_siguen_a_la_temporalidad(self):
        df_semanal = build_crypto_panel({"BTC-USD": make_ohlcv([100.0] * 300)}, timeframe="1wk")
        assert "RSI (14) (Sem)" in df_semanal.columns
        assert "Var. 13s (%)" in df_semanal.columns

    def test_una_cripto_fuera_del_catalogo_conserva_su_precio(self):
        df = build_crypto_panel({"RARO-USD": make_ohlcv([10.0, 11.0, 12.0])})
        assert df.loc[0, "Cripto"] == "RARO-USD"
        assert df.loc[0, "Categoría"] == "Sin catalogar"
        assert df.loc[0, "Precio (USD)"] == pytest.approx(12.0)

    def test_sin_benchmark_la_fuerza_relativa_queda_sin_dato(self):
        df = build_crypto_panel({"ETH-USD": make_ohlcv(list(np.linspace(100, 200, 300)))})
        assert np.isnan(df.loc[0, "Exceso vs BTC (pp)"])
        assert df.loc[0, "vs BTC"] == CRYPTO_RS_NOT_AVAILABLE

    def test_un_historial_vacio_no_rompe_el_cuadro(self):
        df = build_crypto_panel({"ETH-USD": pd.DataFrame()})
        assert len(df) == 1
        assert np.isnan(df.loc[0, "Precio (USD)"])

    def test_sin_criptos_devuelve_un_cuadro_vacio(self):
        assert build_crypto_panel({}).empty


class TestFiltrosDelCuadro:
    @pytest.fixture
    def df(self):
        return pd.DataFrame([
            {"Semáforo": SIGNAL_SQUEEZE, "vs BTC": CRYPTO_RS_OUTPERFORM,
             "DIFF_SMA_200_VAL": 5.0, "RSI_VAL": 40.0},
            {"Semáforo": "🟡 NEUTRAL", "vs BTC": CRYPTO_RS_UNDERPERFORM,
             "DIFF_SMA_200_VAL": -8.0, "RSI_VAL": 75.0},
            {"Semáforo": "🟡 NEUTRAL", "vs BTC": CRYPTO_RS_NOT_AVAILABLE,
             "DIFF_SMA_200_VAL": np.nan, "RSI_VAL": np.nan},
        ])

    def _filtrar(self, df, **kwargs):
        opciones = dict(
            signal_filter=CRYPTO_FILTER_SIGNAL_ALL,
            rs_filter=CRYPTO_FILTER_RS_ALL,
            trend_filter=CRYPTO_FILTER_TREND_ALL,
        )
        opciones.update(kwargs)
        return apply_crypto_filters(df, **opciones)

    def test_sin_filtros_no_recorta_nada(self, df):
        assert len(self._filtrar(df)) == 3

    def test_filtra_por_semaforo(self, df):
        assert len(self._filtrar(df, signal_filter=CRYPTO_FILTER_SIGNAL_SQUEEZE)) == 1

    def test_filtra_por_fuerza_relativa(self, df):
        assert len(self._filtrar(df, rs_filter=CRYPTO_FILTER_RS_OUTPERFORM)) == 1
        assert len(self._filtrar(df, rs_filter=CRYPTO_FILTER_RS_UNDERPERFORM)) == 1

    def test_pedir_una_condicion_descarta_las_filas_sin_dato(self, df):
        # La fila sin fuerza relativa no puede colarse en "las que superan a
        # BTC": no se sabe si la supera.
        filtrado = self._filtrar(df, rs_filter=CRYPTO_FILTER_RS_OUTPERFORM)
        assert CRYPTO_RS_NOT_AVAILABLE not in set(filtrado["vs BTC"])

    def test_filtra_por_tendencia(self, df):
        assert len(self._filtrar(df, trend_filter=CRYPTO_FILTER_TREND_BULLISH)) == 1
        assert len(self._filtrar(df, trend_filter=CRYPTO_FILTER_TREND_BEARISH)) == 1

    def test_el_rango_de_rsi_no_esconde_las_criptos_sin_rsi(self, df):
        # Un RSI en NaN es falta de historial, no un valor fuera de rango:
        # ocultarlas haría desaparecer del cuadro monedas recién listadas.
        filtrado = self._filtrar(df, rsi_range=(0.0, 50.0))
        assert len(filtrado) == 2

    def test_un_cuadro_vacio_sobrevive_a_los_filtros(self):
        assert self._filtrar(pd.DataFrame()).empty


class TestFormatoDePrecio:
    @pytest.mark.parametrize("valor,esperado", [
        (75654.96, "$75,655"),
        (121.4, "$121.40"),
        (0.17611, "$0.1761"),
        (0.007062, "$0.007062"),
        (0.000005, "$0.00000500"),
    ])
    def test_usa_tantos_decimales_como_hagan_falta(self, valor, esperado):
        # Con dos decimales fijos, media tabla mostraría "$0.00"; con ocho,
        # Bitcoin sería ilegible.
        assert format_crypto_price(valor) == esperado

    @pytest.mark.parametrize("valor", [None, np.nan, "no es un número"])
    def test_sin_precio_no_imprime_nan(self, valor):
        assert format_crypto_price(valor) == "N/A"

    @pytest.mark.parametrize("valor,esperado", [
        (2_400_000_000, "$2.4B"),
        (340_500_000, "$340.5M"),
        (12_300, "$12.3K"),
        (450, "$450"),
    ])
    def test_el_volumen_se_abrevia(self, valor, esperado):
        assert format_usd_compact(valor) == esperado

    def test_sin_volumen_no_imprime_nan(self):
        assert format_usd_compact(np.nan) == "N/A"

    def test_los_montos_enormes_se_abrevian_en_billones(self):
        # La capitalización del mercado cripto completo pasa el billón de
        # dólares: sin este tramo se mostraba como "$2,939.5B".
        assert format_usd_compact(2_939_500_000_000) == "$2.94T"

    def test_los_meses_salen_en_castellano(self):
        # Con strftime, el idioma dependería de cómo esté configurada la
        # máquina donde corre la app.
        assert format_month_year(pd.Timestamp("2025-05-14")) == "may 2025"
        assert format_month_year(None) == "N/A"
