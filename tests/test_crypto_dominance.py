"""
Tests de dominancia y rotación (`crypto/dominance.py`).

Series fijas, sin red: la reconstrucción de la dominancia es aritmética sobre
precios y ofertas, y es justo donde un error pasaría desapercibido porque el
número resultante siempre "parece" un porcentaje razonable.
"""

import numpy as np
import pandas as pd
import pytest

from constants import (
    CRYPTO_ALTSEASON_MIN_PCT,
    CRYPTO_DOMINANCE_BAND_PP,
    CRYPTO_ROTATION_STABLE,
    CRYPTO_ROTATION_TO_ALTS,
    CRYPTO_ROTATION_TO_BTC,
    CRYPTO_SEASON_ALTS,
    CRYPTO_SEASON_BTC,
    CRYPTO_SEASON_MIXED,
)
from crypto.dominance import (
    altseason_index,
    build_rotation_reading,
    classify_rotation,
    classify_season,
    dominance_change_pp,
    reconstruct_panel_dominance,
)


def hist(precios):
    """Historial mínimo con solo la columna que usa la reconstrucción."""
    idx = pd.date_range("2024-01-01", periods=len(precios), freq="D")
    return pd.DataFrame({"Close": [float(p) for p in precios]}, index=idx)


class TestReconstruccionDeLaDominancia:
    def test_reparte_segun_capitalizacion(self):
        # BTC: 100 x 3 = 300. ALT: 50 x 2 = 100. Dominancia = 300/400 = 75%.
        serie = reconstruct_panel_dominance(
            {"BTC-USD": hist([100] * 5), "ALT-USD": hist([50] * 5)},
            {"BTC-USD": 3.0, "ALT-USD": 2.0},
            "BTC-USD",
        )
        assert serie.iloc[-1] == pytest.approx(75.0)

    def test_sube_cuando_bitcoin_le_gana_al_resto(self):
        serie = reconstruct_panel_dominance(
            {"BTC-USD": hist([100, 120]), "ALT-USD": hist([100, 100])},
            {"BTC-USD": 1.0, "ALT-USD": 1.0},
            "BTC-USD",
        )
        assert serie.iloc[0] == pytest.approx(50.0)
        assert serie.iloc[-1] > serie.iloc[0]

    def test_las_monedas_sin_oferta_conocida_no_entran_al_total(self):
        # Una capitalización inventada movería el reparto sin que se note,
        # así que la moneda sin oferta se excluye.
        con_oferta = reconstruct_panel_dominance(
            {"BTC-USD": hist([100] * 3), "ALT-USD": hist([100] * 3)},
            {"BTC-USD": 1.0, "ALT-USD": 1.0},
            "BTC-USD",
        )
        sin_oferta = reconstruct_panel_dominance(
            {"BTC-USD": hist([100] * 3), "ALT-USD": hist([100] * 3), "RARA-USD": hist([100] * 3)},
            {"BTC-USD": 1.0, "ALT-USD": 1.0, "RARA-USD": None},
            "BTC-USD",
        )
        assert sin_oferta.iloc[-1] == pytest.approx(con_oferta.iloc[-1])

    def test_sin_la_oferta_de_bitcoin_no_hay_serie(self):
        serie = reconstruct_panel_dominance(
            {"BTC-USD": hist([100] * 3), "ALT-USD": hist([100] * 3)},
            {"BTC-USD": None, "ALT-USD": 1.0},
            "BTC-USD",
        )
        assert serie.empty

    def test_una_sola_moneda_no_define_un_reparto(self):
        # Con Bitcoin solo, la dominancia sería 100% siempre: un número cierto
        # y completamente inútil. Mejor no devolver serie.
        serie = reconstruct_panel_dominance(
            {"BTC-USD": hist([100] * 3)}, {"BTC-USD": 1.0}, "BTC-USD"
        )
        assert serie.empty

    def test_sin_bitcoin_no_hay_dominancia(self):
        serie = reconstruct_panel_dominance(
            {"ALT-USD": hist([100] * 3)}, {"ALT-USD": 1.0}, "BTC-USD"
        )
        assert serie.empty

    def test_la_dominancia_siempre_esta_entre_0_y_100(self):
        rng = np.random.default_rng(3)
        serie = reconstruct_panel_dominance(
            {
                "BTC-USD": hist(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 120)))),
                "ALT-USD": hist(10 * np.exp(np.cumsum(rng.normal(0, 0.06, 120)))),
            },
            {"BTC-USD": 19.0, "ALT-USD": 1000.0},
            "BTC-USD",
        )
        assert serie.between(0, 100).all()

    def test_corta_la_serie_en_la_ventana_pedida(self):
        # El supuesto de oferta constante no aguanta varios años.
        serie = reconstruct_panel_dominance(
            {"BTC-USD": hist([100] * 500), "ALT-USD": hist([100] * 500)},
            {"BTC-USD": 1.0, "ALT-USD": 1.0},
            "BTC-USD",
            max_bars=365,
        )
        assert len(serie) == 365


class TestCambioDeDominancia:
    def test_mide_la_diferencia_en_puntos_porcentuales(self):
        serie = pd.Series([50.0, 51.0, 52.0, 53.0])
        assert dominance_change_pp(serie, 3) == pytest.approx(3.0)

    def test_sin_historial_suficiente_devuelve_nan(self):
        assert np.isnan(dominance_change_pp(pd.Series([50.0, 51.0]), 30))

    def test_serie_vacia_devuelve_nan(self):
        assert np.isnan(dominance_change_pp(pd.Series(dtype=float), 5))


class TestClasificacionDeRotacion:
    def test_suba_clara_es_rotacion_hacia_bitcoin(self):
        assert classify_rotation(CRYPTO_DOMINANCE_BAND_PP + 1) == CRYPTO_ROTATION_TO_BTC

    def test_baja_clara_es_rotacion_hacia_altcoins(self):
        assert classify_rotation(-CRYPTO_DOMINANCE_BAND_PP - 1) == CRYPTO_ROTATION_TO_ALTS

    @pytest.mark.parametrize("cambio", [0.0, 0.3, -0.3, np.nan, None])
    def test_dentro_de_la_banda_no_hay_rotacion(self, cambio):
        # La serie está reconstruida con oferta constante: décimas de punto
        # no son señal de nada.
        assert classify_rotation(cambio) == CRYPTO_ROTATION_STABLE


class TestTermometroDeTemporada:
    def test_cuenta_las_que_le_ganan_a_bitcoin(self):
        # Cuatro monedas, dos con ventaja clara (la de +1 cae en la banda muerta).
        assert altseason_index(pd.Series([10.0, 20.0, 1.0, -5.0])) == pytest.approx(50.0)

    def test_bitcoin_no_se_cuenta_a_si_mismo(self):
        # Su exceso es cero por construcción; sumarlo al denominador haría
        # que el índice nunca llegue al tope.
        assert altseason_index(pd.Series([0.0, 10.0, 20.0])) == pytest.approx(100.0)

    def test_sin_datos_devuelve_nan(self):
        assert np.isnan(altseason_index(pd.Series([np.nan, np.nan])))

    def test_indice_alto_es_temporada_de_altcoins(self):
        assert classify_season(CRYPTO_ALTSEASON_MIN_PCT) == CRYPTO_SEASON_ALTS

    def test_indice_bajo_es_temporada_de_bitcoin(self):
        assert classify_season(10.0) == CRYPTO_SEASON_BTC

    def test_el_medio_es_mercado_mixto(self):
        # Que cinco de veinte le ganen a Bitcoin no es una temporada.
        assert classify_season(50.0) == CRYPTO_SEASON_MIXED


class TestLecturaCompleta:
    def test_arma_las_dos_mediciones_juntas(self):
        lectura = build_rotation_reading(
            history={"BTC-USD": hist([100, 110, 120]), "ALT-USD": hist([100, 100, 100])},
            supplies={"BTC-USD": 1.0, "ALT-USD": 1.0},
            excess_vs_btc=pd.Series([0.0, -10.0, -20.0]),
            benchmark_ticker="BTC-USD",
            window_bars=2,
        )
        assert lectura.rotation_label == CRYPTO_ROTATION_TO_BTC
        assert lectura.season_label == CRYPTO_SEASON_BTC
        assert lectura.dominance_change_pp > 0

    def test_sin_dominancia_global_la_lectura_sigue_siendo_valida(self):
        # La fuente externa puede no responder; lo que se calcula en casa no
        # depende de ella.
        lectura = build_rotation_reading(
            history={"BTC-USD": hist([100] * 5), "ALT-USD": hist([100] * 5)},
            supplies={"BTC-USD": 1.0, "ALT-USD": 1.0},
            excess_vs_btc=pd.Series([0.0, 5.0]),
            benchmark_ticker="BTC-USD",
            window_bars=2,
            global_error="La fuente no respondió.",
        )
        assert lectura.global_btc_dominance_pct is None
        assert not lectura.dominance_series.empty
        assert lectura.global_error


class TestHistorialesDeDistintoOrigen:
    def test_mezclar_fechas_con_y_sin_zona_horaria_no_rompe(self):
        # Los dos caminos de descarga (bloque masivo y reintento individual)
        # devuelven el índice con distinta convención de zona horaria. Alinear
        # uno contra otro fallaba con "Cannot join tz-naive with tz-aware", y
        # solo se manifestaba los días en que alguna moneda caía al reintento.
        sin_zona = hist([100] * 5)
        con_zona = hist([50] * 5)
        con_zona.index = con_zona.index.tz_localize("UTC")

        serie = reconstruct_panel_dominance(
            {"BTC-USD": sin_zona, "ALT-USD": con_zona},
            {"BTC-USD": 3.0, "ALT-USD": 2.0},
            "BTC-USD",
        )
        assert serie.iloc[-1] == pytest.approx(75.0)
