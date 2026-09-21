"""
Tests del catálogo de criptomonedas (`crypto/catalog.py`).

Verifican lo que puede romperse en silencio al editar la lista: un ticker
duplicado, un universo que queda vacío, o una stablecoin que se cuela.
"""

import pytest

from constants import (
    CRYPTO_BENCHMARK_TICKER,
    CRYPTO_UNIVERSE_DEFI,
    CRYPTO_UNIVERSE_LAYER1,
    CRYPTO_UNIVERSE_MEME,
    CRYPTO_UNIVERSE_OPTIONS,
    CRYPTO_UNIVERSE_TOP,
)
from crypto.catalog import (
    CRYPTO_UNIVERSE,
    assets_for_universe,
    find_asset,
    tickers_for_universe,
)


class TestIntegridadDelCatalogo:
    def test_no_hay_tickers_repetidos(self):
        tickers = [a.ticker for a in CRYPTO_UNIVERSE]
        assert len(tickers) == len(set(tickers))

    def test_no_hay_simbolos_repetidos(self):
        # Dos filas con el mismo símbolo se verían como la misma moneda
        # duplicada en el cuadro, aunque los tickers de Yahoo difieran.
        simbolos = [a.simbolo for a in CRYPTO_UNIVERSE]
        assert len(simbolos) == len(set(simbolos))

    def test_todos_los_tickers_cotizan_contra_dolar(self):
        # El panel descuenta precios en dólares: un ticker en otra moneda
        # daría una fuerza relativa contra BTC sin sentido.
        assert all(a.ticker.endswith("-USD") for a in CRYPTO_UNIVERSE)

    def test_ningun_campo_viene_vacio(self):
        for activo in CRYPTO_UNIVERSE:
            assert activo.ticker and activo.simbolo and activo.nombre and activo.categoria

    def test_bitcoin_esta_en_el_catalogo(self):
        # Es la referencia de la columna de fuerza relativa.
        assert find_asset(CRYPTO_BENCHMARK_TICKER) is not None

    @pytest.mark.parametrize("simbolo", ["USDT", "USDC", "DAI", "BUSD", "TUSD"])
    def test_las_stablecoins_quedan_afuera(self, simbolo):
        # Decisión documentada en el módulo: cotizan pegadas a un dólar por
        # diseño, así que su lectura técnica describe ruido de centésimas.
        assert simbolo not in {a.simbolo for a in CRYPTO_UNIVERSE}


class TestUniversos:
    @pytest.mark.parametrize("universe", CRYPTO_UNIVERSE_OPTIONS)
    def test_todo_universo_del_selector_devuelve_criptos(self, universe):
        # Si un universo queda vacío, la sección se dibuja en blanco y eso no
        # se distingue de un fallo de red.
        assert len(assets_for_universe(universe)) > 0

    @pytest.mark.parametrize("universe", CRYPTO_UNIVERSE_OPTIONS)
    def test_todo_universo_sale_del_catalogo(self, universe):
        del_catalogo = {a.ticker for a in CRYPTO_UNIVERSE}
        assert set(tickers_for_universe(universe)) <= del_catalogo

    def test_universo_desconocido_cae_en_el_de_omision(self):
        # Un texto que no coincide con ningún literal del selector no debe
        # devolver una lista vacía.
        assert assets_for_universe("cualquier cosa") == assets_for_universe(CRYPTO_UNIVERSE_TOP)

    def test_cada_grupo_devuelve_solo_su_categoria(self):
        for universe in (CRYPTO_UNIVERSE_LAYER1, CRYPTO_UNIVERSE_DEFI, CRYPTO_UNIVERSE_MEME):
            categorias = {a.categoria for a in assets_for_universe(universe)}
            assert len(categorias) == 1

    def test_el_universo_por_omision_incluye_bitcoin(self):
        assert CRYPTO_BENCHMARK_TICKER in tickers_for_universe(CRYPTO_UNIVERSE_TOP)


class TestBusquedaPorTicker:
    def test_encuentra_sin_importar_mayusculas_ni_espacios(self):
        assert find_asset("  btc-usd  ") is find_asset("BTC-USD")

    def test_ticker_inexistente_devuelve_none(self):
        assert find_asset("NOEXISTE-USD") is None
