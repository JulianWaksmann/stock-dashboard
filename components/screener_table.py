"""
components/screener_table.py - Visualización interactiva con colores condicionales (Verde para subas, Rojo para bajas)
"""

import streamlit as st
import pandas as pd
import numpy as np


def style_percentage(val):
    """Aplica color verde a subas/valores positivos y rojo a bajas/valores negativos."""
    if pd.isna(val):
        return ""
    try:
        num = float(val)
        if num > 0:
            return "color: #22c55e; font-weight: 600;"
        elif num < 0:
            return "color: #ef4444; font-weight: 600;"
        else:
            return "color: #9ca3af;"
    except Exception:
        return ""


def style_semaforo(val):
    """Resalta el semáforo según el grado de la señal."""
    val_str = str(val)
    if "COMPRA FUERTE" in val_str:
        return "background-color: #052e16; color: #4ade80; font-weight: bold;"
    elif "COMPRA MODERADA" in val_str:
        return "background-color: #064e3b; color: #86efac; font-weight: 600;"
    elif "VENTA FUERTE" in val_str:
        return "background-color: #450a0a; color: #f87171; font-weight: bold;"
    elif "VENTA MODERADA" in val_str:
        return "background-color: #431407; color: #fdba74; font-weight: 600;"
    elif "SQUEEZE" in val_str:
        return "background-color: #422006; color: #fde047; font-weight: bold;"
    return "color: #9ca3af;"


def render_screener_table(df: pd.DataFrame, timeframe_label: str = "Diario"):
    """
    Renderiza la tabla interactiva en Streamlit con:
      - 'Semáforo' con sistema de grados.
      - Colores condicionales en TODAS las columnas de porcentaje (Verde para subas / Rojo para bajas).
      - Ratios de valuación y métricas técnicas.
    """
    if df.empty:
        st.warning("No hay acciones que coincidan con los filtros seleccionados.")
        return

    tf_suffix = " (Sem)" if timeframe_label.lower().startswith("sem") else " (Día)"

    rsi_col = f"RSI (14){tf_suffix}"
    diff_20_col = f"Dif. % SMA 20{tf_suffix}"
    diff_50_col = f"Dif. % SMA 50{tf_suffix}"
    diff_200_col = f"Dif. % SMA 200{tf_suffix}"

    display_cols = [
        "Semáforo",
        "Ticker",
        "Flujo Institucional",
        "Precio Actual",
        "Var. Período (%)",
        "PER Pasado (Trailing)",
        "PER Futuro (Forward)",
        "PER Prom. Hist. (5A)",
        rsi_col,
        diff_20_col,
        diff_50_col,
        diff_200_col,
        "Dif. % Máx 52S",
        "Bollinger BW (%)"
    ]

    available_cols = [c for c in display_cols if c in df.columns]
    df_display = df[available_cols].copy()

    # Columnas que llevan color condicional (%)
    pct_cols = [
        col for col in [
            "Var. Período (%)",
            diff_20_col,
            diff_50_col,
            diff_200_col,
            "Dif. % Máx 52S"
        ] if col in df_display.columns
    ]

    # Aplicar estilos con Pandas Styler
    styled_df = df_display.style.map(style_percentage, subset=pct_cols).map(style_semaforo, subset=["Semáforo"])

    # Configuración de columnas
    col_configs = {
        "Semáforo": st.column_config.TextColumn(
            "🚦 Semáforo",
            width="medium",
            help="🌟 COMPRA FUERTE | 🟢 COMPRA MODERADA | 🚨 VENTA FUERTE / ROTAR | 🟠 VENTA MODERADA | 🚨 SQUEEZE | 🟡 NEUTRAL"
        ),
        "Ticker": st.column_config.TextColumn("Ticker", width="small"),
        "Flujo Institucional": st.column_config.TextColumn(
            "Smart Money (OBV)",
            width="medium",
            help="🐳 Acumulación (OBV > SMA 20) | 📉 Distribución (OBV < SMA 20)"
        ),
        "Precio Actual": st.column_config.NumberColumn("Precio ($)", format="$%.2f"),
        "Var. Período (%)": st.column_config.NumberColumn("Var. (%)", format="%+.2f%%"),
        "PER Pasado (Trailing)": st.column_config.NumberColumn("PER Pasado", format="%.1fx", help="Trailing P/E (últimos 12 meses)"),
        "PER Futuro (Forward)": st.column_config.NumberColumn("PER Futuro", format="%.1fx", help="Forward P/E estimado a 12 meses"),
        "PER Prom. Hist. (5A)": st.column_config.NumberColumn("PER Hist. (5A)", format="%.1fx", help="Promedio histórico 5 años"),
        rsi_col: st.column_config.ProgressColumn(
            f"RSI 14 ({timeframe_label})",
            format="%.1f",
            min_value=0,
            max_value=100,
            help=f"RSI 14 {timeframe_label}: <45 Zona de entrada, >65 Zona de sobrecompra"
        ),
        diff_20_col: st.column_config.NumberColumn(f"vs SMA 20{tf_suffix}", format="%+.2f%%"),
        diff_50_col: st.column_config.NumberColumn(f"vs SMA 50{tf_suffix}", format="%+.2f%%"),
        diff_200_col: st.column_config.NumberColumn(f"vs SMA 200{tf_suffix}", format="%+.2f%%"),
        "Dif. % Máx 52S": st.column_config.NumberColumn("vs Máx 52S (%)", format="%+.2f%%", help="Distancia respecto al Máximo de 52 semanas"),
        "Bollinger BW (%)": st.column_config.NumberColumn("Bandwidth (%)", format="%.1f%%", help="Ancho de Bandas de Bollinger")
    }

    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config=col_configs,
        height=620
    )
