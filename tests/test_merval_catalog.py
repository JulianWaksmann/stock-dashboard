"""
Tests del universo argentino (`merval/catalog.py`).

El catálogo es dato escrito a mano, así que lo que se fija son las propiedades
que lo vuelven usable: que los tickers tengan el sufijo con el que los publica
el proveedor, que no haya duplicados y que todo par con ADR traiga su ratio
—sin ratio, ese par no puede aportar al dólar implícito—.
"""

from merval.catalog import (
    MERVAL_UNIVERSE,
    adr_pairs,
    adr_tickers,
    local_tickers,
    stock_for,
)


class TestUniverso:
    def test_los_tickers_locales_llevan_sufijo_de_buenos_aires(self):
        assert all(a.ticker.endswith(".BA") for a in MERVAL_UNIVERSE)

    def test_no_hay_tickers_repetidos(self):
        tickers = local_tickers()
        assert len(tickers) == len(set(tickers))

    def test_no_hay_adr_repetidos(self):
        adrs = adr_tickers()
        assert len(adrs) == len(set(adrs))

    def test_todas_tienen_nombre_y_sector(self):
        assert all(a.nombre and a.sector for a in MERVAL_UNIVERSE)

    def test_hay_acciones_con_adr_y_sin_adr(self):
        """
        Las dos clases importan: las que tienen ADR forman el dólar implícito y
        las que no son las que justifican tenerlo.
        """
        con = [a for a in MERVAL_UNIVERSE if a.tiene_adr]
        sin = [a for a in MERVAL_UNIVERSE if not a.tiene_adr]

        assert len(con) >= 5
        assert len(sin) >= 1


class TestParesConAdr:
    def test_todo_par_con_adr_trae_su_ratio(self):
        for activo in adr_pairs():
            assert activo.adr, activo.ticker
            assert activo.adr_ratio and activo.adr_ratio > 0, activo.ticker

    def test_tiene_adr_exige_las_dos_cosas(self):
        from merval.catalog import MervalStock

        assert not MervalStock("X.BA", "X", "S").tiene_adr
        assert not MervalStock("X.BA", "X", "S", "X").tiene_adr
        assert MervalStock("X.BA", "X", "S", "X", 10).tiene_adr

    def test_los_ratios_sin_verificar_estan_declarados_como_tales(self):
        """
        Un ratio cambia con cada split o reestructuración: la marca dice contra
        qué se comprobó, y no haberlo comprobado tiene que verse.
        """
        for activo in adr_pairs():
            assert isinstance(activo.ratio_verificado, bool)


class TestBusqueda:
    def test_encuentra_por_ticker_sin_importar_el_caso(self):
        assert stock_for("ggal.ba") is not None
        assert stock_for("GGAL.BA").nombre

    def test_un_ticker_ajeno_devuelve_none(self):
        assert stock_for("AAPL") is None
        assert stock_for("") is None
