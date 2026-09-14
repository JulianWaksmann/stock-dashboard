# Quantitative Stock Dashboard & Confluence Screener

A high-performance quantitative stock screening dashboard built with **Streamlit**, **Pandas**, and **Yahoo Finance (`yfinance`)**. 

The platform monitors the top 50 market leaders in real-time, combining **fundamental valuation metrics** (Trailing P/E, Forward P/E, and 5-Year Historical P/E) with **John Murphy's Technical Confluence Principles** and an **On-Balance Volume "Smart Money" flow check** to identify swing trading opportunities, rotation exhaustion points, and volatility squeeze setups at a glance.

---

## ⚡ Key Features

### 1. Confluence Engine (Grade-Based "Traffic Light" System)
Scores each ticker against a small set of mandatory and optional conditions to produce a graded signal:

**Buy side (swing setups)**
* Mandatory: price within ±4% of SMA 50, **or** at/below the Lower Bollinger Band (1% tolerance) — **and** RSI (14) < 45.
* Optional, one point each: confirmed uptrend (SMA 50 > SMA 200, tolerating up to 5% below SMA 200), Stochastic bullish crossover or %K < 30, and OBV above its 20-period SMA (Smart Money accumulation).
* 4-5 points → 🌟 **STRONG BUY**. Exactly 3 points → 🟢 **MODERATE BUY**.

**Sell side (rotation / exhaustion)**
* Mandatory: price within 6% of its 52-week high — **and** RSI (14) > 65.
* Optional, one point each: Stochastic bearish crossover or %K ≥ 80, a weakening MACD (falling histogram or MACD line below signal line), and OBV below its 20-period SMA (Smart Money distribution).
* 3-4 points → 🚨 **STRONG SELL / ROTATE**. Exactly 2 points → 🟠 **MODERATE SELL**.

**Other states**
* 🚨 **SQUEEZE:** Bollinger Bandwidth at, or within 8% of, its 6-month (126-bar) low — signaling volatility compression and an imminent directional expansion.
* 🟡 **NEUTRAL:** baseline tracking mode when no confluence thresholds are met.

Every signal label and numeric threshold above lives in `constants.py`, which is the single source of truth shared by the algorithm (`indicators.py`) and the sidebar filters (`app.py`) — tune the rules there, not in the code that consumes them.

---

### 2. Smart Money Flow (Institutional OBV)
* Compares On-Balance Volume (OBV) against its own 20-period SMA to flag each ticker as 🐳 **Accumulation** or 📉 **Distribution**. This feeds both the confluence score above and its own "Flujo Institucional" column and sidebar filter.

---

### 3. Fundamental Valuation Matrix
* **Trailing P/E:** Price-to-Earnings based on real earnings from the last 12 months (TTM).
* **Forward P/E:** Price-to-Earnings based on analyst consensus earnings estimates for the next 12 months.
* **5-Year Historical Average P/E:** Multi-year baseline calculated from annual fiscal statements, allowing quick detection of multiple expansion or undervaluation.

---

### 4. Quantitative Technical Indicators
* **Moving Averages & % Distances:** SMA 20 (Short-term), SMA 50 (Medium-term), and SMA 200 (Macro trend), with real-time percentage deviation ($\Delta\%$).
* **Relative Strength Index (RSI 14):** Wilder's smoothed momentum oscillator, charted with fixed 30 and 70 threshold markers.
* **MACD (12, 26, 9):** Trend-following momentum indicator measuring convergence/divergence.
* **Bollinger Bands (20, 2):** Volatility envelopes and dynamic support/resistance channels with normalized bandwidth calculation.
* **Stochastic Oscillator (%K 14, %D 3):** Momentum trigger confirming micro trend turns.
* **52-Week High / Low:** 252-period rolling extremes and percentage distance from cycle highs.

---

### 5. Architecture & Usability
* **Dual Timeframe Engine:** Seamlessly toggle between **Daily (1D)** and **Weekly (1W)** calculations.
* **Market Selector:** the sidebar lets you pick a market; **USA Stocks (S&P 500)** is the fully implemented default, while Crypto and Argentine Equities (Merval) currently show as "coming soon" placeholders.
* **Quick Filters:** filter the screener by signal grade, Smart Money flow (OBV), RSI (14) range, and trend vs. SMA 200.
* **Top Alerts Panel:** immediate categorization of tickers activating Buy, Sell, or Squeeze setups.
* **Multi-threaded Ingestion:** fast parallel data downloading using `concurrent.futures` and intelligent caching via `st.cache_data`.
* **Resilient Data Loading:** if some tickers fail to download (Yahoo Finance rate limits, delisted symbols, network hiccups, etc.), the rest of the dashboard keeps working and a warning lists the tickers that were skipped.
* **One-Click Export:** instant filtered CSV downloads.

---

## 📁 Repository Structure

```
stock-dashboard/
├── app.py                          # Streamlit entry point: page layout, sidebar filters and market/timeframe selectors
├── constants.py                    # Single source of truth for signal labels and confluence engine thresholds
├── theme.py                        # Centralized color palette shared by the table and the charts
├── data_loader.py                  # Parallel price + fundamentals download, caching, and technicals aggregation
├── indicators.py                   # Indicator math (SMA/EMA/RSI/MACD/Bollinger/Stochastic/OBV/52W) and the confluence algorithm
├── components/
│   ├── __init__.py                 # Marks components as a package
│   ├── alerts_panel.py             # Top "quick alerts" cards grouped by signal grade
│   ├── charts.py                   # Plotly 4-panel technical chart and the valuation-vs-momentum scatter plot
│   ├── formatting.py               # Shared text formatting helpers (e.g. signed percentages)
│   ├── kpi_cards.py                # Market breadth and valuation summary KPI cards
│   ├── screener_table.py           # Interactive screener table with conditional color highlighting
│   └── ticker_detail.py            # Per-ticker detail view (chart + technical snapshot); not yet wired into app.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Shared pytest fixtures (deterministic synthetic series)
│   ├── test_52w_high_low.py        # Tests for compute_52w_high_low
│   ├── test_bollinger.py           # Tests for compute_bollinger_bands
│   ├── test_compute_stock_technicals.py  # Tests for the compute_stock_technicals aggregator
│   ├── test_confluence_signal.py   # Tests for evaluate_confluence_signal
│   ├── test_obv.py                 # Tests for compute_obv
│   ├── test_rsi.py                 # Tests for compute_rsi
│   ├── test_sma_ema_macd.py        # Tests for compute_sma / compute_ema / compute_macd
│   └── test_stochastic.py          # Tests for compute_stochastic
├── .github/workflows/ci.yml        # GitHub Actions CI: runs ruff and pytest on push/PR to main
├── requirements.txt                # Runtime dependencies
├── requirements-dev.txt            # Adds pytest + ruff on top of requirements.txt, for development and CI
├── ruff.toml                       # Linter configuration
├── pytest.ini                      # pytest configuration
├── .python-version                 # Pins the Python version (3.11) for local tooling
├── run.sh                          # One-click virtualenv setup + launch script
├── LICENSE                         # MIT license
└── .gitignore
```

---

## 🚀 Quick Start

### Prerequisites
* Python 3.11+
* Git

### 1. Clone the repository
```bash
git clone https://github.com/JulianWaksmann/stock-dashboard.git
cd stock-dashboard
```

### 2. Set up a virtual environment & install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Run the dashboard
```bash
streamlit run app.py
```
Or execute directly using the launcher script:
```bash
./run.sh
```

The application will open in your default browser at `http://localhost:8501`.

---

## 🛠️ Development / Contributing

### Install development dependencies
```bash
pip install -r requirements-dev.txt
```
This installs the runtime dependencies plus `pytest` and `ruff`.

### Run the test suite
```bash
pytest
```
The suite currently has 76 unit tests covering the indicator math and the confluence algorithm in `indicators.py`.

### Run the linter
```bash
ruff check .
```

### Continuous Integration
Every push and pull request against `main` runs both `ruff check .` and `pytest` via GitHub Actions (see `.github/workflows/ci.yml`); a PR won't be mergeable if either step fails.

### Where to change things
* Confluence signal labels and numeric thresholds: `constants.py`.
* Colors used across the table and the charts: `theme.py`.

---

## ☁️ Deployment (Streamlit Community Cloud)

This application is fully optimized for **Streamlit Community Cloud**:

1. Fork or push this repository to your GitHub account: `https://github.com/JulianWaksmann/stock-dashboard`.
2. Navigate to [share.streamlit.io](https://share.streamlit.io) and log in with GitHub.
3. Click **"New app"**, select your repository, branch (`main`), and set the main file path to `app.py`.
4. Click **"Deploy"**.

---

## 📊 Technical Rules Summary

$$\text{Distance to SMA}\% = \frac{\text{Price} - \text{SMA}}{\text{SMA}} \times 100$$

$$\text{Bollinger Bandwidth}\% = \frac{\text{Upper Band} - \text{Lower Band}}{\text{Middle Band}} \times 100$$

$$\text{Distance to 52W High}\% = \frac{\text{Price} - \text{High}_{252}}{\text{High}_{252}} \times 100$$

---

## 📄 License

This project is licensed under the **MIT License** — see [`LICENSE`](LICENSE) for the full text.

---

## ⚠️ Disclaimer
*This project is built for quantitative research and screening purposes only. It does not constitute financial advice. Past performance and quantitative indicators do not guarantee future market results.*
