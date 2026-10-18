#!/usr/bin/env python3
"""
scripts/medir_semaforo.py - ¿Funcionó el semáforo? en la terminal.

Replaya el semáforo barra por barra sobre el historial de un panel y lo cruza
con el retorno de las barras siguientes. Es la misma cadena que la sección del
tablero (`components/signal_stats_panel.py`), impresa como texto: sirve para
medir las dos calibraciones —acciones y cripto— una al lado de la otra sin
levantar la interfaz.

Igual que los otros scripts, no importa nada de Streamlit. Los precios se
piden directo al proveedor (`yfinance` para acciones, `crypto/prices_source`
para cripto) en vez de pasar por los `data_loader`, que son la capa de I/O de
la interfaz y traen el caché de Streamlit con ellos.

Lo primero que hay que leer es la fila de base: una señal solo aporta si su
exceso sobre una barra cualquiera del mismo período es claramente positivo
(negativo, en las de venta). Los límites de la medición están en el docstring
de `signal_stats.py` y conviene leerlos antes de sacar conclusiones.

Uso:
    python3 scripts/medir_semaforo.py                          # acciones, 20 ruedas
    python3 scripts/medir_semaforo.py --horizonte 5 60
    python3 scripts/medir_semaforo.py --mercado cripto --grupo memes
    python3 scripts/medir_semaforo.py --mercado cripto --semanal
    python3 scripts/medir_semaforo.py --top 10 --casos casos.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# El script vive en scripts/ y usa los módulos del proyecto, así que agrega la
# raíz del repositorio al path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from constants import (  # noqa: E402
    CRYPTO_UNIVERSE_DEFI,
    CRYPTO_UNIVERSE_LAYER1,
    CRYPTO_UNIVERSE_MEME,
    CRYPTO_UNIVERSE_TOP,
    SIGNAL_STATS_MIN_CASES,
)
from crypto.catalog import assets_for_universe  # noqa: E402
from crypto.panel import CRYPTO_THRESHOLDS, spec_for_timeframe  # noqa: E402
from crypto.prices_source import fetch_crypto_history  # noqa: E402
from indicators import STOCK_THRESHOLDS  # noqa: E402
from signal_stats import COL_CASES, COL_SIGNAL, measure_signal_quality  # noqa: E402

_GRUPOS = {
    "top": CRYPTO_UNIVERSE_TOP,
    "capa1": CRYPTO_UNIVERSE_LAYER1,
    "defi": CRYPTO_UNIVERSE_DEFI,
    "memes": CRYPTO_UNIVERSE_MEME,
}

# Ventanas de calendario de una acción: 252 ruedas al año, squeeze contra seis
# meses. Son los valores por omisión de `compute_stock_technicals`.
_ACCIONES_VENTANA_52W = 252
_ACCIONES_SQUEEZE_LOOKBACK = 126


def _historiales_acciones(tickers: list[str], interval: str) -> dict[str, pd.DataFrame]:
    """OHLCV de cada acción, pedido en bloque como lo hace el tablero."""
    import yfinance as yf

    period = "5y" if interval == "1wk" else "2y"
    descarga = yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    historiales = {}
    for ticker in tickers:
        if isinstance(descarga.columns, pd.MultiIndex):
            if ticker not in descarga.columns.levels[0]:
                continue
            df = descarga[ticker].dropna(how="all")
        else:
            df = descarga
        if not df.empty and "Close" in df.columns:
            historiales[ticker] = df.sort_index()
    return historiales


def main() -> int:
    parser = argparse.ArgumentParser(description="Medición del semáforo de confluencia")
    parser.add_argument(
        "--mercado",
        choices=("acciones", "cripto"),
        default="acciones",
        help="Qué panel medir (por omisión, acciones).",
    )
    parser.add_argument(
        "--horizonte",
        type=int,
        nargs="+",
        default=[20],
        help="Horizontes en barras, uno o varios (por omisión, 20).",
    )
    parser.add_argument("--semanal", action="store_true", help="Medir en velas semanales.")
    parser.add_argument(
        "--grupo",
        choices=tuple(_GRUPOS),
        default="top",
        help="Universo cripto (solo con --mercado cripto).",
    )
    parser.add_argument("--top", type=int, default=20, help="Cuántos activos medir.")
    parser.add_argument("--casos", metavar="ARCHIVO.csv", help="Guardar el detalle barra por barra.")
    args = parser.parse_args()

    interval = "1wk" if args.semanal else "1d"

    if args.mercado == "cripto":
        activos = assets_for_universe(_GRUPOS[args.grupo])[: args.top]
        tickers = [a.ticker for a in activos]
        print(f"Descargando {len(tickers)} criptomonedas ({interval})...", file=sys.stderr)
        historiales, fallidas = fetch_crypto_history(tickers, timeframe=interval)
        spec = spec_for_timeframe(interval)
        ventana_52w = spec.ventana_52w
        squeeze_lookback = spec.squeeze_lookback
        thresholds = CRYPTO_THRESHOLDS
        if fallidas:
            print(f"No respondieron: {', '.join(fallidas)}", file=sys.stderr)
    else:
        from data_loader import TOP_50_DEFAULT  # noqa: PLC0415

        tickers = TOP_50_DEFAULT[: args.top]
        print(f"Descargando {len(tickers)} acciones ({interval})...", file=sys.stderr)
        historiales = _historiales_acciones(tickers, interval)
        ventana_52w = _ACCIONES_VENTANA_52W
        squeeze_lookback = _ACCIONES_SQUEEZE_LOOKBACK
        thresholds = STOCK_THRESHOLDS

    if not historiales:
        print("No se pudo descargar ningún historial.", file=sys.stderr)
        return 1

    unidad = "semanas" if args.semanal else "ruedas"
    detalle = []

    for horizonte in args.horizonte:
        resumen, casos = measure_signal_quality(
            historiales,
            horizon=horizonte,
            window_52w=ventana_52w,
            squeeze_lookback=squeeze_lookback,
            thresholds=thresholds,
        )
        if resumen.empty:
            print(f"\nHorizonte {horizonte} {unidad}: sin casos suficientes.")
            continue

        print(
            f"\n=== {args.mercado.upper()} | horizonte {horizonte} {unidad} | "
            f"{len(historiales)} activos | {len(casos):,} barras ==="
        )
        anecdoticas = resumen.loc[resumen[COL_CASES] < SIGNAL_STATS_MIN_CASES, COL_SIGNAL].tolist()
        print(resumen.round(2).to_string(index=False))
        if anecdoticas:
            print(
                f"(menos de {SIGNAL_STATS_MIN_CASES} casos, anecdótico: "
                f"{', '.join(anecdoticas)})"
            )

        casos = casos.copy()
        casos["Horizonte"] = horizonte
        detalle.append(casos)

    if args.casos and detalle:
        pd.concat(detalle, ignore_index=True).to_csv(args.casos, index=False)
        print(f"\nDetalle barra por barra guardado en {args.casos}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
