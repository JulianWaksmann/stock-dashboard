"""
Tests del archivo de calificaciones (`bonds/ratings.py`).

Dos comportamientos que el resto del panel da por sentados: que una entrada
sin verificar NO se muestre, y que el mismo emisor escrito de dos formas
distintas por las dos fuentes de precios encuentre igual su calificación.
"""

import json

import pytest

from bonds.ratings import find_rating, load_ratings, normalize_issuer


def escribir(tmp_path, entradas):
    destino = tmp_path / "calificaciones.json"
    destino.write_text(json.dumps({"emisores": entradas}), encoding="utf-8")
    return destino


def entrada(emisor, calificacion="AA+(arg)", verificado=True, **extra):
    base = {
        "emisor": emisor,
        "alias": [],
        "calificacion": calificacion,
        "agencia": "FIX SCR",
        "escala": "nacional",
        "fecha": "2026-03-01",
        "fuente": "https://ejemplo",
        "verificado": verificado,
    }
    base.update(extra)
    return base


class TestNormalizacionDeEmisor:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("ARCOR S.A.I.C.", "Arcor"),
            ("GENNEIA S.A.", "Genneia"),
            ("TECPETROL S.A.", "Tecpetrol"),
            ("PAMPA ENERGIA S.A", "Pampa Energía"),
            ("LOMA NEGRA COMPAÑIA INDUSTRIAL ARGENTINA SOCIEDAD ANONIMA",
             "Loma Negra Compania Industrial Argentina"),
        ],
    )
    def test_el_mismo_emisor_escrito_distinto_da_la_misma_clave(self, a, b):
        assert normalize_issuer(a) == normalize_issuer(b)

    def test_emisores_distintos_no_colapsan(self):
        # Es el riesgo de normalizar de más: son dos emisores diferentes.
        assert normalize_issuer("MSU S.A.") != normalize_issuer("MSU GREEN ENERGY S.A.")
        assert normalize_issuer("YPF S.A.") != normalize_issuer("YPF Energía Eléctrica S.A.")

    def test_tolera_vacios(self):
        assert normalize_issuer(None) == ""
        assert normalize_issuer("") == ""


class TestCargaDelArchivo:
    def test_una_entrada_sin_verificar_no_se_publica(self, tmp_path):
        ruta = escribir(tmp_path, [entrada("YPF S.A.", verificado=False)])
        ratings, avisos = load_ratings(ruta)
        assert ratings == {}
        assert avisos == []

    def test_una_entrada_sin_calificacion_no_se_publica(self, tmp_path):
        # Es la plantilla que se versiona con el repo: no es un error.
        ruta = escribir(tmp_path, [entrada("YPF S.A.", calificacion="", verificado=True)])
        ratings, avisos = load_ratings(ruta)
        assert ratings == {}
        assert avisos == []

    def test_una_entrada_verificada_se_encuentra_por_cualquier_alias(self, tmp_path):
        ruta = escribir(tmp_path, [entrada("ARCOR S.A.I.C.", alias=["Arcor", "ARCOR SAIC"])])
        ratings, _ = load_ratings(ruta)
        for nombre in ("ARCOR S.A.I.C.", "Arcor", "arcor s.a.i.c.", "ARCOR SAIC"):
            assert find_rating(ratings, nombre) is not None, nombre

    def test_la_etiqueta_lleva_la_calificadora(self, tmp_path):
        ruta = escribir(tmp_path, [entrada("YPF S.A.", calificacion="AAA(arg)")])
        ratings, _ = load_ratings(ruta)
        assert find_rating(ratings, "YPF S.A.").label == "AAA(arg) (FIX SCR)"

    def test_un_emisor_no_cargado_devuelve_None(self, tmp_path):
        ruta = escribir(tmp_path, [entrada("YPF S.A.")])
        ratings, _ = load_ratings(ruta)
        assert find_rating(ratings, "CAPEX S.A.") is None

    def test_un_archivo_que_no_existe_no_rompe(self, tmp_path):
        ratings, avisos = load_ratings(tmp_path / "no_esta.json")
        assert ratings == {}
        assert avisos == []

    def test_un_archivo_roto_avisa_en_vez_de_explotar(self, tmp_path):
        destino = tmp_path / "calificaciones.json"
        destino.write_text("{esto no es json", encoding="utf-8")
        ratings, avisos = load_ratings(destino)
        assert ratings == {}
        assert len(avisos) == 1


class TestArchivoDelRepositorio:
    def test_el_archivo_versionado_carga_sin_avisos(self):
        # Hoy son todas plantillas sin completar, así que no publica ninguna
        # calificación; lo que se verifica es que el JSON sea válido y que
        # las plantillas no se cuelen como si fueran datos.
        ratings, avisos = load_ratings()
        assert avisos == []
        assert all(r.verified and r.rating for r in ratings.values())
