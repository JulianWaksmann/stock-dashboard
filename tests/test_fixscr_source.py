"""
Tests del parseo del listado de FIX SCR (`bonds/fixscr_source.py`).

Es una página web de terceros sin contrato de estabilidad, así que lo que hay
que fijar es el comportamiento ante lo inesperado: el modo de falla correcto es
no traer nada, nunca traer una calificación inventada.
"""

from bonds.fixscr_source import parse_ratings_page

FILA = (
    "<tr><td>{entidad}</td><td>{fecha}</td><td>Argentina</td><td>Finanzas Corporativas</td>"
    "<td>Energia</td><td>Emisor</td><td>{corto}</td><td>{largo}</td>"
    "<td>Perspectiva Estable</td><td>Confirma</td></tr>"
)


def pagina(*filas: str) -> str:
    cabecera = (
        "<table><thead><tr><th>ENTIDAD</th><th>FECHA</th><th>PAÍS</th><th>AREA</th>"
        "<th>SECTOR</th><th>TIPO</th><th>CORTO</th><th>LARGO</th><th>PERSPECTIVA</th>"
        "<th>ESTADO</th></tr></thead><tbody>"
    )
    return cabecera + "".join(filas) + "</tbody></table>"


def fila(entidad="YPF S.A.", fecha="2026-07-07", corto="", largo="AAA(arg)") -> str:
    return FILA.format(entidad=entidad, fecha=fecha, corto=corto, largo=largo)


class TestLoQueSiEsUnaCalificacion:
    def test_lee_entidad_nota_y_fecha(self):
        notas = parse_ratings_page(pagina(fila()), area="Finanzas Corporativas")
        assert len(notas) == 1
        assert notas[0].issuer == "YPF S.A."
        assert notas[0].rating == "AAA(arg)"
        assert notas[0].as_of == "2026-07-07"
        assert notas[0].area == "Finanzas Corporativas"

    def test_lee_varias_filas(self):
        html = pagina(fila("YPF S.A."), fila("ARCOR S.A.I.C.", largo="AA+(arg)"))
        assert len(parse_ratings_page(html)) == 2


class TestLoQueSeDescarta:
    def test_el_encabezado_no_es_una_calificacion(self):
        assert parse_ratings_page(pagina()) == []

    def test_una_fila_sin_entidad_se_descarta(self):
        # El listado trae filas de continuación de la misma emisión, sin
        # entidad. Tomarlas sería atribuirle la nota al emisor equivocado.
        assert parse_ratings_page(pagina(fila(entidad=""))) == []

    def test_una_nota_que_no_es_de_escala_nacional_se_descarta(self):
        # Sin el sufijo "(arg)" no hay forma de saber que la celda es una nota.
        assert parse_ratings_page(pagina(fila(largo="Confirma"))) == []
        assert parse_ratings_page(pagina(fila(largo=""))) == []

    def test_una_fecha_con_otro_formato_se_descarta(self):
        assert parse_ratings_page(pagina(fila(fecha="07/07/2026"))) == []

    def test_una_fila_corta_se_descarta(self):
        assert parse_ratings_page("<table><tr><td>YPF</td><td>2026-01-01</td></tr></table>") == []

    def test_una_pagina_sin_tabla_no_rompe(self):
        assert parse_ratings_page("<html><body>Error 500</body></html>") == []
        assert parse_ratings_page("") == []

    def test_solo_se_toma_la_nota_de_largo_plazo(self):
        # La de corto plazo vive en otra columna y usa otra escala (A1+(arg)).
        notas = parse_ratings_page(pagina(fila(corto="A1+(arg)", largo="AA(arg)")))
        assert len(notas) == 1
        assert notas[0].rating == "AA(arg)"
