"""
bonds/byma_terms.py - Ficha técnica de cada especie, desde BYMA.

El panel de precios (`bonds/byma_source.py`) devuelve las 2700 especies en una
llamada, pero casi sin datos descriptivos: `description` y `securityDesc`
vienen vacíos. La ficha técnica sí los trae, aunque de a una especie por
pedido.

Qué resuelve: el emisor, la lámina mínima, la tasa de cupón y la estructura de
amortización de **todas** las ONs que cotizan, no solo de las que están en el
dataset comunitario de cronogramas. Ese dataset cubre 54 emisiones y ninguna de las más operadas del
panel —tiene las series vecinas, CP36 y CP37 donde se opera CP38 y CP40—, así
que sin esto la tabla queda con el emisor vacío y la dimensión Jurisdicción del
puntaje sin medir.

Qué NO resuelve:

  * **La ley aplicable.** BYMA tiene los campos `ley` y `paisLey` y no los
    llena: sobre 40 fichas del panel operado, `paisLey` vino vacío en las 40 y
    `ley` en 39. La jurisdicción solo puede salir del catálogo local.
  * **El cronograma de los bonos que amortizan en cuotas.** Ese detalle vive en
    `formaAmortizacion` como prosa, y extraerlo emisor por emisor sería
    adivinar. Para esos bonos la TIR sigue saliendo del cronograma ya resuelto
    de la otra fuente.

Sí permite, en cambio, reconstruir el flujo de los bonos **bullet a tasa fija**,
que son la estructura dominante: con fecha de emisión, vencimiento, tasa y la
certeza de que el capital vuelve entero al final, el flujo queda determinado.
Lo único que hay que suponer es la frecuencia de pago, que BYMA no publica.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

import requests

from bonds.byma_source import BYMA_BASE_URL, BYMA_HEADERS
from bonds.catalog import base_ticker_of

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

# Detección de estructura de amortización a partir de `formaAmortizacion`.
#
# El campo es texto libre y NO se parsea para extraer un cronograma: eso sería
# adivinar. Se usa solo para una pregunta binaria —¿devuelve todo el capital al
# vencimiento?— que sobre las respuestas reales se contesta con dos marcas y un
# veto, sin ambigüedad. Verificado contra los 20 textos distintos que devuelve
# hoy el panel operado: 8 bullet, 12 con amortización parcial, cero errores.
#
# El veto es lo que lo hace seguro: si el texto menciona cuotas o pagos en
# plural, no se considera bullet aunque nombre el vencimiento. Un texto que no
# se reconoce tampoco es bullet, así que el modo de falla es abstenerse.
_BULLET_MARKERS: Final[tuple[str, ...]] = ("AL VENCIMIENTO", "AL VENCIMENTO")
_BULLET_VETO: Final[tuple[str, ...]] = ("CUOTAS", "PAGOS")

# Detección de tasa a partir de `interes`, que llega como "FIJO 7,50%",
# "FIJO DE 5,50%" o "TASA DE REFERENCIA + MARGEN APLICABLE (2,50%)".
#
# Reconocer las variables importa tanto como leer las fijas: el motor descuenta
# un flujo determinado hoy, y el de un bono a tasa variable no lo está. Sin
# este filtro, una ON Badlar mostraría una TIR calculada sobre un cupón que no
# es el que va a pagar.
_VARIABLE_RATE_MARKERS: Final[tuple[str, ...]] = (
    "TASA DE REFERENCIA", "MARGEN", "BADLAR", "TAMAR", "CER", "VARIABLE", "MIXTA", "UVA",
)
_FIXED_RATE_MARKER: Final[str] = "FIJ"
_RATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"(\d{1,3})[,.](\d{1,4})\s*%?")

# Frecuencia de pago supuesta. BYMA NO la publica en ninguno de sus campos, y
# es el único dato del flujo que falta. Semestral es la convención dominante en
# las ONs corporativas argentinas en dólares; suponerla acota el error a unos
# 15 puntos básicos de TIR para cupones típicos (un 7,5% anual capitalizado
# semestralmente rinde 7,64% efectivo), mientras que no suponerla deja al bono
# sin TIR. Las filas calculadas así quedan marcadas como estimadas.
ASSUMED_COUPON_FREQUENCY: Final[int] = 2


def _normalize(text: object) -> str:
    """Mayúsculas, sin acentos y con los espacios colapsados, para comparar."""
    plain = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", plain).upper().strip()


@dataclass(frozen=True)
class BondReference:
    """Datos descriptivos de una especie, según la ficha técnica de BYMA."""

    ticker: str
    issuer: str | None
    currency: str | None
    min_denomination: float | None
    maturity: date | None
    issue_date: date | None
    isin: str | None
    in_default: bool
    guarantee: str | None
    # Tasa fija anual, en %. None si el cupón es variable (Badlar, CER, tasa de
    # referencia) o si el texto no se pudo leer: en los dos casos el flujo
    # futuro no está determinado y no hay nada que descontar.
    coupon_rate: float | None
    # True solo si el texto de amortización dice, sin ambigüedad, que devuelve
    # todo el capital al vencimiento. Un texto que no se reconoce da False.
    is_bullet: bool
    # Texto crudo, para poder mostrar de dónde salió cada lectura.
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


def parse_coupon_rate(raw: object) -> float | None:
    """
    Tasa fija anual del cupón, leída de `interes`. None si no es fija.

    Un cupón variable no se puede descontar: el flujo futuro no está
    determinado hoy. Devolver None ahí es lo que evita publicar la TIR de una
    ON Badlar calculada sobre un cupón que no va a pagar.
    """
    text = _normalize(raw)
    if not text or _FIXED_RATE_MARKER not in text:
        return None
    if any(marker in text for marker in _VARIABLE_RATE_MARKERS):
        return None
    match = _RATE_PATTERN.search(text)
    if not match:
        return None
    rate = float(f"{match.group(1)}.{match.group(2)}")
    return rate if 0 < rate < 200 else None


def is_bullet_amortization(raw: object) -> bool:
    """
    True solo si el capital se devuelve entero al vencimiento.

    Es una pregunta binaria sobre texto libre, no una extracción de cronograma.
    El veto por plural es lo que la hace segura: "amortizadas en 7 cuotas
    semestrales ... finalizando en la Fecha de Vencimiento" nombra el
    vencimiento y no es bullet. Lo que no se reconoce devuelve False, así que
    el modo de falla es no calcular.
    """
    text = _normalize(raw)
    if not text or any(veto in text for veto in _BULLET_VETO):
        return False
    return any(marker in text for marker in _BULLET_MARKERS)


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

    # El capital residual por debajo del nominal significa que el bono ya
    # amortizó: no puede ser bullet, diga lo que diga el texto.
    nominal = _parse_number(record.get("montoNominal"))
    residual = _parse_number(record.get("montoResidual"))
    already_amortized = bool(nominal and residual and residual < nominal)

    return BondReference(
        ticker=ticker.strip().upper(),
        issuer=_clean(record.get("emisor")),
        currency=_clean(record.get("moneda")),
        coupon_rate=parse_coupon_rate(record.get("interes")),
        is_bullet=is_bullet_amortization(record.get("formaAmortizacion")) and not already_amortized,
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
