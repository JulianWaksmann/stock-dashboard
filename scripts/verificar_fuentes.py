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
    for ruta in ("bnown/fichatecnica/especies/general", "bnown/fichatecnica/especies/cotizacion"):
        for payload in ({"symbol": ticker}, {"especie": ticker}, {"Symbol": ticker}):
            try:
                datos = _post_byma(sesion, ruta, payload)
                registros = datos.get("data", datos) if isinstance(datos, dict) else datos
                describir(registros if isinstance(registros, list) else [registros])
                break
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

    print("\nListo. Pegame la salida y ajusto el código a lo que devuelvan de verdad.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
