"""
Tests de la corrección de splits no ajustados (`merval/splits.py`).

Lo delicado acá es el falso positivo: una caída real del 50% **no** se puede
confundir con un split de dos a uno, porque "corregirla" borraría la caída. Por
eso la mitad de estos tests son casos que no tienen que detectarse.

El caso real que motivó el módulo: MIRG.BA pasó de 16.350 a 1.640 pesos el
2026-08-03, y Yahoo lo publica así incluso con `auto_adjust` activado.
"""

import numpy as np
import pandas as pd
import pytest

from merval.splits import adjust_for_splits, detect_unadjusted_splits

FECHAS = pd.bdate_range("2026-01-05", periods=20)


def _ohlcv(cierres, fechas=FECHAS):
    cierres = pd.Series(cierres, index=fechas[: len(cierres)], dtype=float)
    return pd.DataFrame({
        "Open": cierres,
        "High": cierres * 1.01,
        "Low": cierres * 0.99,
        "Close": cierres,
        "Volume": np.full(len(cierres), 1_000, dtype="int64"),
    })


def _con_split(factor, n=20, precio=1000.0, posicion=10):
    """Serie plana que se divide por `factor` a partir de `posicion`."""
    cierres = [precio] * posicion + [precio / factor] * (n - posicion)
    return _ohlcv(cierres)


class TestDeteccion:
    @pytest.mark.parametrize("factor", [2, 3, 5, 10, 100])
    def test_detecta_los_factores_habituales(self, factor):
        eventos = detect_unadjusted_splits(_con_split(factor)["Close"])

        assert len(eventos) == 1
        assert eventos[0].factor == pytest.approx(factor)

    def test_detecta_un_split_inverso(self):
        """El precio se multiplica: diez acciones viejas pasan a ser una."""
        cierres = [100.0] * 10 + [1000.0] * 10
        eventos = detect_unadjusted_splits(_ohlcv(cierres)["Close"])

        assert len(eventos) == 1
        assert eventos[0].factor == pytest.approx(0.1)

    def test_el_caso_real_de_mirgor(self):
        cierres = [16675.0, 16350.0] + [1640.0, 1640.0, 1620.0]
        eventos = detect_unadjusted_splits(_ohlcv(cierres)["Close"])

        assert len(eventos) == 1
        assert eventos[0].factor == pytest.approx(10.0)
        assert "split 10×1" in str(eventos[0])


class TestLoQueNoEsUnSplit:
    def test_una_caida_grande_pero_no_de_factor_simple_no_se_toca(self):
        """Caída del 43%: fea, real, y no es ningún split plausible."""
        cierres = [1000.0] * 10 + [570.0] * 10
        assert detect_unadjusted_splits(_ohlcv(cierres)["Close"]) == []

    def test_la_volatilidad_normal_no_dispara(self):
        rng = np.random.default_rng(11)
        cierres = 1000.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 20)))
        assert detect_unadjusted_splits(_ohlcv(cierres)["Close"]) == []

    def test_un_salto_chico_no_alcanza(self):
        """Nadie parte una acción en 1,1: por debajo del mínimo no se mira."""
        cierres = [1000.0] * 10 + [900.0] * 10
        assert detect_unadjusted_splits(_ohlcv(cierres)["Close"]) == []

    def test_series_demasiado_cortas_o_vacias(self):
        assert detect_unadjusted_splits(pd.Series(dtype=float)) == []
        assert detect_unadjusted_splits(pd.Series([100.0, 10.0])) == []


class TestCorreccion:
    def test_la_serie_queda_continua(self):
        corregido, eventos = adjust_for_splits(_con_split(10))
        cierres = corregido["Close"]

        assert len(eventos) == 1
        # Antes del split: 1000 / 10 = 100, igual que después.
        assert cierres.nunique() == 1
        assert cierres.iloc[0] == pytest.approx(100.0)

    def test_el_ultimo_precio_no_cambia(self):
        """
        Se corrige hacia atrás: el precio de hoy es el que se ve en pantalla y
        no puede moverse porque hubo un split hace tres meses.
        """
        original = _con_split(10)
        corregido, _ = adjust_for_splits(original)

        assert corregido["Close"].iloc[-1] == pytest.approx(original["Close"].iloc[-1])

    def test_corrige_todas_las_columnas_de_precio(self):
        corregido, _ = adjust_for_splits(_con_split(10))

        assert corregido["High"].nunique() == 1
        assert corregido["Low"].nunique() == 1
        assert corregido["Open"].nunique() == 1

    def test_el_volumen_se_ajusta_en_sentido_contrario(self):
        """Las mismas operaciones equivalen a diez veces más acciones nuevas."""
        corregido, _ = adjust_for_splits(_con_split(10))
        volumen = corregido["Volume"]

        assert volumen.iloc[0] == pytest.approx(10_000.0)
        assert volumen.iloc[-1] == pytest.approx(1_000.0)

    def test_dos_splits_se_acumulan(self):
        cierres = [10_000.0] * 5 + [1_000.0] * 5 + [200.0] * 5
        corregido, eventos = adjust_for_splits(_ohlcv(cierres))

        assert len(eventos) == 2
        assert corregido["Close"].nunique() == 1
        assert corregido["Close"].iloc[0] == pytest.approx(200.0)

    def test_una_serie_sin_splits_vuelve_igual(self):
        original = _ohlcv([100.0, 101.0, 99.0, 102.0, 103.0])
        corregido, eventos = adjust_for_splits(original)

        assert eventos == []
        pd.testing.assert_frame_equal(corregido, original)

    def test_sin_datos_no_estalla(self):
        corregido, eventos = adjust_for_splits(pd.DataFrame())
        assert corregido.empty and eventos == []

        corregido, eventos = adjust_for_splits(None)
        assert corregido.empty and eventos == []
