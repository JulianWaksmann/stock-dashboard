#!/usr/bin/env python3
"""
scripts/verificar_fuentes.py - Diagnóstico de las fuentes de datos de la
pestaña de Bonos.

Por qué existe: las fuentes de renta fija argentina son APIs públicas sin
documentar ni contrato de estabilidad. Pueden cambiar de forma, empezar a
pedir otro header o simplemente dejar de responder, y cuando eso pasa el
síntoma en el dashboard es una tabla vacía, que no dice nada sobre la causa.
Este script consulta cada fuente por separado y reporta qué respondió, cuántos
registros trajo y con qué campos, para poder distinguir "se cayó el feed" de
"cambió el esquema" de "es la red de esta máquina".

También sirve como exploración: las dos últimas comprobaciones consultan la
ficha técnica de BYMA, que es la candidata a reemplazar el dataset comunitario
de cronogramas por datos del propio mercado. Todavía no se usa en el
dashboard; el script muestra qué campos devuelve para poder decidirlo.

Uso:
    python3 scripts/verificar_fuentes.py
    python3 scripts/verificar_fuentes.py --ticker YMCJD
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import requests

TIMEOUT = 20

# Cabeceras de navegador. BYMA rechaza los pedidos sin ellas: su API está
# pensada para su propia SPA, no para clientes externos.
BYMA_BASE = "https://open.bymadata.com.ar"
BYMA_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": BYMA_BASE,
    "Referer": f"{BYMA_BASE}/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def titulo(texto: str) -> None:
    print(f"\n{'=' * 72}\n{texto}\n{'=' * 72}")


def describir(registros: list[dict], ejemplo_n: int = 1) -> None:
    """Imprime cantidad, campos disponibles y un par de registros de muestra."""
    print(f"  ✅ {len(registros)} registro(s)")
    if not registros:
        return
    campos = sorted({clave for registro in registros[:50] for clave in registro})
    print(f"  campos: {', '.join(campos)}")
    for registro in registros[:ejemplo_n]:
        print(f"  ejemplo: {json.dumps(registro, ensure_ascii=False)[:400]}")


def fallo(exc: Exception) -> None:
    print(f"  ❌ {type(exc).__name__}: {exc}")


def probar_data912() -> None:
    titulo("1. data912 — precios de ONs (fuente actual de precios)")
    url = "https://data912.com/live/arg_corp"
    print(f"  GET {url}")
    try:
        respuesta = requests.get(url, timeout=TIMEOUT)
        respuesta.raise_for_status()
        datos = respuesta.json()
        describir(datos if isinstance(datos, list) else [datos])
    except Exception as exc:
        fallo(exc)


def _sesion_byma() -> requests.Session:
    """
    Sesión con las cookies que BYMA entrega al abrir su dashboard.

    La API no usa API key: valida que el pedido venga de una sesión iniciada en
    su propio sitio, así que hay que visitarlo primero para recibir la cookie.
    """
    sesion = requests.Session()
    sesion.headers.update(BYMA_HEADERS)
    sesion.get(f"{BYMA_BASE}/#/dashboard", timeout=TIMEOUT)
    return sesion


def _post_byma(sesion: requests.Session, ruta: str, payload: dict) -> Any:
    url = f"{BYMA_BASE}/vanoms-be-core/rest/api/bymadata/free/{ruta}"
    print(f"  POST {url}")
    print(f"       body={json.dumps(payload)}")
    respuesta = sesion.post(url, data=json.dumps(payload), timeout=TIMEOUT)
    respuesta.raise_for_status()
    return respuesta.json()


def probar_byma_ons() -> None:
    titulo("2. BYMA Open Data — panel de ONs (candidata a reemplazar data912)")
    # Es POST, no GET: por eso el endpoint devuelve 405 al abrirlo en el navegador.
    payload = {"excludeZeroPxAndQty": False, "T2": True, "T1": False, "T0": False}
    try:
        sesion = _sesion_byma()
        datos = _post_byma(sesion, "negociable-obligations", payload)
        registros = datos.get("data", datos) if isinstance(datos, dict) else datos
        describir(registros if isinstance(registros, list) else [registros])
    except Exception as exc:
        fallo(exc)


def probar_byma_ficha(ticker: str) -> None:
    titulo(f"3. BYMA — ficha técnica de {ticker} (¿trae cupón y amortizaciones?)")
    print("  Exploratorio: todavía no se usa en el dashboard. Lo que importa acá")
    print("  es si aparecen cupón, fecha de emisión y cronograma de amortización.")
    try:
        sesion = _sesion_byma()
    except Exception as exc:
        fallo(exc)
        return
    # Formas de pedido tomadas de PyOBD, que consume estos mismos endpoints:
    # la ficha general pide solo el símbolo, la de cotización además el plazo
    # de liquidación ("1" = CI, "2" = 24HS, "3" = 48HS).
    consultas = (
        ("bnown/fichatecnica/especies/general", {"symbol": ticker}),
        ("bnown/fichatecnica/especies/cotizacion", {"symbol": ticker, "settlementType": "2"}),
    )
    for ruta, payload in consultas:
        try:
            datos = _post_byma(sesion, ruta, payload)
            registros = datos.get("data", datos) if isinstance(datos, dict) else datos
            registros = registros if isinstance(registros, list) else [registros]
            describir(registros)
            # La ficha general se imprime COMPLETA: sus campos de texto (cupón,
            # forma de amortización) son los que deciden si el flujo de fondos
            # se puede reconstruir, y recortarlos deja la pregunta sin responder.
            if registros and ruta.endswith("general"):
                print("  --- registro completo ---")
                for campo, valor in sorted(registros[0].items()):
                    print(f"    {campo}: {valor!r}")
        except Exception as exc:
            fallo(exc)


def probar_cronogramas() -> None:
    titulo("4. rendimientos-ar — cronogramas de pago (fuente actual de flujos)")
    url = "https://raw.githubusercontent.com/arisbdar/rendimientos-ar/main/public/config.json"
    print(f"  GET {url}")
    try:
        respuesta = requests.get(url, timeout=TIMEOUT)
        respuesta.raise_for_status()
        ons = respuesta.json().get("ons", {})
        print(f"  ✅ {len(ons)} ON(s) con cronograma")
        if ons:
            clave = sorted(ons)[0]
            print(f"  ejemplo: {clave} -> {json.dumps(ons[clave], ensure_ascii=False)[:300]}")
    except Exception as exc:
        fallo(exc)


def probar_tesoro() -> None:
    titulo("5. Yahoo Finance — curva del Tesoro de EE.UU. (spread crediticio)")
    try:
        import yfinance as yf
    except ImportError:
        print("  ⚠️  yfinance no está instalado: pip install -r requirements.txt")
        return
    for simbolo, tramo in (("^IRX", "3M"), ("^FVX", "5A"), ("^TNX", "10A"), ("^TYX", "30A")):
        try:
            historial = yf.Ticker(simbolo).history(period="5d")
            ultimo = historial["Close"].dropna().iloc[-1]
            print(f"  ✅ {simbolo} ({tramo}): {ultimo:.2f}%")
        except Exception as exc:
            print(f"  ❌ {simbolo} ({tramo}): {type(exc).__name__}: {exc}")



# Nombres candidatos del ticker y del precio en la respuesta de BYMA. La API
# no está documentada, así que en vez de asumir uno se prueban los habituales
# y se informa cuál se encontró: si ninguno aparece, el problema es que cambió
# el esquema y conviene verlo dicho, no deducirlo de una comparación vacía.
_CAMPOS_TICKER = ("symbol", "securityDesc", "denominationCcy", "ticker")
_CAMPOS_PRECIO = ("settlementPrice", "trade", "closingPrice", "last", "price")


def _primer_campo(registro: dict, candidatos: tuple[str, ...]) -> str | None:
    return next((campo for campo in candidatos if campo in registro), None)


def _indexar_byma(registros: list[dict]) -> tuple[dict[str, float], str | None, str | None]:
    if not registros:
        return {}, None, None
    campo_ticker = _primer_campo(registros[0], _CAMPOS_TICKER)
    campo_precio = _primer_campo(registros[0], _CAMPOS_PRECIO)
    if not campo_ticker or not campo_precio:
        return {}, campo_ticker, campo_precio

    indexado: dict[str, float] = {}
    for registro in registros:
        try:
            indexado[str(registro[campo_ticker]).strip().upper()] = float(registro[campo_precio])
        except (KeyError, TypeError, ValueError):
            continue
    return indexado, campo_ticker, campo_precio


def comparar_fuentes() -> None:
    """
    Cruza los precios de data912 contra los de BYMA, especie por especie.

    La pregunta que responde es si data912 es un espejo de BYMA o una fuente
    distinta. Importa por dos motivos: si son iguales, conviene ir directo a
    BYMA y dejar data912 de respaldo; si difieren, hay que saber en qué, porque
    una diferencia sistemática de precio suele significar que cada uno publica
    un plazo de liquidación distinto (24 hs contra 48 hs), no que uno esté mal.
    """
    titulo("6. data912 vs BYMA — ¿son la misma data?")
    try:
        respuesta = requests.get("https://data912.com/live/arg_corp", timeout=TIMEOUT)
        respuesta.raise_for_status()
        d912 = {
            str(r["symbol"]).strip().upper(): float(r["c"])
            for r in respuesta.json()
            if r.get("symbol") and r.get("c") is not None
        }
        print(f"  data912: {len(d912)} especies con precio")
    except Exception as exc:
        fallo(exc)
        return

    try:
        sesion = _sesion_byma()
    except Exception as exc:
        fallo(exc)
        return

    # Se prueban los tres plazos de liquidación por separado: si data912 calza
    # con uno y no con los otros, eso identifica qué plazo está publicando.
    for etiqueta, plazo in (("48 hs (T2)", "T2"), ("24 hs (T1)", "T1"), ("contado inmediato (T0)", "T0")):
        payload = {"excludeZeroPxAndQty": False, "T2": False, "T1": False, "T0": False}
        payload[plazo] = True
        print(f"\n  --- BYMA a {etiqueta} ---")
        try:
            datos = _post_byma(sesion, "negociable-obligations", payload)
            registros = datos.get("data", datos) if isinstance(datos, dict) else datos
            byma, campo_ticker, campo_precio = _indexar_byma(registros)
        except Exception as exc:
            fallo(exc)
            continue

        if not byma:
            print(f"  ⚠️  no se reconocieron los campos (ticker={campo_ticker}, precio={campo_precio})")
            print(f"      campos disponibles: {sorted(registros[0]) if registros else 'sin registros'}")
            continue

        print(f"  campos usados: ticker={campo_ticker}, precio={campo_precio}")
        comunes = sorted(set(d912) & set(byma))
        print(f"  BYMA: {len(byma)} especies | en común: {len(comunes)}")
        print(f"  solo en data912: {len(set(d912) - set(byma))} | solo en BYMA: {len(set(byma) - set(d912))}")

        if not comunes:
            continue

        iguales = 0
        diferencias: list[tuple[str, float, float, float]] = []
        for ticker in comunes:
            a, b = d912[ticker], byma[ticker]
            if a == b:
                iguales += 1
            elif b:
                diferencias.append((ticker, a, b, abs(a - b) / abs(b) * 100.0))

        print(f"  precios idénticos: {iguales}/{len(comunes)}")
        if diferencias:
            brechas = sorted(d for *_, d in diferencias)
            mediana = brechas[len(brechas) // 2]
            print(f"  diferencia mediana: {mediana:.3f}%  |  máxima: {brechas[-1]:.3f}%")
            print("  mayores diferencias:")
            for ticker, a, b, brecha in sorted(diferencias, key=lambda x: -x[3])[:5]:
                print(f"    {ticker:8} data912={a:>12.4f}  byma={b:>12.4f}  ({brecha:.2f}%)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ticker",
        default="YMCJD",
        help="Especie a consultar en la ficha técnica de BYMA (default: YMCJD)",
    )
    argumentos = parser.parse_args()

    print("Diagnóstico de las fuentes de datos de la pestaña de Bonos.")
    print("Cada bloque es independiente: que una fuente falle no invalida al resto.")

    probar_data912()
    probar_byma_ons()
    probar_byma_ficha(argumentos.ticker)
    probar_cronogramas()
    probar_tesoro()
    comparar_fuentes()

    print("\nListo. Pegame la salida y ajusto el código a lo que devuelvan de verdad.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
