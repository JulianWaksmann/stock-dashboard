"""
cartera/cocos.py - Lee el export de movimientos de cuenta de Cocos.

Cocos no da resultados, da el **libro de movimientos**: un CSV por año con
cada compra, venta, suscripción y rescate de fondo, caución y transferencia,
en pesos y sin tipo de cambio. Este módulo arma lo que Balanz ya trae hecho:

  * **Lotes por orden de llegada.** Cada compra (o suscripción a un FCI) abre
    un lote; cada venta (o rescate) consume los más viejos primero. Los lotes
    son de Cocos: una venta acá nunca consume una compra hecha en otro
    broker. Si una venta no encuentra compras —falta el archivo del año
    anterior, o los títulos llegaron por transferencia— lo que no tiene costo
    va a `no_reconocidos`: no se inventa un costo.
  * **Comisiones de punta a punta.** El costo es el monto bruto; las
    comisiones e impuestos de la compra se cargan a la venta que consume ese
    lote, junto con los de la venta. Así el resultado de cada venta es neto.
  * **Caución.** Llega en dos filas ejecutadas el mismo día: el contado (sale
    la plata) y el término (vuelve con interés, y liquida días después). El
    interés es la suma de las dos. Una caución colocada al final del archivo
    que todavía no volvió queda como posición abierta, al costo.
  * **Dólares.** Cada monto en pesos se pasa al MEP de su fecha con la serie
    que recibe (`cartera/mep_source.py`); un día sin dato toma el último día
    hábil anterior.

Los archivos de dos años se superponen (una caución que cruza el 31 de
diciembre aparece en los dos): se unen y se descartan los duplicados por
`nroTicket`.

El ticker sale del último paréntesis de `instrumento` —"CEDEAR DE MICROSOFT
CORP. (MSFT)" es MSFT— y es el de BYMA, el mismo que usa Balanz. La especie
en dólares de un CEDEAR (MSFTD) se junta con la de pesos solo si el nombre
del instrumento coincide: sacarle la D a ciegas convertiría la acción clase D
de YPF (YPFD) en otra cosa.

Puro: recibe bytes y la serie del MEP, sin red ni Streamlit.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

import pandas as pd

from cartera.modelo import (
    BROKER_COCOS,
    CLASE_ACCION,
    CLASE_CAUCION,
    CLASE_CEDEAR,
    CLASE_FCI,
    COLUMNAS_LOTES,
    COLUMNAS_NO_RECONOCIDOS,
    MOV_DIVIDENDO,
    MOV_INTERES,
    MOV_VENTA,
    TICKER_CAUCION,
    Cartera,
    ExportInvalido,
    armar_operaciones,
    normalizar_ticker,
)

COLUMNAS = (
    "nroTicket", "fechaEjecucion", "fechaLiquidacion", "tipoOperacion", "instrumento",
    "moneda", "cantidad", "precio", "montoBruto", "total",
)

OP_COMPRA = "Compra"
OP_VENTA = "Venta"
OP_SUSCRIPCION = "Liquidacion Suscripcion Fci"
OP_RESCATE = "Liquidacion Rescate Fci"
OP_CAUCION_CONTADO = "Colocador Caucion Contado"
OP_CAUCION_TERMINO = "Colocador Caucion Termino"
OP_DIVIDENDO_ESPECIE = "DIVIDENDOS EN ESPECIE"

ABREN_LOTE = {OP_COMPRA, OP_SUSCRIPCION}
CIERRAN_LOTE = {OP_VENTA, OP_RESCATE}

# Se reconocen y no son resultado: plata que entra o sale de la cuenta, y la
# acreditación en dólares de un dividendo que ya se contó por su otra fila.
SIN_RESULTADO = {"Orden De Pago", "Recibo De Cobro", "Nota De Credito Conversion"}

TICKER_DIVIDENDO_USD = "DIV. USD"
# Las cuotapartes vienen con cuatro decimales: menos que esto es redondeo.
_TOLERANCIA = 1e-3
_PARENTESIS = re.compile(r"\(([^()]+)\)\s*$")


def es_cocos(contenido: bytes) -> bool:
    return contenido.lstrip(b"\xef\xbb\xbf")[:10].decode("latin-1").startswith("nroTicket;")


def _numero(v) -> float:
    """
    '-67.011,8761' → -67011.8761; '$ -1.000' → -1000. Vacío → 0.

    Lo que no se entiende es NaN, no cero: un monto ilegible tomado como cero
    da un resultado falso sin aviso (una caución con lo colocado ilegible
    salía con todo lo devuelto como interés). La fila con NaN se lista.
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0.0
    t = re.sub(r"(U\$S|US\$|\$|\s)", "", str(v).strip(), flags=re.IGNORECASE)
    if not t:
        return 0.0
    t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return float("nan")


def _moneda(v) -> str:
    """'ARS', '$', 'Pesos' → ARS; 'USD', 'U$S', 'US$', 'Dólares', 'USD MEP' → USD; otra cosa → ''."""
    t = str(v or "").strip().upper()
    if t in ("ARS", "$") or t.startswith("PES"):
        return "ARS"
    if t.startswith(("USD", "US$", "U$S", "U$D", "DOL", "DÓL")):
        return "USD"
    return ""


def _leer(contenido: bytes) -> pd.DataFrame:
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            texto = contenido.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    # Se lee a mano y no con `pd.read_csv` para controlar las filas que no
    # tienen la cantidad de campos del encabezado: pandas, según cómo se lo
    # llame, corre todas las columnas o descarta las sobrantes sin avisar, y
    # en los dos casos los montos quedan en la columna equivocada.
    filas = [f for f in csv.reader(io.StringIO(texto), delimiter=";") if any(c.strip() for c in f)]
    if not filas:
        raise ExportInvalido("El CSV está vacío.")
    encabezado, cuerpo = [c.strip() for c in filas[0]], []
    while encabezado and not encabezado[-1]:
        encabezado.pop()
    for f in filas[1:]:
        # Un ";" final deja un campo vacío de más: eso no es un error.
        while len(f) > len(encabezado) and not f[-1].strip():
            f = f[:-1]
        if len(f) > len(encabezado):
            raise ExportInvalido(
                "El CSV de Cocos tiene filas con más columnas de las que indica el encabezado. "
                "Descargalo de nuevo desde Cocos, sin abrirlo y guardarlo con otro programa."
            )
        cuerpo.append(f + [""] * (len(encabezado) - len(f)))
    df = pd.DataFrame(cuerpo, columns=encabezado, dtype=str)
    faltan = [c for c in COLUMNAS if c not in df.columns]
    if faltan:
        raise ExportInvalido(
            "El CSV no tiene las columnas del export de movimientos de Cocos "
            f"({', '.join(faltan)}). Puede que Cocos haya cambiado el formato."
        )
    return df


def mep_en(serie: pd.Series, fecha: str) -> float | None:
    """MEP del día, o del último día con dato antes de esa fecha."""
    i = serie.index.searchsorted(fecha, side="right") - 1
    return None if i < 0 else float(serie.iloc[i])


def _es_especie_dolar(instrumento: str) -> bool:
    """'Dolar Especie CV 7000', 'DOLAR MEP'...: la especie es el dólar mismo."""
    return instrumento.strip().upper().startswith(("DOLAR", "DÓLAR"))


def _cantidad(x: float) -> str:
    """11234.5678 → '11.234,57', para mostrar."""
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".").removesuffix(",00")


def _fecha_corta(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else ""


def _nombre(instrumento: str) -> str:
    return re.sub(r"\s*\([^()]*\)", "", instrumento).strip()


def _ticker_crudo(instrumento: str) -> str:
    m = _PARENTESIS.search(instrumento)
    return normalizar_ticker(m.group(1)) if m else ""


def _clase(instrumento: str) -> str:
    t = instrumento.upper()
    if t.startswith("CEDEAR"):
        return CLASE_CEDEAR
    if t.startswith("FCI"):
        return CLASE_FCI
    if "ESCRIT" in t or " ACC" in t or t.startswith("ACC"):
        return CLASE_ACCION
    return "Otros"


def _mapa_tickers(df: pd.DataFrame) -> dict[str, str]:
    """Ticker crudo → ticker con el que se agrupa (la especie en dólares con la de pesos, si es el mismo instrumento)."""
    nombres: dict[str, str] = {}
    for inst in df["instrumento"]:
        t = _ticker_crudo(inst)
        if t:
            nombres.setdefault(t, _nombre(inst).upper())
    mapa = {}
    for t, nombre in nombres.items():
        mapa[t] = t
        if len(t) < 3 or t[-1] not in "DC":
            continue
        # La especie en pesos de un CEDEAR es el ticker sin la letra (KOD →
        # KO, MSFTD → MSFT); la de una ON termina en O (YCA6D → YCA6O).
        for base in (t[:-1], t[:-1] + "O"):
            if base != t and base in nombres and nombres[base] == nombre:
                mapa[t] = base
                break
    return mapa


@dataclass
class _Lote:
    ticker: str
    descripcion: str
    clase: str
    fecha: str
    cantidad: float
    precio_ars: float  # por unidad
    moneda: str
    mep: float
    costo_usd_u: float
    gastos_usd_u: float
    gastos_ars_u: float
    resto: float = field(init=False)

    def __post_init__(self):
        self.resto = self.cantidad


def _a_usd(monto: float, moneda: str, mep: float | None) -> float | None:
    if moneda == "USD":
        return monto
    return monto / mep if mep else None


def _sin_superposicion(tablas: list[pd.DataFrame]) -> pd.DataFrame:
    """
    Une los archivos sacando lo que se repite **entre** ellos.

    Se compara la fila entera, no solo `nroTicket`: un ticket vacío o
    compartido (contado y término de una caución) haría desaparecer filas
    distintas. Y solo entre archivos: dos filas idénticas dentro del mismo
    archivo son dos movimientos (dos dividendos iguales el mismo día).
    """
    vistas: set = set()
    partes = []
    for t in tablas:
        claves = t.astype(str).apply(tuple, axis=1)
        partes.append(t[~claves.isin(vistas)])
        vistas.update(claves)
    return pd.concat(partes, ignore_index=True)


def leer_cocos(archivos: list[bytes], serie_mep: pd.Series | None) -> Cartera:
    """Uno o varios CSV de movimientos de Cocos → operaciones y lotes en USD MEP."""
    df = _sin_superposicion([_leer(a) for a in archivos])
    if df.empty:
        raise ExportInvalido("Los archivos de Cocos no tienen movimientos.")
    if serie_mep is None or serie_mep.empty:
        raise ExportInvalido(
            "No pudimos bajar la cotización del dólar MEP, que hace falta para pasar a dólares "
            "los movimientos de Cocos. Probá de nuevo en un rato."
        )
    for c in ("fechaEjecucion", "fechaLiquidacion"):
        # Una fecha que no es dd-mm-aaaa queda vacía y esa fila se lista
        # como no reconocida; no puede tumbar la lectura del resto.
        df[c] = pd.to_datetime(df[c], format="%d-%m-%Y", errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    for c in ("cantidad", "precio", "montoBruto", "total"):
        df[c] = df[c].map(_numero)
    df["tipoOperacion"] = df["tipoOperacion"].str.strip()
    df["instrumento"] = df["instrumento"].fillna("").str.strip()
    df["moneda"] = df["moneda"].map(_moneda)
    # El mismo día, primero lo que abre lotes: un rescate y una suscripción
    # del mismo día no deberían dejar al rescate sin cuotapartes.
    df["_orden"] = df["tipoOperacion"].map(lambda t: 0 if t in ABREN_LOTE else 1)
    df = df.sort_values(["fechaEjecucion", "_orden", "nroTicket"], kind="stable").reset_index(drop=True)

    tickers = _mapa_tickers(df)
    mep = lambda f: mep_en(serie_mep, f)  # noqa: E731 - se usa en todo el recorrido
    lotes: dict[str, list[_Lote]] = {}
    filas: list[dict] = []
    raras: list[dict] = []

    def rara(r, motivo):
        raras.append({
            "broker": BROKER_COCOS, "fecha": r["fechaEjecucion"] or "",
            "ticker": tickers.get(_ticker_crudo(r["instrumento"]), ""),
            "descripcion": _nombre(r["instrumento"]), "movimiento": r["tipoOperacion"] or "(vacío)",
            "motivo": motivo,
        })

    # Ventas o rescates sin compra en los archivos, por ticker. Se informan
    # agrupados: un fondo de liquidez que se tenía desde antes del primer
    # archivo deja decenas de rescates así, y una fila por cada uno tapaba lo
    # que de verdad hay que mirar.
    sin_compra: dict[str, dict] = {}
    contados: dict[str, list] = {}
    terminos: dict[str, list] = {}

    for _, r in df.iterrows():
        tipo, fecha = r["tipoOperacion"], r["fechaEjecucion"]
        if not fecha:
            rara(r, "sin fecha")
            continue
        if tipo in SIN_RESULTADO:
            continue
        if any(pd.isna(r[c]) for c in ("cantidad", "montoBruto", "total")):
            rara(r, "tiene un monto o una cantidad que no se pudo leer")
            continue
        if not r["moneda"]:
            rara(r, "moneda desconocida")
            continue
        if tipo == OP_CAUCION_CONTADO:
            contados.setdefault(fecha, []).append(r)
            continue
        if tipo == OP_CAUCION_TERMINO:
            terminos.setdefault(fecha, []).append(r)
            continue

        ticker = tickers.get(_ticker_crudo(r["instrumento"]), "")
        if tipo in ABREN_LOTE or tipo in CIERRAN_LOTE:
            if not ticker:
                rara(r, "no trae ticker")
                continue
            qty, bruto = abs(r["cantidad"]), abs(r["montoBruto"])
            gastos = max(0.0, abs(r["montoBruto"] - r["total"]) if tipo in CIERRAN_LOTE else abs(r["total"]) - bruto)
            m = mep(fecha)
            if qty <= 0 or (r["moneda"] != "USD" and not m):
                rara(r, "faltan datos para pasarlo a dólares")
                continue
            if tipo in ABREN_LOTE:
                lotes.setdefault(ticker, []).append(_Lote(
                    ticker, _nombre(r["instrumento"]), _clase(r["instrumento"]), fecha, qty, bruto / qty,
                    r["moneda"], m or 0.0, _a_usd(bruto, r["moneda"], m) / qty,
                    _a_usd(gastos, r["moneda"], m) / qty, gastos / qty,
                ))
                continue
            venta_usd_u = _a_usd(bruto, r["moneda"], m) / qty
            gastos_v_usd_u = _a_usd(gastos, r["moneda"], m) / qty
            falta = qty
            for lote in lotes.get(ticker, []):
                if falta <= _TOLERANCIA:
                    break
                if lote.resto <= _TOLERANCIA:
                    continue
                p = min(lote.resto, falta)
                lote.resto -= p
                falta -= p
                costo = lote.costo_usd_u * p
                venta = venta_usd_u * p
                gastos_usd = (lote.gastos_usd_u + gastos_v_usd_u) * p
                filas.append({
                    "broker": BROKER_COCOS, "fecha": fecha, "ticker": ticker, "descripcion": lote.descripcion,
                    "clase": lote.clase, "movimiento": MOV_VENTA, "fecha_compra": lote.fecha,
                    "dias": (pd.Timestamp(fecha) - pd.Timestamp(lote.fecha)).days, "cantidad": p,
                    "precio_compra": lote.precio_ars, "moneda_compra": lote.moneda, "precio_venta": bruto / qty,
                    "moneda_venta": r["moneda"], "mep_compra": lote.mep, "mep_venta": m,
                    "costo_usd": costo, "venta_usd": venta, "gastos_ars": (lote.gastos_ars_u + gastos / qty) * p,
                    "gastos_usd": gastos_usd, "resultado_usd": venta - costo - gastos_usd,
                })
            if falta > _TOLERANCIA:
                g = sin_compra.setdefault(ticker, {
                    "n": 0, "cantidad": 0.0, "desde": fecha, "hasta": fecha,
                    "descripcion": _nombre(r["instrumento"]), "rescate": tipo == OP_RESCATE,
                })
                g["n"] += 1
                g["cantidad"] += falta
                g["hasta"] = fecha
            continue

        if tipo == OP_DIVIDENDO_ESPECIE and not _es_especie_dolar(r["instrumento"]):
            # "En especie" también son acciones nuevas de un título: entran
            # como lote a costo cero, que es lo que costaron. Sin ticker no
            # hay forma de saber qué son.
            if not ticker or abs(r["cantidad"]) <= 0:
                rara(r, "dividendo en especie que no es en dólares ni trae ticker")
                continue
            lotes.setdefault(ticker, []).append(_Lote(
                ticker, _nombre(r["instrumento"]), _clase(r["instrumento"]), fecha, abs(r["cantidad"]),
                0.0, r["moneda"], mep(fecha) or 0.0, 0.0, 0.0, 0.0,
            ))
            continue

        if tipo == OP_DIVIDENDO_ESPECIE:
            # Dividendo en dólares ("Dolar Especie"): `cantidad` son los
            # dólares y `total`, en pesos, los impuestos. Cocos no dice de qué
            # activo vino.
            m = mep(fecha)
            monto = abs(r["cantidad"])
            gastos = abs(r["total"])
            if not m or monto <= 0:
                rara(r, "faltan datos para pasarlo a dólares")
                continue
            filas.append({
                "broker": BROKER_COCOS, "fecha": fecha, "ticker": TICKER_DIVIDENDO_USD,
                "descripcion": "Dividendo en dólares (Cocos no informa de qué activo)", "clase": CLASE_CEDEAR,
                "movimiento": MOV_DIVIDENDO, "mep_venta": m, "gastos_ars": gastos, "gastos_usd": gastos / m,
                "resultado_usd": monto - gastos / m, "cobro_monto": monto, "cobro_moneda": "USD", "cobro_usd": monto,
            })
            continue

        rara(r, "movimiento desconocido")

    # Cauciones: contado y término del mismo día de ejecución.
    # El corte es la última ejecución: una caución que liquida después del
    # día del export dejaría una fecha de corte en el futuro.
    fechas = [f for f in df["fechaEjecucion"] if f]
    abiertas_caucion = []
    for fecha in sorted(set(contados) | set(terminos)):
        # Cada término se empareja con su contado del mismo día: el de monto
        # más alto que no supere lo devuelto (la caución vuelve con interés).
        # Sumar todo el día servía solo si había la misma cantidad de filas
        # de cada lado; con un término en el archivo que no se subió, daba un
        # interés negativo enorme.
        libres = sorted(contados.get(fecha, []), key=lambda c: abs(c["total"]))
        for t in sorted(terminos.get(fecha, []), key=lambda t: t["montoBruto"]):
            candidatos = [c for c in libres if abs(c["total"]) <= t["montoBruto"] and c["moneda"] == t["moneda"]]
            if not candidatos:
                rara(t, "caución sin su colocación en los archivos")
                continue
            c = candidatos[-1]
            libres.remove(c)
            colocado, devuelto, bruto = abs(c["total"]), t["total"], t["montoBruto"]
            cobro = t["fechaLiquidacion"] or fecha
            m_cobro, m_coloc = mep(cobro), mep(fecha)
            if t["moneda"] != "USD" and not (m_cobro and m_coloc):
                rara(t, "faltan datos para pasarlo a dólares")
                continue
            gastos = bruto - devuelto
            filas.append({
                "broker": BROKER_COCOS, "fecha": cobro, "ticker": TICKER_CAUCION,
                "descripcion": "Caución en " + ("dólares" if t["moneda"] == "USD" else "pesos"),
                "clase": CLASE_CAUCION, "movimiento": MOV_INTERES, "mep_venta": m_cobro, "gastos_ars": gastos,
                # Lo colocado y desde cuándo: no es un costo de venta, es el
                # capital que el rendimiento anual y la TIR tienen que ver.
                "fecha_compra": fecha, "costo_usd": _a_usd(colocado, t["moneda"], m_coloc),
                "gastos_usd": _a_usd(gastos, t["moneda"], m_cobro),
                "resultado_usd": _a_usd(devuelto - colocado, t["moneda"], m_cobro),
                "cobro_monto": bruto - colocado, "cobro_moneda": t["moneda"],
                "cobro_usd": _a_usd(bruto - colocado, t["moneda"], m_cobro),
            })
        abiertas_caucion += libres

    primera = df["fechaEjecucion"][df["fechaEjecucion"] != ""].min()
    for ticker, g in sin_compra.items():
        que = ("rescate" if g["rescate"] else "venta") + ("s" if g["n"] > 1 else "")
        raras.append({
            "broker": BROKER_COCOS, "fecha": g["desde"], "ticker": ticker, "descripcion": g["descripcion"],
            "movimiento": f"{g['n']} {que}" + (f" hasta el {_fecha_corta(g['hasta'])}" if g["n"] > 1 else ""),
            # Sin suponer la causa: puede ser una compra anterior al primer
            # archivo o títulos que llegaron por transferencia de otro broker.
            "motivo": (
                f"{_cantidad(g['cantidad'])} {'cuotapartes' if g['rescate'] else 'unidades'} sin una compra que las "
                f"cubra en los archivos (el primero empieza el {_fecha_corta(primera)}). Pueden ser de antes de esa "
                "fecha o haber llegado por transferencia desde otro broker."
            ),
        })

    abiertos = []
    for ls in lotes.values():
        for lote in ls:
            if lote.resto > _TOLERANCIA:
                abiertos.append({
                    "broker": BROKER_COCOS, "ticker": lote.ticker, "descripcion": lote.descripcion,
                    "clase": lote.clase, "fecha_compra": lote.fecha, "cantidad": lote.resto,
                    "costo_usd": lote.costo_usd_u * lote.resto,
                })
    for c in abiertas_caucion:
        costo = _a_usd(abs(c["total"]), c["moneda"], mep(c["fechaEjecucion"]))
        if costo is not None:
            abiertos.append({
                "broker": BROKER_COCOS, "ticker": TICKER_CAUCION,
                "descripcion": "Caución en " + ("dólares" if c["moneda"] == "USD" else "pesos"),
                "clase": CLASE_CAUCION, "fecha_compra": c["fechaEjecucion"], "cantidad": abs(c["total"]),
                "costo_usd": costo,
            })

    # Si hay algo no reconocido se devuelve igual: el informe lo lista, que es
    # más útil que un error. Solo sin nada de nada se avisa.
    if (not filas and not abiertos and not raras) or not fechas:
        raise ExportInvalido(
            "Los archivos de Cocos no tienen compras, ventas, cauciones ni cobros que podamos analizar."
        )
    return Cartera(
        operaciones=armar_operaciones(filas),
        lotes_abiertos=pd.DataFrame(abiertos, columns=COLUMNAS_LOTES),
        no_reconocidos=pd.DataFrame(raras, columns=COLUMNAS_NO_RECONOCIDOS),
        fecha_corte=max(fechas),
    )
