"""
cartera/balanz.py - Lee el export "resultados por info completa" de Balanz.

Es el único punto que conoce el formato del Excel. Devuelve una `Cartera`
(`cartera/modelo.py`) en dólares MEP; todo lo que viene después trabaja sobre
esa tabla y no vuelve a mirar nombres de columnas de Balanz.

Puro: recibe bytes, no toca la red ni Streamlit. El archivo lo sube una
persona cualquiera, así que se lo trata como dato no confiable: una hoja o
una columna que falta es un `ExportInvalido` con un mensaje para mostrar, no
un `KeyError`.

Lo que trae el export, medido sobre uno real:

  * `resultados_por_realizado`: una fila por **lote vendido** (`Orden`), por
    cobro (`Dividendo`, `Cupón`, `Caución - Pase - Cheque`) y por lote que
    sigue abierto (`No Realizado`, repetido en la otra hoja). Cada fila trae
    el MEP del día de compra y del día de venta o cobro: no hace falta buscar
    ningún tipo de cambio afuera.
  * `resultados_por_lotes_finales`: los lotes que siguen en cartera. Ojo con
    los nombres: `Fecha` es la fecha de **compra** y `Fecha Lote` la del
    reporte.
  * Los precios son por unidad (un bono en pesos a 195,40 es por nominal, no
    cada 100) y `Gastos` está **siempre en pesos**, aunque la operación sea en
    dólares.
  * `Moneda Venta` describe la especie, no el cobro. Los dividendos de CEDEARs
    vienen en dólares y dicen "Dólares C.V. 7000", pero en el export medido
    los cupones de ONs dicen lo mismo y vienen en pesos: 51.649 de cupón sobre
    996 nominales solo cierra en pesos. Como eso puede no valer para todas las
    cuentas, la moneda de un cupón se decide **por el monto**: se divide por
    los nominales que se tenían ese día (reconstruidos con los lotes) y se
    elige la lectura —pesos al MEP de ese día, o dólares— que da un pago por
    nominal más cercano a uno típico (`_CUPON_TIPICO_POR_NOMINAL`). Un corte
    fijo no sirve: con el MEP de 2018 (unos 38) un cupón en pesos por nominal
    cae en el rango de uno en dólares. Si no hay tenencia de ese bono en el
    archivo, no hay cómo medirlo y el cupón va a `no_reconocidos`.
  * El vencimiento de una ON puede llegar como `Orden` con `Operacion Venta`
    "Renta y Amortización" y un precio de venta negativo. Ahí se toma el
    rescate a la par: 1 por nominal.

Un movimiento que no está en `MOVIMIENTOS` no se adivina: va a
`no_reconocidos` y queda fuera de los totales. Un tipo de activo que no está
en `CLASES` sí entra, con el nombre que le da Balanz: para sumar resultados
alcanza con saber que es un activo, no qué clase de activo es.
"""

from __future__ import annotations

import io
import math
import zipfile
from datetime import date

import pandas as pd

from cartera.modelo import (
    BROKER_BALANZ,
    CLASE_ACCION,
    CLASE_CAUCION,
    CLASE_CEDEAR,
    CLASE_FCI,
    COLUMNAS_LOTES,
    COLUMNAS_NO_RECONOCIDOS,
    MOV_CUPON,
    MOV_DIVIDENDO,
    MOV_INTERES,
    MOV_VENTA,
    Cartera,
    ExportInvalido,
    armar_operaciones,
    normalizar_ticker,
)

HOJA_REALIZADO = "resultados_por_realizado"
HOJA_LOTES = "resultados_por_lotes_finales"

COLUMNAS_REALIZADO = (
    "Cantidad", "Descripcion", "Fecha", "FechaCompra", "Gastos",
    "Moneda Compra", "Moneda Venta", "Precio Compra", "PrecioVenta",
    "Ticker", "Tipo", "Tipo Movimiento", "Cupones", "Dividendos", "Intereses",
    "OperacionCompraDolarMEP", "OperacionVentaDolarMEP",
)
COLUMNAS_HOJA_LOTES = (
    "Cantidad", "Descripcion", "Fecha", "Fecha Lote", "Moneda",
    "Precio Compra", "Ticker", "Tipo", "DolarMEP",
)

# Tipo de activo de Balanz → nombre que se muestra. Lo que no está acá se
# muestra con el nombre de Balanz (ver docstring).
CLASES = {
    "Cedears": CLASE_CEDEAR,
    "Acciones": CLASE_ACCION,
    "Fondos": CLASE_FCI,
    "Corporativos - Dólar": "ONs en dólares",
    "Corporativos - ARS": "ONs en pesos",
    "Bonos - Dólar": "Bonos en dólares",
    "Bonos - CER": "Bonos y letras CER",
    "Letras - CER": "Bonos y letras CER",
    "Bonos - ARS": "Tasa fija en pesos",
    "Letras - ARS": "Tasa fija en pesos",
    "Efectivo": CLASE_CAUCION,
}

# Tipo Movimiento de Balanz → movimiento del informe. `None` marca lo que se
# reconoce pero no es una operación cerrada (los lotes abiertos se leen de su
# propia hoja).
MOVIMIENTOS = {
    "Orden": MOV_VENTA,
    "Dividendo": MOV_DIVIDENDO,
    "Cupón": MOV_CUPON,
    "Caución - Pase - Cheque": MOV_INTERES,
    "No Realizado": None,
}

# Lo que paga un bono en dólares por nominal en un cupón típico (3%). Sirve de
# referencia para elegir entre leer el monto en pesos o en dólares: se toma la
# lectura cuyo pago por nominal queda más cerca de este, en escala logarítmica.
# Entre las dos lecturas hay un factor MEP (de 38 a más de 1.500), así que la
# equivocada siempre queda lejísimos.
_CUPON_TIPICO_POR_NOMINAL = 0.03

# Columna donde viene el monto cobrado, por movimiento de renta.
_COLUMNA_COBRO = {
    MOV_DIVIDENDO: "Dividendos",
    MOV_CUPON: "Cupones",
    MOV_INTERES: "Intereses",
}


def moneda(texto) -> str | None:
    """'Pesos' → ARS; 'Dólares', 'Dólares C.V. 7000', 'US Dollar (Cable)' → USD."""
    if not isinstance(texto, str):
        return None
    t = texto.strip().lower()
    if t.startswith("peso"):
        return "ARS"
    if "dólar" in t or "dolar" in t or "dollar" in t or t.startswith("usd"):
        return "USD"
    return None


def _a_usd(monto: float, mon: str | None, mep: float) -> float | None:
    if mon == "USD":
        return monto
    if mon == "ARS" and mep and mep > 0:
        return monto / mep
    return None


def _fecha(serie: pd.Series) -> pd.Series:
    """
    Fechas a ISO. Acepta lo que puede venir en un xlsx: celdas de fecha, texto
    ISO (lo que trae Balanz), texto dd/mm/aaaa y números de serie de Excel.
    """
    def una(v):
        if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
            return None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            # Número de serie de Excel: días desde el 30/12/1899.
            return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(v))).strftime("%Y-%m-%d")
        if isinstance(v, (pd.Timestamp, date)):
            return pd.Timestamp(v).strftime("%Y-%m-%d")
        t = str(v).strip()[:10]
        for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return pd.to_datetime(t, format=formato).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    return serie.map(una)


class _SinMoneda(ValueError):
    """Un cupón cuya moneda no se puede deducir (no hay nominales de ese bono en el reporte)."""


class _DatoIlegible(ValueError):
    """Una celda numérica que no es un número. La fila se lista, no se adivina."""


def _num(v) -> float:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        raise _DatoIlegible(str(type(v).__name__)) from None


def _texto(v) -> str:
    return "" if pd.isna(v) else str(v).strip()


# Un reporte real pesa unos cientos de KB descomprimido. Un xlsx es un zip:
# uno chico puede inflarse a gigas al abrirlo y tumbar el servidor, que es
# compartido. Se mide antes de abrir.
_MAX_DESCOMPRIMIDO = 100 * 1024 * 1024


def _leer_hojas(contenido: bytes) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        tamanio = sum(i.file_size for i in zipfile.ZipFile(io.BytesIO(contenido)).infolist())
    except zipfile.BadZipFile as exc:
        raise ExportInvalido(
            "No pudimos abrir el archivo. Tiene que ser el Excel (.xlsx) tal como lo descarga Balanz."
        ) from exc
    if tamanio > _MAX_DESCOMPRIMIDO:
        raise ExportInvalido("El Excel es demasiado grande para un reporte de Balanz.")
    try:
        hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None)
    except Exception as exc:  # openpyxl tira varios tipos según qué esté roto
        raise ExportInvalido(
            "No pudimos abrir el archivo. Tiene que ser el Excel (.xlsx) tal "
            "como lo descarga Balanz."
        ) from exc
    faltan = [h for h in (HOJA_REALIZADO, HOJA_LOTES) if h not in hojas]
    if faltan:
        raise ExportInvalido(
            "Este Excel no es el reporte de resultados con información "
            "completa de Balanz: le falta la hoja " + ", ".join(faltan) + "."
        )
    realizado, lotes = hojas[HOJA_REALIZADO], hojas[HOJA_LOTES]
    for nombre, df, columnas in (
        (HOJA_REALIZADO, realizado, COLUMNAS_REALIZADO),
        (HOJA_LOTES, lotes, COLUMNAS_HOJA_LOTES),
    ):
        # Una hoja sin filas puede venir sin encabezado: no hay nada que leer.
        if df.empty:
            continue
        ausentes = [c for c in columnas if c not in df.columns]
        if ausentes:
            raise ExportInvalido(
                f"La hoja {nombre} no tiene las columnas que esperamos "
                f"({', '.join(ausentes)}). Puede que Balanz haya cambiado el "
                "formato del reporte."
            )
    return realizado, lotes


def _fila_venta(r) -> dict | None:
    mon_c, mon_v = moneda(r["Moneda Compra"]), moneda(r["Moneda Venta"])
    mep_c, mep_v = _num(r["OperacionCompraDolarMEP"]), _num(r["OperacionVentaDolarMEP"])
    cant = _num(r["Cantidad"])
    precio_v = _num(r["PrecioVenta"])
    # Las letras que vencen traen su precio de rescate bien ("Amortización /
    # S10N5" a 1,22); solo el vencimiento con renta lo trae negativo.
    if precio_v < 0 and "amortizaci" in _texto(r.get("Operacion Venta")).lower():
        precio_v = 1.0
    if precio_v < 0 or pd.isna(r["FechaCompra"]):
        return None
    costo = _a_usd(cant * _num(r["Precio Compra"]), mon_c, mep_c)
    venta = _a_usd(cant * precio_v, mon_v, mep_v)
    gastos = _a_usd(_num(r["Gastos"]), "ARS", mep_v)
    if costo is None or venta is None or gastos is None:
        return None
    return {
        "fecha_compra": r["FechaCompra"],
        "dias": (pd.Timestamp(r["Fecha"]) - pd.Timestamp(r["FechaCompra"])).days,
        "costo_usd": costo,
        "venta_usd": venta,
        "gastos_usd": gastos,
        "resultado_usd": venta - costo - gastos,
        "cantidad": cant,
        "precio_compra": _num(r["Precio Compra"]),
        "moneda_compra": mon_c,
        "precio_venta": precio_v,
        "moneda_venta": mon_v,
        "mep_compra": mep_c,
    }


def _moneda_cupon(r, bruto: float, tenencia, mep: float) -> str | None:
    """Pesos o dólares, según cuánto da el cupón por nominal (ver docstring). `None`: no se puede saber."""
    if moneda(r["Moneda Venta"]) != "USD":
        return "ARS"
    nominales = tenencia(normalizar_ticker(r["Ticker"]), r["Fecha"])
    if nominales <= 0 or bruto <= 0 or not mep or mep <= 0:
        return None
    en_usd = bruto / nominales
    en_ars = en_usd / mep
    distancia = lambda x: abs(math.log(x / _CUPON_TIPICO_POR_NOMINAL))  # noqa: E731
    return "USD" if distancia(en_usd) <= distancia(en_ars) else "ARS"


def _fila_cobro(r, mov: str, tenencia) -> dict | None:
    mep_v = _num(r["OperacionVentaDolarMEP"])
    bruto = _num(r[_COLUMNA_COBRO[mov]])
    mon = _moneda_cupon(r, bruto, tenencia, mep_v) if mov == MOV_CUPON else moneda(r["Moneda Venta"])
    if mov == MOV_CUPON and mon is None:
        raise _SinMoneda()
    cobro = _a_usd(bruto, mon, mep_v)
    gastos = _a_usd(_num(r["Gastos"]), "ARS", mep_v)
    if cobro is None or gastos is None:
        return None
    return {
        "gastos_usd": gastos,
        "resultado_usd": cobro - gastos,
        "cobro_monto": bruto,
        "cobro_moneda": mon,
        "cobro_usd": cobro,
    }


def _tenencias(df: pd.DataFrame, lotes: pd.DataFrame):
    """
    Función (ticker, día) → nominales que se tenían, con los lotes vendidos
    (comprados antes de ese día y vendidos después) y los que siguen abiertos.
    """
    ventas = df[df["Tipo Movimiento"].map(_texto) == "Orden"]
    v = pd.DataFrame({
        "ticker": ventas["Ticker"].map(normalizar_ticker), "desde": ventas["FechaCompra"],
        "hasta": ventas["Fecha"], "cantidad": pd.to_numeric(ventas["Cantidad"], errors="coerce").fillna(0),
    })
    if not lotes.empty:
        a = pd.DataFrame({
            "ticker": lotes["Ticker"].map(normalizar_ticker), "desde": _fecha(lotes["Fecha"]),
            "hasta": "9999-12-31", "cantidad": pd.to_numeric(lotes["Cantidad"], errors="coerce").fillna(0),
        })
        v = pd.concat([v, a], ignore_index=True)
    v = v.dropna(subset=["desde", "hasta"])

    def tenencia(ticker: str, dia: str) -> float:
        # El día de la venta (o del vencimiento) todavía se tenía: un cupón
        # cobrado ese mismo día se paga sobre esos nominales.
        t = v[(v["ticker"] == ticker) & (v["desde"] <= dia) & (dia <= v["hasta"])]
        return float(t["cantidad"].sum())

    return tenencia


def _operaciones(realizado: pd.DataFrame, lotes: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    df = realizado.copy()
    df["Fecha"] = _fecha(df["Fecha"])
    df["FechaCompra"] = _fecha(df["FechaCompra"])
    tenencia = _tenencias(df, lotes)
    filas, raras = [], []
    for _, r in df.iterrows():
        crudo = _texto(r["Tipo Movimiento"])
        mov = MOVIMIENTOS.get(crudo, "?")
        if mov is None:
            continue

        motivo = None
        try:
            fila = _fila(r, mov, tenencia)
        except _DatoIlegible:
            fila, motivo = None, "tiene un número que no se pudo leer"
        except _SinMoneda:
            fila, motivo = None, ("no se pudo saber si el cupón vino en pesos o en dólares: "
                                  "el reporte no trae los nominales de ese bono")
        if fila is None:
            raras.append({
                "broker": BROKER_BALANZ,
                "fecha": r["Fecha"] if pd.notna(r["Fecha"]) else "",
                "ticker": normalizar_ticker(r["Ticker"]),
                "descripcion": _texto(r["Descripcion"]),
                "movimiento": crudo or "(vacío)",
                "motivo": motivo or ("movimiento desconocido" if mov == "?" else "faltan datos para pasarlo a dólares"),
            })
            continue
        filas.append(fila)
    return armar_operaciones(filas), raras


def _fila(r, mov: str, tenencia) -> dict | None:
    """Una fila del realizado → operación, o `None` si no se puede pasar a dólares."""
    base = {
        "broker": BROKER_BALANZ,
        "fecha": r["Fecha"],
        "ticker": normalizar_ticker(r["Ticker"]),
        "descripcion": _texto(r["Descripcion"]),
        "clase": CLASES.get(_texto(r["Tipo"]), _texto(r["Tipo"]) or "Sin tipo"),
        "mep_venta": _num(r["OperacionVentaDolarMEP"]),
        "gastos_ars": _num(r["Gastos"]),
    }
    detalle = None
    if pd.notna(r["Fecha"]) and mov == MOV_VENTA:
        detalle = _fila_venta(r)
    elif pd.notna(r["Fecha"]) and mov in _COLUMNA_COBRO:
        detalle = _fila_cobro(r, mov, tenencia)
    return None if detalle is None else {**base, "movimiento": mov, **detalle}


def _lotes(lotes: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    if lotes.empty:
        return pd.DataFrame(columns=COLUMNAS_LOTES), []
    df = lotes.copy()
    df["Fecha"] = _fecha(df["Fecha"])
    filas, raras = [], []
    for _, r in df.iterrows():
        try:
            cant = _num(r["Cantidad"])
            costo = _a_usd(cant * _num(r["Precio Compra"]), moneda(r["Moneda"]), _num(r["DolarMEP"]))
        except _DatoIlegible:
            cant, costo = 0.0, None
        if costo is None or pd.isna(r["Fecha"]):
            raras.append({
                "broker": BROKER_BALANZ,
                "fecha": "",
                "ticker": normalizar_ticker(r["Ticker"]),
                "descripcion": _texto(r["Descripcion"]),
                "movimiento": "Lote abierto",
                "motivo": "faltan datos para pasarlo a dólares",
            })
            continue
        filas.append({
            "broker": BROKER_BALANZ,
            "ticker": normalizar_ticker(r["Ticker"]),
            "descripcion": _texto(r["Descripcion"]),
            "clase": CLASES.get(_texto(r["Tipo"]), _texto(r["Tipo"]) or "Sin tipo"),
            "fecha_compra": r["Fecha"],
            "cantidad": cant,
            "costo_usd": costo,
        })
    return pd.DataFrame(filas, columns=COLUMNAS_LOTES), raras


def es_excel(contenido: bytes) -> bool:
    """Un .xlsx es un zip: empieza con 'PK'. Si es de Balanz lo decide `leer_balanz`."""
    return contenido[:2] == b"PK"


def leer_balanz(contenido: bytes) -> Cartera:
    """Bytes del .xlsx → operaciones cerradas y lotes abiertos en USD MEP."""
    realizado, lotes = _leer_hojas(contenido)
    ops, raras_ops = (pd.DataFrame(), []) if realizado.empty else _operaciones(realizado, lotes)
    abiertos, raras_lotes = _lotes(lotes)
    if ops.empty and abiertos.empty:
        raise ExportInvalido("El reporte no tiene operaciones ni posiciones para analizar.")

    # La fecha del reporte: la de los lotes abiertos si hay, si no la última
    # operación. Es el "hoy" contra el que se miden los últimos doce meses.
    cortes = []
    if not lotes.empty and "Fecha Lote" in lotes:
        cortes += list(_fecha(lotes["Fecha Lote"]).dropna())
    if not ops.empty:
        cortes += list(ops["fecha"])
    if not cortes:
        raise ExportInvalido("El reporte no trae ninguna fecha que se pueda leer.")
    fecha_corte = max(cortes)

    raras = pd.DataFrame(raras_ops + raras_lotes, columns=COLUMNAS_NO_RECONOCIDOS)
    return Cartera(ops, abiertos, raras, fecha_corte)
