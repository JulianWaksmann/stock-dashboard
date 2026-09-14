"""
Tests de la fuente pública de cronogramas de pago (`bonds/flows_source.py`).

Es un archivo de terceros: no controlamos su forma ni su calidad. Lo que se
verifica acá es que el parser lo traduzca bien cuando viene bien, y que
degrade sin romper cuando viene mal, que es el caso que tarde o temprano pasa.
"""

from datetime import date

import pytest

from bonds.flows_source import COMMUNITY_FLOWS_SOURCE_NAME, parse_community_flows


def payload(*entries: tuple[str, dict]) -> dict:
    return {"ons": dict(entries)}


ENTRADA_VALIDA = (
    "ARC1",
    {
        "ticker_d912": "ARC1D",
        "vencimiento": "2031-08-01",
        "nombre": "AA2000",
        "flujos": [
            {"fecha": "2027-02-01", "monto": 0.0683},
            {"fecha": "2026-05-04", "monto": 0.0214},
        ],
    },
)


class TestParseo:
    def test_traduce_una_entrada_completa(self):
        flows = parse_community_flows(payload(ENTRADA_VALIDA))
        bond = flows["ARC1"]
        assert bond.quote_ticker == "ARC1D"
        assert bond.issuer == "AA2000"
        assert bond.maturity == date(2031, 8, 1)
        assert bond.currency == "USD"
        assert bond.source == COMMUNITY_FLOWS_SOURCE_NAME

    def test_escala_los_importes_a_base_100(self):
        # La fuente publica por cada 1 de valor nominal; el motor trabaja por 100.
        bond = parse_community_flows(payload(ENTRADA_VALIDA))["ARC1"]
        assert bond.cashflows[0].total == pytest.approx(2.14)

    def test_ordena_el_cronograma_por_fecha(self):
        bond = parse_community_flows(payload(ENTRADA_VALIDA))["ARC1"]
        fechas = [flow.date for flow in bond.cashflows]
        assert fechas == sorted(fechas)

    def test_marca_los_pagos_como_no_desglosados(self):
        # La fuente informa el total del pago, no cuánto es renta y cuánto
        # capital. Sin esa marca, la vida promedio devolvería un número falso.
        bond = parse_community_flows(payload(ENTRADA_VALIDA))["ARC1"]
        assert all(not flow.split_known for flow in bond.cashflows)

    def test_se_indexa_por_la_raiz_del_ticker_que_cotiza(self):
        # La clave del diccionario original es una etiqueta interna del
        # proyecto de origen y no siempre coincide con la especie real.
        entrada = ("HBC", {**ENTRADA_VALIDA[1], "ticker_d912": "HBCDD"})
        flows = parse_community_flows(payload(entrada))
        assert list(flows) == ["HBCD"]
        assert flows["HBCD"].quote_ticker == "HBCDD"


class TestEntradasInvalidas:
    @pytest.mark.parametrize(
        "entrada",
        [
            {"vencimiento": "2031-08-01", "flujos": [{"fecha": "2027-02-01", "monto": 0.1}]},
            {"ticker_d912": "ARC1D", "flujos": [{"fecha": "2027-02-01", "monto": 0.1}]},
            {"ticker_d912": "ARC1D", "vencimiento": "2031-08-01", "flujos": []},
            {"ticker_d912": "ARC1D", "vencimiento": "01/08/2031", "flujos": [{"fecha": "2027-02-01", "monto": 0.1}]},
            {"ticker_d912": "ARC1D", "vencimiento": "2031-08-01", "flujos": [{"fecha": "2027-02-01"}]},
            {"ticker_d912": "ARC1D", "vencimiento": "2031-08-01", "flujos": [{"fecha": "x", "monto": 0.1}]},
        ],
    )
    def test_una_entrada_rota_se_descarta_sin_frenar_el_resto(self, entrada):
        flows = parse_community_flows(payload(ENTRADA_VALIDA, ("ROTA", entrada)))
        assert list(flows) == ["ARC1"]

    @pytest.mark.parametrize("payload_raro", [{}, {"ons": None}, {"ons": []}, {"otra_cosa": {}}])
    def test_un_json_con_otra_forma_devuelve_vacio(self, payload_raro):
        assert parse_community_flows(payload_raro) == {}
