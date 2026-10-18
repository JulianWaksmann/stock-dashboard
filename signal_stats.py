"""
signal_stats.py - Medición del semáforo contra lo que pasó después.

El tablero afirma algo verificable: que cuando varias señales independientes
coinciden, lo que sigue es distinto de un día cualquiera. Este módulo lo mide.
Replaya el semáforo barra por barra sobre el historial que el tablero ya
descarga y lo cruza con el retorno de las barras siguientes.

Qué hay que leer de la tabla que devuelve: **la fila de base, primero**. Un
"COMPRA FUERTE" con +3% a veinte ruedas no dice nada si el promedio de todas
las barras del período también fue +3%. Lo único que importa es el exceso
sobre esa base.

Tres límites que conviene tener presentes, porque la tabla invita a pedirle
más de lo que puede dar:

  * **Las muestras se solapan.** El retorno a veinte barras medido desde el
    lunes y desde el martes comparte diecinueve días. La columna de casos
    cuenta barras, no episodios independientes, así que es mucho mayor que el
    tamaño de muestra real. Por eso acá no hay valores p ni intervalos: con
    datos solapados saldrían espectacularmente optimistas.
  * **Es el período que se descargó, no "la historia".** Dos años de acciones
    o de cripto entran casi enteros en un mismo régimen de mercado. Un semáforo
    que mide bien en una suba no demuestra nada sobre una caída.
  * **Mide la señal, no una estrategia.** No hay costos, ni deslizamiento, ni
    tamaño de posición, ni stop: es el retorno que tuvo el activo, no el que
    habría tenido una cuenta.

Es puro: sin red y sin Streamlit. Lo usan `components/signal_stats_panel.py` y
`scripts/medir_semaforo.py`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from constants import (
    SIGNAL_MODERATE_BUY,
    SIGNAL_MODERATE_SELL,
    SIGNAL_NEUTRAL,
    SIGNAL_SQUEEZE,
    SIGNAL_STATS_BASELINE,
    SIGNAL_STATS_MIN_CASES,
    SIGNAL_STRONG_BUY,
    SIGNAL_STRONG_SELL,
    SQUEEZE_BANDWIDTH_TOLERANCE,
    SQUEEZE_LOOKBACK_BARS,
)
from indicators import (
    STOCK_THRESHOLDS,
    ConfluenceThresholds,
    compute_52w_high_low,
    compute_bollinger_bands,
    compute_macd,
    compute_obv,
    compute_percent_diff,
    compute_rsi,
    compute_sma,
    compute_stochastic,
    evaluate_confluence_signal,
)

# Mínimo de barras que exige `evaluate_confluence_signal` para pronunciarse.
_MIN_BARS = 20

# Orden de lectura de la tabla: de compra a venta, con los estados de descarte
# en el medio. No es alfabético ni por frecuencia a propósito — se lee como se
# lee el semáforo.
SIGNAL_ORDER = (
    SIGNAL_STRONG_BUY,
    SIGNAL_MODERATE_BUY,
    SIGNAL_SQUEEZE,
    SIGNAL_NEUTRAL,
    SIGNAL_MODERATE_SELL,
    SIGNAL_STRONG_SELL,
)

# Hacia dónde dice cada señal que va el precio. Un acierto de compra es un
# retorno positivo y uno de venta, negativo: medirlos con la misma regla haría
# que un lado se viera bien justo cuando el otro se ve mal.
#
# Squeeze y neutral no quedan afuera por descuido: no afirman dirección. El
# squeeze afirma **magnitud** (que la compresión se resuelve con un movimiento
# grande), y eso se lee en la columna de movimiento absoluto, no en la de
# aciertos.
SIGNAL_DIRECTION = {
    SIGNAL_STRONG_BUY: 1,
    SIGNAL_MODERATE_BUY: 1,
    SIGNAL_MODERATE_SELL: -1,
    SIGNAL_STRONG_SELL: -1,
}

COL_SIGNAL = "Señal"
COL_CASES = "Casos"
COL_MEAN = "Retorno Medio (%)"
COL_MEDIAN = "Retorno Mediano (%)"
COL_EXCESS = "Exceso vs Base (pp)"
COL_HIT_RATE = "Tasa de Acierto (%)"
COL_ABS_MOVE = "Mov. Absoluto (%)"
COL_WORST = "Peor (%)"
COL_BEST = "Mejor (%)"

SUMMARY_COLUMNS = (
    COL_SIGNAL,
    COL_CASES,
    COL_MEAN,
    COL_EXCESS,
    COL_MEDIAN,
    COL_HIT_RATE,
    COL_ABS_MOVE,
    COL_WORST,
    COL_BEST,
)


def forward_returns(close: pd.Series, horizon: int) -> pd.Series:
    """
    Retorno porcentual de las `horizon` barras siguientes a cada barra.

    Las últimas `horizon` barras quedan en NaN por construcción: su futuro
    todavía no pasó. Es la única forma honesta de hacerlo — rellenarlas con el
    último precio disponible acortaría el horizonte justo en el tramo más
    reciente, que es el que más mira cualquiera.

    Un horizonte no positivo devuelve la serie entera en NaN, con la misma
    longitud e índice: quien la recibe la alinea contra las señales, y una
    serie más corta rompería ese alineamiento en silencio.
    """
    close = pd.to_numeric(close, errors="coerce")
    if close.empty or horizon <= 0:
        return pd.Series(np.nan, index=close.index, dtype=float)
    return (close.shift(-horizon) / close - 1.0) * 100.0


def replay_confluence_signals(
    df_history: pd.DataFrame,
    window_52w: int = 252,
    squeeze_lookback: int = SQUEEZE_LOOKBACK_BARS,
    thresholds: ConfluenceThresholds = STOCK_THRESHOLDS,
) -> pd.Series:
    """
    Señal del semáforo en cada barra, como la habría mostrado el tablero ese día.

    Reusa `evaluate_confluence_signal` sin tocarlo: si la medición usara una
    copia de las reglas, mediría otro sistema. Lo que se arma acá es la entrada
    que esa función espera —un diccionario de indicadores por barra— en forma
    vectorizada, calculando cada serie una sola vez en lugar de rehacer
    `compute_stock_technicals` sobre una ventana creciente, que es cuadrático.

    Cada barra ve únicamente datos hasta ella misma: las medias, el RSI, las
    bandas y el OBV son acumulados hacia atrás, y los mínimos de bandwidth y la
    dispersión se toman con ventanas móviles que terminan en la barra. No hay
    forma de que se filtre el futuro.
    """
    if df_history is None or df_history.empty or "Close" not in df_history.columns:
        return pd.Series(dtype=object)

    df = df_history.sort_index()
    close = pd.to_numeric(df["Close"], errors="coerce")

    sma_50 = compute_sma(close, 50)
    sma_200 = compute_sma(close, 200)
    rsi = compute_rsi(close, 14)
    macd = compute_macd(close, fast=12, slow=26, signal=9)
    bb = compute_bollinger_bands(close, period=20, num_std=2.0)
    stoch = compute_stochastic(df, period_k=14, period_d=3)
    obv = compute_obv(df, period_sma=20)
    banda_52w = compute_52w_high_low(df, window=window_52w)

    # Squeeze: bandwidth en mínimos de la ventana que termina en cada barra.
    # Es el mismo criterio que `compute_stock_technicals` aplica sobre la
    # última barra, expresado como mínimo móvil.
    bandwidth = bb["bb_bandwidth"]
    minimo_movil = bandwidth.rolling(squeeze_lookback, min_periods=_MIN_BARS).min()
    squeeze = bandwidth <= minimo_movil * SQUEEZE_BANDWIDTH_TOLERANCE

    # Dispersión típica alrededor de la SMA 50, móvil (ver compute_sma50_dispersion).
    ratio_sma50 = (close - sma_50) / sma_50.replace(0, np.nan) * 100.0
    dispersion = ratio_sma50.rolling(window_52w, min_periods=30).std(ddof=1)

    campos = pd.DataFrame({
        "close": close,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "rsi_14": rsi,
        "macd_line": macd["macd"],
        "signal_line": macd["signal"],
        "macd_hist": macd["hist"],
        "prev_macd_hist": macd["hist"].shift(1),
        "bb_lower": bb["bb_lower"],
        "is_bb_squeeze": squeeze,
        "stoch_k": stoch["stoch_k"],
        "stoch_d": stoch["stoch_d"],
        "prev_stoch_k": stoch["stoch_k"].shift(1),
        "prev_stoch_d": stoch["stoch_d"].shift(1),
        "obv": obv["obv"],
        "sma_obv_20": obv["sma_obv_20"],
        "dist_52w_high_pct": banda_52w["dist_52w_high_pct"],
        "sma50_dispersion_pct": dispersion,
    })
    campos["diff_sma_50_pct"] = [
        compute_percent_diff(c, s) for c, s in zip(campos["close"], campos["sma_50"], strict=False)
    ]

    señales = []
    for posicion, (_, fila) in enumerate(campos.iterrows()):
        if posicion + 1 < _MIN_BARS:
            # El propio semáforo se abstiene con menos de 20 barras de historia.
            señales.append(SIGNAL_NEUTRAL)
            continue
        # `evaluate_confluence_signal` usa `df_history` solo para ese mínimo de
        # barras, así que pasarle el historial completo es equivalente a
        # pasarle el tramo hasta la barra y evita copiarlo en cada iteración.
        señales.append(evaluate_confluence_signal(df, fila.to_dict(), thresholds))

    return pd.Series(señales, index=campos.index, dtype=object)


def collect_signal_outcomes(
    historiales: dict[str, pd.DataFrame],
    horizon: int,
    window_52w: int = 252,
    squeeze_lookback: int = SQUEEZE_LOOKBACK_BARS,
    thresholds: ConfluenceThresholds = STOCK_THRESHOLDS,
) -> pd.DataFrame:
    """
    Tabla larga: una fila por barra y por activo, con su señal y lo que vino después.

    Es el dato crudo de la medición, y se devuelve aparte del resumen para que
    se pueda mirar un caso puntual (qué activo, qué fecha) en vez de solo el
    promedio.
    """
    filas = []
    for ticker, historial in (historiales or {}).items():
        if historial is None or historial.empty or "Close" not in historial.columns:
            continue

        df = historial.sort_index()
        señales = replay_confluence_signals(
            df,
            window_52w=window_52w,
            squeeze_lookback=squeeze_lookback,
            thresholds=thresholds,
        )
        if señales.empty:
            continue

        retornos = forward_returns(pd.to_numeric(df["Close"], errors="coerce"), horizon)
        parcial = pd.DataFrame({
            "Ticker": ticker,
            "Fecha": señales.index,
            COL_SIGNAL: señales.to_numpy(),
            "Retorno (%)": retornos.reindex(señales.index).to_numpy(),
        })
        filas.append(parcial.dropna(subset=["Retorno (%)"]))

    if not filas:
        return pd.DataFrame(columns=["Ticker", "Fecha", COL_SIGNAL, "Retorno (%)"])

    return pd.concat(filas, ignore_index=True)


def _resumen_de_grupo(señal: str, retornos: pd.Series, base_media: float) -> dict:
    direccion = SIGNAL_DIRECTION.get(señal)
    if direccion is None:
        tasa_acierto = np.nan
    elif direccion > 0:
        tasa_acierto = float((retornos > 0).mean() * 100.0)
    else:
        tasa_acierto = float((retornos < 0).mean() * 100.0)

    media = float(retornos.mean())
    return {
        COL_SIGNAL: señal,
        COL_CASES: int(len(retornos)),
        COL_MEAN: media,
        COL_EXCESS: media - base_media if np.isfinite(base_media) else np.nan,
        COL_MEDIAN: float(retornos.median()),
        COL_HIT_RATE: tasa_acierto,
        COL_ABS_MOVE: float(retornos.abs().mean()),
        COL_WORST: float(retornos.min()),
        COL_BEST: float(retornos.max()),
    }


def summarize_outcomes(outcomes: pd.DataFrame, min_cases: int = SIGNAL_STATS_MIN_CASES) -> pd.DataFrame:
    """
    Resumen por señal, con la fila de base primero.

    Las señales con menos de `min_cases` casos se informan igual, porque su
    ausencia también es información —un semáforo que nunca dispara el lado
    venta es un hallazgo, no un dato faltante—, pero el componente que dibuja
    las marca para que nadie lea un promedio de tres casos como una medición.
    """
    if outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=list(SUMMARY_COLUMNS))

    retornos_totales = pd.to_numeric(outcomes["Retorno (%)"], errors="coerce").dropna()
    if retornos_totales.empty:
        return pd.DataFrame(columns=list(SUMMARY_COLUMNS))

    base_media = float(retornos_totales.mean())
    base = {
        COL_SIGNAL: SIGNAL_STATS_BASELINE,
        COL_CASES: int(len(retornos_totales)),
        COL_MEAN: base_media,
        COL_EXCESS: 0.0,
        COL_MEDIAN: float(retornos_totales.median()),
        COL_HIT_RATE: float((retornos_totales > 0).mean() * 100.0),
        COL_ABS_MOVE: float(retornos_totales.abs().mean()),
        COL_WORST: float(retornos_totales.min()),
        COL_BEST: float(retornos_totales.max()),
    }

    filas = [base]
    presentes = set(outcomes[COL_SIGNAL].dropna().unique())
    orden = list(SIGNAL_ORDER) + sorted(presentes - set(SIGNAL_ORDER))
    for señal in orden:
        grupo = pd.to_numeric(
            outcomes.loc[outcomes[COL_SIGNAL] == señal, "Retorno (%)"], errors="coerce"
        ).dropna()
        if grupo.empty:
            continue
        filas.append(_resumen_de_grupo(señal, grupo, base_media))

    return pd.DataFrame(filas, columns=list(SUMMARY_COLUMNS))


def measure_signal_quality(
    historiales: dict[str, pd.DataFrame],
    horizon: int,
    window_52w: int = 252,
    squeeze_lookback: int = SQUEEZE_LOOKBACK_BARS,
    thresholds: ConfluenceThresholds = STOCK_THRESHOLDS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Atajo: devuelve `(resumen, casos)` en una sola llamada."""
    casos = collect_signal_outcomes(
        historiales,
        horizon,
        window_52w=window_52w,
        squeeze_lookback=squeeze_lookback,
        thresholds=thresholds,
    )
    return summarize_outcomes(casos), casos
