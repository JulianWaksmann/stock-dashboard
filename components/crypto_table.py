"""
components/crypto_table.py - Cuadro de criptomonedas.

Solo dibuja: recibe el DataFrame ya filtrado por `crypto/panel.py` y no hace
ninguna cuenta propia.

Es un módulo aparte de `screener_table.py` porque el cuadro de cripto no tiene
las mismas columnas (no hay PER, ni sector, ni dividendos) y sí tiene dos que
no existen en acciones: la fuerza relativa contra Bitcoin y la volatilidad
anualizada. Los estilos condicionales, en cambio, se importan de allá: pintar
de verde lo positivo y de rojo lo negativo es la misma regla en las dos
secciones, y duplicarla haría que un cambio de color llegue a una tabla y no
a la otra.
"""

import pandas as pd
import streamlit as st

from components.formatting import format_crypto_price, format_usd_compact
from components.screener_table import style_percentage, style_semaforo
from constants import (
    CRYPTO_FLOW_COLUMN,
    CRYPTO_RS_OUTPERFORM,
    CRYPTO_RS_UNDERPERFORM,
)
from theme import COLOR_NEGATIVE, COLOR_NEUTRAL, COLOR_POSITIVE

# Columnas que no se muestran nunca: son las claves estables que usan filtros
# y KPIs, duplicadas a propósito de las columnas con nombre en castellano.
_COLUMNAS_INTERNAS = (
    "Ticker",
    "PRECIO_VAL",
    "RSI_VAL",
    "DIFF_SMA_50_VAL",
    "DIFF_SMA_200_VAL",
    "DIST_52W_HIGH_PCT",
    "BB_BANDWIDTH",
    "RET_LONG_PCT",
    "RS_BTC_PP",
    "VOL_ANN_PCT",
    "VOLUMEN_VAL",
    "MARKET_CAP_VAL",
    "PESO_PANEL_PCT",
    "EXTENSION_SIGMAS",
    "Timeframe",
)


def style_relative_strength(val):
    """Pinta la columna de fuerza relativa con el mismo par verde/rojo del resto."""
    if val == CRYPTO_RS_OUTPERFORM:
        return f"color: {COLOR_POSITIVE}; font-weight: 600;"
    if val == CRYPTO_RS_UNDERPERFORM:
        return f"color: {COLOR_NEGATIVE}; font-weight: 600;"
    return f"color: {COLOR_NEUTRAL};"


def render_crypto_table(df: pd.DataFrame, timeframe_label: str = "Diario"):
    """
    Dibuja el cuadro de criptomonedas con colores condicionales.

    Precio y volumen se pasan a texto antes de mostrarse, en vez de usar una
    columna numérica con formato fijo: en el mismo cuadro conviven Bitcoin en
    decenas de miles de dólares y monedas de cinco millonésimos, y ningún
    formato con una cantidad fija de decimales sirve para los dos. El costo es
    que esas dos columnas ordenan como texto; se acepta porque comparar el
    precio nominal de dos criptos distintas no significa nada (depende de
    cuántas unidades se emitieron, no de cuánto vale la red).
    """
    if df.empty:
        st.warning("No hay criptomonedas que coincidan con los filtros seleccionados.")
        return

    df_display = df.drop(columns=[c for c in _COLUMNAS_INTERNAS if c in df.columns]).copy()

    for columna, formateador in (
        ("Precio (USD)", format_crypto_price),
        ("Volumen (USD)", format_usd_compact),
        ("Cap. Mercado (USD)", format_usd_compact),
    ):
        if columna in df_display.columns:
            df_display[columna] = df_display[columna].map(formateador)

    # Toda columna cuyo título termina en "(%)" o "(pp)" lleva color según el
    # signo. Se detectan por el título y no con una lista fija porque varios
    # dependen de la temporalidad elegida ("Var. 7d (%)" o "Var. 4s (%)").
    pct_cols = [
        c for c in df_display.columns
        if (c.endswith("(%)") or c.endswith("(pp)"))
        and c not in ("Bollinger BW (%)", "Volatilidad Anual. (%)", "Peso en Panel (%)")
        and not c.startswith("RSI")
    ]

    styled = df_display.style.map(style_percentage, subset=pct_cols).map(
        style_semaforo, subset=["Semáforo"]
    )
    if "vs BTC" in df_display.columns:
        styled = styled.map(style_relative_strength, subset=["vs BTC"])

    rsi_col = next((c for c in df_display.columns if c.startswith("RSI (14)")), None)

    col_configs = {
        "Semáforo": st.column_config.TextColumn(
            "🚦 Semáforo",
            width="medium",
            help="🌟 COMPRA FUERTE | 🟢 COMPRA MODERADA | 🚨 VENTA FUERTE / ROTAR | 🟠 VENTA MODERADA | 🚨 SQUEEZE | 🟡 NEUTRAL",
        ),
        "Cripto": st.column_config.TextColumn("Cripto", width="small"),
        "Nombre": st.column_config.TextColumn("Nombre", width="medium"),
        "Categoría": st.column_config.TextColumn("Categoría", width="small"),
        "Precio (USD)": st.column_config.TextColumn("Precio", width="small"),
        "Var. Período (%)": st.column_config.NumberColumn("Var. (%)", format="%+.2f%%"),
        "vs BTC": st.column_config.TextColumn(
            "vs BTC",
            width="medium",
            help="Cómo rindió frente a Bitcoin en la ventana larga. En cripto casi todo se mueve con BTC: subir menos que él es, en los hechos, perder terreno.",
        ),
        "Exceso vs BTC (pp)": st.column_config.NumberColumn(
            "Exceso vs BTC",
            format="%+.1f pp",
            help="Diferencia en puntos porcentuales entre el retorno de la cripto y el de Bitcoin en la misma ventana.",
        ),
        "Dif. % Máx 52S": st.column_config.NumberColumn(
            "vs Máx 52S (%)",
            format="%+.2f%%",
            help="Distancia respecto al máximo del último año (365 días: cripto opera todos los días).",
        ),
        "Bollinger BW (%)": st.column_config.NumberColumn("Bandwidth (%)", format="%.1f%%"),
        "Volatilidad Anual. (%)": st.column_config.NumberColumn(
            "Volatilidad Anual.",
            format="%.0f%%",
            help="Desvío de los retornos del último mes, anualizado. Es la medida de riesgo habitual del activo.",
        ),
        CRYPTO_FLOW_COLUMN: st.column_config.TextColumn(
            "Flujo (OBV)",
            width="medium",
            help="🐳 Acumulación (OBV > SMA 20) | 📉 Distribución (OBV < SMA 20). El volumen de cripto es minorista y agregado entre exchanges: no es huella institucional.",
        ),
        "Volumen (USD)": st.column_config.TextColumn("Volumen", width="small"),
        "Cap. Mercado (USD)": st.column_config.TextColumn(
            "Cap. Mercado",
            width="small",
            help="Capitalización de mercado: precio por oferta en circulación.",
        ),
        "Peso en Panel (%)": st.column_config.NumberColumn(
            "Peso en Panel",
            format="%.1f%%",
            help="Qué porción de la capitalización del panel representa esta moneda. Para Bitcoin es su dominancia dentro de este universo, que no es la dominancia global del mercado.",
        ),
        "Extensión (σ)": st.column_config.NumberColumn(
            "Extensión",
            format="%+.1f σ",
            help="Cuántos desvíos típicos de esta moneda separan hoy al precio de su media de 50 barras. Por encima de 2σ el semáforo la considera en zona de techo.",
        ),
    }

    if rsi_col:
        col_configs[rsi_col] = st.column_config.ProgressColumn(
            f"RSI 14 ({timeframe_label})",
            format="%.1f",
            min_value=0,
            max_value=100,
            help=f"RSI 14 {timeframe_label}: <45 zona de entrada, >65 zona de sobrecompra",
        )

    for columna in df_display.columns:
        if columna.startswith("Dif. % SMA") or columna.startswith("Var. "):
            col_configs.setdefault(
                columna,
                st.column_config.NumberColumn(columna.replace("Dif. % ", "vs "), format="%+.2f%%"),
            )

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config=col_configs,
        height=620,
    )
