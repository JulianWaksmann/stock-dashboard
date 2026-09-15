"""
Tests del parseo del panel de ONs de BYMA (`bonds/byma_source.py`).

BYMA es ahora la única fuente de precios, y su API no está documentada ni
tiene contrato de estabilidad. Lo que se verifica acá es el comportamiento
ante lo que esa respuesta trae de verdad: campos en cero que significan "no
hubo" y no "vale cero", especies que no operaron, y campos que podrían
desaparecer de un día para el otro.

Los registros de prueba están copiados de una respuesta real del endpoint.
"""

import numpy as np
import pandas as pd
import pytest

from bonds.byma_source import parse_byma_bonds

# Especie que operó: puntas, volumen y precio del día.
OPERADA = {
    "symbol": "YMCJD",
    "settlementType": "2",
    "settlementPrice": 105.6,
    "previousSettlementPrice": 106.2,
    "bidPrice": 105.0,
    "offerPrice": 105.6,
    "quantityBid": 500,
    "quantityOffer": 300,
    "volumeAmount": 1_317_000.0,
    "tradeVolume": 124_737,
    "numberOfOrders": 128,
    "maturityDate": "2033-09-30",
    "denominationCcy": "USD",
}

# Especie que no operó: BYMA informa ceros, no ausencias.
SIN_OPERAR = {
    "symbol": "A11LD",
    "settlementPrice": 0.0,
    "previousSettlementPrice": 98.9171,
    "previousClosingPrice": 98.9171,
    "bidPrice": 0.0,
    "offerPrice": 0.0,
    "openingPrice": 0.0,
    "tradeVolume": 0.0,
    "numberOfOrders": 0,
    "maturityDate": "2028-03-31",
    "denominationCcy": "USD",
}


class TestEspecieOperada:
    def test_lee_precio_puntas_y_volumen(self):
        fila = parse_byma_bonds([OPERADA]).iloc[0]
        assert fila["Ticker"] == "YMCJD"
        assert fila["Precio"] == pytest.approx(105.6)
        assert fila["Punta Compra"] == pytest.approx(105.0)
        assert fila["Punta Venta"] == pytest.approx(105.6)
        assert fila["Volumen"] == pytest.approx(1_317_000.0)
        assert fila["Operaciones"] == pytest.approx(128)

    def test_calcula_la_variacion_contra_el_cierre_anterior(self):
        fila = parse_byma_bonds([OPERADA]).iloc[0]
        assert fila["Var. (%)"] == pytest.approx((105.6 / 106.2 - 1) * 100)

    def test_trae_vencimiento_y_moneda_de_la_especie(self):
        # Son campos que ahorran cruzar otra fuente para saber el plazo.
        fila = parse_byma_bonds([OPERADA]).iloc[0]
        assert fila["Vencimiento BYMA"] == pd.Timestamp("2033-09-30")
        assert fila["Moneda BYMA"] == "USD"


class TestEspecieSinOperar:
    def test_cae_al_cierre_anterior_cuando_no_hubo_precio(self):
        fila = parse_byma_bonds([SIN_OPERAR]).iloc[0]
        assert fila["Precio"] == pytest.approx(98.9171)

    def test_no_inventa_puntas_a_partir_de_los_ceros(self):
        # Un cero en la punta significa que no hay punta. Tomarlo como precio
        # daría un spread de 100% y una TIR sin sentido.
        fila = parse_byma_bonds([SIN_OPERAR]).iloc[0]
        assert np.isnan(fila["Punta Compra"])
        assert np.isnan(fila["Punta Venta"])

    def test_queda_con_volumen_cero_para_que_el_panel_la_descarte(self):
        fila = parse_byma_bonds([SIN_OPERAR]).iloc[0]
        assert fila["Volumen"] == 0.0


class TestRespuestasImperfectas:
    def test_acepta_la_respuesta_envuelta_en_data(self):
        assert len(parse_byma_bonds({"data": [OPERADA]})) == 1

    @pytest.mark.parametrize("payload", [[], {}, None, "texto", {"data": []}, [None, 42]])
    def test_una_respuesta_sin_especies_devuelve_vacio(self, payload):
        assert parse_byma_bonds(payload).empty

    def test_descarta_registros_sin_ticker(self):
        assert parse_byma_bonds([{**OPERADA, "symbol": "  "}]).empty

    def test_un_registro_sin_ningun_precio_no_rompe(self):
        minimo = {"symbol": "XXXXD"}
        fila = parse_byma_bonds([minimo]).iloc[0]
        assert np.isnan(fila["Precio"])
        assert fila["Volumen"] == 0.0

    def test_no_duplica_una_especie_repetida(self):
        repetida = {**OPERADA, "settlementPrice": 99.0}
        resultado = parse_byma_bonds([OPERADA, repetida])
        assert len(resultado) == 1
        assert resultado.iloc[0]["Precio"] == pytest.approx(105.6)

    def test_normaliza_el_ticker(self):
        assert parse_byma_bonds([{**OPERADA, "symbol": " ymcjd "}]).iloc[0]["Ticker"] == "YMCJD"

    def test_un_vencimiento_ilegible_no_rompe(self):
        fila = parse_byma_bonds([{**OPERADA, "maturityDate": "30/09/2033"}]).iloc[0]
        assert pd.isna(fila["Vencimiento BYMA"])

    def test_cae_a_otro_campo_de_volumen_si_falta_el_preferido(self):
        sin_monto = {k: v for k, v in OPERADA.items() if k != "volumeAmount"}
        assert parse_byma_bonds([sin_monto]).iloc[0]["Volumen"] == pytest.approx(124_737)


class TestSeñalesDeCambioDeEsquema:
    def test_avisa_cuando_ninguna_especie_informa_volumen(self):
        # Sin esta marca, el filtro de liquidez (top 50 por defecto) vaciaría
        # la pantalla y parecería un problema de red, no un campo renombrado.
        resultado = parse_byma_bonds([{k: v for k, v in OPERADA.items() if "olume" not in k}])
        assert "volumen" in resultado.attrs.get("volume_missing", "").lower()

    def test_no_avisa_cuando_hay_volumen(self):
        assert "volume_missing" not in parse_byma_bonds([OPERADA]).attrs


class TestVariacionDiaria:
    def test_no_informa_variacion_si_la_especie_no_operó(self):
        # Con precio caído al cierre anterior, la cuenta da 0,00%, que se lee
        # como "no se movió" cuando significa "no operó".
        assert np.isnan(parse_byma_bonds([SIN_OPERAR]).iloc[0]["Var. (%)"])

    def test_informa_variacion_cuando_sí_operó(self):
        fila = parse_byma_bonds([OPERADA]).iloc[0]
        assert fila["Var. (%)"] == pytest.approx((105.6 / 106.2 - 1) * 100)


class TestPlazoDeLiquidacion:
    """
    La respuesta trae la misma especie repetida por plazo: sobre 800 registros
    reales hay 419 símbolos distintos. Sin filtrar, cuál sobrevive depende del
    orden de la respuesta, y las dos filas tienen precios distintos.
    """

    def test_conserva_solo_el_plazo_estandar(self):
        registros = [
            {**OPERADA, "settlementType": "1", "settlementPrice": 99.9},
            {**OPERADA, "settlementType": "2", "settlementPrice": 105.6},
        ]
        resultado = parse_byma_bonds(registros)
        assert len(resultado) == 1
        assert resultado.iloc[0]["Precio"] == pytest.approx(105.6)

    def test_el_orden_de_la_respuesta_no_cambia_el_resultado(self):
        a = [{**OPERADA, "settlementType": "1"}, {**OPERADA, "settlementType": "2"}]
        b = list(reversed(a))
        assert parse_byma_bonds(a).iloc[0]["Precio"] == parse_byma_bonds(b).iloc[0]["Precio"]

    def test_un_registro_sin_plazo_declarado_no_se_descarta(self):
        sin_plazo = {k: v for k, v in OPERADA.items() if k != "settlementType"}
        assert len(parse_byma_bonds([sin_plazo])) == 1


class TestMonedaDelPrecio:
    """
    BYMA informa la moneda de cotización en `denominationCcy`, y ese dato le
    gana a deducirla de la última letra del ticker.
    """

    @pytest.mark.parametrize(
        "denominacion,esperada",
        [("USD", "USD"), ("EXT", "USD"), ("ARS", "ARS")],
    )
    def test_traduce_la_denominacion_a_la_moneda(self, denominacion, esperada):
        # "EXT" es la especie cable: liquida en dólares, en una cuenta del
        # exterior.
        fila = parse_byma_bonds([{**OPERADA, "denominationCcy": denominacion}]).iloc[0]
        assert fila["Moneda Precio"] == esperada

    def test_una_denominacion_desconocida_no_se_traduce(self):
        fila = parse_byma_bonds([{**OPERADA, "denominationCcy": "XYZ"}]).iloc[0]
        assert fila["Moneda Precio"] is None
