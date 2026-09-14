"""
Tests del catálogo de ONs (`bonds/catalog.py`).

El catálogo es el único lugar donde viven las condiciones de emisión, y se
edita a mano. Estos tests cubren sobre todo el camino del error: qué pasa
cuando una fila viene mal cargada. El requisito no es que el parser "no
explote" sino que **reporte la línea y siga cargando el resto**: un catálogo
que se cae entero por una coma de más deja el panel vacío sin explicar por qué.
"""

from datetime import date

import pytest

from bonds.catalog import (
    DEFAULT_CATALOG_PATH,
    REQUIRED_COLUMNS,
    base_ticker_of,
    find_terms,
    load_catalog,
    quote_currency_of,
    settlement_of,
)
from constants import (
    BOND_SETTLEMENT_CABLE,
    BOND_SETTLEMENT_MEP,
    BOND_SETTLEMENT_PESOS,
    BOND_SETTLEMENT_UNKNOWN,
)

HEADER = ",".join(REQUIRED_COLUMNS)

VALID_ROW = "YMCJO,YPF S.A.,Energía,USD,NY,7.00,2,2024-02-12,2033-02-12,,1000,AAA,si,ok"


def write_catalog(tmp_path, *rows, header: str = HEADER):
    path = tmp_path / "catalogo.csv"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


class TestCatalogoDelRepositorio:
    """El CSV versionado tiene que cargar sin errores en cada commit."""

    def test_el_catalogo_del_repo_carga_sin_errores(self):
        terms, errors = load_catalog()
        assert errors == []
        assert terms, "El catálogo versionado no debería estar vacío"

    def test_el_catalogo_del_repo_existe_en_la_ruta_por_defecto(self):
        assert DEFAULT_CATALOG_PATH.exists()

    def test_todas_las_ons_del_repo_vencen_despues_de_emitirse(self):
        terms, _ = load_catalog()
        assert all(bond.maturity > bond.issue_date for bond in terms.values())


class TestParseoDeFilas:
    def test_carga_una_fila_valida(self, tmp_path):
        terms, errors = load_catalog(write_catalog(tmp_path, VALID_ROW))
        assert errors == []
        bond = terms["YMCJO"]
        assert bond.issuer == "YPF S.A."
        assert bond.coupon_rate == pytest.approx(7.0)
        assert bond.frequency == 2
        assert bond.maturity == date(2033, 2, 12)
        assert bond.law == "NY"
        assert bond.min_denomination == pytest.approx(1000.0)
        assert bond.verified is True

    def test_amortizaciones_vacias_significan_bullet(self, tmp_path):
        terms, _ = load_catalog(write_catalog(tmp_path, VALID_ROW))
        assert terms["YMCJO"].amortizations == ()
        assert terms["YMCJO"].is_bullet is True

    def test_parsea_un_cronograma_de_amortizacion(self, tmp_path):
        row = "TEST1,Emisor,Sector,USD,ARG,8.0,2,2023-01-15,2027-01-15,2026-01-15:50|2027-01-15:50,1,s/c,no,"
        terms, errors = load_catalog(write_catalog(tmp_path, row))
        assert errors == []
        assert terms["TEST1"].amortizations == ((date(2026, 1, 15), 50.0), (date(2027, 1, 15), 50.0))
        assert terms["TEST1"].is_bullet is False

    def test_el_ticker_se_normaliza_a_mayusculas(self, tmp_path):
        row = VALID_ROW.replace("YMCJO", " ymcjo ", 1)
        terms, _ = load_catalog(write_catalog(tmp_path, row))
        assert "YMCJO" in terms

    def test_lamina_minima_vacia_queda_en_none(self, tmp_path):
        row = "TEST1,Emisor,Sector,USD,ARG,8.0,2,2023-01-15,2027-01-15,,,s/c,no,"
        terms, _ = load_catalog(write_catalog(tmp_path, row))
        assert terms["TEST1"].min_denomination is None

    @pytest.mark.parametrize("raw,expected", [("si", True), ("sí", True), ("SI", True), ("no", False), ("", False)])
    def test_lectura_de_la_marca_de_verificado(self, tmp_path, raw, expected):
        row = f"TEST1,Emisor,Sector,USD,ARG,8.0,2,2023-01-15,2027-01-15,,1,s/c,{raw},"
        terms, _ = load_catalog(write_catalog(tmp_path, row))
        assert terms["TEST1"].verified is expected

    def test_las_lineas_con_numeral_se_ignoran(self, tmp_path):
        path = tmp_path / "catalogo.csv"
        path.write_text(f"# comentario\n{HEADER}\n# otro comentario\n{VALID_ROW}\n", encoding="utf-8")
        terms, errors = load_catalog(path)
        assert errors == []
        assert list(terms) == ["YMCJO"]

    def test_las_filas_totalmente_vacias_se_saltean(self, tmp_path):
        terms, errors = load_catalog(write_catalog(tmp_path, VALID_ROW, ",,,,,,,,,,,,,"))
        assert errors == []
        assert len(terms) == 1


class TestFilasInvalidas:
    """Una fila mal cargada se reporta con su línea y no frena el resto."""

    def _assert_reporta_error(self, tmp_path, bad_row, fragment):
        terms, errors = load_catalog(write_catalog(tmp_path, VALID_ROW, bad_row))
        assert len(errors) == 1
        assert fragment in errors[0]
        assert "línea 3" in errors[0]
        # La fila válida anterior sigue cargada.
        assert "YMCJO" in terms
        return errors[0]

    def test_ticker_vacio(self, tmp_path):
        self._assert_reporta_error(
            tmp_path, ",Emisor,Sector,USD,ARG,8.0,2,2023-01-15,2027-01-15,,1,s/c,no,", "falta el ticker"
        )

    def test_frecuencia_no_soportada(self, tmp_path):
        self._assert_reporta_error(
            tmp_path, "TEST1,Emisor,Sector,USD,ARG,8.0,3,2023-01-15,2027-01-15,,1,s/c,no,", "pagos_por_anio=3"
        )

    def test_ley_desconocida(self, tmp_path):
        self._assert_reporta_error(
            tmp_path, "TEST1,Emisor,Sector,USD,UK,8.0,2,2023-01-15,2027-01-15,,1,s/c,no,", "ley 'UK'"
        )

    def test_vencimiento_anterior_a_la_emision(self, tmp_path):
        self._assert_reporta_error(
            tmp_path, "TEST1,Emisor,Sector,USD,ARG,8.0,2,2027-01-15,2023-01-15,,1,s/c,no,", "anterior o igual"
        )

    def test_cupon_negativo(self, tmp_path):
        self._assert_reporta_error(
            tmp_path, "TEST1,Emisor,Sector,USD,ARG,-8.0,2,2023-01-15,2027-01-15,,1,s/c,no,", "negativo"
        )

    def test_amortizaciones_que_no_suman_cien(self, tmp_path):
        self._assert_reporta_error(
            tmp_path,
            "TEST1,Emisor,Sector,USD,ARG,8.0,2,2023-01-15,2027-01-15,2026-01-15:40|2027-01-15:40,1,s/c,no,",
            "suman 80.00%",
        )

    def test_amortizacion_posterior_al_vencimiento(self, tmp_path):
        self._assert_reporta_error(
            tmp_path,
            "TEST1,Emisor,Sector,USD,ARG,8.0,2,2023-01-15,2027-01-15,2028-01-15:100,1,s/c,no,",
            "posterior al vencimiento",
        )

    def test_tramo_de_amortizacion_con_formato_invalido(self, tmp_path):
        self._assert_reporta_error(
            tmp_path,
            "TEST1,Emisor,Sector,USD,ARG,8.0,2,2023-01-15,2027-01-15,2026-01-15-100,1,s/c,no,",
            "sin formato fecha:porcentaje",
        )

    def test_fecha_con_formato_invalido(self, tmp_path):
        terms, errors = load_catalog(
            write_catalog(tmp_path, "TEST1,Emisor,Sector,USD,ARG,8.0,2,15/01/2023,2027-01-15,,1,s/c,no,")
        )
        assert terms == {}
        assert len(errors) == 1
        assert "línea 2" in errors[0]

    def test_ticker_duplicado_conserva_la_primera_aparicion(self, tmp_path):
        segunda = VALID_ROW.replace("YPF S.A.", "Otro Emisor")
        terms, errors = load_catalog(write_catalog(tmp_path, VALID_ROW, segunda))
        assert terms["YMCJO"].issuer == "YPF S.A."
        assert any("duplicado" in error for error in errors)

    def test_tolera_decimales_periodicos_en_las_amortizaciones(self, tmp_path):
        row = (
            "TEST1,Emisor,Sector,USD,ARG,8.0,2,2023-01-15,2027-01-15,"
            "2026-01-15:33.33|2026-07-15:33.33|2027-01-15:33.34,1,s/c,no,"
        )
        _, errors = load_catalog(write_catalog(tmp_path, row))
        assert errors == []


class TestArchivoInvalido:
    def test_archivo_inexistente(self, tmp_path):
        terms, errors = load_catalog(tmp_path / "no-existe.csv")
        assert terms == {}
        assert "No se encontró" in errors[0]

    def test_archivo_vacio(self, tmp_path):
        path = tmp_path / "vacio.csv"
        path.write_text("", encoding="utf-8")
        terms, errors = load_catalog(path)
        assert terms == {}
        assert "vacío" in errors[0]

    def test_faltan_columnas_obligatorias(self, tmp_path):
        path = write_catalog(tmp_path, "YMCJO,YPF", header="ticker,emisor")
        terms, errors = load_catalog(path)
        assert terms == {}
        assert "faltan columnas obligatorias" in errors[0]


class TestEspeciesDeLiquidacion:
    """
    En BYMA una misma ON cotiza en tres especies según la última letra del
    ticker: O liquida en pesos, D en dólar MEP y C en dólar cable. Las tres
    comparten cupón, vencimiento y cronograma, así que el catálogo necesita
    una sola fila por bono, no tres.
    """

    @pytest.mark.parametrize(
        "ticker,esperado",
        [
            ("YMCJO", BOND_SETTLEMENT_PESOS),
            ("YMCJD", BOND_SETTLEMENT_MEP),
            ("YMCJC", BOND_SETTLEMENT_CABLE),
        ],
    )
    def test_lee_la_especie_desde_la_ultima_letra(self, ticker, esperado):
        assert settlement_of(ticker) == esperado

    @pytest.mark.parametrize("ticker", ["YMCJ", "YMCJDD", "YMCJX", "", "  "])
    def test_un_ticker_fuera_de_la_convencion_no_se_adivina(self, ticker):
        assert settlement_of(ticker) == BOND_SETTLEMENT_UNKNOWN
        assert quote_currency_of(ticker) is None

    def test_la_moneda_del_precio_sale_de_la_especie_no_del_bono(self):
        # El mismo bono en dólares cotiza en pesos si se opera la especie O.
        assert quote_currency_of("YMCJO") == "ARS"
        assert quote_currency_of("YMCJD") == "USD"
        assert quote_currency_of("YMCJC") == "USD"

    @pytest.mark.parametrize("ticker", ["YMCJO", "YMCJD", "YMCJC"])
    def test_las_tres_especies_comparten_raiz(self, ticker):
        assert base_ticker_of(ticker) == "YMCJ"

    def test_un_ticker_sin_especie_es_su_propia_raiz(self):
        assert base_ticker_of("RARO") == "RARO"

    def test_la_normalizacion_ignora_mayusculas_y_espacios(self):
        assert base_ticker_of(" ymcjd ") == "YMCJ"
        assert settlement_of(" ymcjd ") == BOND_SETTLEMENT_MEP


class TestBusquedaDeCondiciones:
    def test_una_fila_cargada_como_especie_o_cubre_las_especies_d_y_c(self, tmp_path):
        terms, _ = load_catalog(write_catalog(tmp_path, VALID_ROW))
        assert find_terms(terms, "YMCJD") is terms["YMCJO"]
        assert find_terms(terms, "YMCJC") is terms["YMCJO"]

    def test_el_ticker_exacto_le_gana_a_la_raiz(self, tmp_path):
        # Permite cargar una especie puntual con condiciones distintas sin que
        # la fila genérica del bono la pise.
        especifica = VALID_ROW.replace("YMCJO", "YMCJD", 1).replace("YPF S.A.", "YPF especie D")
        terms, errors = load_catalog(write_catalog(tmp_path, VALID_ROW, especifica))
        assert errors == []
        assert find_terms(terms, "YMCJD").issuer == "YPF especie D"
        assert find_terms(terms, "YMCJO").issuer == "YPF S.A."

    def test_un_ticker_ajeno_al_catalogo_no_matchea(self, tmp_path):
        terms, _ = load_catalog(write_catalog(tmp_path, VALID_ROW))
        assert find_terms(terms, "ZZZZD") is None

    def test_la_busqueda_normaliza_el_ticker(self, tmp_path):
        terms, _ = load_catalog(write_catalog(tmp_path, VALID_ROW))
        assert find_terms(terms, " ymcjd ") is terms["YMCJO"]
