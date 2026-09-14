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

from bonds.byma_terms import is_bullet_amortization, parse_coupon_rate, parse_technical_sheet

FICHA = {
    "emisor": "YPF S.A.",
    "ley": "",
    "moneda": "USD",
    "denominacionMinima": 1,
    "fechaEmision": "2024-02-12 00:00:00.0",
    "fechaVencimiento": "2033-09-30 00:00:00.0",
    "codigoIsin": "USP989MJBT72",
    "default": False,
    "tipoGarantia": "Con garantía común",
    "interes": "FIJO 7,00%",
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

    def test_lee_la_tasa_y_la_estructura(self):
        r = parse_technical_sheet("YMCJD", {"data": [FICHA]})
        assert r.coupon_rate == pytest.approx(7.0)
        assert r.is_bullet is False  # el texto de muestra amortiza en cuotas

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
        assert r.raw_interest == "FIJO 7,00%"
        assert r.raw_amortization.startswith("Las Obligaciones Negociables")


class TestLeyAplicable:
    """
    BYMA tiene los campos `ley` y `paisLey` y no los llena: sobre 40 fichas del
    panel operado, `paisLey` vino vacío en las 40 y `ley` en 39. La ficha no es
    fuente de jurisdicción, y el panel no debe pretender que lo sea.
    """

    def test_la_ficha_no_aporta_ley(self):
        assert not hasattr(parse_technical_sheet("X", {"data": [FICHA]}), "law")


class TestTasaDeCupon:
    """
    `interes` llega como texto, pero con una estructura estable: "FIJO 7,50%",
    "FIJO DE 5,50%" o "TASA DE REFERENCIA + MARGEN APLICABLE (2,50%)".
    """

    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("FIJO 7,50%", 7.5),
            ("FIJO DE 5,50%", 5.5),
            ("FIJA 9,5%", 9.5),
            ("FIJO DE 8,00 %", 8.0),
            ("FIJO 12,125%", 12.125),
        ],
    )
    def test_lee_la_tasa_fija(self, texto, esperado):
        assert parse_coupon_rate(texto) == pytest.approx(esperado)

    @pytest.mark.parametrize(
        "texto",
        [
            "TASA DE REFERENCIA + MARGEN APLICABLE (2,50%)",
            "BADLAR + 4,00%",
            "TAMAR + 3,00%",
            "VARIABLE 5,00%",
            "CER + 2,00%",
        ],
    )
    def test_una_tasa_variable_no_devuelve_cupon(self, texto):
        # El motor descuenta un flujo determinado hoy, y el de un bono a tasa
        # variable no lo está: publicar su TIR sería calcularla sobre un cupón
        # que no va a pagar.
        assert parse_coupon_rate(texto) is None

    @pytest.mark.parametrize("texto", ["", None, "A DETERMINAR", "FIJO", "7,50%"])
    def test_un_texto_que_no_se_entiende_no_devuelve_cupon(self, texto):
        assert parse_coupon_rate(texto) is None


class TestEstructuraDeAmortizacion:
    """
    Los 20 textos distintos que devuelve hoy el panel operado. No se extrae el
    cronograma de la prosa: se contesta una sola pregunta binaria, y lo que no
    se reconoce se responde que no.
    """

    @pytest.mark.parametrize(
        "texto",
        [
            "AL VENCIMIENTO",
            "Al vencimiento.",
            "AL VENCIMENTO",
            "AL  VENCIMIENTO",
            "AL VENCIMIENTO\n",
            "En una cuota al vencimiento.",
            "En una cuota al vencimiento.\nLa totalidad de las condiciones generales consta en el Suplemento",
            "\nEn una cuota al vencimiento.\nLa totalidad de las condiciones",
        ],
    )
    def test_reconoce_los_bullet(self, texto):
        assert is_bullet_amortization(texto) is True

    @pytest.mark.parametrize(
        "texto",
        [
            "EN TRES CUOTAS, DOS DE 30% Y LA ULTIMA DE 40%",
            "EN TRES CUOTAS, DOS CUOTAS DE 33% Y LA ULTIMA DE 34%",
            "En tres pagos anuales.\nLa totalidad de las condiciones",
            "En tres cuotas anuales y consecutivas, empezando el 11.09.2029",
            "En tres cuotas",
            "EN TRES PAGOS, DOS DE 33,33% Y LA ULTIMA DE 33,34%",
            "EN DOS CUOTAS DE 50%",
            "Tres cuotas anuales y consecutivas, dos del 33% y una del 34%.",
            "DOS CUOTAS DE 15%,DOS CUOTAS DE 4,25%, DOS CUOTAS DE 8,50% , Y LA ULTIMA DE 59,50%",
            "Las ON Clase XVIII seran amortizadas en 4 (cuatro) cuotas anuales, es decir el 30 de septiembre de 2030",
        ],
    )
    def test_no_confunde_las_que_amortizan_en_cuotas(self, texto):
        assert is_bullet_amortization(texto) is False

    def test_el_veto_por_plural_gana_sobre_la_mención_del_vencimiento(self):
        # El caso que hace necesario el veto: nombra el vencimiento y no es
        # bullet.
        texto = (
            "Las ON Clase XVII seran amortizadas en 7 (siete) cuotas semestrales, "
            "comenzando el 30 de junio de 2026 y finalizando en la Fecha de Vencimiento"
        )
        assert is_bullet_amortization(texto) is False

    @pytest.mark.parametrize("texto", ["", None, "SEGUN PROSPECTO", "A DETERMINAR"])
    def test_lo_que_no_se_reconoce_no_es_bullet(self, texto):
        assert is_bullet_amortization(texto) is False

    def test_un_bono_que_ya_amortizo_no_es_bullet(self):
        # El capital residual por debajo del nominal lo desmiente, diga lo que
        # diga el texto.
        ficha = {**FICHA, "montoNominal": 1000, "montoResidual": 600}
        assert parse_technical_sheet("X", {"data": [ficha]}).is_bullet is False


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
