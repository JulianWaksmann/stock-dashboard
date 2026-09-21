"""
Tests de divergencias (`crypto/divergences.py`).

El precio y el oscilador se construyen a mano para que la divergencia esté
donde el test dice que está: es un detector fácil de "arreglar" hasta que
encuentra divergencias en cualquier lado, así que importa tanto lo que marca
como lo que **no** marca.
"""

import numpy as np
import pandas as pd
import pytest

from constants import (
    CRYPTO_DIVERGENCE_BEARISH,
    CRYPTO_DIVERGENCE_BULLISH,
    CRYPTO_DIVERGENCE_MIN_RSI_GAP,
)
from crypto.divergences import detect_divergences
from crypto.levels import find_pivots


def serie_con_dos_giros(primero, segundo, hacia_arriba=True, plano=10):
    """Precio con dos giros claros (dos máximos o dos mínimos) y nada más."""
    base = 100.0
    pico_1, pico_2 = (primero, segundo)
    if hacia_arriba:
        tramo = lambda p: list(np.linspace(base, p, 6)) + list(np.linspace(p, base, 6))  # noqa: E731
    else:
        tramo = lambda p: list(np.linspace(base, p, 6)) + list(np.linspace(p, base, 6))  # noqa: E731
    return [base] * plano + tramo(pico_1) + [base] * plano + tramo(pico_2) + [base] * plano


def ohlc(precios):
    close = pd.Series([float(p) for p in precios])
    idx = pd.date_range("2024-01-01", periods=len(close), freq="D")
    return pd.DataFrame(
        {"Open": close.to_numpy(), "High": close.to_numpy(),
         "Low": close.to_numpy(), "Close": close.to_numpy(), "Volume": 1.0},
        index=idx,
    )


def oscilador_en_giros(df, valor_primero, valor_segundo, en_maximos=True, lookaround=3):
    """
    Oscilador plano en 50, con un valor puesto en cada giro del precio.

    Se apoya en `find_pivots` —el mismo detector que usa la función bajo
    prueba— para que los valores caigan exactamente en las barras que se van
    a comparar, en vez de adivinar en qué posición quedó cada giro.
    """
    maximos, minimos = find_pivots(df, lookaround=lookaround)
    giros = maximos if en_maximos else minimos
    assert len(giros) >= 2, "la serie de prueba debería tener dos giros"

    osc = pd.Series(50.0, index=df.index)
    osc.loc[giros[0][0]] = valor_primero
    osc.loc[giros[1][0]] = valor_segundo
    return osc


class TestDivergenciaBajista:
    @pytest.fixture
    def precio(self):
        # Segundo máximo más alto que el primero.
        return ohlc(serie_con_dos_giros(150, 170))

    def test_la_marca_cuando_el_impulso_no_acompana(self, precio):
        # Precio: máximo más alto. RSI: máximo más bajo.
        osc = oscilador_en_giros(precio, 80.0, 65.0)
        divergencias = detect_divergences(precio, osc, lookaround=3)
        assert len(divergencias) == 1
        assert divergencias[0].kind == CRYPTO_DIVERGENCE_BEARISH
        assert divergencias[0].is_bearish

    def test_no_la_marca_cuando_el_impulso_acompana(self, precio):
        # Máximo más alto con RSI también más alto: eso es una tendencia
        # sana, no una divergencia.
        osc = oscilador_en_giros(precio, 65.0, 80.0)
        assert detect_divergences(precio, osc, lookaround=3) == []

    def test_una_diferencia_minima_de_rsi_no_alcanza(self, precio):
        # Sin este piso, medio punto de RSI ya dibujaría una divergencia.
        osc = oscilador_en_giros(precio, 80.0, 80.0 - CRYPTO_DIVERGENCE_MIN_RSI_GAP / 2)
        assert detect_divergences(precio, osc, lookaround=3) == []

    def test_dos_maximos_casi_iguales_no_son_divergencia(self):
        # Es un doble techo: el precio no hizo un máximo más alto.
        # Sin mesetas planas: en una serie plana toda barra es máximo local
        # y los giros comparados dejarían de ser los dos picos.
        precio = ohlc(
            list(np.linspace(80, 150, 8)) + list(np.linspace(150, 80, 8))
            + list(np.linspace(80, 150.2, 8)) + list(np.linspace(150.2, 80, 8))
        )
        osc = oscilador_en_giros(precio, 80.0, 60.0)
        bajistas = [d for d in detect_divergences(precio, osc, lookaround=3) if d.is_bearish]
        assert bajistas == []


class TestDivergenciaAlcista:
    def test_la_marca_cuando_la_baja_pierde_fuerza(self):
        # Precio: mínimo más bajo. RSI: mínimo más alto.
        # Los dos giros bajistas son los pisos de 60 y 40.
        precio = ohlc([100] * 6 + list(np.linspace(100, 60, 5)) + list(np.linspace(60, 100, 5))
                      + [100] * 6 + list(np.linspace(100, 40, 5)) + list(np.linspace(40, 100, 5))
                      + [100] * 6)
        osc = oscilador_en_giros(precio, 20.0, 35.0, en_maximos=False)
        divergencias = detect_divergences(precio, osc, lookaround=3)
        assert len(divergencias) == 1
        assert divergencias[0].kind == CRYPTO_DIVERGENCE_BULLISH
        assert not divergencias[0].is_bearish


class TestLimites:
    def test_dos_giros_muy_separados_no_se_comparan(self):
        # Dos máximos separados por años no son una divergencia, son dos
        # tramos distintos del mercado.
        precio = ohlc(serie_con_dos_giros(150, 170, plano=60))
        osc = oscilador_en_giros(precio, 80.0, 60.0)
        assert detect_divergences(precio, osc, lookaround=3, max_gap_bars=10) == []

    def test_devuelve_las_mas_recientes_primero(self):
        precio = ohlc(serie_con_dos_giros(150, 170) + serie_con_dos_giros(180, 200))
        osc = pd.Series(np.linspace(90, 50, len(precio)), index=precio.index)
        divergencias = detect_divergences(precio, osc, lookaround=3)
        fechas = [d.second_date for d in divergencias]
        assert fechas == sorted(fechas, reverse=True)

    def test_respeta_el_tope_de_cuantas_se_muestran(self):
        precio = ohlc(serie_con_dos_giros(150, 170) + serie_con_dos_giros(180, 200))
        osc = pd.Series(np.linspace(90, 50, len(precio)), index=precio.index)
        assert len(detect_divergences(precio, osc, lookaround=3, max_shown=1)) <= 1

    def test_sin_oscilador_no_hay_divergencias(self):
        precio = ohlc(serie_con_dos_giros(150, 170))
        assert detect_divergences(precio, pd.Series(dtype=float), lookaround=3) == []

    def test_un_historial_vacio_no_rompe(self):
        assert detect_divergences(pd.DataFrame(), pd.Series(dtype=float), lookaround=3) == []

    def test_un_oscilador_con_huecos_no_inventa_divergencias(self):
        precio = ohlc(serie_con_dos_giros(150, 170))
        osc = pd.Series(np.nan, index=precio.index)
        assert detect_divergences(precio, osc, lookaround=3) == []
