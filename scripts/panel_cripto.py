#!/usr/bin/env python3
"""
scripts/panel_cripto.py - El panel de criptomonedas en la terminal.

Corre la misma cadena que la sección de Streamlit —misma fuente, mismo motor
de cálculo, mismos filtros— pero imprime el resultado como texto. Sirve para
verificar el pipeline de punta a punta sin levantar la interfaz.

No importa nada de Streamlit, y eso es una prueba viva de la regla de capas:
`crypto/prices_source.py`, `crypto/catalog.py` y `crypto/panel.py` están
escritos sin dependencia de la interfaz justamente para poder usarlos así. Si
alguien mete un `st.` en cualquiera de los tres, este script deja de correr.

Uso:
    python3 scripts/panel_cripto.py                       # top 20, diario
    python3 scripts/panel_cripto.py --semanal
    python3 scripts/panel_cripto.py --grupo memes
    python3 scripts/panel_cripto.py --csv cripto.csv
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
    CRYPTO_BENCHMARK_TICKER,
    CRYPTO_UNIVERSE_DEFI,
    CRYPTO_UNIVERSE_LAYER1,
    CRYPTO_UNIVERSE_MEME,
    CRYPTO_UNIVERSE_TOP,
)
from crypto.catalog import assets_for_universe  # noqa: E402
from crypto.panel import build_crypto_panel  # noqa: E402
from crypto.prices_source import fetch_crypto_history  # noqa: E402

_GRUPOS = {
    "top": CRYPTO_UNIVERSE_TOP,
    "capa1": CRYPTO_UNIVERSE_LAYER1,
    "defi": CRYPTO_UNIVERSE_DEFI,
    "memes": CRYPTO_UNIVERSE_MEME,
}

# Lo que se imprime por omisión. El cuadro completo tiene treinta columnas y
# no entra en una terminal; con --todas se ven todas.
_COLUMNAS_RESUMEN = (
    "Semáforo",
    "Cripto",
    "Precio (USD)",
    "vs BTC",
    "Exceso vs BTC (pp)",
    "Volatilidad Anual. (%)",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Panel de criptomonedas en la terminal")
    parser.add_argument("--grupo", choices=sorted(_GRUPOS), default="top", help="Universo a analizar")
    parser.add_argument("--semanal", action="store_true", help="Usar velas semanales en vez de diarias")
    parser.add_argument("--todas", action="store_true", help="Imprimir todas las columnas")
    parser.add_argument("--csv", metavar="ARCHIVO", help="Exportar el cuadro a un CSV")
    args = parser.parse_args()

    universe = _GRUPOS[args.grupo]
    timeframe = "1wk" if args.semanal else "1d"
    assets = assets_for_universe(universe)

    tickers = [a.ticker for a in assets]
    a_descargar = list(dict.fromkeys([*tickers, CRYPTO_BENCHMARK_TICKER]))

    print(f"Bajando {len(a_descargar)} criptomonedas ({timeframe})...", file=sys.stderr)
    historiales, fallidas = fetch_crypto_history(a_descargar, timeframe=timeframe)

    if not historiales:
        print("No se pudo descargar ninguna cotización.", file=sys.stderr)
        return 1
    if fallidas:
        print(f"Sin datos para: {', '.join(fallidas)}", file=sys.stderr)

    df = build_crypto_panel(
        history=historiales,
        benchmark_history=historiales.get(CRYPTO_BENCHMARK_TICKER),
        timeframe=timeframe,
        assets=tuple(a for a in assets if a.ticker in historiales),
    )

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"Cuadro exportado a {args.csv}", file=sys.stderr)

    columnas = list(df.columns) if args.todas else [c for c in _COLUMNAS_RESUMEN if c in df.columns]
    with pd.option_context("display.width", 200, "display.max_columns", None):
        print(df[columnas].to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
