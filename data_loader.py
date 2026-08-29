"""
data_loader.py - Descarga optimizada de datos y fundamentales con Yahoo Finance
"""

import concurrent.futures
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from indicators import compute_stock_technicals

# Listas de Tickers Predefinidos
TOP_50_DEFAULT = [
    "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "BRK-B", "TSLA", "AVGO", "JPM",
    "LLY", "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "COST", "ABBV",
    "MRK", "CRM", "BAC", "NFLX", "AMD", "KO", "PEP", "ORCL", "CVX", "ADBE",
    "QCOM", "WMT", "CSCO", "INTC", "MCD", "DIS", "WFC", "TXN", "AMAT", "INTU",
    "IBM", "NOW", "PM", "GE", "CAT", "UBER", "ISRG", "AXP", "BKNG", "CMG"
]

TOP_TECH = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "ORCL", "CRM",
    "AMD", "ADBE", "QCOM", "NFLX", "INTC", "TXN", "AMAT", "INTU", "IBM", "NOW",
    "UBER", "PANW", "SNPS", "CDNS", "CRWD", "PLTR", "MRVL", "KLAC", "LRCX", "MU"
]

TOP_DIVIDEND_VALUE = [
    "JNJ", "PG", "KO", "PEP", "XOM", "CVX", "JPM", "BAC", "ABBV", "MRK",
    "HD", "MCD", "PM", "CAT", "WMT", "IBM", "CSCO", "VZ", "T", "UNP"
]


def calculate_historical_avg_pe(t_obj: yf.Ticker, history_df: pd.DataFrame = None) -> float:
    """
    Calcula el promedio histórico del PER (5 años) a partir del EPS de los balances anuales
    y los precios de mercado en torno a cada cierre de ejercicio fiscal.
    """
    try:
        stmt = t_obj.income_stmt
        if stmt is None or stmt.empty or "Diluted EPS" not in stmt.index:
            return np.nan
        eps_series = stmt.loc["Diluted EPS"].dropna()
        if eps_series.empty:
            return np.nan
        
        if history_df is None or history_df.empty:
            history_df = t_obj.history(period="5y")
            
        hist_idx = history_df.index.tz_localize(None) if history_df.index.tz is not None else history_df.index
        df_temp = history_df.copy()
        df_temp.index = hist_idx

        pes = []
        for date_col, eps_val in eps_series.items():
            if pd.isna(eps_val) or eps_val <= 0:
                continue
            date_ts = pd.to_datetime(date_col).tz_localize(None)
            hist_sub = df_temp.loc[date_ts - pd.Timedelta(days=60):date_ts + pd.Timedelta(days=60)]
            if not hist_sub.empty and "Close" in hist_sub.columns:
                avg_price = hist_sub["Close"].mean()
                pe = avg_price / eps_val
                if 0 < pe < 300:
                    pes.append(pe)
        if pes:
            return float(np.mean(pes))
        return np.nan
    except Exception:
        return np.nan


def fetch_single_ticker_info(ticker: str) -> dict:
    """
    Obtiene los metadatos fundamentales de una acción individual (P/E Pasado, P/E Futuro, P/E Promedio Histórico, etc.).
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        
        long_name = info.get("shortName") or info.get("longName") or ticker
        sector = info.get("sector", "Desconocido")
        industry = info.get("industry", "Desconocido")
        
        trailing_pe = info.get("trailingPE")
        if trailing_pe is not None and (trailing_pe <= 0 or trailing_pe > 500):
            trailing_pe = np.nan
            
        forward_pe = info.get("forwardPE")
        if forward_pe is not None and (forward_pe <= 0 or forward_pe > 500):
            forward_pe = np.nan
            
        hist_avg_pe = calculate_historical_avg_pe(t)
        
        peg_ratio = info.get("pegRatio")
        market_cap = info.get("marketCap")
        dividend_yield = info.get("dividendYield")
        if dividend_yield is not None:
            dividend_yield = dividend_yield * 100.0
            
        fifty_two_week_high = info.get("fiftyTwoWeekHigh")
        fifty_two_week_low = info.get("fiftyTwoWeekLow")
        
        return {
            "ticker": ticker,
            "name": long_name,
            "sector": sector,
            "industry": industry,
            "trailing_pe": trailing_pe,
            "forward_pe": forward_pe,
            "hist_avg_pe": hist_avg_pe,
            "peg_ratio": peg_ratio,
            "market_cap": market_cap,
            "dividend_yield": dividend_yield,
            "fifty_two_week_high": fifty_two_week_high,
            "fifty_two_week_low": fifty_two_week_low,
            "currency": info.get("currency", "USD")
        }
    except Exception:
        return {
            "ticker": ticker,
            "name": ticker,
            "sector": "Desconocido",
            "industry": "Desconocido",
            "trailing_pe": np.nan,
            "forward_pe": np.nan,
            "hist_avg_pe": np.nan,
            "peg_ratio": np.nan,
            "market_cap": np.nan,
            "dividend_yield": np.nan,
            "fifty_two_week_high": np.nan,
            "fifty_two_week_low": np.nan,
            "currency": "USD"
        }


@st.cache_data(ttl=300, show_spinner=False)
def load_all_stocks_data(tickers: list[str], timeframe: str = "1d") -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """
    Descarga en paralelo los datos históricos y fundamentales según la temporalidad.
    """
    tickers = list(dict.fromkeys([t.strip().upper() for t in tickers if t.strip()]))
    if not tickers:
        return pd.DataFrame(), {}
    
    period = "5y" if timeframe == "1wk" else "2y"
    interval = "1wk" if timeframe == "1wk" else "1d"

    # 1. Descarga masiva de datos de precios
    try:
        df_download = yf.download(
            tickers=tickers,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False
        )
    except Exception:
        df_download = pd.DataFrame()

    dict_history = {}
    technicals_map = {}
    is_multi_ticker = len(tickers) > 1

    for ticker in tickers:
        try:
            if is_multi_ticker and isinstance(df_download.columns, pd.MultiIndex):
                if ticker in df_download.columns.levels[0]:
                    df_t = df_download[ticker].dropna(how="all").copy()
                else:
                    df_t = pd.DataFrame()
            else:
                df_t = df_download.copy()
            
            if not df_t.empty and 'Close' in df_t.columns:
                df_t = df_t.sort_index()
                dict_history[ticker] = df_t
                technicals_map[ticker] = compute_stock_technicals(df_t)
            else:
                t_obj = yf.Ticker(ticker)
                df_single = t_obj.history(period=period, interval=interval)
                if not df_single.empty:
                    dict_history[ticker] = df_single
                    technicals_map[ticker] = compute_stock_technicals(df_single)
                else:
                    technicals_map[ticker] = compute_stock_technicals(pd.DataFrame())
        except Exception:
            technicals_map[ticker] = compute_stock_technicals(pd.DataFrame())

    # 2. Descarga multithreading de datos fundamentales
    fundamentals_map = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(20, len(tickers))) as executor:
        future_to_ticker = {executor.submit(fetch_single_ticker_info, t): t for t in tickers}
        for future in concurrent.futures.as_completed(future_to_ticker):
            t = future_to_ticker[future]
            try:
                res = future.result()
                fundamentals_map[t] = res
            except Exception:
                fundamentals_map[t] = {
                    "ticker": t,
                    "name": t,
                    "sector": "Desconocido",
                    "trailing_pe": np.nan,
                    "forward_pe": np.nan,
                    "hist_avg_pe": np.nan,
                    "market_cap": np.nan
                }

    # 3. Consolidar en un solo DataFrame con 'Semáforo' al inicio y 'Flujo Institucional'
    tf_suffix = " (Sem)" if timeframe == "1wk" else " (Día)"
    rows = []
    for ticker in tickers:
        fund = fundamentals_map.get(ticker, {})
        tech = technicals_map.get(ticker, {})
        
        row = {
            "Semáforo": tech.get("confluence_signal", "🟡 NEUTRAL"),
            "Ticker": ticker,
            "Flujo Institucional": tech.get("institutional_flow", "N/A"),
            "Precio Actual": tech.get("close", np.nan),
            "Var. Período (%)": tech.get("day_change_pct", np.nan),
            "PER Pasado (Trailing)": fund.get("trailing_pe", np.nan),
            "PER Futuro (Forward)": fund.get("forward_pe", np.nan),
            "PER Prom. Hist. (5A)": fund.get("hist_avg_pe", np.nan),
            f"RSI (14){tf_suffix}": tech.get("rsi_14", np.nan),
            f"Dif. % SMA 20{tf_suffix}": tech.get("diff_sma_20_pct", np.nan),
            f"Dif. % SMA 50{tf_suffix}": tech.get("diff_sma_50_pct", np.nan),
            f"Dif. % SMA 200{tf_suffix}": tech.get("diff_sma_200_pct", np.nan),
            "Dif. % Máx 52S": tech.get("dist_52w_high_pct", np.nan),
            "Bollinger BW (%)": tech.get("bb_bandwidth", np.nan),
            "MACD Hist": tech.get("macd_hist", np.nan),
            "Estocástico %K": tech.get("stoch_k", np.nan),
            "Estocástico %D": tech.get("stoch_d", np.nan),
            # Claves genéricas para filtros y KPIs
            "RSI_VAL": tech.get("rsi_14", np.nan),
            "SMA_20_VAL": tech.get("sma_20", np.nan),
            "SMA_50_VAL": tech.get("sma_50", np.nan),
            "SMA_200_VAL": tech.get("sma_200", np.nan),
            "DIFF_SMA_20_VAL": tech.get("diff_sma_20_pct", np.nan),
            "DIFF_SMA_50_VAL": tech.get("diff_sma_50_pct", np.nan),
            "DIFF_SMA_200_VAL": tech.get("diff_sma_200_pct", np.nan),
            "DIST_52W_HIGH_PCT": tech.get("dist_52w_high_pct", np.nan),
            "BB_BANDWIDTH": tech.get("bb_bandwidth", np.nan),
            "Sector": fund.get("sector", "Desconocido"),
            "Market Cap ($B)": (fund.get("market_cap") / 1e9) if fund.get("market_cap") else np.nan,
            "Timeframe": timeframe
        }
        rows.append(row)

    df_summary = pd.DataFrame(rows)
    return df_summary, dict_history
