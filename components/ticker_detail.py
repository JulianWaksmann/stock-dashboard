"""
components/ticker_detail.py - Vista detallada y ficha técnica de una acción individual
"""

import pandas as pd
import streamlit as st

from components.charts import compute_chart_indicators, plot_stock_detail
from components.formatting import format_signed_pct


def render_ticker_detail_view(ticker: str, df_summary: pd.DataFrame, dict_history: dict[str, pd.DataFrame], timeframe_label: str = "Diario"):
    """
    Renderiza la ficha técnica y el gráfico interactivo avanzado de 4 paneles apilados.
    """
    if df_summary.empty or ticker not in df_summary['Ticker'].values:
        st.warning("Selecciona una acción válida.")
        return

    row = df_summary[df_summary['Ticker'] == ticker].iloc[0]
    df_hist = dict_history.get(ticker, pd.DataFrame())

    tf_suffix = " (Sem)" if "sem" in timeframe_label.lower() else " (Día)"
    confluence = row.get('Señal Confluencia', '🟡 NEUTRAL')

    col_title, col_sig = st.columns([3, 1])
    with col_title:
        st.markdown(f"### 🏢 {row['Empresa']} (`{ticker}`)")
        st.caption(f"Sector: **{row['Sector']}** | Temporalidad activa: **{timeframe_label}**")
    with col_sig:
        st.markdown(f"<div style='text-align:right; padding-top:10px; font-size:16px; font-weight:700;'>{confluence}</div>", unsafe_allow_html=True)

    # 1. Métricas de Valuación y Momentum
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Precio Actual", f"${row['Precio Actual']:.2f}", format_signed_pct(row['Var. Período (%)']))
    
    t_pe = f"{row['PER Pasado (Trailing)']:.1f}x" if pd.notna(row['PER Pasado (Trailing)']) else "N/A"
    c2.metric("PER Pasado", t_pe)

    f_pe = f"{row['PER Futuro (Forward)']:.1f}x" if pd.notna(row['PER Futuro (Forward)']) else "N/A"
    c3.metric("PER Futuro", f_pe)

    h_pe = f"{row['PER Prom. Hist. (5A)']:.1f}x" if ('PER Prom. Hist. (5A)' in row and pd.notna(row['PER Prom. Hist. (5A)'])) else "N/A"
    c4.metric("PER Hist. (5A)", h_pe)

    rsi_val = f"{row['RSI_VAL']:.1f}" if pd.notna(row['RSI_VAL']) else "N/A"
    c5.metric(f"RSI 14 ({timeframe_label})", rsi_val)

    st.divider()

    # 2. Indicadores de John Murphy (Medias, Bollinger, Estocástico, 52W High)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric(
        f"SMA 50{tf_suffix}",
        f"${row['SMA_50_VAL']:.2f}" if pd.notna(row['SMA_50_VAL']) else "N/A",
        format_signed_pct(row['DIFF_SMA_50_VAL']) if pd.notna(row['DIFF_SMA_50_VAL']) else None
    )
    m2.metric(
        f"SMA 200{tf_suffix}",
        f"${row['SMA_200_VAL']:.2f}" if pd.notna(row['SMA_200_VAL']) else "N/A",
        format_signed_pct(row['DIFF_SMA_200_VAL']) if pd.notna(row['DIFF_SMA_200_VAL']) else None
    )
    
    bw_val = f"{row.get('BB_BANDWIDTH', 0):.1f}%" if pd.notna(row.get('BB_BANDWIDTH')) else "N/A"
    m3.metric("Bollinger Bandwidth", bw_val, help="Ancho porcentual de las Bandas de Bollinger (detección de Squeeze)")

    stoch_str = f"{row.get('STOCH_K', 0):.1f} / {row.get('STOCH_D', 0):.1f}" if pd.notna(row.get('STOCH_K')) else "N/A"
    m4.metric("Estocástico %K/%D", stoch_str, help="%K (14) y %D (SMA 3)")

    dist_52w = format_signed_pct(row.get('DIST_52W_HIGH_PCT'))
    m5.metric("Distancia Máx 52S", dist_52w, help="Distancia porcentual al Máximo de 52 Semanas")

    st.markdown("#### 📊 Gráfico Avanzado (4 Paneles: Velas+SMAs+Bollinger | Volumen | MACD | RSI+Estocástico)")
    if not df_hist.empty:
        indicators = compute_chart_indicators(df_hist)
        fig = plot_stock_detail(df_hist, indicators, ticker, row['Empresa'], timeframe_label)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Cargando historial para el gráfico...")
