"""
crypto/panel.py - Armado del cuadro de criptomonedas.

Capa pura entre la descarga (`crypto/data_loader.py`) y el dibujo
(`components/crypto_table.py`): recibe historiales OHLCV ya bajados y
devuelve el DataFrame final con todas las métricas calculadas. No importa
`streamlit` ni toca la red, así que toda la aritmética que el usuario ve en
pantalla se testea pasándole un puñado de barras fijas.

Reusa `indicators.compute_stock_technicals` sin modificarlo: la lectura
técnica de una cripto (medias, RSI, Bollinger, estocástico, OBV) es la misma
que la de una acción. Lo que cambia es todo lo demás, y es lo que vive acá:

  * **El calendario.** Cripto opera los 365 días del año, así que "máximo de
    52 semanas" son 365 barras diarias y no 252. Con el valor de acciones, el
    máximo anual de una cripto sería en realidad el de los últimos ocho meses
    y medio.
  * **La referencia.** En acciones el marco es el índice; en cripto casi todo
    se mueve con Bitcoin, así que la pregunta útil no es cuánto subió una
    moneda sino cuánto subió **frente a Bitcoin**.
  * **La falta de balances.** No hay PER, ni sector, ni dividendos. En su
    lugar se muestra la volatilidad anualizada, que en esta clase de activo
    es la medida de riesgo que efectivamente se usa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from constants import (
    BUY_SIGNALS,
    CRYPTO_52W_WINDOW_DAILY,
    CRYPTO_52W_WINDOW_WEEKLY,
    CRYPTO_BARS_PER_YEAR_DAILY,
    CRYPTO_BARS_PER_YEAR_WEEKLY,
    CRYPTO_DOMINANCE_WINDOW_DAILY,
    CRYPTO_DOMINANCE_WINDOW_WEEKLY,
    CRYPTO_FILTER_RS_OUTPERFORM,
    CRYPTO_FILTER_RS_UNDERPERFORM,
    CRYPTO_FILTER_SIGNAL_BUY,
    CRYPTO_FILTER_SIGNAL_SELL,
    CRYPTO_FILTER_SIGNAL_SQUEEZE,
    CRYPTO_FILTER_SIGNAL_STRONG_BUY,
    CRYPTO_FILTER_TREND_BEARISH,
    CRYPTO_FILTER_TREND_BULLISH,
    CRYPTO_FLOW_COLUMN,
    CRYPTO_RETURN_LONG_DAILY,
    CRYPTO_RETURN_LONG_WEEKLY,
    CRYPTO_RETURN_SHORT_DAILY,
    CRYPTO_RETURN_SHORT_WEEKLY,
    CRYPTO_RS_INLINE,
    CRYPTO_RS_NEUTRAL_BAND_PP,
    CRYPTO_RS_NOT_AVAILABLE,
    CRYPTO_RS_OUTPERFORM,
    CRYPTO_RS_UNDERPERFORM,
    CRYPTO_SQUEEZE_LOOKBACK_DAILY,
    CRYPTO_SQUEEZE_LOOKBACK_WEEKLY,
    CRYPTO_STRETCH_SIGMAS,
    CRYPTO_VOLATILITY_WINDOW_DAILY,
    CRYPTO_VOLATILITY_WINDOW_WEEKLY,
    FLOW_NOT_AVAILABLE,
    SELL_SIGNALS,
    SIGNAL_NEUTRAL,
    SIGNAL_SQUEEZE,
    SIGNAL_STRONG_BUY,
)
from crypto.catalog import CryptoAsset, find_asset
from indicators import ConfluenceThresholds, compute_stock_technicals

logger = logging.getLogger(__name__)

TIMEFRAME_DAILY: Final[str] = "1d"
TIMEFRAME_WEEKLY: Final[str] = "1wk"

# Calibración del semáforo para esta clase de activo. Es el mismo algoritmo
# con un solo número distinto: el camino de "techo por extensión sobre la
# media", que en acciones está apagado. El porqué está en `constants.py`,
# junto al valor, y en `indicators._sell_near_ceiling`.
CRYPTO_THRESHOLDS: Final[ConfluenceThresholds] = ConfluenceThresholds(
    stretch_sigmas=CRYPTO_STRETCH_SIGMAS,
)


@dataclass(frozen=True)
class TimeframeSpec:
    """
    Cuántas barras mide cada plazo de calendario en la temporalidad elegida.

    Existe para que la traducción "un mes son 30 barras diarias o 13
    semanales" se escriba una sola vez, en vez de repartir cuentas de barras
    por el módulo.
    """

    interval: str
    sufijo: str            # sufijo de las columnas que dependen de la temporalidad
    unidad: str            # cómo se nombra una barra en los títulos ("d" o "s")
    ventana_52w: int
    squeeze_lookback: int
    barras_por_anio: int
    ventana_volatilidad: int
    retorno_corto: int
    retorno_largo: int
    ventana_dominancia: int


_SPEC_DAILY: Final[TimeframeSpec] = TimeframeSpec(
    interval=TIMEFRAME_DAILY,
    sufijo=" (Día)",
    unidad="d",
    ventana_52w=CRYPTO_52W_WINDOW_DAILY,
    squeeze_lookback=CRYPTO_SQUEEZE_LOOKBACK_DAILY,
    barras_por_anio=CRYPTO_BARS_PER_YEAR_DAILY,
    ventana_volatilidad=CRYPTO_VOLATILITY_WINDOW_DAILY,
    retorno_corto=CRYPTO_RETURN_SHORT_DAILY,
    retorno_largo=CRYPTO_RETURN_LONG_DAILY,
    ventana_dominancia=CRYPTO_DOMINANCE_WINDOW_DAILY,
)

_SPEC_WEEKLY: Final[TimeframeSpec] = TimeframeSpec(
    interval=TIMEFRAME_WEEKLY,
    sufijo=" (Sem)",
    unidad="s",
    ventana_52w=CRYPTO_52W_WINDOW_WEEKLY,
    squeeze_lookback=CRYPTO_SQUEEZE_LOOKBACK_WEEKLY,
    barras_por_anio=CRYPTO_BARS_PER_YEAR_WEEKLY,
    ventana_volatilidad=CRYPTO_VOLATILITY_WINDOW_WEEKLY,
    retorno_corto=CRYPTO_RETURN_SHORT_WEEKLY,
    retorno_largo=CRYPTO_RETURN_LONG_WEEKLY,
    ventana_dominancia=CRYPTO_DOMINANCE_WINDOW_WEEKLY,
)


def spec_for_timeframe(timeframe: str) -> TimeframeSpec:
    """Traduce la temporalidad elegida a sus ventanas en barras."""
    return _SPEC_WEEKLY if timeframe == TIMEFRAME_WEEKLY else _SPEC_DAILY


def compute_return_pct(close: pd.Series, bars: int) -> float:
    """
    Variación porcentual de los últimos `bars` barras.

    Devuelve NaN si no hay historial suficiente, en vez de medir contra la
    barra más vieja disponible: un "retorno de 30 días" calculado sobre 6
    días es un número que no es lo que dice ser.
    """
    if close is None or bars <= 0:
        return np.nan
    serie = close.dropna()
    if len(serie) < bars + 1:
        return np.nan

    base = float(serie.iloc[-(bars + 1)])
    ultimo = float(serie.iloc[-1])
    if base == 0 or not np.isfinite(base) or not np.isfinite(ultimo):
        return np.nan
    return (ultimo - base) / base * 100.0


def compute_annualized_volatility(close: pd.Series, window: int, bars_per_year: int) -> float:
    """
    Volatilidad anualizada, en %, sobre los últimos `window` retornos.

    Se usa el desvío de los retornos **logarítmicos**: en cripto los saltos de
    20% en una barra son corrientes, y sobre movimientos de esa magnitud el
    retorno simple y el logarítmico dejan de ser intercambiables.
    """
    if close is None or window <= 1 or bars_per_year <= 0:
        return np.nan

    serie = close.dropna()
    if len(serie) < window + 1:
        return np.nan

    retornos = np.log(serie / serie.shift(1)).dropna().tail(window)
    if len(retornos) < window:
        return np.nan

    desvio = float(retornos.std(ddof=1))
    if not np.isfinite(desvio):
        return np.nan
    return desvio * np.sqrt(bars_per_year) * 100.0


def classify_relative_strength(excess_pp: float) -> str:
    """
    Etiqueta de fuerza relativa contra Bitcoin a partir del exceso de retorno.

    La banda muerta de `CRYPTO_RS_NEUTRAL_BAND_PP` existe porque en un activo
    que se mueve 5% en un día, dos puntos de diferencia acumulados en un mes
    son ruido: llamarlos "supera a BTC" sería leer una ventaja donde no hay.
    """
    if excess_pp is None or not np.isfinite(excess_pp):
        return CRYPTO_RS_NOT_AVAILABLE
    if excess_pp > CRYPTO_RS_NEUTRAL_BAND_PP:
        return CRYPTO_RS_OUTPERFORM
    if excess_pp < -CRYPTO_RS_NEUTRAL_BAND_PP:
        return CRYPTO_RS_UNDERPERFORM
    return CRYPTO_RS_INLINE


def _close_of(history: pd.DataFrame | None) -> pd.Series:
    """Serie de cierres de un historial, o una serie vacía si no la tiene."""
    if history is None or history.empty or "Close" not in history.columns:
        return pd.Series(dtype=float)
    return history["Close"].dropna()


def _last_volume(history: pd.DataFrame | None) -> float:
    """Volumen operado en la última barra, en dólares."""
    if history is None or history.empty or "Volume" not in history.columns:
        return np.nan
    volumen = history["Volume"].dropna()
    if volumen.empty:
        return np.nan
    valor = float(volumen.iloc[-1])
    return valor if np.isfinite(valor) else np.nan


def build_crypto_panel(
    history: dict[str, pd.DataFrame],
    benchmark_history: pd.DataFrame | None = None,
    timeframe: str = TIMEFRAME_DAILY,
    assets: tuple[CryptoAsset, ...] | None = None,
    market_caps: dict[str, float | None] | None = None,
) -> pd.DataFrame:
    """
    Arma el cuadro de criptomonedas a partir de los historiales descargados.

    `history` mapea ticker de Yahoo a su OHLCV; `benchmark_history` es el de
    Bitcoin, que se pasa aparte porque se usa como referencia de todas las
    filas **esté o no Bitcoin en el universo elegido** (si se mira solo
    memecoins, sigue haciendo falta saber contra qué se las compara).

    `assets` fija el orden y los nombres de las filas. Si no se pasa, se
    resuelve cada ticker contra el catálogo y los que no figuren se muestran
    igual, con el ticker como nombre: que una cripto no esté catalogada no es
    motivo para perder su precio.

    `market_caps` es opcional: sin él las columnas de tamaño quedan vacías y
    todo lo demás se calcula igual. El peso de cada moneda dentro del panel
    se computa sobre las que **sí** tienen capitalización conocida, para que
    los porcentajes sumen cien entre ellas en vez de repartir contra un total
    incompleto.

    Como en el cuadro de acciones, hay columnas duplicadas a propósito: las
    de nombre en castellano (con el sufijo de temporalidad) son para mostrar,
    y las de nombre estable en mayúsculas son las que leen filtros y KPIs sin
    tener que reconstruir el título según la temporalidad elegida.
    """
    spec = spec_for_timeframe(timeframe)

    if assets is None:
        tickers = list(history.keys())
    else:
        tickers = [a.ticker for a in assets]

    benchmark_close = _close_of(benchmark_history)
    benchmark_return = compute_return_pct(benchmark_close, spec.retorno_largo)

    col_corto = f"Var. {spec.retorno_corto}{spec.unidad} (%)"
    col_largo = f"Var. {spec.retorno_largo}{spec.unidad} (%)"
    col_rsi = f"RSI (14){spec.sufijo}"

    market_caps = market_caps or {}
    capitalizacion_total = sum(
        cap for t, cap in market_caps.items()
        if t in tickers and cap and np.isfinite(cap) and cap > 0
    )

    filas = []
    for ticker in tickers:
        df_t = history.get(ticker)
        activo = find_asset(ticker)
        close = _close_of(df_t)

        tech = compute_stock_technicals(
            df_t if df_t is not None else pd.DataFrame(),
            window_52w=spec.ventana_52w,
            squeeze_lookback=spec.squeeze_lookback,
            thresholds=CRYPTO_THRESHOLDS,
        )

        retorno_largo = compute_return_pct(close, spec.retorno_largo)
        if np.isfinite(retorno_largo) and np.isfinite(benchmark_return):
            exceso_btc = retorno_largo - benchmark_return
        else:
            exceso_btc = np.nan

        # Extensión sobre la media en desvíos propios: es lo que decide la
        # señal de techo en cripto, así que se muestra en vez de quedar
        # escondida dentro del semáforo.
        dispersion = tech.get("sma50_dispersion_pct", np.nan)
        diff_sma_50 = tech.get("diff_sma_50_pct", np.nan)
        if np.isfinite(dispersion) and dispersion > 0 and np.isfinite(diff_sma_50):
            extension_sigmas = diff_sma_50 / dispersion
        else:
            extension_sigmas = np.nan

        capitalizacion = market_caps.get(ticker)
        if not capitalizacion or not np.isfinite(capitalizacion) or capitalizacion <= 0:
            capitalizacion = np.nan
        if np.isfinite(capitalizacion) and capitalizacion_total > 0:
            peso_panel = capitalizacion / capitalizacion_total * 100.0
        else:
            peso_panel = np.nan

        filas.append({
            "Semáforo": tech.get("confluence_signal", SIGNAL_NEUTRAL),
            "Cripto": activo.simbolo if activo else ticker,
            "Nombre": activo.nombre if activo else ticker,
            "Categoría": activo.categoria if activo else "Sin catalogar",
            CRYPTO_FLOW_COLUMN: tech.get("institutional_flow", FLOW_NOT_AVAILABLE),
            "Precio (USD)": tech.get("close", np.nan),
            "Var. Período (%)": tech.get("day_change_pct", np.nan),
            col_corto: compute_return_pct(close, spec.retorno_corto),
            col_largo: retorno_largo,
            "vs BTC": classify_relative_strength(exceso_btc),
            "Exceso vs BTC (pp)": exceso_btc,
            col_rsi: tech.get("rsi_14", np.nan),
            f"Dif. % SMA 20{spec.sufijo}": tech.get("diff_sma_20_pct", np.nan),
            f"Dif. % SMA 50{spec.sufijo}": tech.get("diff_sma_50_pct", np.nan),
            f"Dif. % SMA 200{spec.sufijo}": tech.get("diff_sma_200_pct", np.nan),
            "Dif. % Máx 52S": tech.get("dist_52w_high_pct", np.nan),
            "Extensión (σ)": extension_sigmas,
            "Bollinger BW (%)": tech.get("bb_bandwidth", np.nan),
            "Volatilidad Anual. (%)": compute_annualized_volatility(
                close, spec.ventana_volatilidad, spec.barras_por_anio
            ),
            "Volumen (USD)": _last_volume(df_t),
            "Cap. Mercado (USD)": capitalizacion,
            "Peso en Panel (%)": peso_panel,
            # Claves estables para filtros, KPIs y alertas.
            "Ticker": ticker,
            "PRECIO_VAL": tech.get("close", np.nan),
            "RSI_VAL": tech.get("rsi_14", np.nan),
            "DIFF_SMA_50_VAL": tech.get("diff_sma_50_pct", np.nan),
            "DIFF_SMA_200_VAL": tech.get("diff_sma_200_pct", np.nan),
            "DIST_52W_HIGH_PCT": tech.get("dist_52w_high_pct", np.nan),
            "BB_BANDWIDTH": tech.get("bb_bandwidth", np.nan),
            "EXTENSION_SIGMAS": extension_sigmas,
            "RET_LONG_PCT": retorno_largo,
            "RS_BTC_PP": exceso_btc,
            "VOL_ANN_PCT": compute_annualized_volatility(
                close, spec.ventana_volatilidad, spec.barras_por_anio
            ),
            "VOLUMEN_VAL": _last_volume(df_t),
            "MARKET_CAP_VAL": capitalizacion,
            "PESO_PANEL_PCT": peso_panel,
            "Timeframe": spec.interval,
        })

    df = pd.DataFrame(filas)
    df.attrs["timeframe"] = spec.interval
    df.attrs["benchmark_return_pct"] = benchmark_return
    return df


def apply_crypto_filters(
    df: pd.DataFrame,
    signal_filter: str,
    rs_filter: str,
    trend_filter: str,
    rsi_range: tuple[float, float] | None = None,
) -> pd.DataFrame:
    """
    Recorta el cuadro según los filtros de la pestaña.

    Los textos que llegan son los literales de `constants.py`; compararlos
    contra strings escritos acá haría que editar un selector rompiera el
    filtro en silencio.

    Las filas sin dato (RSI o fuerza relativa en NaN) **sobreviven al filtro
    de rango de RSI** pero no a los filtros que piden explícitamente una
    condición: pedir "solo las que superan a BTC" y recibir monedas sin
    historial suficiente sería responder otra pregunta.
    """
    if df.empty:
        return df

    filtrado = df.copy()

    if signal_filter == CRYPTO_FILTER_SIGNAL_STRONG_BUY:
        filtrado = filtrado[filtrado["Semáforo"] == SIGNAL_STRONG_BUY]
    elif signal_filter == CRYPTO_FILTER_SIGNAL_BUY:
        filtrado = filtrado[filtrado["Semáforo"].isin(BUY_SIGNALS)]
    elif signal_filter == CRYPTO_FILTER_SIGNAL_SELL:
        filtrado = filtrado[filtrado["Semáforo"].isin(SELL_SIGNALS)]
    elif signal_filter == CRYPTO_FILTER_SIGNAL_SQUEEZE:
        filtrado = filtrado[filtrado["Semáforo"] == SIGNAL_SQUEEZE]

    if rs_filter == CRYPTO_FILTER_RS_OUTPERFORM:
        filtrado = filtrado[filtrado["vs BTC"] == CRYPTO_RS_OUTPERFORM]
    elif rs_filter == CRYPTO_FILTER_RS_UNDERPERFORM:
        filtrado = filtrado[filtrado["vs BTC"] == CRYPTO_RS_UNDERPERFORM]

    if trend_filter == CRYPTO_FILTER_TREND_BULLISH:
        filtrado = filtrado[filtrado["DIFF_SMA_200_VAL"] > 0]
    elif trend_filter == CRYPTO_FILTER_TREND_BEARISH:
        filtrado = filtrado[filtrado["DIFF_SMA_200_VAL"] < 0]

    if rsi_range is not None:
        minimo, maximo = rsi_range
        filtrado = filtrado[
            filtrado["RSI_VAL"].isna()
            | ((filtrado["RSI_VAL"] >= minimo) & (filtrado["RSI_VAL"] <= maximo))
        ]

    filtrado.attrs.update(df.attrs)
    return filtrado
