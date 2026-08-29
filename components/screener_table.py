"""
components/screener_table.py - Visualización y formateo de la tabla de acciones (Sin Empresa ni Sector, con Flujo Institucional)
"""

import streamlit as st
import pandas as pd
import numpy as np


def render_screener_table(df: pd.DataFrame, timeframe_label: str = "Diario"):
    """
    Renderiza la tabla interactiva en Streamlit:
      - 'Semáforo' como primera columna.
      - 'Ticker' y 'Flujo Institucional' (🐳 Acumulación / 📉 Distribución).
      - Ratios de valuación y métricas de momentum.
      - Sin columnas 'Empresa' ni 'Sector' para máxima limpieza visual.
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

    # Configuración de columnas interactivas
    col_configs = {
        "Semáforo": st.column_config.TextColumn(
            "🚦 Semáforo Confluencia",
            width="medium",
            help="🔴 VENTA/ROTAR | 🟢 COMPRA/SWING | 🚨 SQUEEZE | 🟡 NEUTRAL"
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
            help=f"RSI 14 {timeframe_label}: <35 Sobreventa, >70 Sobrecompra"
        ),
        diff_20_col: st.column_config.NumberColumn(f"vs SMA 20{tf_suffix}", format="%+.2f%%"),
        diff_50_col: st.column_config.NumberColumn(f"vs SMA 50{tf_suffix}", format="%+.2f%%"),
        diff_200_col: st.column_config.NumberColumn(f"vs SMA 200{tf_suffix}", format="%+.2f%%"),
        "Dif. % Máx 52S": st.column_config.NumberColumn("vs Máx 52S (%)", format="%+.2f%%", help="Distancia respecto al Máximo de 52 semanas"),
        "Bollinger BW (%)": st.column_config.NumberColumn("Bandwidth (%)", format="%.1f%%", help="Ancho de Bandas de Bollinger")
    }

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config=col_configs,
        height=620
    )
