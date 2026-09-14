"""
bonds/byma_terms.py - Ficha técnica de cada especie, desde BYMA.

El panel de precios (`bonds/byma_source.py`) devuelve las 2700 especies en una
llamada, pero casi sin datos descriptivos: `description` y `securityDesc`
vienen vacíos. La ficha técnica sí los trae, aunque de a una especie por
pedido.

Qué resuelve: el emisor, la ley aplicable y la lámina mínima de **todas** las
ONs que cotizan, no solo de las que están en el dataset comunitario de
cronogramas. Ese dataset cubre 54 emisiones y ninguna de las más operadas del
panel —tiene las series vecinas, CP36 y CP37 donde se opera CP38 y CP40—, así
que sin esto la tabla queda con el emisor vacío y la dimensión Jurisdicción del
puntaje sin medir.

Qué NO resuelve, todavía: el flujo de fondos. El cronograma de amortización
viene en `formaAmortizacion` como prosa libre, y la frecuencia de pago no
aparece como campo. Reconstruir el flujo a partir de eso sería adivinar, así
que la TIR sigue saliendo del cronograma ya resuelto de la otra fuente.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

import requests

from bonds.byma_source import BYMA_BASE_URL, BYMA_HEADERS
from bonds.catalog import LAW_ARGENTINA, LAW_NEW_YORK, base_ticker_of

logger = logging.getLogger(__name__)

BYMA_TECHNICAL_SHEET_PATH: Final[str] = (
    "vanoms-be-core/rest/api/bymadata/free/bnown/fichatecnica/especies/general"
)

REQUEST_TIMEOUT_SECONDS: Final[int] = 20

# Pedidos en paralelo. La ficha técnica es una especie por llamada, así que
# cubrir el panel operado son cientos de pedidos; sin paralelismo la primera
# carga tardaría minutos. El tope es conservador a propósito: es una API
# pública y gratuita, y no tiene sentido castigarla.
MAX_WORKERS: Final[int] = 12

# Códigos de país que se mapean a la ley aplicable del catálogo.
_FOREIGN_LAW_MARKERS: Final[tuple[str, ...]] = ("EEUU", "ESTADOS UNIDOS", "USA", "US", "NEW YORK", "NUEVA YORK")
_LOCAL_LAW_MARKERS: Final[tuple[str, ...]] = ("ARGENTINA", "ARG", "AR")


@dataclass(frozen=True)
class BondReference:
    """Datos descriptivos de una especie, según la ficha técnica de BYMA."""

    ticker: str
    issuer: str | None
    law: str | None
    currency: str | None
    min_denomination: float | None
    maturity: date | None
    issue_date: date | None
    isin: str | None
    in_default: bool
    guarantee: str | None
    # Texto crudo del cupón y de la amortización. NO se parsean para calcular:
    # se conservan para poder mostrarlos y para decidir más adelante, con datos
    # reales a la vista, si son parseables de forma confiable.
    raw_interest: str | None
    raw_amortization: str | None


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _parse_date(value: object) -> date | None:
    """
    Fecha de la ficha técnica, que llega como "2033-09-30 00:00:00.0".

    El formato se fija en lugar de dejar que se infiera: una fecha ambigua
    interpretada al revés no falla, devuelve un vencimiento equivocado.
    """
    text = _clean(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    logger.warning("Fecha con formato inesperado en la ficha técnica: %r", text)
    return None


def _parse_law(country: object, law_field: object) -> str | None:
    """
    Traduce el país de la ley aplicable a la etiqueta del catálogo.

    Se mira `paisLey` y no `ley`, que en las respuestas observadas viene vacío.
    Un país que no se reconoce devuelve None: el panel prefiere no informar la
    jurisdicción antes que clasificarla mal, porque es una de las dimensiones
    que puntúa.
    """
    text = (_clean(country) or _clean(law_field) or "").upper()
    if not text:
        return None
    if any(marker in text for marker in _FOREIGN_LAW_MARKERS):
        return LAW_NEW_YORK
    if any(marker in text for marker in _LOCAL_LAW_MARKERS):
        return LAW_ARGENTINA
    logger.info("País de ley no reconocido en la ficha técnica: %r", text)
    return None


def _parse_number(value: object) -> float | None:
    try:
        return float(str(value).strip().replace(".", "").replace(",", ".")) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_technical_sheet(ticker: str, payload: object) -> BondReference | None:
    """
    Convierte la respuesta de la ficha técnica en un `BondReference`.

    Función pura, para poder testearla con respuestas fijas: la API no tiene
    contrato de estabilidad y lo que hay que poder verificar es qué pasa cuando
    un campo desaparece o cambia de forma.
    """
    records = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        return None

    record = records[0]
    # Un registro vacío es "no hay ficha", no "una ficha con todo en blanco":
    # devolver un BondReference lleno de None haría creer al panel que la
    # consulta trajo datos.
    if not record:
        return None

    return BondReference(
        ticker=ticker.strip().upper(),
        issuer=_clean(record.get("emisor")),
        law=_parse_law(record.get("paisLey"), record.get("ley")),
        currency=_clean(record.get("moneda")),
        min_denomination=_parse_number(record.get("denominacionMinima")),
        maturity=_parse_date(record.get("fechaVencimiento")),
        issue_date=_parse_date(record.get("fechaEmision")),
        isin=_clean(record.get("codigoIsin")),
        in_default=bool(record.get("default")),
        guarantee=_clean(record.get("tipoGarantia")),
        raw_interest=_clean(record.get("interes")),
        raw_amortization=_clean(record.get("formaAmortizacion")),
    )


def _fetch_one(session: requests.Session, ticker: str) -> BondReference | None:
    try:
        response = session.post(
            f"{BYMA_BASE_URL}/{BYMA_TECHNICAL_SHEET_PATH}",
            data=json.dumps({"symbol": ticker}),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return parse_technical_sheet(ticker, response.json())
    except (requests.RequestException, ValueError):
        logger.warning("No se pudo obtener la ficha técnica de %s", ticker, exc_info=True)
        return None


def fetch_byma_terms(tickers: list[str]) -> tuple[dict[str, BondReference], str | None]:
    """
    Descarga las fichas técnicas de una lista de especies, en paralelo.

    Devuelve `(referencias_por_raíz_de_ticker, error)`. Se indexa por raíz
    —sin la letra de especie— porque las tres especies de un bono comparten
    emisor, ley y lámina: alcanza con pedir una.

    Un fallo individual no interrumpe al resto: se registra y esa especie queda
    sin datos descriptivos, que es mejor que dejar el panel entero sin ellos.
    """
    unique = sorted({base_ticker_of(t): t for t in tickers if t}.items())
    if not unique:
        return {}, None

    references: dict[str, BondReference] = {}
    try:
        session = requests.Session()
        session.headers.update(BYMA_HEADERS)
        session.get(f"{BYMA_BASE_URL}/#/dashboard", timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        logger.warning("No se pudo iniciar sesión contra BYMA para las fichas técnicas: %s", exc)
        return {}, f"No se pudieron consultar las fichas técnicas de BYMA ({exc})."

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch_one, session, ticker): base for base, ticker in unique}
        for future in concurrent.futures.as_completed(futures):
            base = futures[future]
            try:
                reference = future.result()
            except Exception:
                logger.exception("El hilo de la ficha técnica de %s terminó con error", base)
                continue
            if reference is not None:
                references[base] = reference

    if not references:
        return {}, "Ninguna ficha técnica de BYMA respondió; el panel queda sin emisor ni ley."

    missing = len(unique) - len(references)
    if missing:
        logger.info("%d de %d fichas técnicas no respondieron", missing, len(unique))
    return references, None
