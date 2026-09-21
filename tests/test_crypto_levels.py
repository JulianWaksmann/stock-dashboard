"""
Tests de soportes y resistencias (`crypto/levels.py`).

Las series son construidas a mano con los giros en posiciones conocidas, así
que el nivel esperado se puede escribir en el test sin recalcularlo.
"""

import numpy as np
import pandas as pd
import pytest

from constants import CRYPTO_LEVEL_STRONG_TOUCHES
from crypto.levels import (
    PriceLevel,
    cluster_levels,
    detect_support_resistance,
    find_pivots,
    scale_params,
)


def ohlc(precios):
    """OHLCV donde el máximo y el mínimo de cada barra son el cierre."""
    close = pd.Series([float(p) for p in precios])
    idx = pd.date_range("2024-01-01", periods=len(close), freq="D")
    return pd.DataFrame(
        {"Open": close.to_numpy(), "High": close.to_numpy(),
         "Low": close.to_numpy(), "Close": close.to_numpy(), "Volume": 1.0},
        index=idx,
    )


def diente_de_sierra(pico, valle, dientes, largo_lado=12):
    """Precio que sube y baja entre dos valores fijos, con giros limpios."""
    serie = []
    for _ in range(dientes):
        serie += list(np.linspace(valle, pico, largo_lado))
        serie += list(np.linspace(pico, valle, largo_lado))
    return serie


class TestDeteccionDePivotes:
    def test_encuentra_el_maximo_local(self):
        maximos, _ = find_pivots(ohlc([1, 2, 3, 10, 3, 2, 1]), lookaround=3)
        assert [round(p) for _, p in maximos] == [10]

    def test_encuentra_el_minimo_local(self):
        _, minimos = find_pivots(ohlc([10, 8, 5, 1, 5, 8, 10]), lookaround=3)
        assert [round(p) for _, p in minimos] == [1]

    def test_solo_las_barras_con_entorno_completo_pueden_ser_pivote(self):
        # Las primeras y últimas `lookaround` barras no tienen un costado
        # contra el cual confirmarse, así que no producen pivotes aunque sean
        # el valor más extremo de la serie.
        _, minimos = find_pivots(ohlc([1, 2, 3, 10, 3, 2, 1]), lookaround=3)
        assert minimos == []

    def test_una_serie_corta_no_produce_pivotes(self):
        # Sin barras a los costados no hay nada que confirme un giro.
        maximos, minimos = find_pivots(ohlc([1, 2, 3]), lookaround=10)
        assert maximos == [] and minimos == []

    def test_las_ultimas_barras_no_pueden_ser_pivote(self):
        # Un techo no es un techo hasta que el precio se aleja de él.
        precios = [1] * 20 + [50]
        maximos, _ = find_pivots(ohlc(precios), lookaround=5)
        assert all(round(p) != 50 for _, p in maximos)

    def test_una_meseta_plana_es_un_solo_pivote(self):
        # Regresión: el proveedor redondea el precio de las monedas muy chicas
        # a un decimal significativo, así que aparecen mesetas perfectamente
        # planas de decenas de barras. Sin colapsarlas, cada barra de la
        # meseta contaba como un giro y el nivel salía con 117 "toques".
        precios = [1] * 15 + [10] * 30 + [1] * 15
        maximos, _ = find_pivots(ohlc(precios), lookaround=5)
        en_el_techo = [p for _, p in maximos if p == 10]
        assert len(en_el_techo) == 1

    def test_dos_giros_separados_siguen_siendo_dos(self):
        # El colapso junta el mismo giro, no giros distintos a la misma altura.
        precios = [1] * 12 + [10] * 3 + [1] * 30 + [10] * 3 + [1] * 12
        maximos, _ = find_pivots(ohlc(precios), lookaround=5)
        en_el_techo = [p for _, p in maximos if p == 10]
        assert len(en_el_techo) == 2

    def test_un_dataframe_vacio_no_rompe(self):
        assert find_pivots(pd.DataFrame()) == ([], [])


class TestAgrupamientoDeNiveles:
    def test_dos_pivotes_a_la_misma_altura_son_un_solo_nivel(self):
        niveles = cluster_levels([(None, 100.0), (None, 101.0)], cluster_pct=2.5)
        assert len(niveles) == 1
        assert niveles[0].touches == 2
        assert niveles[0].price == pytest.approx(100.5)

    def test_dos_pivotes_lejanos_son_niveles_distintos(self):
        niveles = cluster_levels([(None, 100.0), (None, 150.0)], cluster_pct=2.5)
        assert len(niveles) == 2

    def test_la_cercania_se_mide_en_porcentaje_y_no_en_dolares(self):
        # Un dólar de diferencia es el mismo nivel en Bitcoin y dos niveles
        # distintos en una moneda que cotiza a tres dólares.
        caros = cluster_levels([(None, 80000.0), (None, 80001.0)], cluster_pct=1.0)
        baratos = cluster_levels([(None, 3.0), (None, 4.0)], cluster_pct=1.0)
        assert len(caros) == 1
        assert len(baratos) == 2

    def test_un_nivel_muy_visitado_se_marca_como_fuerte(self):
        niveles = cluster_levels([(None, 100.0)] * CRYPTO_LEVEL_STRONG_TOUCHES, cluster_pct=2.5)
        assert niveles[0].is_strong

    def test_un_nivel_tocado_una_vez_no_es_fuerte(self):
        assert not PriceLevel(price=100.0, touches=1, last_touch=None).is_strong

    def test_sin_pivotes_no_hay_niveles(self):
        assert cluster_levels([]) == []


class TestSoportesYResistencias:
    @pytest.fixture
    def sierra(self):
        # Rebota tres veces entre 100 y 200, y termina en el medio.
        return ohlc(diente_de_sierra(pico=200, valle=100, dientes=3) + [150] * 12)

    def test_separa_lo_que_esta_arriba_de_lo_que_esta_abajo(self, sierra):
        soportes, resistencias = detect_support_resistance(sierra, current_price=150.0)
        assert all(n.price < 150 for n in soportes)
        assert all(n.price > 150 for n in resistencias)

    def test_encuentra_el_techo_y_el_piso_del_rango(self, sierra):
        soportes, resistencias = detect_support_resistance(sierra, current_price=150.0)
        assert resistencias[0].price == pytest.approx(200, abs=5)
        assert soportes[0].price == pytest.approx(100, abs=5)

    def test_el_nivel_repetido_acumula_toques(self, sierra):
        _, resistencias = detect_support_resistance(sierra, current_price=150.0)
        assert resistencias[0].touches >= 3
        assert resistencias[0].is_strong

    def test_devuelve_como_mucho_los_pedidos_por_lado(self):
        rng = np.random.default_rng(5)
        ruidoso = ohlc(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 600))))
        soportes, resistencias = detect_support_resistance(ruidoso, per_side=3)
        assert len(soportes) <= 3 and len(resistencias) <= 3

    def test_ordena_del_mas_cercano_al_mas_lejano(self):
        rng = np.random.default_rng(9)
        ruidoso = ohlc(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 600))))
        soportes, resistencias = detect_support_resistance(ruidoso)
        precio = float(ruidoso["Close"].iloc[-1])
        assert [precio - n.price for n in soportes] == sorted(precio - n.price for n in soportes)
        assert [n.price - precio for n in resistencias] == sorted(n.price - precio for n in resistencias)

    def test_toma_el_ultimo_cierre_si_no_se_pasa_precio(self, sierra):
        sin_precio = detect_support_resistance(sierra)
        con_precio = detect_support_resistance(sierra, current_price=float(sierra["Close"].iloc[-1]))
        assert [n.price for n in sin_precio[0]] == [n.price for n in con_precio[0]]

    def test_un_historial_vacio_no_rompe(self):
        assert detect_support_resistance(pd.DataFrame()) == ([], [])

    def test_un_precio_invalido_no_rompe(self, sierra):
        assert detect_support_resistance(sierra, current_price=float("nan")) == ([], [])


class TestEscalaDelGrafico:
    def test_cada_escala_trae_sus_propios_parametros(self):
        # El entorno del pivote no puede ser el mismo en las tres: 10 barras
        # son dos semanas en diario y casi un año en mensual.
        from constants import (
            CRYPTO_CHART_SCALE_DAILY,
            CRYPTO_CHART_SCALE_MONTHLY,
            CRYPTO_CHART_SCALE_WEEKLY,
        )
        mensual = scale_params(CRYPTO_CHART_SCALE_MONTHLY)
        semanal = scale_params(CRYPTO_CHART_SCALE_WEEKLY)
        diaria = scale_params(CRYPTO_CHART_SCALE_DAILY)

        assert (mensual.interval, semanal.interval, diaria.interval) == ("1mo", "1wk", "1d")
        assert mensual.lookaround < semanal.lookaround < diaria.lookaround
        assert mensual.bars < diaria.bars  # menos velas, pero muchos más años de historia
        # Agrupar con la tolerancia diaria partiría en dos el mismo techo
        # cuando se lo mira en meses.
        assert mensual.cluster_pct > diaria.cluster_pct

    def test_una_escala_desconocida_cae_en_mensual(self):
        from constants import CRYPTO_CHART_SCALE_MONTHLY
        assert scale_params("cualquier cosa") == scale_params(CRYPTO_CHART_SCALE_MONTHLY)

    def test_la_tolerancia_mensual_une_giros_que_en_diario_quedan_separados(self):
        # Es el efecto que se busca al subir la escala: dos giros a 4% de
        # distancia son dos niveles distintos mirando el día a día, y el
        # mismo techo mirado en meses.
        from constants import CRYPTO_CHART_SCALE_DAILY, CRYPTO_CHART_SCALE_MONTHLY

        pivotes = [(None, 100.0), (None, 104.0)]
        diaria = scale_params(CRYPTO_CHART_SCALE_DAILY).cluster_pct
        mensual = scale_params(CRYPTO_CHART_SCALE_MONTHLY).cluster_pct
        assert len(cluster_levels(pivotes, cluster_pct=diaria)) == 2
        assert len(cluster_levels(pivotes, cluster_pct=mensual)) == 1
