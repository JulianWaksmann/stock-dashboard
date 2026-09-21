"""
components/formatting.py - Helpers de formato de texto compartidos entre componentes.

Se separa de `theme.py` (que es puramente visual: colores) porque esto es
formato de datos a texto, no estilo. Vive en `components/` porque es un
detalle de presentación usado únicamente por los componentes de Streamlit,
no una regla de negocio (esas están en `constants.py`/`indicators.py`).
"""

import pandas as pd


def format_signed_pct(value: int | float | None, decimals: int = 2) -> str:
    """
    Formatea un valor numérico como porcentaje con signo explícito (ej: "+3.25%").

    Devuelve "N/A" si el valor es None, NaN o no se puede convertir a float,
    en vez de propagar el error o imprimir literalmente "nan%".
    """
    if value is None or pd.isna(value):
        return "N/A"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return f"{num:+.{decimals}f}%"


def format_crypto_price(value: int | float | None) -> str:
    """
    Formatea un precio de cripto con tantos decimales como haga falta.

    Un precio fijo de dos decimales no sirve en esta clase de activo: en el
    mismo cuadro conviven Bitcoin en decenas de miles de dólares y monedas que
    cotizan a cinco millonésimos. Con dos decimales, media tabla mostraría
    "$0.00"; con ocho, Bitcoin sería ilegible. Los tramos de acá abajo dan
    siempre entre tres y cuatro cifras significativas.
    """
    if value is None or pd.isna(value):
        return "N/A"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "N/A"

    magnitud = abs(num)
    if magnitud >= 1000:
        return f"${num:,.0f}"
    if magnitud >= 1:
        return f"${num:,.2f}"
    if magnitud >= 0.01:
        return f"${num:.4f}"
    if magnitud >= 0.0001:
        return f"${num:.6f}"
    return f"${num:.8f}"


def format_usd_compact(value: int | float | None) -> str:
    """
    Formatea un monto en dólares de forma abreviada ("$1.2B", "$340.5M").

    El volumen diario de una cripto va de cientos de miles a decenas de miles
    de millones, y la capitalización del mercado entero pasa el billón: escrito
    completo, el número es una fila de dígitos que nadie compara de un vistazo.
    """
    if value is None or pd.isna(value):
        return "N/A"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "N/A"

    magnitud = abs(num)
    if magnitud >= 1e12:
        return f"${num / 1e12:,.2f}T"
    if magnitud >= 1e9:
        return f"${num / 1e9:,.1f}B"
    if magnitud >= 1e6:
        return f"${num / 1e6:,.1f}M"
    if magnitud >= 1e3:
        return f"${num / 1e3:,.1f}K"
    return f"${num:,.0f}"


# Nombres de mes en castellano. Se escriben acá en vez de usar `strftime`
# con locale: el locale depende de cómo esté configurada la máquina donde
# corre la app, así que el mismo código imprimiría "Jan" en un servidor y
# "ene" en otro.
_MESES: tuple[str, ...] = (
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)


def format_month_year(fecha) -> str:
    """Formatea una fecha como "may 2025", en castellano y sin depender del locale."""
    try:
        return f"{_MESES[fecha.month - 1]} {fecha.year}"
    except (AttributeError, IndexError, TypeError):
        return "N/A"
