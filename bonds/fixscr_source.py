"""
bonds/fixscr_source.py - Calificaciones vigentes publicadas por FIX SCR.

FIX SCR es la calificadora afiliada a Fitch y la que más emisores argentinos
cubre. Publica un listado de calificaciones vigentes con filtros por país,
área y tipo, paginado y renderizado en el servidor, así que se puede consultar
sin navegador y sin dependencias de parseo.

Qué se pide: **Argentina + calificación de Emisor**, en las dos áreas que
emiten obligaciones negociables (Finanzas Corporativas y Entidades
Financieras). Queda afuera Finanzas Estructuradas, que son fideicomisos y no
emisores, y son la mayor parte del listado.

Límites que conviene tener presentes:

  * **Cubre a los emisores que FIX SCR califica, no a todos.** Los que
    califican Moody's Local, Evaluadora Latinoamericana o UNTREF no aparecen
    acá y siguen necesitando carga manual.
  * **Es una página web, no un contrato.** Si FIX SCR cambia la tabla, esto
    deja de traer datos. El modo de falla es no traer nada, nunca traer algo
    equivocado: una fila que no se entiende se descarta.
  * `per-page` no admite cualquier valor: por encima de 70 el servidor
    responde 500.

No se consulta desde la aplicación. Lo usa un script que actualiza el archivo
de calificaciones cuando uno quiere, de modo que el tablero no dependa de este
sitio para dibujar, los cambios de nota queden en el historial del repositorio
y no se golpee a un tercero en cada carga de pantalla.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Final

import requests

logger = logging.getLogger(__name__)

FIXSCR_RATINGS_URL: Final[str] = "https://www.fixscr.com/calificaciones"
FIXSCR_SOURCE_NAME: Final[str] = "FIX SCR"

# El sitio declara `Disallow:` vacío en robots.txt, es decir que no restringe
# la consulta automatizada. Aun así se pide de a una página y con pausa: son
# tres pedidos por corrida, no hay motivo para apurarlos.
REQUEST_TIMEOUT_SECONDS: Final[int] = 30
PAGE_SIZE: Final[int] = 70
PAUSE_BETWEEN_PAGES: Final[float] = 0.5
MAX_PAGES: Final[int] = 30

_COUNTRY_ARGENTINA: Final[int] = 230
_AREAS: Final[dict[int, str]] = {1: "Finanzas Corporativas", 2: "Entidades Financieras"}

# NO se filtra por tipo de calificación. Filtrar por "Emisor" parecía lo
# correcto —queremos la nota de quien paga, no la de un papel suelto— y dejaba
# afuera a la mayoría: FIX califica a muchos emisores solo a nivel de EMISIÓN,
# es decir la ON concreta y no la entidad. Pan American Energy, Cresud y Loma
# Negra quedaban sin nota por eso, teniéndola.
#
# Como la nota de una emisión de deuda sin garantía real refleja la calidad
# del emisor, tomarla como su calificación es correcto. Lo que sí importa es
# quedarse con la más reciente cuando hay varias, que es lo que hace el
# llamador.

# Posición de cada dato en la fila del listado.
_COL_ENTITY: Final[int] = 0
_COL_DATE: Final[int] = 1
_COL_LONG_TERM: Final[int] = 7
_MIN_COLUMNS: Final[int] = 8

# Una nota de escala nacional argentina termina en "(arg)". Se exige para no
# tomar por calificación un texto cualquiera de la celda.
_NATIONAL_SCALE: Final[re.Pattern[str]] = re.compile(r"\(arg\)\s*$", re.IGNORECASE)
_ISO_DATE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class FixScrRating:
    """Una calificación de emisor vigente, tal como la publica FIX SCR."""

    issuer: str
    rating: str
    as_of: str
    area: str


class _RatingsTableParser(HTMLParser):
    """
    Extrae las filas de la tabla del listado.

    Con `html.parser` de la biblioteca estándar y no con pandas o BeautifulSoup
    para no sumarle al proyecto una dependencia de parseo de HTML por una sola
    página. La tabla es plana y regular, no necesita más.
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell, self._in_cell = [], True

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
        elif tag in ("td", "th") and self._row is not None:
            text = re.sub(r"\s+", " ", "".join(self._cell or [])).strip()
            self._row.append(text)
            self._in_cell = False

    def handle_data(self, data: str) -> None:
        if self._in_cell and self._cell is not None:
            self._cell.append(data)


def parse_table_rows(html: str) -> list[list[str]]:
    """Filas de datos de la tabla, sin interpretar. Solo para paginar."""
    parser = _RatingsTableParser()
    parser.feed(html)
    return [
        row for row in parser.rows
        if len(row) >= _MIN_COLUMNS and (row[_COL_ENTITY].upper() != "ENTIDAD")
    ]


def parse_ratings_page(html: str, area: str = "") -> list[FixScrRating]:
    """
    Calificaciones de emisor presentes en una página del listado.

    Se descarta toda fila que no traiga las tres cosas que hacen falta —
    entidad, fecha y una nota en escala nacional— en lugar de completarlas con
    lo que haya. El listado mezcla filas de continuación sin entidad y notas de
    corto plazo en otra columna: aceptarlas de cualquier forma sería inventar
    calificaciones.
    """
    ratings: list[FixScrRating] = []
    for row in parse_table_rows(html):
        issuer = row[_COL_ENTITY].strip()
        as_of = row[_COL_DATE].strip()
        rating = row[_COL_LONG_TERM].strip()
        if not issuer or issuer.upper() == "ENTIDAD":
            continue
        if not _ISO_DATE.match(as_of) or not _NATIONAL_SCALE.search(rating):
            continue
        ratings.append(FixScrRating(issuer=issuer, rating=rating, as_of=as_of, area=area))
    return ratings


def fetch_issuer_ratings(
    session: requests.Session | None = None,
) -> tuple[dict[str, FixScrRating], list[str]]:
    """
    Descarga las calificaciones de emisor vigentes, indexadas por nombre.

    Devuelve `(por_emisor, avisos)`. Cuando un emisor aparece más de una vez se
    conserva la calificación más reciente, que es la vigente.
    """
    http = session or requests.Session()
    http.headers.setdefault("User-Agent", "Mozilla/5.0")

    ratings: dict[str, FixScrRating] = {}
    warnings: list[str] = []

    for area_id, area_name in _AREAS.items():
        for page in range(1, MAX_PAGES + 1):
            params = {
                "per-page": PAGE_SIZE,
                "page": page,
                "CalificacionesWebSearch[paises_id]": _COUNTRY_ARGENTINA,
                "CalificacionesWebSearch[section_id]": area_id,
            }
            try:
                response = http.get(
                    FIXSCR_RATINGS_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                warnings.append(f"No se pudo consultar {area_name} (página {page}): {exc}")
                break

            # Cuántas FILAS trajo la página, no cuántas notas se pudieron
            # leer: la mayoría de las filas son calificaciones de corto plazo
            # o sin nota de largo, y se descartan. Paginar mirando las notas
            # cortaba en la primera página y perdía el 95% del listado.
            filas = parse_table_rows(response.text)
            if not filas:
                break
            page_ratings = parse_ratings_page(response.text, area=area_name)

            for record in page_ratings:
                previous = ratings.get(record.issuer)
                if previous is None or record.as_of > previous.as_of:
                    ratings[record.issuer] = record

            if len(filas) < PAGE_SIZE:
                break
            time.sleep(PAUSE_BETWEEN_PAGES)

    if not ratings:
        warnings.append(
            "El listado de FIX SCR no devolvió ninguna calificación. "
            "Lo más probable es que haya cambiado la estructura de la tabla."
        )
    return ratings, warnings
