"""
cartera/informe.py - Arma el informe de cartera a partir de lo ya leído.

Puro: recibe una `Cartera` (de uno o varios brokers ya combinados) y devuelve
un diccionario listo para serializar a JSON, que es lo único que ve el dibujo
(`components/cartera_report.py`). No sabe de qué broker vino cada fila: suma
por ticker, que es el mismo en todos. Ninguna cuenta vive en el JavaScript: ahí
solo se da formato y se dibuja.

Ningún precio de mercado sale de afuera: solo lo operado. Eso fija tres reglas:

  * **Lo que sigue en cartera cuenta al costo**: sin precio de hoy no hay
    resultado sin realizar, así que es cero hasta que se vende.
  * **El resultado de cada venta se reparte entre los años en que se tuvo el
    activo**, en proporción a los días. Cargarlo entero al año de la venta
    inflaría ese año y dejaría vacíos los anteriores; repartirlo con precios
    de cierre de cada año exigiría buscarlos afuera.
  * **La renta (dividendos, cupones, intereses) cuenta el día que se cobró.**

El rendimiento de cada año es ese resultado sobre el capital promedio
invertido en el año: el costo de cada lote (y lo colocado en cada caución que
lo informa) ponderado por los días que estuvo adentro. La TIR anualizada usa los mismos flujos (compras, ventas, cobros y,
al final, la cartera abierta valuada al costo).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from cartera.modelo import MOV_CUPON, MOV_DIVIDENDO, MOV_INTERES, MOV_VENTA, Cartera

# Cuántas posiciones muestra por nombre la composición de cartera; el resto
# va a "Otros".
TOP_CARTERA = 5
TOP_VENTAS = 5

# Una venta con costo menor a esto no se compara por rendimiento: sale de un
# lote con costo cero (cambio de ratio de un CEDEAR) y su porcentaje no
# significa nada.
COSTO_MINIMO_COMPARABLE = 1.0


def _r2(x: float) -> float:
    return round(float(x), 2)


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _ventas(ops: pd.DataFrame) -> pd.DataFrame:
    return ops[ops["movimiento"] == MOV_VENTA] if not ops.empty else ops


def _renta(ops: pd.DataFrame) -> pd.DataFrame:
    return ops[ops["movimiento"] != MOV_VENTA] if not ops.empty else ops


def _renta_sin_capital(ops: pd.DataFrame) -> pd.DataFrame:
    """
    Intereses de caución que no informan cuánto se colocó (los de Balanz).

    Un dividendo o un cupón tienen su capital en el lote del activo; una
    caución no tiene lote. Sin lo colocado, su interés sumaría resultado sin
    sumar capital e inflaría el rendimiento (medido: 361% en un año con doce
    cauciones). Cuentan en los totales, pero no en el rendimiento ni en la TIR.
    """
    r = _renta(ops)
    if r.empty:
        return r
    return r[(r["movimiento"] == MOV_INTERES) & (r["costo_usd"].isna() | r["fecha_compra"].isna())]


def _renta_para_rendimiento(ops: pd.DataFrame) -> pd.DataFrame:
    r = _renta(ops)
    return r.drop(index=_renta_sin_capital(ops).index) if not r.empty else r


def por_ticker(ops: pd.DataFrame, lotes: pd.DataFrame) -> list[dict]:
    filas: dict[str, dict] = {}

    def fila(t, desc, clase):
        return filas.setdefault(t, {
            "ticker": t, "descripcion": desc, "clase": clase, "operaciones": 0,
            "compraventa": 0.0, "renta": 0.0, "total": 0.0, "costo_vendido": 0.0,
            "cartera_costo": 0.0, "cartera_cant": 0.0, "vendio": False,
        })

    for r in ops.itertuples():
        a = fila(r.ticker, r.descripcion, r.clase)
        a["operaciones"] += 1
        a["total"] += r.resultado_usd
        if r.movimiento == MOV_VENTA:
            a["compraventa"] += r.resultado_usd
            a["costo_vendido"] += r.costo_usd
            a["vendio"] = True
        else:
            a["renta"] += r.resultado_usd
    for r in lotes.itertuples():
        a = fila(r.ticker, r.descripcion, r.clase)
        a["cartera_costo"] += r.costo_usd
        a["cartera_cant"] += r.cantidad

    salida = []
    for a in filas.values():
        rend = a["compraventa"] / a["costo_vendido"] * 100 if a["costo_vendido"] > 0 else None
        salida.append({
            **a,
            **{k: _r2(a[k]) for k in ("compraventa", "renta", "total", "costo_vendido", "cartera_costo", "cartera_cant")},
            "rendimiento": None if rend is None else round(rend, 1),
            # Si vendió algo, aunque el costo haya sido cero (acciones
            # recibidas como dividendo): su compraventa se muestra igual.
            "vendio": a["vendio"],
        })
    return sorted(salida, key=lambda a: a["total"], reverse=True)


def por_anio(ops: pd.DataFrame) -> list[dict]:
    if ops.empty:
        return []
    g = ops.assign(es_venta=ops["movimiento"] == MOV_VENTA)
    out = []
    for anio, d in g.groupby("anio"):
        ventas = d.loc[d["es_venta"], "resultado_usd"].sum()
        renta = d.loc[~d["es_venta"], "resultado_usd"].sum()
        out.append({"anio": str(anio), "ventas": round(ventas), "renta": round(renta), "total": round(ventas + renta)})
    return out


def por_clase(ops: pd.DataFrame) -> list[dict]:
    if ops.empty:
        return []
    s = ops.groupby("clase")["resultado_usd"].sum().sort_values(ascending=False)
    return [{"clase": c, "resultado": round(v)} for c, v in s.items()]


def cartera_mix(lotes: pd.DataFrame) -> list[dict]:
    """Peso de cada posición abierta, al costo: por activo (top y Otros) y por tipo."""
    if lotes.empty or lotes["costo_usd"].sum() <= 0:
        return []
    total = lotes["costo_usd"].sum()
    por_activo = lotes.groupby("ticker")["costo_usd"].sum().sort_values(ascending=False)
    out = [
        {"grupo": "activo", "nombre": t, "costo": round(v), "peso": round(v / total * 100, 1)}
        for t, v in por_activo.head(TOP_CARTERA).items()
    ]
    resto = por_activo.iloc[TOP_CARTERA:]
    if len(resto):
        out.append({"grupo": "activo", "nombre": f"Otros ({len(resto)})", "costo": round(resto.sum()), "peso": round(resto.sum() / total * 100, 1)})
    for c, v in lotes.groupby("clase")["costo_usd"].sum().sort_values(ascending=False).items():
        out.append({"grupo": "tipo", "nombre": c, "costo": round(v), "peso": round(v / total * 100, 1)})
    return out


def kpis(ops: pd.DataFrame, lotes: pd.DataFrame) -> dict:
    ventas, renta = _ventas(ops), _renta(ops)
    total = float(ops["resultado_usd"].sum()) if not ops.empty else 0.0
    out = {
        "total": _r2(total),
        "ventas": _r2(ventas["resultado_usd"].sum()) if not ventas.empty else 0.0,
        "renta": _r2(renta["resultado_usd"].sum()) if not renta.empty else 0.0,
        "cartera_costo": _r2(lotes["costo_usd"].sum()) if not lotes.empty else 0.0,
        "posiciones": int(lotes["ticker"].nunique()) if not lotes.empty else 0,
        "primer_anio": None, "mejor_anio": None, "mejor_anio_total": None, "mejor_ticker": None,
    }
    if not ops.empty:
        anios = ops.groupby("anio")["resultado_usd"].sum()
        tks = ops.groupby("ticker")["resultado_usd"].sum()
        out.update({
            "primer_anio": str(anios.index.min()),
            "mejor_anio": str(anios.idxmax()),
            "mejor_anio_total": _r2(anios.max()),
            "mejor_ticker": tks.idxmax(),
        })
    return out


def estilo(ops: pd.DataFrame, fecha_corte: str) -> dict:
    """Patrones de las ventas y cobros. Números: el texto lo arma el dibujo."""
    ventas = _ventas(ops)
    out: dict = {"ventas": int(len(ventas))}
    if ventas.empty:
        return out
    g = ventas[ventas["resultado_usd"] > 0]
    p = ventas[ventas["resultado_usd"] < 0]
    total = float(ops["resultado_usd"].sum())
    gastos = float(ops["gastos_usd"].sum())
    top = ops.groupby("ticker")["resultado_usd"].sum().sort_values(ascending=False).head(3)
    corte = pd.Timestamp(fecha_corte)
    edad = (corte - pd.to_datetime(_renta(ops)["fecha"])).dt.days
    renta = _renta(ops)["resultado_usd"]
    out.update({
        "ganadoras": int(len(g)),
        "perdedoras": int(len(p)),
        "ganancia_media": _r2(g["resultado_usd"].mean()) if len(g) else 0.0,
        "perdida_media": _r2(p["resultado_usd"].mean()) if len(p) else 0.0,
        "dias_ganadoras": round(g["dias"].mean()) if len(g) else None,
        "dias_perdedoras": round(p["dias"].mean()) if len(p) else None,
        "gastos": _r2(gastos),
        "gastos_pct": round(gastos / (total + gastos) * 100) if total + gastos > 0 else None,
        "top_tickers": list(top.index),
        "top_pct": round(top.sum() / total * 100) if total > 0 else None,
        "renta_12m": _r2(renta[edad < 365].sum()),
        "renta_12m_previos": _r2(renta[(edad >= 365) & (edad < 730)].sum()),
    })
    # Lo derivado también se calcula acá y no en el dibujo, que solo da formato.
    previos = out["renta_12m_previos"]
    out.update({
        "acierto_pct": round(out["ganadoras"] / out["ventas"] * 100),
        "payoff": round(out["ganancia_media"] / abs(out["perdida_media"]), 1) if out["perdida_media"] else None,
        "renta_var_pct": round((out["renta_12m"] - previos) / abs(previos) * 100) if previos else None,
    })
    return out


def mensual(ops: pd.DataFrame) -> list[dict]:
    if ops.empty:
        return []
    s = ops.groupby(ops["fecha"].str[:7])["resultado_usd"].sum()
    return [{"mes": k, "anio": k[:4], "m": int(k[5:7]), "resultado": _r2(v)} for k, v in s.items()]


def ventas_rend(ops: pd.DataFrame) -> list[dict]:
    ventas = _ventas(ops)
    if ventas.empty:
        return []
    # Un ticker con algún lote a costo cero tuvo un cambio de ratio: sus
    # lotes no son comparables entre sí, ni siquiera los que tienen costo.
    raros = set(ventas.loc[ventas["costo_usd"] < 0.01, "ticker"])
    v = ventas[~ventas["ticker"].isin(raros) & (ventas["costo_usd"] >= COSTO_MINIMO_COMPARABLE)]
    return [
        {"id": int(r.id), "ticker": r.ticker, "fecha": r.fecha, "dias": int(r.dias), "costo": _r2(r.costo_usd),
         "resultado": _r2(r.resultado_usd), "rend": round(r.resultado_usd / r.costo_usd * 100, 1)}
        for r in v.itertuples()
    ]


def tickers_excluidos(ops: pd.DataFrame) -> list[str]:
    ventas = _ventas(ops)
    if ventas.empty:
        return []
    return sorted(set(ventas.loc[ventas["costo_usd"] < 0.01, "ticker"]))


def renta_trim(ops: pd.DataFrame) -> list[dict]:
    if ops.empty:
        return []

    def trim(f: str) -> str:
        return f"{f[:4]}-T{(int(f[5:7]) - 1) // 3 + 1}"

    primero, ultimo = trim(ops["fecha"].min()), trim(ops["fecha"].max())
    claves = [
        f"{y}-T{q}"
        for y in range(int(primero[:4]), int(ultimo[:4]) + 1)
        for q in range(1, 5)
        if primero <= f"{y}-T{q}" <= ultimo
    ]
    acc = {k: {"trimestre": k, "dividendos": 0.0, "cupones": 0.0, "intereses": 0.0} for k in claves}
    for r in _renta(ops).itertuples():
        col = "dividendos" if r.movimiento == MOV_DIVIDENDO else "cupones" if r.movimiento == MOV_CUPON else "intereses"
        acc[trim(r.fecha)][col] += r.resultado_usd
    return [
        {**a, **{k: _r2(a[k]) for k in ("dividendos", "cupones", "intereses")},
         "total": _r2(a["dividendos"] + a["cupones"] + a["intereses"])}
        for a in acc.values()
    ]


def _tenencia(ops: pd.DataFrame, lotes: pd.DataFrame, broker: str, ticker: str, dia: str) -> float:
    """
    Cantidad de `ticker` que se tenía en `broker` el día `dia`, con los lotes.

    Por broker: un dividendo cobrado en Balanz se paga sobre lo que había en
    Balanz, no sobre la suma de las tenencias en todos los brokers.
    """
    v = _ventas(ops)
    v = v[(v["broker"] == broker) & (v["ticker"] == ticker) & v["fecha_compra"].notna()]
    # `fecha_compra` es texto solo si hay alguna venta: sin ventas la columna
    # entera es NaN (float) y compararla contra un texto revienta.
    v = v[(v["fecha_compra"].astype(str) <= dia) & (dia < v["fecha"].astype(str))]
    a = lotes[(lotes["broker"] == broker) & (lotes["ticker"] == ticker)] if not lotes.empty else lotes
    a = a[a["fecha_compra"].astype(str) <= dia] if not a.empty else a
    return float(v["cantidad"].sum()) + (float(a["cantidad"].sum()) if not a.empty else 0.0)


def _meses_desde(inicio: date, n: int) -> list[str]:
    return [date(inicio.year + (inicio.month - 1 + i) // 12, (inicio.month - 1 + i) % 12 + 1, 1).isoformat()[:7]
            for i in range(n)]


def calendario_cobros(ops: pd.DataFrame, lotes: pd.DataFrame, fecha_corte: str) -> dict:
    """
    Cobros esperados en los próximos doce meses con lo que se tiene hoy.

    Repite cada dividendo o cupón del último año en el mismo día del año
    siguiente, escalado de lo que se tenía ese día a lo que se tiene hoy, en
    el mismo broker. Los doce meses arrancan en el mes del corte: un cobro de
    ese mes que todavía no pasó también se ve. Montos brutos, en dólares.
    """
    corte = _d(fecha_corte)
    meses = _meses_desde(corte, 12)
    hoy = lotes.groupby(["broker", "ticker"])["cantidad"].sum().to_dict() if not lotes.empty else {}
    pagos = []
    renta = _renta(ops)
    for r in renta[renta["movimiento"].isin([MOV_DIVIDENDO, MOV_CUPON])].itertuples():
        clave = (r.broker, r.ticker)
        if clave not in hoy:
            continue
        f = _d(r.fecha)
        try:
            sig = f.replace(year=f.year + 1)
        except ValueError:  # 29 de febrero
            sig = f.replace(year=f.year + 1, day=28)
        if not (sig > corte and sig.isoformat()[:7] in meses):
            continue
        q = _tenencia(ops, lotes, r.broker, r.ticker, r.fecha)
        if q <= 0 or pd.isna(r.cobro_usd):
            continue
        pagos.append({
            "broker": r.broker, "ticker": r.ticker, "tipo": r.movimiento, "mes": sig.isoformat()[:7],
            "fecha_est": sig.isoformat(), "base": r.fecha, "monto_usd": _r2(r.cobro_usd / q * hoy[clave]),
        })
    pagos.sort(key=lambda p: p["fecha_est"])
    total = sum(p["monto_usd"] for p in pagos)
    pagan = sorted({p["ticker"] for p in pagos})
    pares = {(p["broker"], p["ticker"]) for p in pagos}
    costo = float(sum(
        lotes.loc[(lotes["broker"] == b) & (lotes["ticker"] == t), "costo_usd"].sum() for b, t in pares
    )) if pares else 0.0
    prox = pagos[0]["mes"] if pagos else None
    return {
        "pagos": pagos,
        "desde": meses[0],
        "total": _r2(total),
        "mensual": _r2(total / 12),
        "yoc": round(total / costo * 100, 1) if costo > 0 else None,
        "costo_pagan": _r2(costo),
        "pagan": pagan,
        "proximo_mes": prox,
        "proximo_tickers": sorted({p["ticker"] for p in pagos if p["mes"] == prox}),
        "proximo_total": _r2(sum(p["monto_usd"] for p in pagos if p["mes"] == prox)),
        "sin_cobro": sorted({t for _, t in hoy} - set(pagan)),
    }


def _dias_en(inicio: date, fin: date, a: date, b: date) -> int:
    """Días de [inicio, fin) que caen dentro de [a, b)."""
    return max(0, (min(fin, b) - max(inicio, a)).days)


def rendimiento_anual(ops: pd.DataFrame, lotes: pd.DataFrame, fecha_corte: str) -> list[dict]:
    """
    Resultado y rendimiento de cada año calendario.

    Una venta reparte su resultado entre los años que estuvo en cartera, en
    proporción a los días; la renta cuenta el año del cobro. El capital del
    año es el costo de cada lote (vendido o abierto) ponderado por los días
    que estuvo adentro, sobre los días del período: el primer año arranca en
    la primera compra y el último termina en la fecha del reporte.
    """
    corte = _d(fecha_corte)
    tramos = []  # (compra, salida, costo, resultado)
    for r in _ventas(ops).itertuples():
        tramos.append((_d(r.fecha_compra), _d(r.fecha), r.costo_usd, r.resultado_usd))
    for r in lotes.itertuples():
        tramos.append((_d(r.fecha_compra), corte, r.costo_usd, 0.0))
    # Renta que trae su capital (una caución de Cocos: lo colocado y desde
    # cuándo). Su resultado ya cuenta como renta; acá solo suma capital.
    renta_con_capital = _renta_para_rendimiento(ops)
    if not renta_con_capital.empty:
        renta_con_capital = renta_con_capital[renta_con_capital["costo_usd"].notna() & renta_con_capital["fecha_compra"].notna()]
        for r in renta_con_capital.itertuples():
            tramos.append((_d(r.fecha_compra), _d(r.fecha), r.costo_usd, 0.0))
    fechas = [t[0] for t in tramos] + ([_d(f) for f in ops["fecha"]] if not ops.empty else [])
    if not fechas:
        return []
    primero = min(fechas)
    renta = _renta_para_rendimiento(ops)
    out = []
    for anio in range(primero.year, corte.year + 1):
        a = max(date(anio, 1, 1), primero)
        b = min(date(anio + 1, 1, 1), corte + pd.Timedelta(days=1).to_pytimedelta())
        largo = (b - a).days
        if largo <= 0:
            continue
        capital = cv = 0.0
        for compra, salida, costo, resultado in tramos:
            dentro = _dias_en(compra, salida, a, b)
            capital += costo * dentro
            total = (salida - compra).days
            if total <= 0:
                # Comprado y vendido el mismo día: todo al año de la venta.
                cv += resultado if a <= salida < b else 0.0
            else:
                cv += resultado * dentro / total
        capital /= largo
        r_anio = float(renta.loc[renta["fecha"].str[:4] == str(anio), "resultado_usd"].sum()) if not renta.empty else 0.0
        resultado = cv + r_anio
        out.append({
            "anio": str(anio),
            "compraventa": _r2(cv),
            "renta": _r2(r_anio),
            "resultado": _r2(resultado),
            "capital": _r2(capital),
            "rendimiento": round(resultado / capital * 100, 1) if capital > 0 else None,
            "desde": a.isoformat(),
            "hasta": (b - pd.Timedelta(days=1).to_pytimedelta()).isoformat(),
            "parcial": a != date(anio, 1, 1) or b != date(anio + 1, 1, 1),
        })
    return out


def _xirr(flujos: list[tuple[date, float]]) -> float | None:
    """Tasa anual que hace cero el valor presente de los flujos (bisección)."""
    if not flujos or not any(m > 0 for _, m in flujos) or not any(m < 0 for _, m in flujos):
        return None
    t0 = min(f for f, _ in flujos)
    if (max(f for f, _ in flujos) - t0).days < 30:
        return None

    def vpn(tasa: float) -> float:
        return sum(m / (1 + tasa) ** ((f - t0).days / 365.0) for f, m in flujos)

    lo, hi = -0.99, 10.0
    if vpn(lo) * vpn(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if vpn(lo) * vpn(mid) <= 0:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-7:
            break
    return (lo + hi) / 2


def tir_anualizada(ops: pd.DataFrame, lotes: pd.DataFrame, fecha_corte: str) -> float | None:
    """
    TIR de toda la historia, en %: compras, ventas, cobros y la cartera al
    costo al final. Sin nada cerrado no hay TIR: daría 0% por construcción.
    """
    if ops.empty:
        return None
    flujos: list[tuple[date, float]] = []
    for r in _ventas(ops).itertuples():
        flujos.append((_d(r.fecha_compra), -r.costo_usd))
        flujos.append((_d(r.fecha), r.venta_usd - r.gastos_usd))
    for r in _renta_para_rendimiento(ops).itertuples():
        # Una caución que informa lo colocado es plata que sale y vuelve con
        # interés; sin eso la TIR vería solo el interés y daría cientos de %.
        if pd.notna(r.costo_usd) and pd.notna(r.fecha_compra):
            flujos.append((_d(r.fecha_compra), -r.costo_usd))
            flujos.append((_d(r.fecha), r.costo_usd + r.resultado_usd))
        else:
            flujos.append((_d(r.fecha), r.resultado_usd))
    corte = _d(fecha_corte)
    for r in lotes.itertuples():
        flujos.append((_d(r.fecha_compra), -r.costo_usd))
        flujos.append((corte, r.costo_usd))
    t = _xirr(flujos)
    return None if t is None else round(t * 100, 1)


def armar_informe(cartera: Cartera) -> dict:
    """El informe completo, como lo consume el dibujo."""
    ops, lotes, corte = cartera.operaciones, cartera.lotes_abiertos, cartera.fecha_corte
    vr = ventas_rend(ops)
    columnas_ops = [
        "id", "broker", "fecha", "ticker", "movimiento", "fecha_compra", "cantidad", "precio_compra", "moneda_compra",
        "precio_venta", "moneda_venta", "mep_compra", "mep_venta", "costo_usd", "venta_usd",
        "cobro_monto", "cobro_moneda", "cobro_usd", "gastos_ars", "gastos_usd", "resultado_usd",
    ]
    detalle = ops.reindex(columns=columnas_ops) if not ops.empty else pd.DataFrame(columns=columnas_ops)
    detalle = detalle.astype(object).where(detalle.notna(), None)
    return {
        "fecha_corte": corte,
        "brokers": sorted(set(ops["broker"]) | set(lotes["broker"])) if not (ops.empty and lotes.empty) else [],
        "kpis": kpis(ops, lotes),
        "por_ticker": por_ticker(ops, lotes),
        "operaciones": detalle.to_dict("records"),
        "por_anio": por_anio(ops),
        "por_clase": por_clase(ops),
        "cartera_mix": cartera_mix(lotes),
        "calendario_cobros": calendario_cobros(ops, lotes, corte),
        "estilo": estilo(ops, corte),
        "mensual": mensual(ops),
        "ventas_rend": vr,
        "excluidos": tickers_excluidos(ops),
        "renta_trim": renta_trim(ops),
        "mejores": sorted(vr, key=lambda r: r["resultado"], reverse=True)[:TOP_VENTAS],
        "peores": sorted(vr, key=lambda r: r["resultado"])[:TOP_VENTAS],
        "rendimiento_anual": rendimiento_anual(ops, lotes, corte),
        "tir": tir_anualizada(ops, lotes, corte),
        "renta_sin_capital": _r2(_renta_sin_capital(ops)["resultado_usd"].sum()) if not ops.empty else 0.0,
        "no_reconocidos": cartera.no_reconocidos.astype(object).where(cartera.no_reconocidos.notna(), None).to_dict("records"),
    }
