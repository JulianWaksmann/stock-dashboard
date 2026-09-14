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
