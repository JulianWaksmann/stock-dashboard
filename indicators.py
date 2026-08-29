"""
indicators.py - Cálculos matemáticos en Pandas y Algoritmo de Confluencia de John Murphy
"""

import numpy as np
import pandas as pd


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calcula el RSI (Relative Strength Index) utilizando el método de suavizado de Wilder.
    """
    if len(series) < period + 1:
        return pd.Series(np.nan, index=series.index)
    
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(100.0 * (gain > 0))


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    """Calcula la Media Móvil Simple (SMA)."""
    return series.rolling(window=period, min_periods=max(1, period // 2)).mean()


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Calcula la Media Móvil Exponencial (EMA)."""
    return series.ewm(span=period, adjust=False).mean()


def compute_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    Calcula el MACD:
      - macd_line = EMA(12) - EMA(26)
      - signal_line = EMA(macd_line, 9)
      - macd_hist = macd_line - signal_line
    """
    ema_fast = compute_ema(series, fast)
    ema_slow = compute_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    macd_hist = macd_line - signal_line
    
    return pd.DataFrame({
        'macd': macd_line,
        'signal': signal_line,
        'hist': macd_hist
    }, index=series.index)


def compute_bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """
    Calcula las Bandas de Bollinger y el Bandwidth:
      - bb_mid = SMA(20)
      - bb_upper = bb_mid + 2 * STD(20)
      - bb_lower = bb_mid - 2 * STD(20)
      - bb_bandwidth = ((bb_upper - bb_lower) / bb_mid) * 100
    """
    bb_mid = compute_sma(series, period)
    bb_std = series.rolling(window=period, min_periods=max(1, period // 2)).std()
    bb_upper = bb_mid + (num_std * bb_std)
    bb_lower = bb_mid - (num_std * bb_std)
    bb_bandwidth = ((bb_upper - bb_lower) / bb_mid.replace(0, np.nan)) * 100.0
    
    return pd.DataFrame({
        'bb_mid': bb_mid,
        'bb_upper': bb_upper,
        'bb_lower': bb_lower,
        'bb_bandwidth': bb_bandwidth
    }, index=series.index)


def compute_stochastic(df: pd.DataFrame, period_k: int = 14, period_d: int = 3) -> pd.DataFrame:
    """
    Calcula el Oscilador Estocástico:
      - %K (14) = (Close - Lowest Low) / (Highest High - Lowest Low) * 100
      - %D (3) = SMA(%K, 3)
    """
    high = df['High'] if 'High' in df.columns else df['Close']
    low = df['Low'] if 'Low' in df.columns else df['Close']
    close = df['Close']
    
    lowest_low = low.rolling(window=period_k, min_periods=max(1, period_k // 2)).min()
    highest_high = high.rolling(window=period_k, min_periods=max(1, period_k // 2)).max()
    
    denom = (highest_high - lowest_low).replace(0, np.nan)
    stoch_k = ((close - lowest_low) / denom) * 100.0
    stoch_k = stoch_k.fillna(50.0)
    stoch_d = stoch_k.rolling(window=period_d, min_periods=1).mean()
    
    return pd.DataFrame({
        'stoch_k': stoch_k,
        'stoch_d': stoch_d
    }, index=df.index)


def compute_52w_high_low(df: pd.DataFrame, window: int = 252) -> pd.DataFrame:
    """
    Calcula el Máximo y Mínimo de 52 semanas (252 ruedas) y la distancia % al máximo.
    """
    high = df['High'] if 'High' in df.columns else df['Close']
    low = df['Low'] if 'Low' in df.columns else df['Close']
    close = df['Close']
    
    rolling_high = high.rolling(window=window, min_periods=min(len(df), 20)).max()
    rolling_low = low.rolling(window=window, min_periods=min(len(df), 20)).min()
    dist_52w_high_pct = ((close - rolling_high) / rolling_high.replace(0, np.nan)) * 100.0
    
    return pd.DataFrame({
        'high_52w': rolling_high,
        'low_52w': rolling_low,
        'dist_52w_high_pct': dist_52w_high_pct
    }, index=df.index)


def compute_percent_diff(current_price: float, reference_value: float) -> float:
    if reference_value is None or np.isnan(reference_value) or reference_value == 0:
        return np.nan
    if current_price is None or np.isnan(current_price):
        return np.nan
    return ((current_price - reference_value) / reference_value) * 100.0


def evaluate_confluence_signal(df_history: pd.DataFrame, tech_data: dict) -> str:
    """
    Algoritmo de Confluencia de John Murphy ("El Semáforo"):
      - 🔴 VENTA/ROTAR: Precio a < 5% del Máx 52W + RSI > 70 + Estocástico bajista (o >80) + MACD perdiendo fuerza.
      - 🟢 COMPRA/SWING: SMA 50 > SMA 200 + Retroceso a soporte (cerca Banda Inferior o SMA 50) + RSI < 35 + Estocástico alcista.
      - 🚨 SQUEEZE: Bandwidth en mínimos de los últimos 6 meses.
      - 🟡 NEUTRAL: Cualquier otro escenario.
    """
    if df_history is None or df_history.empty or len(df_history) < 20:
        return "🟡 NEUTRAL"

    close = tech_data.get('close', np.nan)
    dist_52w_high = tech_data.get('dist_52w_high_pct', np.nan)
    rsi_14 = tech_data.get('rsi_14', np.nan)
    stoch_k = tech_data.get('stoch_k', np.nan)
    stoch_d = tech_data.get('stoch_d', np.nan)
    prev_stoch_k = tech_data.get('prev_stoch_k', np.nan)
    prev_stoch_d = tech_data.get('prev_stoch_d', np.nan)
    
    macd_hist = tech_data.get('macd_hist', np.nan)
    prev_macd_hist = tech_data.get('prev_macd_hist', np.nan)
    macd_line = tech_data.get('macd_line', np.nan)
    signal_line = tech_data.get('signal_line', np.nan)
    
    sma_50 = tech_data.get('sma_50', np.nan)
    sma_200 = tech_data.get('sma_200', np.nan)
    bb_lower = tech_data.get('bb_lower', np.nan)
    is_bb_squeeze = tech_data.get('is_bb_squeeze', False)

    # 1. 🔴 VENTA/ROTAR (Rotación en Máximos)
    near_52w_high = (not np.isnan(dist_52w_high) and dist_52w_high >= -5.0)
    rsi_overbought = (not np.isnan(rsi_14) and rsi_14 >= 68.0)
    stoch_bearish = (
        (not np.isnan(stoch_k) and stoch_k >= 80.0) or
        (not np.isnan(stoch_k) and not np.isnan(stoch_d) and not np.isnan(prev_stoch_k) and not np.isnan(prev_stoch_d) and prev_stoch_k >= prev_stoch_d and stoch_k < stoch_d)
    )
    macd_weakening = (
        (not np.isnan(macd_hist) and not np.isnan(prev_macd_hist) and macd_hist < prev_macd_hist) or
        (not np.isnan(macd_line) and not np.isnan(signal_line) and macd_line < signal_line)
    )
    if near_52w_high and rsi_overbought and stoch_bearish and macd_weakening:
        return "🔴 VENTA/ROTAR"

    # 2. 🟢 COMPRA/SWING (Retroceso a soporte en tendencia alcista)
    uptrend_confirmed = (not np.isnan(sma_50) and not np.isnan(sma_200) and sma_50 > sma_200 and close >= sma_200 * 0.95)
    near_support = (
        (not np.isnan(bb_lower) and close <= bb_lower * 1.025) or
        (not np.isnan(sma_50) and abs((close - sma_50) / sma_50 * 100.0) <= 3.0) or
        (not np.isnan(sma_50) and close <= sma_50 * 1.02 and close >= sma_50 * 0.96)
    )
    rsi_oversold = (not np.isnan(rsi_14) and rsi_14 <= 38.0)
    stoch_bullish = (
        (not np.isnan(stoch_k) and stoch_k <= 30.0) or
        (not np.isnan(stoch_k) and not np.isnan(stoch_d) and not np.isnan(prev_stoch_k) and not np.isnan(prev_stoch_d) and prev_stoch_k <= prev_stoch_d and stoch_k > stoch_d)
    )
    if uptrend_confirmed and near_support and rsi_oversold and stoch_bullish:
        return "🟢 COMPRA/SWING"

    # 3. 🚨 SQUEEZE (Compresión de Volatilidad)
    if is_bb_squeeze:
        return "🚨 SQUEEZE"

    return "🟡 NEUTRAL"


def compute_stock_technicals(df_history: pd.DataFrame) -> dict:
    """
    Calcula todos los indicadores técnicos y evalúa la señal del semáforo.
    """
    if df_history is None or df_history.empty or 'Close' not in df_history.columns or len(df_history) == 0:
        return {'close': np.nan, 'confluence_signal': '🟡 NEUTRAL', 'technical_status': 'Sin datos'}
    
    close_series = df_history['Close'].dropna()
    if len(close_series) == 0:
        return {}

    current_close = float(close_series.iloc[-1])
    prev_close = float(close_series.iloc[-2]) if len(close_series) > 1 else current_close
    day_change_pct = ((current_close - prev_close) / prev_close * 100.0) if prev_close else 0.0

    # 1. Medias Móviles y RSI
    sma_20_series = compute_sma(close_series, 20)
    sma_50_series = compute_sma(close_series, 50)
    sma_200_series = compute_sma(close_series, 200)
    rsi_series = compute_rsi(close_series, 14)

    # 2. MACD
    df_macd = compute_macd(close_series, fast=12, slow=26, signal=9)
    
    # 3. Bandas de Bollinger
    df_bb = compute_bollinger_bands(close_series, period=20, num_std=2.0)
    
    # 4. Estocástico
    df_stoch = compute_stochastic(df_history, period_k=14, period_d=3)
    
    # 5. Máximos / Mínimos 52 Semanas
    df_52w = compute_52w_high_low(df_history, window=252)

    # Extracción de valores escalares
    sma_20 = float(sma_20_series.iloc[-1]) if not sma_20_series.empty else np.nan
    sma_50 = float(sma_50_series.iloc[-1]) if not sma_50_series.empty else np.nan
    sma_200 = float(sma_200_series.iloc[-1]) if not sma_200_series.empty else np.nan
    rsi_14 = float(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

    bb_mid = float(df_bb['bb_mid'].iloc[-1]) if not df_bb.empty else np.nan
    bb_upper = float(df_bb['bb_upper'].iloc[-1]) if not df_bb.empty else np.nan
    bb_lower = float(df_bb['bb_lower'].iloc[-1]) if not df_bb.empty else np.nan
    bb_bandwidth = float(df_bb['bb_bandwidth'].iloc[-1]) if not df_bb.empty else np.nan

    # Squeeze en mínimos de 6 meses (126 ruedas)
    bandwidth_6m = df_bb['bb_bandwidth'].tail(126).dropna()
    is_bb_squeeze = False
    if len(bandwidth_6m) >= 20 and bb_bandwidth <= bandwidth_6m.min() * 1.08:
        is_bb_squeeze = True

    stoch_k = float(df_stoch['stoch_k'].iloc[-1]) if not df_stoch.empty else np.nan
    stoch_d = float(df_stoch['stoch_d'].iloc[-1]) if not df_stoch.empty else np.nan
    prev_stoch_k = float(df_stoch['stoch_k'].iloc[-2]) if len(df_stoch) > 1 else stoch_k
    prev_stoch_d = float(df_stoch['stoch_d'].iloc[-2]) if len(df_stoch) > 1 else stoch_d

    high_52w = float(df_52w['high_52w'].iloc[-1]) if not df_52w.empty else np.nan
    low_52w = float(df_52w['low_52w'].iloc[-1]) if not df_52w.empty else np.nan
    dist_52w_high_pct = float(df_52w['dist_52w_high_pct'].iloc[-1]) if not df_52w.empty else np.nan

    tech_dict = {
        'close': current_close,
        'prev_close': prev_close,
        'day_change_pct': day_change_pct,
        'sma_20': sma_20,
        'sma_50': sma_50,
        'sma_200': sma_200,
        'diff_sma_20_pct': compute_percent_diff(current_close, sma_20),
        'diff_sma_50_pct': compute_percent_diff(current_close, sma_50),
        'diff_sma_200_pct': compute_percent_diff(current_close, sma_200),
        'rsi_14': rsi_14,
        'macd_line': float(df_macd['macd'].iloc[-1]) if not df_macd.empty else np.nan,
        'signal_line': float(df_macd['signal'].iloc[-1]) if not df_macd.empty else np.nan,
        'macd_hist': float(df_macd['hist'].iloc[-1]) if not df_macd.empty else np.nan,
        'prev_macd_hist': float(df_macd['hist'].iloc[-2]) if len(df_macd) > 1 else np.nan,
        'bb_mid': bb_mid,
        'bb_upper': bb_upper,
        'bb_lower': bb_lower,
        'bb_bandwidth': bb_bandwidth,
        'is_bb_squeeze': is_bb_squeeze,
        'stoch_k': stoch_k,
        'stoch_d': stoch_d,
        'prev_stoch_k': prev_stoch_k,
        'prev_stoch_d': prev_stoch_d,
        'high_52w': high_52w,
        'low_52w': low_52w,
        'dist_52w_high_pct': dist_52w_high_pct
    }

    confluence_signal = evaluate_confluence_signal(df_history, tech_dict)
    tech_dict['confluence_signal'] = confluence_signal
    tech_dict['technical_status'] = confluence_signal

    return tech_dict
