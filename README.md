# Quantitative Stock Dashboard & Confluence Screener

A high-performance quantitative stock screening dashboard built with **Streamlit**, **Pandas**, and **Yahoo Finance (`yfinance`)**. 

The platform monitors the top 50 market leaders in real-time, combining **fundamental valuation metrics** (Trailing P/E, Forward P/E, and 5-Year Historical P/E) with **John Murphy's Technical Confluence Principles** to identify swing trading opportunities, rotation exhaustion points, and volatility squeeze setups at a glance.

---

## ⚡ Key Features

### 1. Confluence Engine (The "Traffic Light" System)
Evaluates market data across multiple indicators simultaneously to generate unified, actionable trading signals:

* 🔴 **SELL / ROTATE:** Triggered when price trades within 5% of its 52-Week High, RSI (14) enters overbought territory (> 70), Stochastic crosses down (or > 80), and MACD histogram begins losing upward momentum.
* 🟢 **SWING BUY:** Triggered in a confirmed structural uptrend ($\text{SMA 50} > \text{SMA 200}$) when price executes a healthy pullback to key support (Lower Bollinger Band or SMA 50), with RSI < 35 and Stochastic crossing upward out of oversold territory.
* 🚨 **SQUEEZE:** Detects extreme volatility compression where Bollinger Bandwidth hits multi-month lows (6-month minimum), signaling an imminent directional expansion.
* 🟡 **NEUTRAL:** Baseline tracking mode when conditions do not meet strict confluence thresholds.

---

### 2. Fundamental Valuation Matrix
* **Trailing P/E:** Price-to-Earnings based on real earnings from the last 12 months (TTM).
* **Forward P/E:** Price-to-Earnings based on analyst consensus earnings estimates for the next 12 months.
* **5-Year Historical Average P/E:** Multi-year baseline calculated from annual fiscal statements, allowing quick detection of multiple expansion or undervaluation.

---

### 3. Quantitative Technical Indicators
* **Moving Averages & % Distances:** SMA 20 (Short-term), SMA 50 (Medium-term), and SMA 200 (Macro trend), with real-time percentage deviation ($\Delta\%$).
* **Relative Strength Index (RSI 14):** Wilder's smoothed momentum oscillator with fixed 30 and 70 threshold markers.
* **MACD (12, 26, 9):** Trend-following momentum indicator measuring convergence/divergence.
* **Bollinger Bands (20, 2):** Volatility envelopes and dynamic support/resistance channels with normalized bandwidth calculation.
* **Stochastic Oscillator (%K 14, %D 3):** Momentum trigger confirming micro trend turns.
* **52-Week High / Low:** 252-period rolling extremes and percentage distance from cycle highs.

---

### 4. Architecture & Usability
* **Dual Timeframe Engine:** Seamlessly toggle between **Daily (1D)** and **Weekly (1W)** calculations.
* **Top Alerts Panel:** Immediate categorization of tickers activating Sell, Buy, or Squeeze setups.
* **Multi-threaded Ingestion:** Fast parallel data downloading using `concurrent.futures` and intelligent caching via `st.cache_data`.
* **One-Click Export:** Instant filtered CSV downloads.

---

## 📁 Repository Structure

```
stock-dashboard/
├── app.py                  # Main Streamlit application and layout
├── data_loader.py          # Parallel data extraction, fundamentals & caching
├── indicators.py           # Technical indicators & Confluence algorithm
├── components/
│   ├── alerts_panel.py     # Top prominent signal cards
│   ├── kpi_cards.py        # Market breadth & valuation aggregations
│   └── screener_table.py   # Interactive screener table
├── requirements.txt        # Project dependencies
├── run.sh                  # One-click startup script
└── .gitignore
```

---

## 🚀 Quick Start

### Prerequisites
* Python 3.10+
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

## ⚠️ Disclaimer
*This project is built for quantitative research and screening purposes only. It does not constitute financial advice. Past performance and quantitative indicators do not guarantee future market results.*
