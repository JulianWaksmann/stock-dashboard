#!/usr/bin/env python3
"""
scripts/panel_merval.py - El panel argentino en la terminal.

Corre la misma cadena que la sección de Streamlit —mismos precios, mismo dólar
implícito, mismo semáforo— pero imprime el resultado como texto.

Su uso más importante es `--ccl`: imprime el tipo de cambio que surge de cada
par acción local / ADR y señala los que no coinciden con el resto. Es la forma
práctica de verificar los ratios de `merval/catalog.py`, que son dato escrito a
mano y cambian con cada split o reestructuración. Un par que se despega diez
veces de la mediana es un ratio diez veces mal cargado, y la columna de ratio
sugerido dice cuál sería el correcto.

Uso:
    python3 scripts/panel_merval.py              # cuadro resumido, diario
    python3 scripts/panel_merval.py --ccl        # diagnóstico del dólar implícito
    python3 scripts/panel_merval.py --semanal
    python3 scripts/panel_merval.py --csv merval.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# El script vive en scripts/ y usa los módulos del proyecto, así que agrega la
# raíz del repositorio al path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from constants import MERVAL_CCL_MAX_DISPERSION_PCT  # noqa: E402
from indicators import compute_stock_technicals  # noqa: E402
from merval.catalog import adr_pairs, adr_tickers, local_tickers, stock_for  # noqa: E402
from merval.ccl import implied_ccl_series, to_usd  # noqa: E402
from merval.data_loader import _descargar, ventanas_para  # noqa: E402

_COLUMNAS_RESUMEN = (
    "Semáforo",
    "Ticker",
    "Empresa",
    "Precio (USD)",
    "RSI",
    "vs SMA 200 (%)",
    "vs Máx 52S (%)",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Panel de acciones argentinas en dólares")
    parser.add_argument("--semanal", action="store_true", help="Calcular en velas semanales.")
    parser.add_argument(
        "--ccl",
        action="store_true",
        help="Imprimir el diagnóstico del dólar implícito par por par y salir.",
    )
    parser.add_argument("--csv", metavar="ARCHIVO.csv", help="Guardar el cuadro completo.")
    args = parser.parse_args()

    interval = "1wk" if args.semanal else "1d"
    locales = list(local_tickers())
    adrs = list(adr_tickers())

    print(f"Descargando {len(locales)} acciones locales y {len(adrs)} ADR ({interval})...", file=sys.stderr)
    historiales = _descargar(locales + adrs, interval)

    ccl = implied_ccl_series(
        {t: historiales.get(t) for t in locales},
        {t: historiales.get(t) for t in adrs},
        adr_pairs(),
    )

    if not ccl.disponible:
        print("No se pudo calcular el dólar implícito: ningún par tiene las dos puntas.", file=sys.stderr)
        return 1

    print(f"\nDólar implícito del panel: ${ccl.ultimo:,.2f}")
    print(f"Pares usados: {len(ccl.pares_usados)} | dispersión: {ccl.dispersion_pct:.2f}%")
    if np.isfinite(ccl.dispersion_pct) and ccl.dispersion_pct > MERVAL_CCL_MAX_DISPERSION_PCT:
        print(
            f"ATENCIÓN: la dispersión supera el {MERVAL_CCL_MAX_DISPERSION_PCT:.0f}% esperado. "
            "Hay al menos un ratio mal cargado."
        )

    if args.ccl:
        print()
        print(ccl.detalle.round(2).to_string(index=False))
        sospechosos = ccl.detalle[ccl.detalle["Sospechoso"]]
        if not sospechosos.empty:
            print("\nPares a revisar en merval/catalog.py:")
            for _, fila in sospechosos.iterrows():
                sugerido = fila["Ratio sugerido"]
                sugerencia = f" → probar ratio {int(sugerido)}" if pd.notna(sugerido) else ""
                print(f"  {fila['Ticker']} / {fila['ADR']}: {fila['Desvío (%)']:+.1f}%{sugerencia}")
        return 0

    ventana_52w, squeeze_lookback = ventanas_para(interval)
    filas = []
    for ticker in locales:
        en_pesos = historiales.get(ticker)
        if en_pesos is None or en_pesos.empty:
            continue
        en_dolares = to_usd(en_pesos, ccl.serie)
        if en_dolares.empty:
            continue

        tecnicos = compute_stock_technicals(
            en_dolares, window_52w=ventana_52w, squeeze_lookback=squeeze_lookback
        )
        ficha = stock_for(ticker)
        filas.append({
            "Semáforo": tecnicos["confluence_signal"],
            "Ticker": ticker,
            "Empresa": ficha.nombre if ficha else ticker,
            "Precio (USD)": tecnicos["close"],
            "RSI": tecnicos["rsi_14"],
            "vs SMA 200 (%)": tecnicos["diff_sma_200_pct"],
            "vs Máx 52S (%)": tecnicos["dist_52w_high_pct"],
            "Flujo": tecnicos["institutional_flow"],
        })

    if not filas:
        print("No se pudo convertir ninguna acción a dólares.", file=sys.stderr)
        return 1

    df = pd.DataFrame(filas)
    print()
    print(df[list(_COLUMNAS_RESUMEN)].round(2).to_string(index=False))

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"\nCuadro guardado en {args.csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
