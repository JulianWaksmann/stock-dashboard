"""
bonds/byma_source.py - Precios de ONs desde BYMA Open Data.

Es la fuente primaria de precios: BYMA es el mercado donde las ONs
efectivamente cotizan, así que su panel es el dato de origen y no una copia.
Frente al feed alternativo (data912) aporta tres cosas que el diagnóstico
`scripts/verificar_fuentes.py` dejó medidas:

  * **Más universo.** 2727 especies contra 616. data912 resultó ser casi un
    subconjunto: de sus 616, 614 están también en BYMA.
  * **Menos atraso.** Sobre las 614 en común, la mitad de los precios coincide
    exactamente y el resto difiere en una mediana de 0,17%. La diferencia no
    depende del plazo de liquidación (T1 y T2 dan el mismo resultado), así que
    es atraso de la copia, no otra convención.
  * **Más campos.** Vencimiento, moneda de la especie y cantidad de órdenes
    vienen en la misma respuesta, sin necesidad de cruzarlos contra otra fuente.

Detalles de la API, que no está documentada:

  * Es **POST**, no GET: abrirla en el navegador devuelve 405.
  * Valida que el pedido venga de una sesión iniciada en su propio sitio, así
    que hay que visitar el dashboard primero para recibir la cookie, y mandar
    cabeceras de navegador.
  * No hay contrato de estabilidad. Por eso el parseo es defensivo y el
    llamador puede caer al feed alternativo si esto falla.
"""

from __future__ import annotations

import logging
from typing import Final

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

BYMA_BASE_URL: Final[str] = "https://open.bymadata.com.ar"
BYMA_CORPORATE_BONDS_PATH: Final[str] = "vanoms-be-core/rest/api/bymadata/free/negociable-obligations"

REQUEST_TIMEOUT_SECONDS: Final[int] = 20

# Cabeceras de navegador. Sin ellas BYMA rechaza el pedido: su API está
# pensada para su propia interfaz web, no para clientes externos.
BYMA_HEADERS: Final[dict[str, str]] = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": BYMA_BASE_URL,
    "Referer": f"{BYMA_BASE_URL}/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Plazo de liquidación pedido. T2 (48 hs) es el plazo estándar de la renta
# fija local y el que más especies devuelve. El precio que informa BYMA no
# cambia entre T1 y T2 —el diagnóstico lo verificó—, lo que cambia es qué
# especies aparecen listadas.
BYMA_SETTLEMENT_PAYLOAD: Final[dict[str, object]] = {
    "excludeZeroPxAndQty": False,
    "T2": True,
    "T1": False,
    "T0": False,
}

# El precio de referencia. `settlementPrice` es el del día; cuando la especie
# no operó viene en cero y se cae al cierre anterior, que es lo que muestra
# cualquier pantalla. Esas filas quedan con volumen cero, así que el filtro de
# liquidez del panel las descarta por defecto en vez de tratarlas como frescas.
_PRICE_FIELDS: Final[tuple[str, ...]] = ("settlementPrice", "trade", "closingPrice")
_PREVIOUS_PRICE_FIELDS: Final[tuple[str, ...]] = ("previousSettlementPrice", "previousClosingPrice")

# BYMA publica varias medidas de actividad y no documenta cuál es cuál. Se
# toma la primera disponible por orden de preferencia: el monto operado es la
# mejor medida de liquidez, y las otras dos sirven de reemplazo razonable.
_VOLUME_FIELDS: Final[tuple[str, ...]] = ("volumeAmount", "volume", "tradeVolume")


def _number(record: dict, field: str) -> float:
    """Lee un campo numérico del registro, devolviendo NaN si no se puede."""
    try:
        value = float(record[field])
    except (KeyError, TypeError, ValueError):
        return np.nan
    return value if np.isfinite(value) else np.nan


def _first_positive(record: dict, fields: tuple[str, ...]) -> float:
    """
    Primer campo de la lista con un valor positivo.

    BYMA usa 0 para "no hubo", no para "cero": una punta compradora en cero
    significa que no hay punta, y tratarla como un precio de cero daría
    spreads y rendimientos absurdos.
    """
    for field in fields:
        value = _number(record, field)
        if np.isfinite(value) and value > 0:
            return value
    return np.nan


def parse_byma_bonds(payload: object) -> pd.DataFrame:
    """
    Normaliza la respuesta de BYMA al mismo formato que consume el panel.

    Es una función pura para poder testearla con respuestas fijas: la API no
    tiene contrato de estabilidad, así que lo que hay que poder verificar es
    justamente el comportamiento ante campos ausentes, en cero o con otro
    nombre.
    """
    records = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list) or not records:
        return pd.DataFrame()

    rows: list[dict] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        symbol = str(record.get("symbol") or "").strip().upper()
        if not symbol:
            continue

        price = _first_positive(record, _PRICE_FIELDS)
        previous = _first_positive(record, _PREVIOUS_PRICE_FIELDS)
        traded_today = np.isfinite(price)
        if not traded_today:
            price = previous

        # La variación solo se informa si hubo precio del día. Cayendo al cierre
        # anterior, precio y referencia son el mismo número y la cuenta da
        # 0,00%, que en pantalla se lee como "no se movió" cuando en realidad
        # significa "no operó".
        change_pct = np.nan
        if traded_today and np.isfinite(price) and np.isfinite(previous) and previous > 0:
            change_pct = (price / previous - 1.0) * 100.0

        rows.append(
            {
                "Ticker": symbol,
                "Precio": price,
                "Punta Compra": _first_positive(record, ("bidPrice",)),
                "Punta Venta": _first_positive(record, ("offerPrice",)),
                "Cant. Compra": _number(record, "quantityBid"),
                "Cant. Venta": _number(record, "quantityOffer"),
                "Volumen": _first_positive(record, _VOLUME_FIELDS),
                "Operaciones": _number(record, "numberOfOrders"),
                "Var. (%)": change_pct,
                # Campos que evitan cruzar otra fuente para saber el plazo.
                # El formato se fija explícitamente: dejando que pandas lo
                # adivine, un "09/10/2033" se interpreta como 9 de octubre o
                # como 10 de septiembre según el resto del lote, y el error no
                # se nota. Si BYMA cambia el formato, preferimos un vencimiento
                # vacío antes que uno silenciosamente equivocado.
                "Vencimiento BYMA": pd.to_datetime(
                    record.get("maturityDate"), format="ISO8601", errors="coerce"
                ),
                "Moneda BYMA": str(record.get("denominationCcy") or "").strip().upper() or None,
            }
        )

    if not rows:
        return pd.DataFrame()

    # Una especie puede repetirse entre plazos de liquidación; nos quedamos con
    # la primera aparición para no duplicar filas en el panel.
    frame = pd.DataFrame(rows)

    # Si NINGUNA especie del panel informa volumen, lo más probable no es que
    # no haya operado nada: es que BYMA renombró sus campos de volumen. Sin
    # esta marca, el filtro de liquidez —que por defecto muestra el top 50—
    # vaciaría la pantalla sin explicar por qué, y un panel vacío parece un
    # problema de red y no un cambio de esquema.
    if not (frame["Volumen"] > 0).any():
        frame.attrs["volume_missing"] = (
            "Ninguna especie informó volumen operado. Puede ser una rueda sin "
            "actividad, pero lo habitual es que BYMA haya cambiado el nombre de "
            f"sus campos de volumen (se buscan: {', '.join(_VOLUME_FIELDS)}). "
            "Mientras tanto, el filtro de liquidez no puede ordenar el panel."
        )

    # Volumen ausente y volumen cero son cosas distintas para BYMA, que informa
    # cero cuando la especie no operó; el panel usa ese dato para descartarla.
    frame["Volumen"] = frame["Volumen"].fillna(0.0)
    return frame.drop_duplicates(subset="Ticker", keep="first").reset_index(drop=True)


def fetch_byma_bond_prices() -> tuple[pd.DataFrame, str | None]:
    """
    Descarga el panel de ONs de BYMA. Devuelve `(precios, error)`.

    No propaga excepciones: un fallo vuelve como texto para que el llamador
    pueda caer a la fuente alternativa en vez de dejar la pestaña vacía.
    """
    try:
        session = requests.Session()
        session.headers.update(BYMA_HEADERS)
        # La API valida la cookie que entrega su propio sitio al cargar.
        session.get(f"{BYMA_BASE_URL}/#/dashboard", timeout=REQUEST_TIMEOUT_SECONDS)
        response = session.post(
            f"{BYMA_BASE_URL}/{BYMA_CORPORATE_BONDS_PATH}",
            json=BYMA_SETTLEMENT_PAYLOAD,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("No se pudo consultar el panel de ONs de BYMA: %s", exc)
        return pd.DataFrame(), f"BYMA no respondió ({exc})."
    except ValueError:
        logger.warning("BYMA devolvió una respuesta que no es JSON")
        return pd.DataFrame(), "BYMA devolvió una respuesta ilegible."

    prices = parse_byma_bonds(payload)
    if prices.empty:
        return prices, "BYMA respondió pero no se pudo interpretar ninguna especie."
    return prices, None
