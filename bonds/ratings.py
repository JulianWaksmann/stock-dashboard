"""
bonds/ratings.py - Calificaciones crediticias de los emisores, desde un archivo local.

Por qué un archivo del repositorio y no una descarga: **no existe fuente
pública y gratuita que publique calificaciones en formato consultable por
máquina**. Se verificó una por una:

  * La ficha técnica de BYMA tiene 19 campos y ninguno de calificación.
  * El dataset comunitario de cronogramas tiene cuatro campos: ticker,
    nombre, vencimiento y flujos.
  * La CNV exige que toda emisión con oferta pública esté calificada, pero
    publica esa calificación dentro del prospecto y sus suplementos, en PDF.
  * Las calificadoras registradas (FIX SCR, Moody's Local Argentina,
    Evaluadora Latinoamericana, UNTREF ACR) publican informes, no una API.

Las calificaciones son además dato propietario de cada calificadora, así que
tampoco es probable que aparezca un feed abierto más adelante.

Se indexa por **emisor y no por especie**: una calificación es del emisor (o
del programa), no de cada clase de ON por separado, así que una entrada cubre
todas las series del mismo emisor. Son ~50 emisores contra ~120 bonos.

El matcheo es por nombre normalizado porque las dos fuentes de precios
escriben distinto al mismo emisor —"ARCOR S.A.I.C." y "Arcor", "IRSA
INVERSIONES Y REPRESENTACIONES S.A." e "IRSA"—, y con el texto crudo como
clave la mitad del panel quedaría sin calificación aunque el dato esté
cargado.

Ninguna entrada se da por buena sin `verificado: true`. Una calificación
equivocada es peor que ninguna: se lee como dato duro, y a diferencia de un
cupón mal cargado no hay ninguna otra columna que la contradiga.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

DEFAULT_RATINGS_PATH: Final[Path] = Path(__file__).resolve().parent.parent / "data" / "calificaciones.json"

# Formas societarias que no distinguen al emisor. Se quitan antes de comparar
# para que "ARCOR S.A.I.C." y "Arcor" caigan en la misma clave.
_LEGAL_SUFFIXES: Final[tuple[str, ...]] = (
    "SOCIEDAD ANONIMA",
    "SAICYF", "SAIC", "SACIF", "SAIF", "SAU", "SAS", "SRL", "SCA",
    "S A I C Y F", "S A I C", "S A C I F", "S A U", "S A S", "S R L", "S L", "S A",
    "SUCURSAL ARGENTINA",
    "CIA FINANCIERA", "COMPANIA FINANCIERA",
)


def normalize_issuer(name: object) -> str:
    """
    Clave comparable de un emisor: sin acentos, sin puntuación, sin forma
    societaria y sin espacios de más.

    Es deliberadamente agresiva. El costo de normalizar de más es unir dos
    emisores parecidos; el de normalizar de menos es que el mismo emisor
    escrito de dos formas quede sin calificación, que es lo que efectivamente
    pasa con las dos fuentes de precios que usa el panel.
    """
    plain = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    plain = re.sub(r"[^A-Za-z0-9 ]+", " ", plain).upper()
    plain = re.sub(r"\s+", " ", plain).strip()
    for _ in range(3):  # Un nombre puede arrastrar más de un sufijo encadenado.
        for suffix in _LEGAL_SUFFIXES:
            if plain.endswith(" " + suffix):
                plain = plain[: -len(suffix) - 1].strip()
                break
        else:
            break
    return plain


@dataclass(frozen=True)
class IssuerRating:
    """Calificación de un emisor, con su procedencia."""

    issuer: str
    rating: str
    agency: str
    scale: str
    as_of: str
    source: str
    verified: bool

    @property
    def label(self) -> str:
        """Texto para la tabla: la nota y quién la puso."""
        if not self.rating:
            return ""
        return f"{self.rating} ({self.agency})" if self.agency else self.rating


def load_ratings(path: Path | str | None = None) -> tuple[dict[str, IssuerRating], list[str]]:
    """
    Lee el archivo de calificaciones y devuelve `(por_clave_normalizada, avisos)`.

    Solo entran las entradas con `verificado: true` y una calificación no
    vacía. El archivo se versiona con los emisores ya cargados y la nota en
    blanco, así que la mayoría de las entradas son plantillas a completar: sin
    este filtro, cada plantilla se mostraría como si fuera un dato.
    """
    target = Path(path) if path is not None else DEFAULT_RATINGS_PATH
    if not target.exists():
        return {}, []

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("No se pudo leer %s: %s", target.name, exc)
        return {}, [f"No se pudo leer el archivo de calificaciones ({target.name}): {exc}"]

    entries = payload.get("emisores")
    if not isinstance(entries, list):
        return {}, [f"{target.name} no tiene una lista 'emisores'."]

    ratings: dict[str, IssuerRating] = {}
    warnings: list[str] = []
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            warnings.append(f"Entrada {position} de {target.name} ignorada: no es un objeto.")
            continue

        issuer = str(entry.get("emisor") or "").strip()
        rating = str(entry.get("calificacion") or "").strip()
        if not issuer:
            warnings.append(f"Entrada {position} de {target.name} ignorada: sin 'emisor'.")
            continue
        if not rating or not bool(entry.get("verificado")):
            # Plantilla sin completar o sin verificar: no es un error.
            continue

        record = IssuerRating(
            issuer=issuer,
            rating=rating,
            agency=str(entry.get("agencia") or "").strip(),
            scale=str(entry.get("escala") or "").strip(),
            as_of=str(entry.get("fecha") or "").strip(),
            source=str(entry.get("fuente") or "").strip(),
            verified=True,
        )

        # Los alias son los nombres tal como los escriben las fuentes de
        # precios. Se indexan todos contra el mismo registro.
        names = [issuer, *(entry.get("alias") or [])]
        for name in names:
            key = normalize_issuer(name)
            if key:
                ratings[key] = record

    return ratings, warnings


def find_rating(ratings: dict[str, IssuerRating], issuer: object) -> IssuerRating | None:
    """Calificación del emisor, comparando por nombre normalizado."""
    if not ratings:
        return None
    return ratings.get(normalize_issuer(issuer))


# Escalera de calificaciones, de peor a mejor. El índice en esta lista es el
# orden de la nota; el texto exacto de cada agencia se normaliza contra ella.
#
# Conviven las dos notaciones porque en el panel conviven las dos familias de
# calificadoras: la de letras (S&P, Fitch, FIX SCR, Evaluadora) y la de
# Moody's. Son escalas equivalentes peldaño a peldaño, así que se mapean a los
# mismos valores y quedan comparables entre sí.
_RATING_LADDER: Final[tuple[tuple[str, ...], ...]] = (
    ("D", "RD", "SD", "C"),
    ("CC", "CA"),
    ("CCC-", "CAA3"),
    ("CCC", "CAA2"),
    ("CCC+", "CAA1"),
    ("B-", "B3"),
    ("B", "B2"),
    ("B+", "B1"),
    ("BB-", "BA3"),
    ("BB", "BA2"),
    ("BB+", "BA1"),
    ("BBB-", "BAA3"),
    ("BBB", "BAA2"),
    ("BBB+", "BAA1"),
    ("A-", "A3"),
    ("A", "A2"),
    ("A+", "A1"),
    ("AA-", "AA3"),
    ("AA", "AA2"),
    ("AA+", "AA1"),
    ("AAA", "AAA"),
)

_RATING_RANKS: Final[dict[str, int]] = {
    nota: posicion
    for posicion, peldano in enumerate(_RATING_LADDER)
    for nota in peldano
}

# Sufijos de escala nacional que no cambian el peldaño: "AAA(arg)", "AAA.ar"
# y "AAA" son la misma nota dentro de su propia escala. Cuál es esa escala lo
# dice el campo `escala`, no el sufijo, y por eso se descarta acá.
_SCALE_SUFFIX: Final[re.Pattern[str]] = re.compile(r"\((?:ARG|AR|BOL|PY|UY)\)|\.(?:ARG|AR)$")


def rating_rank(rating: object) -> int | None:
    """
    Peldaño de una calificación: 0 es default, 20 es la nota máxima.

    Devuelve None si la nota no se reconoce, en vez de adivinar un peldaño.
    Una calificación mal ubicada en la escalera no se nota en pantalla y
    mueve el puntaje, así que el modo de falla correcto es abstenerse.

    Las perspectivas y los avisos ("estable", "en revisión", "CreditWatch") se
    ignoran: modifican la expectativa, no la nota vigente.
    """
    texto = unicodedata.normalize("NFKD", str(rating or "")).encode("ascii", "ignore").decode()
    texto = texto.upper().strip()
    texto = _SCALE_SUFFIX.sub("", texto).strip()
    # Se corta en el primer separador: "AA+ (estable)" o "BBB / perspectiva".
    texto = re.split(r"[\s/,;(]", texto, maxsplit=1)[0].strip()
    return _RATING_RANKS.get(texto)
