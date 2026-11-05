"""
cartera/modelo.py - Lo que comparten los lectores de cada broker.

Cada broker exporta otra cosa: Balanz da resultados ya calculados por lote,
Cocos da el libro de movimientos crudo. Los dos lectores (`cartera/balanz.py`,
`cartera/cocos.py`) devuelven la misma `Cartera`: operaciones cerradas y lotes
abiertos en dólares MEP, con las mismas columnas. Desde ahí en adelante
(`cartera/informe.py`) nadie sabe de qué broker vino cada fila, salvo por la
columna `broker`, que sirve para filtrar y para mostrar.

Puro: sin red y sin Streamlit.

El activo se identifica por su **ticker de BYMA**, que es el mismo en todos
los brokers argentinos: MSFT de Balanz y MSFT de Cocos son el mismo activo y
el informe los suma en una fila. Lo que no se mezcla son los lotes: lo que se
compró en un broker solo se vende en ese broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

BROKER_BALANZ = "Balanz"
BROKER_COCOS = "Cocos"

MOV_VENTA = "Venta"
MOV_DIVIDENDO = "Dividendo"
MOV_CUPON = "Cupón"
MOV_INTERES = "Interés caución"

# Tipos de activo que se muestran. Cada lector traduce los suyos a estos; lo
# que un lector no sepa clasificar entra con el nombre que le da el broker.
CLASE_CEDEAR = "CEDEARs"
CLASE_ACCION = "Acciones argentinas"
CLASE_FCI = "Fondos (FCI)"
CLASE_CAUCION = "Caución"

# Ticker con el que se agrupan los intereses de caución. Es el que usa
# Balanz; Cocos no le pone ticker, así que adopta este para que los dos se
# sumen en la misma fila.
TICKER_CAUCION = "PESOS"

COLUMNAS_OPERACIONES = [
    "id", "broker", "fecha", "anio", "ticker", "descripcion", "clase", "movimiento",
    "fecha_compra", "dias", "cantidad", "precio_compra", "moneda_compra", "precio_venta",
    "moneda_venta", "mep_compra", "mep_venta", "costo_usd", "venta_usd", "gastos_ars",
    "gastos_usd", "resultado_usd", "cobro_monto", "cobro_moneda", "cobro_usd",
]
COLUMNAS_LOTES = ["broker", "ticker", "descripcion", "clase", "fecha_compra", "cantidad", "costo_usd"]
COLUMNAS_NO_RECONOCIDOS = ["broker", "fecha", "ticker", "descripcion", "movimiento", "motivo"]


class ExportInvalido(ValueError):
    """El archivo no es un export que sepamos leer. El mensaje es para mostrar."""


@dataclass(frozen=True)
class Cartera:
    operaciones: pd.DataFrame
    lotes_abiertos: pd.DataFrame
    no_reconocidos: pd.DataFrame
    fecha_corte: str
    # Fecha hasta la que informa cada broker. Al combinar, `fecha_corte` es la
    # más reciente; al filtrar por un broker se vuelve a la suya, o un reporte
    # de Balanz bajado en marzo se mediría como si llegara hasta octubre.
    cortes: dict = field(default_factory=dict)


def normalizar_ticker(t) -> str:
    return "" if not isinstance(t, str) else t.strip().upper()


def armar_operaciones(filas: list[dict]) -> pd.DataFrame:
    """Filas sueltas → tabla ordenada, con `anio`. Los `id` se ponen al combinar."""
    ops = pd.DataFrame(filas).reindex(columns=COLUMNAS_OPERACIONES)
    if ops.empty:
        return ops
    ops["anio"] = ops["fecha"].str[:4]
    return ops.sort_values(["fecha", "broker", "ticker"], kind="stable").reset_index(drop=True)


def _cortes(c: Cartera) -> dict[str, str]:
    """Corte de cada broker de una cartera: el propio si ya lo trae, si no su `fecha_corte`."""
    if c.cortes:
        return dict(c.cortes)
    brokers = set(c.operaciones.get("broker", pd.Series(dtype=str)).dropna()) | set(
        c.lotes_abiertos.get("broker", pd.Series(dtype=str)).dropna()
    )
    return {b: c.fecha_corte for b in brokers}


def combinar(carteras: list[Cartera]) -> Cartera:
    """Une las carteras de varios archivos o brokers en una sola."""
    ops = [c.operaciones for c in carteras if not c.operaciones.empty]
    lotes = [c.lotes_abiertos for c in carteras if not c.lotes_abiertos.empty]
    raras = [c.no_reconocidos for c in carteras if not c.no_reconocidos.empty]
    cortes: dict[str, str] = {}
    for c in carteras:
        for broker, fecha in _cortes(c).items():
            cortes[broker] = max(fecha, cortes.get(broker, fecha))
    op = pd.concat(ops, ignore_index=True) if ops else pd.DataFrame(columns=COLUMNAS_OPERACIONES)
    if not op.empty:
        op = op.sort_values(["fecha", "broker", "ticker"], kind="stable").reset_index(drop=True)
        op["id"] = range(1, len(op) + 1)
    return Cartera(
        operaciones=op,
        lotes_abiertos=pd.concat(lotes, ignore_index=True) if lotes else pd.DataFrame(columns=COLUMNAS_LOTES),
        no_reconocidos=pd.concat(raras, ignore_index=True) if raras else pd.DataFrame(columns=COLUMNAS_NO_RECONOCIDOS),
        fecha_corte=max(c.fecha_corte for c in carteras),
        cortes=cortes,
    )


def filtrar_broker(c: Cartera, broker: str | None) -> Cartera:
    """La cartera de un solo broker; `None` la deja entera."""
    if broker is None:
        return c

    def f(df):
        return df[df["broker"] == broker].reset_index(drop=True) if not df.empty else df

    corte = c.cortes.get(broker, c.fecha_corte)
    return Cartera(f(c.operaciones), f(c.lotes_abiertos), f(c.no_reconocidos), corte, {broker: corte})
