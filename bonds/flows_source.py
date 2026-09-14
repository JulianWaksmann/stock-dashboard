"""
bonds/flows_source.py - Cronogramas de pago de ONs publicados por terceros.

El catálogo local (`bonds/catalog.py`) describe las condiciones de emisión y
permite calcular todo, pero hay que cargarlo a mano bono por bono. Esta es la
otra mitad del problema: una fuente que ya publica el **cronograma de pagos
resuelto** de las ONs más operadas, de modo que el panel tenga cobertura sin
mantenimiento manual.

La fuente es el archivo de configuración del proyecto abierto `rendimientos-ar`
(licencia ISC), que publica, por cada ON en dólares, la lista de pagos futuros
con fecha e importe por cada 1 de valor nominal.

Dos límites que conviene tener presentes, y que el panel expone en pantalla:

  * Es un dataset **comunitario**, mantenido a mano por terceros. No es
    autoritativo: puede quedar desactualizado o incompleto, igual que el
    catálogo local. Sirve para comparar rendimientos, no para liquidar.
  * Publica el **total** de cada pago, sin separar renta de amortización. Eso
    alcanza para TIR, duration y convexidad, pero no para paridad, valor
    técnico ni vida promedio, que necesitan saber cuánto de cada pago es
    capital. Esas métricas quedan en blanco salvo que el bono también esté en
    el catálogo local.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

import requests

from bonds.bond_math import FACE_VALUE, CashFlow
from bonds.catalog import base_ticker_of

logger = logging.getLogger(__name__)

# Archivo de configuración de https://github.com/arisbdar/rendimientos-ar,
# leído directamente del repositorio para tomar siempre la última versión
# publicada en lugar de una copia congelada acá.
COMMUNITY_FLOWS_URL: Final[str] = (
    "https://raw.githubusercontent.com/arisbdar/rendimientos-ar/main/public/config.json"
)

COMMUNITY_FLOWS_SOURCE_NAME: Final[str] = "rendimientos-ar"

REQUEST_TIMEOUT_SECONDS: Final[int] = 15

# Los importes del dataset vienen por cada 1 de valor nominal; el motor de
# cálculo trabaja por cada 100, que es la convención de cotización local.
_AMOUNT_SCALE: Final[float] = FACE_VALUE


@dataclass(frozen=True)
class BondFlows:
    """Cronograma de pagos de una ON, sin desglose entre renta y capital."""

    base_ticker: str
    quote_ticker: str
    issuer: str
    maturity: date
    cashflows: tuple[CashFlow, ...]
    currency: str = "USD"
    source: str = COMMUNITY_FLOWS_SOURCE_NAME


def parse_community_flows(payload: dict) -> dict[str, BondFlows]:
    """
    Convierte el JSON de la fuente en cronogramas indexados por raíz de ticker.

    Se indexa por la raíz del ticker de cotización (`ticker_d912`) y no por la
    clave del diccionario original: esas claves son etiquetas internas del
    proyecto de origen y no siempre coinciden con la especie que cotiza (hay
    entradas bajo "HBC" cuyo ticker real es HBCDD). La raíz del ticker es el
    único identificador que se puede cruzar contra el feed de precios.

    Las entradas mal formadas se descartan con un aviso en el log en lugar de
    abortar: es un archivo de terceros, y una sola fila rota no debería dejar
    el panel sin cronogramas.
    """
    raw_bonds = payload.get("ons")
    if not isinstance(raw_bonds, dict):
        return {}

    flows_by_base: dict[str, BondFlows] = {}
    for key, entry in raw_bonds.items():
        try:
            quote_ticker = str(entry["ticker_d912"]).strip().upper()
            maturity = datetime.strptime(str(entry["vencimiento"]).strip(), "%Y-%m-%d").date()
            schedule = tuple(
                sorted(
                    (
                        CashFlow.unsplit(
                            datetime.strptime(str(flow["fecha"]).strip(), "%Y-%m-%d").date(),
                            float(flow["monto"]) * _AMOUNT_SCALE,
                        )
                        for flow in entry["flujos"]
                    ),
                    key=lambda flow: flow.date,
                )
            )
            if not quote_ticker or not schedule:
                raise ValueError("entrada sin ticker o sin cronograma")
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Entrada '%s' del dataset de cronogramas ignorada: %s", key, exc)
            continue

        base = base_ticker_of(quote_ticker)
        flows_by_base[base] = BondFlows(
            base_ticker=base,
            quote_ticker=quote_ticker,
            issuer=str(entry.get("nombre") or base).strip(),
            maturity=maturity,
            cashflows=schedule,
        )
    return flows_by_base


def fetch_community_flows(url: str = COMMUNITY_FLOWS_URL) -> tuple[dict[str, BondFlows], str | None]:
    """
    Descarga los cronogramas publicados. Devuelve `(cronogramas, error)`.

    Un fallo acá no es fatal: el panel sigue funcionando con el catálogo local
    y con los precios, así que el error vuelve como texto para mostrar y no
    como excepción.
    """
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("No se pudieron descargar los cronogramas de pago desde %s: %s", url, exc)
        return {}, f"No se pudieron descargar los cronogramas de pago de las ONs ({exc})."
    except ValueError:
        logger.warning("El dataset de cronogramas no devolvió JSON válido")
        return {}, "El dataset de cronogramas de pago devolvió una respuesta ilegible."

    flows = parse_community_flows(payload)
    if not flows:
        return {}, "El dataset de cronogramas de pago no trajo ninguna ON."
    return flows, None
