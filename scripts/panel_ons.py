#!/usr/bin/env python3
"""
scripts/panel_ons.py - El panel de ONs en la terminal.

Corre exactamente la misma cadena que la pestaña de Streamlit —mismas fuentes,
mismo motor de cálculo, mismos filtros, mismo puntaje— pero imprime el
resultado como texto. Sirve para verificar el pipeline de punta a punta sin
levantar la interfaz, y para ver los números cuando algo no cierra.

No importa nada de Streamlit: los módulos de `bonds/` que hacen el trabajo
(`byma_source`, `flows_source`, `catalog`, `panel`, `scoring`) están escritos
sin dependencia de la interfaz justamente para poder usarlos así.

Uso:
    python3 scripts/panel_ons.py                      # top 50 en dólares
    python3 scripts/panel_ons.py --top 20
    python3 scripts/panel_ons.py --moneda mep
    python3 scripts/panel_ons.py --desglose           # aporte de cada dimensión
    python3 scripts/panel_ons.py --todas              # todas las columnas
    python3 scripts/panel_ons.py --csv panel.csv      # exportar
    python3 scripts/panel_ons.py --fecha 2026-09-30   # otra fecha de liquidación
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

# El script vive en scripts/ y usa los módulos del proyecto, así que agrega la
# raíz del repositorio al path. Copiarlo suelto a otra carpeta no alcanza: lo
# que importa está en bonds/, no acá.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from bonds.byma_source import fetch_byma_bond_prices  # noqa: E402
    from bonds.catalog import load_catalog  # noqa: E402
    from bonds.flows_source import fetch_community_flows  # noqa: E402
    from bonds.panel import apply_bond_filters, build_bonds_panel  # noqa: E402
except ModuleNotFoundError as exc:
    # Sin este mensaje, correr el script fuera del repositorio falla con un
    # "No module named 'bonds'" que no dice qué hacer al respecto.
    print(
        f"No se encontró el módulo '{exc.name}'.\n\n"
        "Este script forma parte del proyecto y usa el motor de cálculo que vive en bonds/,\n"
        "así que tiene que correrse desde adentro del repositorio:\n\n"
        "    git clone https://github.com/JulianWaksmann/stock-dashboard.git\n"
        "    cd stock-dashboard\n"
        "    git checkout corporate-bonds-tab\n"
        "    pip install -r requirements.txt\n"
        "    python scripts/panel_ons.py\n\n"
        "Si ya tenés el repositorio, entrá a su carpeta y corré 'python scripts/panel_ons.py'\n"
        "desde ahí, en lugar de copiar el archivo suelto a otro directorio.",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

from constants import (  # noqa: E402
    BOND_FILTER_LAW_ALL,
    BOND_FILTER_LIQUIDITY_ALL,
    BOND_FILTER_LIQUIDITY_TOP_20,
    BOND_FILTER_LIQUIDITY_TOP_50,
    BOND_FILTER_LIQUIDITY_TRADED,
    BOND_FILTER_SETTLEMENT_ALL,
    BOND_FILTER_SETTLEMENT_MEP,
    BOND_FILTER_SETTLEMENT_PESOS,
    BOND_FILTER_SETTLEMENT_USD,
    BOND_FILTER_SIGNAL_ALL,
    BOND_SCORE_JURISDICTION,
    BOND_SCORE_LIQUIDITY,
    BOND_SCORE_PARITY,
    BOND_SCORE_RATE_RISK,
    BOND_SCORE_YIELD,
)

# Las mismas columnas esenciales que muestra la pestaña, en el mismo orden.
COLUMNAS_ESENCIALES = [
    "Atractivo",
    "Puntaje",
    "Ticker",
    "Emisor",
    "TIR (%)",
    "Duration Mod.",
    "Paridad (%)",
    "Spread (%)",
    "Volumen",
    "Precio",
    "Vencimiento",
    "Ley",
]

COLUMNAS_DESGLOSE = [
    BOND_SCORE_YIELD,
    BOND_SCORE_LIQUIDITY,
    BOND_SCORE_RATE_RISK,
    BOND_SCORE_PARITY,
    BOND_SCORE_JURISDICTION,
    "Cobertura",
]

_MONEDAS = {
    "usd": BOND_FILTER_SETTLEMENT_USD,
    "mep": BOND_FILTER_SETTLEMENT_MEP,
    "pesos": BOND_FILTER_SETTLEMENT_PESOS,
    "todas": BOND_FILTER_SETTLEMENT_ALL,
}

_LIQUIDEZ_POR_TOPE = {
    20: BOND_FILTER_LIQUIDITY_TOP_20,
    50: BOND_FILTER_LIQUIDITY_TOP_50,
}


def _liquidez(tope: int | None) -> str:
    """
    Traduce el tope pedido al filtro de liquidez correspondiente.

    Los cortes de 20 y 50 son los que ofrece la pestaña; cualquier otro número
    no tiene filtro propio, así que se pide "solo las que operaron" y el recorte
    se hace después sobre el resultado ya ordenado por puntaje.
    """
    if tope is None:
        return BOND_FILTER_LIQUIDITY_ALL
    return _LIQUIDEZ_POR_TOPE.get(tope, BOND_FILTER_LIQUIDITY_TRADED)


def construir_panel(settlement: date) -> tuple[pd.DataFrame, list[str]]:
    """Descarga las tres fuentes y arma el panel. Devuelve `(panel, avisos)`."""
    avisos: list[str] = []

    print("⏳ Descargando precios de BYMA...", flush=True)
    precios, error_precios = fetch_byma_bond_prices()
    if error_precios:
        return pd.DataFrame(), [error_precios]
    print(f"   {len(precios)} especies")

    print("⏳ Descargando cronogramas de pago...", flush=True)
    flujos, error_flujos = fetch_community_flows()
    if error_flujos:
        avisos.append(error_flujos)
    print(f"   {len(flujos)} ONs con cronograma")

    catalogo, errores_catalogo = load_catalog()
    avisos.extend(errores_catalogo)
    if catalogo:
        print(f"   {len(catalogo)} ON(s) con condiciones cargadas a mano")

    # La curva del Tesoro es opcional: sin ella el panel omite el spread
    # crediticio, que es una columna informativa y no parte del puntaje.
    curva: dict[float, float] = {}
    try:
        print("⏳ Descargando curva del Tesoro...", flush=True)
        import yfinance as yf

        for simbolo, tramo in (("^IRX", 0.25), ("^FVX", 5.0), ("^TNX", 10.0), ("^TYX", 30.0)):
            historial = yf.Ticker(simbolo).history(period="5d")
            if not historial.empty:
                curva[tramo] = float(historial["Close"].dropna().iloc[-1])
        print(f"   {len(curva)} tramos")
    except Exception as exc:
        avisos.append(f"Sin curva del Tesoro ({exc}); no se informa el spread crediticio.")

    panel = build_bonds_panel(
        prices=precios,
        catalog=catalogo,
        settlement=settlement,
        flows_by_base=flujos,
        treasury_curve=curva,
    )
    return panel, avisos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--top", type=int, default=50, help="Cuántas ONs mostrar, por volumen (default: 50; 0 = todas)")
    parser.add_argument("--moneda", choices=sorted(_MONEDAS), default="usd", help="Especie de liquidación (default: usd)")
    parser.add_argument("--fecha", default=None, help="Fecha de liquidación YYYY-MM-DD (default: hoy)")
    parser.add_argument("--desglose", action="store_true", help="Agrega el aporte de cada dimensión al puntaje")
    parser.add_argument("--todas", action="store_true", help="Muestra todas las columnas calculadas")
    parser.add_argument("--incluir-sin-tir", action="store_true", help="Incluye las ONs sin cronograma conocido")
    parser.add_argument("--incluir-por-vencer", action="store_true",
                        help="Incluye las ONs a menos de 3 meses del vencimiento (ocultas por defecto: su TIR anualizada es un artefacto)")
    parser.add_argument("--csv", default=None, help="Guarda el resultado en un CSV")
    argumentos = parser.parse_args()

    settlement = (
        datetime.strptime(argumentos.fecha, "%Y-%m-%d").date() if argumentos.fecha else date.today()
    )
    tope = argumentos.top if argumentos.top and argumentos.top > 0 else None

    panel, avisos = construir_panel(settlement)
    for aviso in avisos:
        print(f"\n⚠️  {aviso}")

    if panel.empty:
        print("\nNo se pudo armar el panel.")
        return 1

    filtrado = apply_bond_filters(
        panel,
        settlement_filter=_MONEDAS[argumentos.moneda],
        liquidity_filter=_liquidez(tope),
        signal_filter=BOND_FILTER_SIGNAL_ALL,
        law_filter=BOND_FILTER_LAW_ALL,
        only_with_yield=not argumentos.incluir_sin_tir,
        include_near_maturity=argumentos.incluir_por_vencer,
    )
    if tope is not None:
        filtrado = filtrado.head(tope)

    if argumentos.todas:
        columnas = list(filtrado.columns)
    else:
        columnas = [c for c in COLUMNAS_ESENCIALES if c in filtrado.columns]
        if argumentos.desglose:
            columnas += [c for c in COLUMNAS_DESGLOSE if c in filtrado.columns]

    mediana = panel.attrs.get("median_ytm_pct", float("nan"))
    print(f"\n{'=' * 100}")
    print(f"PANEL DE ONs — liquidación {settlement:%d/%m/%Y} — {len(filtrado)} de {len(panel)} especies")
    print(f"Mediana de TIR del panel: {mediana:.2f}%  (es la referencia contra la que se puntúa)")
    print("=" * 100)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", None)
    print(filtrado[columnas].to_string(index=False, float_format=lambda v: f"{v:,.2f}"))

    print("\nDistribución del semáforo:")
    print(filtrado["Atractivo"].value_counts().to_string())

    if argumentos.csv:
        filtrado.to_csv(argumentos.csv, index=False)
        print(f"\n💾 Guardado en {argumentos.csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
