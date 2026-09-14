"""
components/bonds_table.py - Cuadro comparativo de Obligaciones Negociables.

Es el equivalente de `screener_table.py` para renta fija. Mantiene la misma
gramática visual (semáforo coloreado a la izquierda, porcentajes en verde/rojo)
para que las dos pestañas se lean igual, pero el orden de las columnas responde
a cómo se evalúa un bono y no una acción: primero rendimiento (TIR), después
riesgo (duration, paridad), después liquidez, y recién al final los datos
descriptivos del emisor.
"""

import pandas as pd
import streamlit as st

from constants import (
    BOND_SIGNAL_ATTRACTIVE,
    BOND_SIGNAL_LOW,
    BOND_SIGNAL_RISK,
    BOND_SIGNAL_VERY_ATTRACTIVE,
)
from theme import (
    COLOR_NEGATIVE,
    COLOR_NEGATIVE_BG,
    COLOR_NEGATIVE_BG_MODERATE,
    COLOR_NEGATIVE_TEXT_MODERATE,
    COLOR_NEGATIVE_TEXT_STRONG,
    COLOR_NEUTRAL,
    COLOR_POSITIVE,
    COLOR_POSITIVE_BG,
    COLOR_POSITIVE_BG_MODERATE,
    COLOR_POSITIVE_TEXT_MODERATE,
    COLOR_POSITIVE_TEXT_STRONG,
)

# Marca visual de la fila cuyas condiciones de emisión todavía no fueron
# contrastadas contra el prospecto. Es la advertencia más importante del
# cuadro: sin condiciones verificadas, la TIR es una estimación.
VERIFIED_BADGE = "✅ Verificado"
UNVERIFIED_BADGE = "⚠️ Sin verificar"

# Orden de lectura del cuadro: rendimiento → riesgo → liquidez → descripción.
DISPLAY_COLUMNS = [
    "Atractivo",
    "Ticker",
    "Emisor",
    "Ley",
    "Calificación",
    "Liquidación",
    "Verif.",
    "Precio",
    "Var. (%)",
    "TIR (%)",
    "Spread vs UST (pb)",
    "Current Yield (%)",
    "Cupón (%)",
    "Paridad (%)",
    "Duration Mod.",
    "Vida Prom. (años)",
    "Vencimiento",
    "Spread (%)",
    "Volumen",
    "Lámina Mínima",
]


def style_bond_signal(val):
    """Colorea la etiqueta de atractivo con la misma paleta que el semáforo de acciones."""
    if val == BOND_SIGNAL_VERY_ATTRACTIVE:
        return f"background-color: {COLOR_POSITIVE_BG}; color: {COLOR_POSITIVE_TEXT_STRONG}; font-weight: bold;"
    if val == BOND_SIGNAL_ATTRACTIVE:
        return f"background-color: {COLOR_POSITIVE_BG_MODERATE}; color: {COLOR_POSITIVE_TEXT_MODERATE}; font-weight: 600;"
    if val == BOND_SIGNAL_RISK:
        return f"background-color: {COLOR_NEGATIVE_BG}; color: {COLOR_NEGATIVE_TEXT_STRONG}; font-weight: bold;"
    if val == BOND_SIGNAL_LOW:
        return f"background-color: {COLOR_NEGATIVE_BG_MODERATE}; color: {COLOR_NEGATIVE_TEXT_MODERATE}; font-weight: 600;"
    return f"color: {COLOR_NEUTRAL};"


def style_variation(val):
    """Verde para variaciones positivas, rojo para negativas."""
    if pd.isna(val):
        return ""
    try:
        num = float(val)
    except (TypeError, ValueError):
        return ""
    if num > 0:
        return f"color: {COLOR_POSITIVE}; font-weight: 600;"
    if num < 0:
        return f"color: {COLOR_NEGATIVE}; font-weight: 600;"
    return f"color: {COLOR_NEUTRAL};"


def style_parity(val):
    """
    Colorea la paridad respecto de la par (100).

    Bajo la par se marca en verde porque implica que parte del retorno del bono
    llega como ganancia de capital al vencimiento; sobre la par, en rojo, porque
    el precio converge a la baja hacia el valor técnico.
    """
    if pd.isna(val):
        return ""
    try:
        num = float(val)
    except (TypeError, ValueError):
        return ""
    if num < 100:
        return f"color: {COLOR_POSITIVE}; font-weight: 600;"
    if num > 100:
        return f"color: {COLOR_NEGATIVE}; font-weight: 600;"
    return f"color: {COLOR_NEUTRAL};"


def render_bonds_table(df: pd.DataFrame):
    """Renderiza el cuadro comparativo de ONs con formato y ayudas por columna."""
    if df.empty:
        st.warning("No hay ONs que coincidan con los filtros seleccionados.")
        return

    df_display = df.copy()
    df_display["Verif."] = df_display["Verificado"].map(
        lambda ok: VERIFIED_BADGE if ok else UNVERIFIED_BADGE
    )

    available = [col for col in DISPLAY_COLUMNS if col in df_display.columns]
    df_display = df_display[available]

    variation_cols = [col for col in ("Var. (%)", "Spread vs UST (pb)") if col in df_display.columns]
    styled = df_display.style.map(style_bond_signal, subset=["Atractivo"])
    if variation_cols:
        styled = styled.map(style_variation, subset=variation_cols)
    if "Paridad (%)" in df_display.columns:
        styled = styled.map(style_parity, subset=["Paridad (%)"])

    column_config = {
        "Atractivo": st.column_config.TextColumn(
            "🚦 Atractivo",
            width="medium",
            help="🌟 MUY ATRACTIVO | 🟢 ATRACTIVO | 🟡 NEUTRAL | 🟠 POCO ATRACTIVO | 🚨 ALERTA DE RIESGO | ⚪ SIN DATOS",
        ),
        "Ticker": st.column_config.TextColumn("Especie", width="small"),
        "Emisor": st.column_config.TextColumn("Emisor", width="medium"),
        "Ley": st.column_config.TextColumn(
            "Ley",
            width="small",
            help="Jurisdicción aplicable. NY = se litiga en tribunales de Nueva York; ARG = tribunales argentinos.",
        ),
        "Calificación": st.column_config.TextColumn(
            "Calificación",
            width="small",
            help="Calificación crediticia local del emisor (FIX SCR, Moody's Local, etc.). 's/c' = sin cargar en el catálogo.",
        ),
        "Liquidación": st.column_config.TextColumn(
            "Liquidación",
            width="small",
            help="Especie según la última letra del ticker: O liquida en pesos, D en dólar MEP, C en dólar cable. Es la misma ON en las tres, cambia la moneda del precio.",
        ),
        "Verif.": st.column_config.TextColumn(
            "Condiciones",
            width="small",
            help="Si dice ⚠️ Sin verificar, el cupón y el vencimiento no fueron contrastados contra el prospecto: la TIR es estimativa.",
        ),
        "Precio": st.column_config.NumberColumn(
            "Precio",
            format="%.2f",
            help="Precio por cada 100 VN (valor nominal), en la moneda de la especie: pesos para la especie O, dólares para D y C.",
        ),
        "Var. (%)": st.column_config.NumberColumn("Var. (%)", format="%+.2f%%"),
        "TIR (%)": st.column_config.NumberColumn(
            "TIR (%)",
            format="%.2f%%",
            help="Rendimiento efectivo anual si se mantiene hasta el vencimiento y se reinvierten los cupones a la misma tasa. Es LA variable de comparación entre bonos.",
        ),
        "Spread vs UST (pb)": st.column_config.NumberColumn(
            "Spread vs UST (pb)",
            format="%+.0f",
            help="Puntos básicos que la ON paga por encima del bono del Tesoro de EE.UU. de duration equivalente. Es el precio del riesgo argentino + riesgo del emisor.",
        ),
        "Current Yield (%)": st.column_config.NumberColumn(
            "Renta Anual (%)",
            format="%.2f%%",
            help="Cupón anual dividido el precio pagado. Mide el flujo de caja del año, sin contar la ganancia o pérdida de capital.",
        ),
        "Cupón (%)": st.column_config.NumberColumn(
            "Cupón (%)",
            format="%.2f%%",
            help="Tasa nominal anual sobre el valor nominal residual. No es el rendimiento: eso es la TIR.",
        ),
        "Paridad (%)": st.column_config.NumberColumn(
            "Paridad (%)",
            format="%.1f%%",
            help="Precio sobre valor técnico. <100 cotiza bajo la par (descuento), >100 sobre la par (premio).",
        ),
        "Duration Mod.": st.column_config.NumberColumn(
            "Duration Mod.",
            format="%.2f",
            help="Riesgo de tasa: caída aproximada del precio, en %, si el rendimiento exigido sube 1 punto porcentual.",
        ),
        "Vida Prom. (años)": st.column_config.NumberColumn(
            "Vida Prom.",
            format="%.2f",
            help="Plazo promedio de devolución del capital. En un bono que amortiza en cuotas es bastante menor al plazo al vencimiento.",
        ),
        "Vencimiento": st.column_config.DateColumn("Vencimiento", format="YYYY-MM-DD"),
        "Spread (%)": st.column_config.NumberColumn(
            "Spread Puntas (%)",
            format="%.2f%%",
            help="Diferencia entre punta vendedora y compradora sobre el punto medio. Es el costo de entrar y salir: la medida práctica de liquidez.",
        ),
        "Volumen": st.column_config.NumberColumn("Volumen", format="%.0f"),
        "Lámina Mínima": st.column_config.NumberColumn(
            "Lámina Mín.",
            format="%.0f",
            help="Valor nominal mínimo negociable. Una lámina de 100.000 deja la ON fuera del alcance minorista.",
        ),
    }

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={k: v for k, v in column_config.items() if k in df_display.columns},
        height=620,
    )
