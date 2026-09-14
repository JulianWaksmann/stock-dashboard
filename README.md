# Quantitative Stock Dashboard & Confluence Screener

A high-performance quantitative screening dashboard built with **Streamlit**, **Pandas**, and **Yahoo Finance (`yfinance`)**, split into two sections: **Equities** (technical confluence screener) and **Argentine Corporate Bonds** (fixed-income analytics for Obligaciones Negociables). Sections are selected rather than tabbed, so each one queries its data sources only when it is actually opened.

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

## 💵 Argentine Corporate Bonds (Obligaciones Negociables)

A second section prices the Argentine corporate hard-dollar bond panel from its **contractual cash
flow** — not from price-momentum indicators, which say nothing useful about a bond.

### What it computes

For every ON whose issue terms are known, the section derives, per 100 of original face value:

| Metric | What it answers |
| --- | --- |
| **YTM (TIR)** | Effective annual return if held to maturity. The single comparison variable across bonds. |
| **Current yield** | Annual coupon over price paid — this year's cash flow, ignoring capital gain/loss. |
| **Modified duration** | Interest-rate risk: approximate % price drop per 1 pp rise in required yield. |
| **Macaulay duration / convexity** | Time-weighted average of the discounted cash flow, and the curvature duration alone misses. |
| **Weighted average life (WAL)** | How long, on average, until the principal comes back. Well below maturity on amortizing bonds. |
| **Parity** | Price over technical value. Below 100 means part of the return arrives as capital gain. |
| **Technical value / accrued interest / residual capital** | What the contract says the bond is worth today. |
| **Spread vs UST** | Basis points over the duration-matched US Treasury — the price of Argentine + issuer risk. |
| **Bid/ask spread, volume** | Whether the quoted yield is actually executable. |
| **Minimum denomination** | Whether a retail investor can buy it at all (many NY-law ONs trade in 100k+ lots). |

An in-app glossary explains every one of these in plain Spanish, next to the table.

### Attractiveness grading

Bonds are graded **against their peers on the same day**, not against their own history: an 11%
yield is excellent or mediocre depending on where the rest of the corporate panel trades. The
reference for every yield threshold is therefore the **panel's median YTM**.

* **Mandatory:** a computable YTM. Without issue terms there is no cash flow to discount (⚪ SIN DATOS).
* **Excluding alert:** YTM above the median + `BOND_RISK_YIELD_PREMIUM_PP` → 🚨 **ALERTA DE RIESGO**.
  A premium that large over peers is the market pricing default risk, not a cheap bond.
* **Points, one each:** yield premium over the median; modified duration ≤ `BOND_SHORT_DURATION_MAX_YEARS`;
  parity below par; bid/ask spread ≤ `BOND_LIQUID_SPREAD_MAX_PCT`; New York law.
* 4-5 points → 🌟 **MUY ATRACTIVO** · 3 → 🟢 **ATRACTIVO** · 2 → 🟡 **NEUTRAL** · 0-1 → 🟠 **POCO ATRACTIVO**.
* **Excluded from grading:** bonds under `BOND_MIN_YEARS_FOR_GRADING` from maturity (⏳ **MUY CORTO**).
  Annualizing a three-week return turns one cent of price into tens of points of yield, so those
  bonds would otherwise top the panel or trigger a risk alert on pure arithmetic artifact. They are
  also left out of the panel median, so they cannot drag the reference everything else is graded against.

All labels and thresholds live in `constants.py`, same as the equity engine.

### Where the data comes from

| Data | Source | Notes |
| --- | --- | --- |
| Prices, bid/ask, volume | [data912](https://data912.com/live/arg_corp) | Public JSON, no API key. Educational feed cached ~2h upstream — good for yield analysis, not for execution. |
| Payment schedules | [rendimientos-ar](https://github.com/arisbdar/rendimientos-ar) (`public/config.json`) | Fetched on every load. A **community dataset** hand-kept by third parties (ISC), not an official source. Publishes each payment's total, without splitting interest from principal. |
| Issue terms | `data/ons_catalog.csv` (this repo) | Optional, empty by default. Only needed for the metrics that require the interest/principal split, or for a bond the community dataset does not cover. |
| US Treasury curve | Yahoo Finance (`^IRX`, `^FVX`, `^TNX`, `^TYX`) | Via `yfinance`, same as the equities section. Linearly interpolated to each bond's duration. |

### Two ways to know a bond

A bond's issue terms are not downloadable. Coupon, amortization schedule and governing law live in
its prospectus, and neither BYMA nor the CNV publishes them in machine-readable form. So the panel
works from whichever of two sources it has, and says which one on every row:

* **Payment schedule** (community dataset, fetched live) — covers the traded universe with no
  manual upkeep, but reports only each payment's total. That is enough for YTM, duration and
  convexity, and not enough for parity, technical value, accrued interest or WAL, which need to
  know how much of each payment is principal. Those columns stay empty rather than guessing.
* **Issue terms** (`data/ons_catalog.csv`) — computes everything, and has to be typed in by hand.
  A catalog row always wins over the community schedule, because loading one is a deliberate act.

The catalog ships **empty on purpose**: shipping plausible-looking coupons nobody verified would
return wrong yields that look authoritative. Any row added there is flagged ⚠️ until marked
`verificado=si`, and is worth checking against the issuer's prospectus (via the
[CNV](https://www.argentina.gob.ar/cnv)), the [IAMC](https://www.iamc.com.ar) daily report (which
publishes YTM, parity and duration already computed, so it validates both the inputs and the
result), or the [BYMA](https://www.byma.com.ar) daily bulletin.

### Settlement species

The last letter of a BYMA ticker is the settlement species, not decoration: **O** settles in pesos,
**D** in MEP dollars, **C** in cable. `YMCJO`, `YMCJD` and `YMCJC` are the same YPF bond, but the
first quotes around 152,000 pesos where the others quote around 105 dollars.

Two consequences, both handled:

* A yield is computed only when the species' quote currency matches the bond's currency of issue.
  Discounting a dollar cash flow against a peso price does not give a slightly wrong yield, it
  gives a meaningless one — the peso species shows price and liquidity with no yield instead.
* The catalog is matched by ticker root, so one row loaded as `YMCJO` also covers `YMCJD` and
  `YMCJC`. An exact ticker still wins over the root, leaving room to load a single species with
  different terms.

The panel quotes 600+ species against a catalog covering a handful, so the species filter defaults
to the dollar ones and the uncatalogued list sits behind an expander rather than in the warning.

### Liquidity

No ticker list is typed anywhere: the universe comes from the price feed. What needs filtering is
the noise in it — species that did not trade today still quote the price of the last session they
did, so their yield measures a different day's market.

The liquidity filter defaults to the top 50 by volume, and offers top-20 or every bond that traded.
Its thresholds are relative rather than absolute because the feed does not document the unit its
volume is expressed in: "over 1,000,000" would be a made-up number, "the 20 that traded most today"
holds without knowing the unit.

Asking for both dollar species collapses each bond to one row, keeping its most traded species:
MEP and cable are the same bond collected in a different place, so showing both would spend half
of a top-50 on repetitions instead of distinct issuers.

Currency is filtered before the volume ranking, and the order is not cosmetic: the peso species'
volume is denominated in pesos and the MEP species' in dollars, so ranking across both compares
different units and the peso rows win on magnitude rather than on activity.

Untraded species are also left out of the panel median for the same reason near-maturity bonds are
— the median is the reference every bond is graded against, so it cannot be built from prices that
are not comparable. They stay visible in the table; only their influence on the grading is removed.

### Modeling limits

* **Fixed-rate bonds only.** CER, dollar-linked, Badlar and TAMAR ONs cannot be modeled here:
  their future cash flow is not determined today. Loading one would produce a meaningless YTM.
* No step-up coupons and no call/put schedules.
* Accrued interest on a 30/360 basis; discounting on ACT/365 with annual compounding, so the
  reported YTM is an **effective annual rate**, directly comparable across payment frequencies.
* The price convention (dirty vs clean) is an explicit selector, because getting it
  wrong silently biases YTM and parity. BYMA publishes dirty prices.

---

## 📁 Repository Structure

```
stock-dashboard/
├── app.py                          # Streamlit entry point: page layout, sidebar filters and market/timeframe selectors
├── constants.py                    # Single source of truth for signal labels and confluence engine thresholds
├── theme.py                        # Centralized color palette shared by the table and the charts
├── data_loader.py                  # Parallel price + fundamentals download, caching, and technicals aggregation
├── indicators.py                   # Indicator math (SMA/EMA/RSI/MACD/Bollinger/Stochastic/OBV/52W) and the confluence algorithm
├── bonds/
│   ├── __init__.py                 # Fixed-income package for Argentine corporate bonds (ONs)
│   ├── bond_math.py                # Cash flows, YTM, duration, convexity, parity, accrued interest (pure, no I/O)
│   ├── catalog.py                  # Parses and validates data/ons_catalog.csv into BondTerms; settlement-species helpers
│   ├── flows_source.py             # Fetches published payment schedules (community dataset)
│   ├── panel.py                    # Pure merge of prices + terms + metrics, and the panel filters (order matters, so it is tested)
│   ├── scoring.py                  # Peer-relative attractiveness grading for ONs
│   └── data_loader.py              # I/O only: live price feed, US Treasury curve, cached orchestration
├── data/
│   └── ons_catalog.csv             # Optional hand-kept issue terms per ON; empty by default, overrides the fetched schedule
├── components/
│   ├── __init__.py                 # Marks components as a package
│   ├── alerts_panel.py             # Top "quick alerts" cards grouped by signal grade
│   ├── bonds_panel.py              # The whole Bonds section: controls, KPIs, filters, glossary and methodology
│   ├── bonds_table.py              # Comparison table of ONs with conditional formatting and per-column help
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
│   ├── test_bond_catalog.py        # Tests for the ONs catalog parser and its error reporting
│   ├── test_bond_filters.py        # Tests for the panel filters and the order they are applied in
│   ├── test_bond_math.py           # Tests for the fixed-income math (cash flows, YTM, duration, parity)
│   ├── test_bond_scoring.py        # Tests for the ONs attractiveness grading
│   ├── test_bonds_panel.py         # Tests for the price/terms merge, source priority and Treasury curve interpolation
│   ├── test_flows_source.py        # Tests for the published payment-schedule parser
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
* Bond grading labels and thresholds: `constants.py` (the "BONOS CORPORATIVOS" section).
* Issue terms of an ON (coupon, maturity, amortization schedule, law): `data/ons_catalog.csv`.
* The payment-schedule dataset: `COMMUNITY_FLOWS_URL` in `bonds/flows_source.py`.
* The bond price feed: `DATA912_CORPORATE_BONDS_URL` in `bonds/data_loader.py` — any source returning
  the same JSON shape drops straight in.
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
