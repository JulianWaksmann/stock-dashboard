"""
components/bonds_table.py - Cuadro comparativo de Obligaciones Negociables.

Es el equivalente de `screener_table.py` para renta fija. Mantiene la misma
gramática visual (porcentajes en verde/rojo) para que las dos pestañas se lean
igual, pero el orden de las columnas responde a cómo se evalúa un bono y no una
acción: primero rendimiento (TIR), después riesgo (duration, paridad), después
liquidez, y recién al final los datos descriptivos del emisor.

La columna "Atractivo" no se muestra: es la traducción del Puntaje a una
etiqueta, y teniendo el puntaje al lado decía lo mismo dos veces ocupando el
ancho de la izquierda. El dato sigue en el DataFrame, porque el filtro por
atractivo y el panel de alertas lo usan, y `style_bond_signal` sigue disponible
para cuando la columna esté presente (vista de desglose o un llamador futuro).
"""

import pandas as pd
import streamlit as st

from constants import (
    BOND_SCORE_JURISDICTION,
    BOND_SCORE_LIQUIDITY,
    BOND_SCORE_PARITY,
    BOND_SCORE_RATE_RISK,
    BOND_SCORE_YIELD,
    BOND_SIGNAL_ATTRACTIVE,
    BOND_SIGNAL_LOW,
    BOND_SIGNAL_RISK,
    BOND_SIGNAL_VERY_ATTRACTIVE,
    BOND_VOLUME_QUARTILE_COLUMN,
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

# Columnas que identifican la fila. No se ocultan aunque vengan vacías: sin
# ellas no se sabe de qué bono habla cada renglón.
_NEVER_HIDE = frozenset({"Ticker", "Emisor"})

# Lo esencial para decidir, en orden de lectura: qué tan buena es la
# oportunidad, de qué bono se trata, cuánto rinde, cuánto riesgo tiene y si se
# puede operar. Todo lo demás (puntas, cantidades, convexidad, valor técnico,
# interés corrido) es detalle de segundo orden y vive detrás del interruptor
# de vista completa: una tabla de veinte columnas no se lee, se escanea.
ESSENTIAL_COLUMNS = [
    "Puntaje",
    "Ticker",
    "Emisor",
    "TIR (%)",
    "Calificación",
    "Duration Mod.",
    "Paridad (%)",
    "Spread (%)",
    "Volumen",
    BOND_VOLUME_QUARTILE_COLUMN,
    "Precio",
    "Vencimiento",
    "Ley",
]

# El desagregado del puntaje: por qué esta ON puntúa lo que puntúa.
SCORE_BREAKDOWN_COLUMNS = [
    BOND_SCORE_YIELD,
    BOND_SCORE_LIQUIDITY,
    BOND_SCORE_RATE_RISK,
    BOND_SCORE_PARITY,
    BOND_SCORE_JURISDICTION,
    "Cobertura",
]

FULL_COLUMNS = [
    "Puntaje",
    "Ticker",
    "Emisor",
    "Ley",
    "Liquidación",
    "Fuente",
    "Verif.",
    "Precio",
    "Var. (%)",
    "TIR (%)",
    "Calificación",
    "Spread vs UST (pb)",
    "Current Yield (%)",
    "Cupón (%)",
    "Paridad (%)",
    "Duration Mod.",
    "Vida Prom. (años)",
    "Vencimiento",
    "Spread (%)",
    "Volumen",
    BOND_VOLUME_QUARTILE_COLUMN,
    "Lámina Mínima",
    "Garantía",
    "ISIN",
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


def render_bonds_table(df: pd.DataFrame, full: bool = False, breakdown: bool = False):
    """
    Renderiza el cuadro comparativo de ONs.

    `full` muestra todas las columnas y `breakdown` agrega el desagregado del
    puntaje. Por defecto se muestra solo lo esencial: el resto está disponible,
    pero no compitiendo por la atención en la primera lectura.
    """
    if df.empty:
        st.warning("No hay ONs que coincidan con los filtros seleccionados.")
        return

    df_display = df.copy()
    df_display["Verif."] = df_display["Verificado"].map(
        lambda ok: VERIFIED_BADGE if ok else UNVERIFIED_BADGE
    )

    columns = list(FULL_COLUMNS if full else ESSENTIAL_COLUMNS)
    if breakdown:
        columns += SCORE_BREAKDOWN_COLUMNS
    available = [col for col in columns if col in df_display.columns]

    # Una columna sin un solo valor no informa nada y ensucia la lectura. Es el
    # caso normal, no el excepcional: paridad, valor técnico, interés corrido y
    # vida promedio necesitan saber qué parte de cada pago es renta, y el
    # cronograma público no lo separa, así que quedan vacías salvo que la ON
    # esté en el catálogo local.
    #
    # Hay un motivo extra para no dejarlas: Streamlit dibuja un NaN numérico
    # como el texto "None" (comportamiento de la librería, no del cuadro: pasa
    # igual sin `column_config`), así que una columna vacía no se ve vacía, se
    # ve rota.
    empty = [
        col
        for col in available
        if col not in _NEVER_HIDE and df_display[col].isna().all()
    ]
    df_display = df_display[[col for col in available if col not in empty]]

    variation_cols = [col for col in ("Var. (%)", "Spread vs UST (pb)") if col in df_display.columns]
    styled = df_display.style
    if "Atractivo" in df_display.columns:
        styled = styled.map(style_bond_signal, subset=["Atractivo"])
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
        "Puntaje": st.column_config.ProgressColumn(
            "Puntaje",
            format="%.0f",
            min_value=0,
            max_value=100,
            help="Puntaje de Oportunidad (0-100): rendimiento, liquidez, riesgo de tasa, paridad y jurisdicción ponderados y comparados contra el resto del panel del día. Un bono promedio ronda 50.",
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
            help=(
                "Calificación crediticia del EMISOR, no de la especie, con la calificadora "
                "entre paréntesis: una nota en escala nacional ('AA(arg)') y una global "
                "('AA') no significan lo mismo ni se comparan entre sí. Se lee al lado de "
                "la TIR a propósito: un rendimiento alto sin saber a quién le estás "
                "prestando no dice nada. 's/c' = sin cargar. Ninguna fuente pública la "
                "publica en formato consultable por máquina, así que se carga a mano en "
                "`data/calificaciones.json` y solo se muestra con `verificado: true`."
            ),
        ),
        "Liquidación": st.column_config.TextColumn(
            "Liquidación",
            width="small",
            help="Especie según la última letra del ticker. O: liquida en pesos. D: dólar MEP, los dólares quedan en tu cuenta local. C: dólar cable (contado con liquidación), los dólares quedan en una cuenta del exterior — algunas plataformas lo muestran como 'ext'. Es la misma ON en las tres: cambia dónde y en qué moneda cobrás.",
        ),
        "Fuente": st.column_config.TextColumn(
            "Fuente",
            width="small",
            help="De dónde salió el cronograma de pagos. El catálogo local permite calcular además paridad, valor técnico y vida promedio; la fuente pública solo informa el total de cada pago, así que esas columnas quedan vacías.",
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
        BOND_VOLUME_QUARTILE_COLUMN: st.column_config.TextColumn(
            "Vol. (cuartil)",
            width="small",
            help=(
                "Cuartil de volumen operado, calculado DENTRO de cada moneda: el "
                "volumen de la especie en pesos está en pesos y el de la MEP en "
                "dólares, así que un ranking conjunto no compararía lo mismo. "
                "Se mide contra el panel entero del mercado, no contra las filas "
                "que dejaron los filtros. Las que no operaron no entran al "
                "cálculo: se etiquetan aparte."
            ),
        ),
        "Garantía": st.column_config.TextColumn(
            "Garantía",
            width="small",
            help="Tipo de garantía de la emisión, según la ficha técnica de BYMA.",
        ),
        "ISIN": st.column_config.TextColumn("ISIN", width="small"),
        "Cobertura": st.column_config.NumberColumn(
            "Cobertura",
            format="%.0f%%",
            help="Qué porcentaje del peso total del puntaje se pudo medir de verdad. Lo que falta no puntúa cero: se excluye y los pesos se reparten sobre el resto.",
        ),
        BOND_SCORE_YIELD: st.column_config.NumberColumn(format="%.0f"),
        BOND_SCORE_LIQUIDITY: st.column_config.NumberColumn(format="%.0f"),
        BOND_SCORE_RATE_RISK: st.column_config.NumberColumn(format="%.0f"),
        BOND_SCORE_PARITY: st.column_config.NumberColumn(format="%.0f"),
        BOND_SCORE_JURISDICTION: st.column_config.NumberColumn(format="%.0f"),
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

    if empty:
        st.caption(
            f"ℹ️ Sin datos para {len(empty)} columna(s), así que no se muestran: "
            f"**{', '.join(empty)}**. Estas métricas necesitan saber qué parte de cada pago "
            "es renta y cuál es capital; el cronograma público solo publica el total. Se "
            "completan cargando las condiciones de emisión en `data/ons_catalog.csv`."
        )
