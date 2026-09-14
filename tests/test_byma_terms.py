"""
Tests de la ficha técnica de BYMA (`bonds/byma_terms.py`).

Es la fuente que le pone emisor, ley y lámina mínima a las especies que
realmente se operan: el dataset comunitario de cronogramas cubre 54 emisiones
y ninguna de las más negociadas del panel. Como la API no está documentada, lo
que se verifica es qué pasa cuando un campo falta, viene vacío o cambia de
forma — no que "funcione" con la respuesta ideal.

El registro de muestra está copiado de una respuesta real.
"""

from datetime import date

import pytest

from bonds.byma_terms import parse_technical_sheet

FICHA = {
    "emisor": "YPF S.A.",
    "paisLey": "ESTADOS UNIDOS",
    "ley": "",
    "moneda": "USD",
    "denominacionMinima": 1,
    "fechaEmision": "2024-02-12 00:00:00.0",
    "fechaVencimiento": "2033-09-30 00:00:00.0",
    "codigoIsin": "USP989MJBT72",
    "default": False,
    "tipoGarantia": "Con garantía común",
    "interes": "7,00",
    "formaAmortizacion": " Las Obligaciones Negociables Clase XVIII serán amortizadas en 4 cuotas ",
}


class TestCamposDescriptivos:
    def test_lee_emisor_moneda_y_lamina(self):
        r = parse_technical_sheet("YMCJD", {"data": [FICHA]})
        assert r.issuer == "YPF S.A."
        assert r.currency == "USD"
        assert r.min_denomination == pytest.approx(1.0)

    def test_lee_las_fechas_con_la_hora_pegada(self):
        r = parse_technical_sheet("YMCJD", {"data": [FICHA]})
        assert r.maturity == date(2033, 9, 30)
        assert r.issue_date == date(2024, 2, 12)

    def test_conserva_isin_garantia_y_flag_de_default(self):
        r = parse_technical_sheet("YMCJD", {"data": [FICHA]})
        assert r.isin == "USP989MJBT72"
        assert r.guarantee == "Con garantía común"
        assert r.in_default is False

    def test_marca_el_default_cuando_viene_en_true(self):
        assert parse_technical_sheet("X", {"data": [{**FICHA, "default": True}]}).in_default is True

    def test_guarda_el_texto_crudo_del_cupon_y_la_amortizacion(self):
        # Se conservan sin parsear: son los campos que deciden si el flujo de
        # fondos se puede reconstruir, y esa decisión todavía no está tomada.
        r = parse_technical_sheet("YMCJD", {"data": [FICHA]})
        assert r.raw_interest == "7,00"
        assert r.raw_amortization.startswith("Las Obligaciones Negociables")


class TestLeyAplicable:
    @pytest.mark.parametrize("pais", ["ESTADOS UNIDOS", "EEUU", "New York", "usa"])
    def test_reconoce_la_ley_extranjera(self, pais):
        assert parse_technical_sheet("X", {"data": [{**FICHA, "paisLey": pais}]}).law == "NY"

    @pytest.mark.parametrize("pais", ["ARGENTINA", "Argentina", "arg"])
    def test_reconoce_la_ley_local(self, pais):
        assert parse_technical_sheet("X", {"data": [{**FICHA, "paisLey": pais}]}).law == "ARG"

    @pytest.mark.parametrize("pais", ["", None, "LUXEMBURGO"])
    def test_un_pais_que_no_se_reconoce_no_se_clasifica(self, pais):
        # La jurisdicción puntúa, así que clasificarla mal es peor que no
        # informarla.
        assert parse_technical_sheet("X", {"data": [{**FICHA, "paisLey": pais, "ley": ""}]}).law is None


class TestRespuestasImperfectas:
    @pytest.mark.parametrize("payload", [None, [], {}, {"data": []}, "texto", [42]])
    def test_una_respuesta_sin_ficha_devuelve_none(self, payload):
        assert parse_technical_sheet("X", payload) is None

    def test_acepta_la_ficha_sin_envolver_en_data(self):
        assert parse_technical_sheet("X", [FICHA]).issuer == "YPF S.A."

    def test_los_campos_vacios_quedan_en_none_y_no_en_cadena_vacia(self):
        r = parse_technical_sheet("X", {"data": [{"emisor": "   ", "tipoGarantia": ""}]})
        assert r.issuer is None
        assert r.guarantee is None

    def test_una_fecha_ilegible_no_rompe(self):
        r = parse_technical_sheet("X", {"data": [{**FICHA, "fechaVencimiento": "30/09/2033"}]})
        assert r.maturity is None

    def test_una_lamina_no_numerica_no_rompe(self):
        assert parse_technical_sheet("X", {"data": [{**FICHA, "denominacionMinima": "s/d"}]}).min_denomination is None

    def test_normaliza_el_ticker(self):
        assert parse_technical_sheet("  ymcjd ", {"data": [FICHA]}).ticker == "YMCJD"
