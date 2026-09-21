"""
indicators.py - Cálculos matemáticos en Pandas, OBV y Algoritmo de Confluencia por Sistema de Grados
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from constants import (
    BUY_BB_LOWER_TOLERANCE,
    BUY_RSI_MAX,
    BUY_SMA50_PROXIMITY_PCT,
    BUY_SMA200_TREND_TOLERANCE,
    BUY_STOCH_K_OVERSOLD,
    FLOW_ACCUMULATION,
    FLOW_DISTRIBUTION,
    FLOW_NOT_AVAILABLE,
    SELL_DIST_52W_HIGH_MIN_PCT,
    SELL_RSI_MIN,
    SELL_STOCH_K_OVERBOUGHT,
    SIGNAL_MODERATE_BUY,
    SIGNAL_MODERATE_SELL,
    SIGNAL_NEUTRAL,
    SIGNAL_SQUEEZE,
    SIGNAL_STRONG_BUY,
    SIGNAL_STRONG_SELL,
    SQUEEZE_BANDWIDTH_TOLERANCE,
    SQUEEZE_LOOKBACK_BARS,
)


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calcula el RSI utilizando el método de suavizado de Wilder."""
    if len(series) < period + 1:
        return pd.Series(np.nan, index=series.index)
    
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # Solo corregimos la división por cero genuina (avg_loss == 0) en
    # posiciones con datos válidos, sin tocar el calentamiento inicial
    # (donde avg_gain/avg_loss son NaN por min_periods=period y el RSI
    # debe seguir siendo NaN).
    valid = avg_gain.notna() & avg_loss.notna()
    rsi = rsi.mask(valid & (avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask(valid & (avg_loss == 0) & (avg_gain == 0), 50.0)
    return rsi


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    """Calcula la Media Móvil Simple (SMA)."""
    return series.rolling(window=period, min_periods=period).mean()


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Calcula la Media Móvil Exponencial (EMA)."""
    return series.ewm(span=period, adjust=False).mean()


def compute_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Calcula MACD (Línea, Señal e Histograma)."""
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
    """Calcula Bandas de Bollinger y Bandwidth."""
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
    """Calcula el Oscilador Estocástico (%K y %D)."""
    if df is None or df.empty or 'Close' not in df.columns:
        return pd.DataFrame({'stoch_k': pd.Series(dtype=float), 'stoch_d': pd.Series(dtype=float)})

    high = df['High'] if 'High' in df.columns else df['Close']
    low = df['Low'] if 'Low' in df.columns else df['Close']
    close = df['Close']
    
    lowest_low = low.rolling(window=period_k, min_periods=max(1, period_k // 2)).min()
    highest_high = high.rolling(window=period_k, min_periods=max(1, period_k // 2)).max()
    
    denom = (highest_high - lowest_low).replace(0, np.nan)
    stoch_k = ((close - lowest_low) / denom) * 100.0

    # 50.0 solo cuando el rango high-low es genuinamente cero con datos
    # válidos; el calentamiento (highest_high/lowest_low en NaN) queda en NaN.
    valid = highest_high.notna() & lowest_low.notna()
    stoch_k = stoch_k.mask(valid & (highest_high == lowest_low), 50.0)
    stoch_d = stoch_k.rolling(window=period_d, min_periods=1).mean()
    
    return pd.DataFrame({
        'stoch_k': stoch_k,
        'stoch_d': stoch_d
    }, index=df.index)


def compute_obv(df: pd.DataFrame, period_sma: int = 20) -> pd.DataFrame:
    """
    Calcula el On-Balance Volume (OBV) y su SMA de 20 períodos.
    """
    if 'Close' not in df.columns or df.empty:
        return pd.DataFrame({'obv': pd.Series(dtype=float), 'sma_obv_20': pd.Series(dtype=float)})
    
    close = df['Close']
    volume = df['Volume'].fillna(0) if 'Volume' in df.columns else pd.Series(0, index=df.index)
    
    direction = np.sign(close.diff()).fillna(0)
    obv = (direction * volume).cumsum()
    sma_obv = obv.rolling(window=period_sma, min_periods=max(1, period_sma // 2)).mean()
    
    return pd.DataFrame({
        'obv': obv,
        'sma_obv_20': sma_obv
    }, index=df.index)


def compute_52w_high_low(df: pd.DataFrame, window: int = 252) -> pd.DataFrame:
    """Calcula Máximo/Mínimo de 52 semanas y la distancia % al máximo."""
    if df is None or df.empty or 'Close' not in df.columns:
        return pd.DataFrame({
            'high_52w': pd.Series(dtype=float),
            'low_52w': pd.Series(dtype=float),
            'dist_52w_high_pct': pd.Series(dtype=float),
        })

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


@dataclass(frozen=True)
class ConfluenceThresholds:
    """
    Los umbrales del semáforo, agrupados para poder calibrarlos por clase de activo.

    El **algoritmo** es uno solo: las mismas condiciones obligatorias, el mismo
    conteo de puntos, los mismos grados. Lo que se parametriza son los números,
    porque un mismo umbral no significa lo mismo en dos mercados con
    volatilidades que difieren por un factor de cinco.

    `stretch_sigmas` es el único campo que no tiene equivalente en acciones, y
    por omisión está apagado (None), así que el comportamiento del tablero de
    acciones no cambia. Ver `_sell_near_ceiling` para qué resuelve.
    """

    trend_tolerance: float = BUY_SMA200_TREND_TOLERANCE
    sma50_proximity_pct: float = BUY_SMA50_PROXIMITY_PCT
    bb_lower_tolerance: float = BUY_BB_LOWER_TOLERANCE
    buy_rsi_max: float = BUY_RSI_MAX
    buy_stoch_oversold: float = BUY_STOCH_K_OVERSOLD
    sell_dist_52w_high_min_pct: float = SELL_DIST_52W_HIGH_MIN_PCT
    sell_rsi_min: float = SELL_RSI_MIN
    sell_stoch_overbought: float = SELL_STOCH_K_OVERBOUGHT
    stretch_sigmas: float | None = None


# Calibración de acciones: los valores históricos del tablero, sin el camino
# de extensión. Es el valor por omisión en todos lados.
STOCK_THRESHOLDS: Final[ConfluenceThresholds] = ConfluenceThresholds()


def _sell_near_ceiling(tech_data: dict, thresholds: ConfluenceThresholds) -> bool:
    """
    Condición obligatoria del lado venta: que el precio esté en un techo.

    Hay dos caminos, y el segundo existe por una razón concreta medida sobre
    datos reales. El camino clásico —estar a menos de 6% del máximo de 52
    semanas— asume un activo que cotiza habitualmente cerca de sus máximos, que
    es el caso de una acción líder. Una criptomoneda que cayó 70% y rebotó 50%
    puede estar con RSI 80 y 50% por encima de su media de 50 barras y seguir
    a 60% de su máximo anual: el primer camino no dispara nunca y el semáforo
    se queda mudo justo cuando el activo está más estirado.

    El segundo camino mide la **extensión sobre la media en desvíos propios**:
    cuántas veces la dispersión típica de esa moneda separa hoy al precio de su
    SMA 50. Es relativo al activo, no un porcentaje fijo, así que una moneda
    que normalmente oscila ±20% alrededor de su media no queda marcada por
    estar 20% arriba, y una que oscila ±5%, sí.
    """
    dist_52w_high = tech_data.get('dist_52w_high_pct', np.nan)
    if not np.isnan(dist_52w_high) and dist_52w_high >= thresholds.sell_dist_52w_high_min_pct:
        return True

    if thresholds.stretch_sigmas is None:
        return False

    dispersion = tech_data.get('sma50_dispersion_pct', np.nan)
    diff_sma_50 = tech_data.get('diff_sma_50_pct', np.nan)
    if np.isnan(dispersion) or np.isnan(diff_sma_50) or dispersion <= 0:
        return False

    return (diff_sma_50 / dispersion) >= thresholds.stretch_sigmas


def evaluate_confluence_signal(
    df_history: pd.DataFrame,
    tech_data: dict,
    thresholds: ConfluenceThresholds = STOCK_THRESHOLDS,
) -> str:
    """
    Algoritmo de Confluencia por Sistema de Grados (John Murphy + Smart Money):
    
    LÓGICA DE COMPRA:
      1. SMA 50 > SMA 200 (1 pto)
      2. Soporte: Precio a +/- 4% de SMA 50 O por debajo de Banda Inferior (1 pto) [OBLIGATORIO]
      3. RSI < 45 (1 pto) [OBLIGATORIO]
      4. Estocástico alcista o %K < 30 (1 pto)
      5. OBV > SMA_OBV_20 (1 pto)
      --> 4-5 ptos: 🌟 COMPRA FUERTE
      --> 3 ptos: 🟢 COMPRA MODERADA
      
    LÓGICA DE VENTA / ROTACIÓN:
      1. Techo: precio a < 6% de Máx 52S, o extensión sobre la SMA 50 por
         encima de `thresholds.stretch_sigmas` desvíos propios (1 pto) [OBLIGATORIO]
      2. RSI > 65 (1 pto) [OBLIGATORIO]
      3. Estocástico bajista O MACD hist decreciente (1 pto)
      4. OBV < SMA_OBV_20 (1 pto)
      --> 3-4 ptos: 🚨 VENTA FUERTE / ROTAR
      --> 2 ptos: 🟠 VENTA MODERADA
      
    OTROS:
      --> Squeeze: Bandwidth en mínimos de 6 meses (🚨 SQUEEZE)
      --> Resto: 🟡 NEUTRAL

    `thresholds` permite calibrar los números por clase de activo sin duplicar
    el algoritmo. Por omisión son los de acciones, que es como se comportó
    siempre el tablero.
    """
    if df_history is None or df_history.empty or len(df_history) < 20:
        return SIGNAL_NEUTRAL

    close = tech_data.get('close', np.nan)
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

    obv = tech_data.get('obv', np.nan)
    sma_obv_20 = tech_data.get('sma_obv_20', np.nan)

    # ----------------------------------------------------
    # 1. EVALUACIÓN DE COMPRA (SWING)
    # ----------------------------------------------------
    # Condición 1: Tendencia de fondo
    buy_c1_trend = (not np.isnan(sma_50) and not np.isnan(sma_200) and sma_50 > sma_200 and close >= sma_200 * thresholds.trend_tolerance)

    # Condición 2 (OBLIGATORIA): Proximidad a Soporte (+/- 4% de SMA 50 o debajo de Banda Inferior)
    buy_c2_support = False
    if not np.isnan(close):
        if not np.isnan(sma_50) and abs((close - sma_50) / sma_50 * 100.0) <= thresholds.sma50_proximity_pct:
            buy_c2_support = True
        elif not np.isnan(bb_lower) and close <= bb_lower * thresholds.bb_lower_tolerance:
            buy_c2_support = True

    # Condición 3 (OBLIGATORIA): Sobreventa aliviada (RSI < 45)
    buy_c3_rsi = (not np.isnan(rsi_14) and rsi_14 < thresholds.buy_rsi_max)

    # Condición 4: Gatillo de Momento (Estocástico al alza o %K < 30)
    buy_c4_stoch = (
        (not np.isnan(stoch_k) and stoch_k < thresholds.buy_stoch_oversold) or
        (not np.isnan(stoch_k) and not np.isnan(stoch_d) and not np.isnan(prev_stoch_k) and not np.isnan(prev_stoch_d) and prev_stoch_k <= prev_stoch_d and stoch_k > stoch_d)
    )

    # Condición 5: Confirmación Institucional (OBV > SMA 20)
    buy_c5_obv = (not np.isnan(obv) and not np.isnan(sma_obv_20) and obv > sma_obv_20)

    # Si cumple las condiciones obligatorias de soporte y RSI, calculamos el puntaje
    if buy_c2_support and buy_c3_rsi:
        buy_score = sum([buy_c1_trend, buy_c2_support, buy_c3_rsi, buy_c4_stoch, buy_c5_obv])
        if buy_score >= 4:
            return SIGNAL_STRONG_BUY
        elif buy_score == 3:
            return SIGNAL_MODERATE_BUY

    # ----------------------------------------------------
    # 2. EVALUACIÓN DE VENTA / ROTACIÓN
    # ----------------------------------------------------
    # Condición 1 (OBLIGATORIA): techo, por proximidad al máximo anual o por
    # extensión sobre la media medida en desvíos propios (ver _sell_near_ceiling).
    sell_c1_high = _sell_near_ceiling(tech_data, thresholds)

    # Condición 2 (OBLIGATORIA): Sobrecompra (RSI > 65)
    sell_c2_rsi = (not np.isnan(rsi_14) and rsi_14 > thresholds.sell_rsi_min)

    # Condición 3: Pérdida de Momento (Estocástico a la baja o MACD debilitándose)
    sell_c3_momentum = (
        (not np.isnan(stoch_k) and stoch_k >= thresholds.sell_stoch_overbought) or
        (not np.isnan(stoch_k) and not np.isnan(stoch_d) and not np.isnan(prev_stoch_k) and not np.isnan(prev_stoch_d) and prev_stoch_k >= prev_stoch_d and stoch_k < stoch_d) or
        (not np.isnan(macd_hist) and not np.isnan(prev_macd_hist) and macd_hist < prev_macd_hist) or
        (not np.isnan(macd_line) and not np.isnan(signal_line) and macd_line < signal_line)
    )

    # Condición 4: Distribución Institucional (OBV < SMA 20)
    sell_c4_obv = (not np.isnan(obv) and not np.isnan(sma_obv_20) and obv < sma_obv_20)

    # Si cumple techo y sobrecompra obligatorios, calculamos el puntaje de venta
    if sell_c1_high and sell_c2_rsi:
        sell_score = sum([sell_c1_high, sell_c2_rsi, sell_c3_momentum, sell_c4_obv])
        if sell_score >= 3:
            return SIGNAL_STRONG_SELL
        elif sell_score == 2:
            return SIGNAL_MODERATE_SELL

    # ----------------------------------------------------
    # 3. SQUEEZE O NEUTRAL
    # ----------------------------------------------------
    if is_bb_squeeze:
        return SIGNAL_SQUEEZE

    return SIGNAL_NEUTRAL


def compute_sma50_dispersion(close: pd.Series, window: int) -> float:
    """
    Dispersión típica del precio alrededor de su SMA 50, en %.

    Es el desvío estándar de `(precio - SMA50) / SMA50` sobre la ventana, y
    responde a "¿cuánto se suele separar este activo de su media?". Sirve para
    medir la extensión actual en unidades del propio activo en vez de en un
    porcentaje fijo: 20% por encima de la media es rutina en una memecoin y un
    extremo histórico en una acción de consumo básico.

    Devuelve NaN si no hay al menos 30 observaciones válidas: un desvío
    calculado sobre cuatro datos no describe ninguna dispersión típica.
    """
    if close is None or len(close) < 50:
        return np.nan

    sma_50 = compute_sma(close, 50)
    ratio = ((close - sma_50) / sma_50.replace(0, np.nan) * 100.0).dropna().tail(window)
    if len(ratio) < 30:
        return np.nan

    dispersion = float(ratio.std(ddof=1))
    return dispersion if np.isfinite(dispersion) and dispersion > 0 else np.nan


def _empty_stock_technicals() -> dict:
    """
    Diccionario por defecto de compute_stock_technicals, usado cuando no hay
    datos utilizables (histórico vacío, sin columna 'Close' o con todos sus
    valores en NaN). Mantiene siempre el mismo conjunto de claves que el
    cálculo completo, para que la UI que indexa por clave nunca reciba un
    dict parcial o vacío.
    """
    return {
        'close': np.nan,
        'prev_close': np.nan,
        'day_change_pct': np.nan,
        'sma_20': np.nan,
        'sma_50': np.nan,
        'sma_200': np.nan,
        'diff_sma_20_pct': np.nan,
        'diff_sma_50_pct': np.nan,
        'diff_sma_200_pct': np.nan,
        'rsi_14': np.nan,
        'macd_line': np.nan,
        'signal_line': np.nan,
        'macd_hist': np.nan,
        'prev_macd_hist': np.nan,
        'bb_mid': np.nan,
        'bb_upper': np.nan,
        'bb_lower': np.nan,
        'bb_bandwidth': np.nan,
        'is_bb_squeeze': False,
        'sma50_dispersion_pct': np.nan,
        'stoch_k': np.nan,
        'stoch_d': np.nan,
        'prev_stoch_k': np.nan,
        'prev_stoch_d': np.nan,
        'obv': np.nan,
        'sma_obv_20': np.nan,
        'institutional_flow': FLOW_NOT_AVAILABLE,
        'high_52w': np.nan,
        'low_52w': np.nan,
        'dist_52w_high_pct': np.nan,
        'confluence_signal': SIGNAL_NEUTRAL,
        'technical_status': SIGNAL_NEUTRAL,
    }


def compute_stock_technicals(
    df_history: pd.DataFrame,
    window_52w: int = 252,
    squeeze_lookback: int = SQUEEZE_LOOKBACK_BARS,
    thresholds: ConfluenceThresholds = STOCK_THRESHOLDS,
) -> dict:
    """
    Calcula todos los indicadores técnicos, OBV y estado de acumulación/distribución.

    `window_52w` y `squeeze_lookback` están parametrizados porque **no son
    períodos, son plazos de calendario expresados en barras**, y cuántas barras
    entran en un año depende del mercado: una acción cotiza unas 252 ruedas al
    año y una cripto 365, porque opera todos los días. Dejar 252 fijo haría que
    el "máximo de 52 semanas" de una cripto fuese en realidad el máximo de ocho
    meses y medio, y que el squeeze se midiera contra cuatro meses en vez de
    seis. Los valores por omisión son los de una acción, para no cambiar el
    comportamiento de la sección que ya existía.

    `thresholds` calibra el semáforo por clase de activo; por omisión son los
    umbrales de acciones.
    """
    if df_history is not None and not df_history.empty and 'Close' in df_history.columns:
        close_series = df_history['Close'].dropna()
    else:
        close_series = pd.Series(dtype=float)

    if len(close_series) == 0:
        return _empty_stock_technicals()

    current_close = float(close_series.iloc[-1])
    prev_close = float(close_series.iloc[-2]) if len(close_series) > 1 else current_close
    day_change_pct = ((current_close - prev_close) / prev_close * 100.0) if prev_close else 0.0

    # Indicadores
    sma_20_series = compute_sma(close_series, 20)
    sma_50_series = compute_sma(close_series, 50)
    sma_200_series = compute_sma(close_series, 200)
    rsi_series = compute_rsi(close_series, 14)
    df_macd = compute_macd(close_series, fast=12, slow=26, signal=9)
    df_bb = compute_bollinger_bands(close_series, period=20, num_std=2.0)
    df_stoch = compute_stochastic(df_history, period_k=14, period_d=3)
    df_obv = compute_obv(df_history, period_sma=20)
    df_52w = compute_52w_high_low(df_history, window=window_52w)

    # Extracción de valores
    sma_20 = float(sma_20_series.iloc[-1]) if not sma_20_series.empty else np.nan
    sma_50 = float(sma_50_series.iloc[-1]) if not sma_50_series.empty else np.nan
    sma_200 = float(sma_200_series.iloc[-1]) if not sma_200_series.empty else np.nan
    rsi_14 = float(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

    bb_mid = float(df_bb['bb_mid'].iloc[-1]) if not df_bb.empty else np.nan
    bb_upper = float(df_bb['bb_upper'].iloc[-1]) if not df_bb.empty else np.nan
    bb_lower = float(df_bb['bb_lower'].iloc[-1]) if not df_bb.empty else np.nan
    bb_bandwidth = float(df_bb['bb_bandwidth'].iloc[-1]) if not df_bb.empty else np.nan

    # Squeeze en mínimos de 6 meses (126 ruedas)
    bandwidth_6m = df_bb['bb_bandwidth'].tail(squeeze_lookback).dropna()
    is_bb_squeeze = False
    if len(bandwidth_6m) >= 20 and bb_bandwidth <= bandwidth_6m.min() * SQUEEZE_BANDWIDTH_TOLERANCE:
        is_bb_squeeze = True

    stoch_k = float(df_stoch['stoch_k'].iloc[-1]) if not df_stoch.empty else np.nan
    stoch_d = float(df_stoch['stoch_d'].iloc[-1]) if not df_stoch.empty else np.nan
    prev_stoch_k = float(df_stoch['stoch_k'].iloc[-2]) if len(df_stoch) > 1 else stoch_k
    prev_stoch_d = float(df_stoch['stoch_d'].iloc[-2]) if len(df_stoch) > 1 else stoch_d

    obv = float(df_obv['obv'].iloc[-1]) if not df_obv.empty else np.nan
    sma_obv_20 = float(df_obv['sma_obv_20'].iloc[-1]) if not df_obv.empty else np.nan
    if not np.isnan(obv) and not np.isnan(sma_obv_20):
        institutional_flow = FLOW_ACCUMULATION if obv >= sma_obv_20 else FLOW_DISTRIBUTION
    else:
        institutional_flow = FLOW_NOT_AVAILABLE

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
        'obv': obv,
        'sma_obv_20': sma_obv_20,
        'institutional_flow': institutional_flow,
        'high_52w': high_52w,
        'low_52w': low_52w,
        'dist_52w_high_pct': dist_52w_high_pct,
        'sma50_dispersion_pct': compute_sma50_dispersion(close_series, window_52w),
    }

    confluence_signal = evaluate_confluence_signal(df_history, tech_dict, thresholds)
    tech_dict['confluence_signal'] = confluence_signal
    tech_dict['technical_status'] = confluence_signal

    return tech_dict
