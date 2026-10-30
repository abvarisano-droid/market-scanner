# Market Scanner

A daily scan of global stock indexes that finds stocks that look mispriced, ranks the strongest bullish and bearish price setups, explains each one in plain words, and then grades its own calls in public. One engine, one static website.

**Not investment advice.** Scores are mechanical rules on valuation, price and volume. They are not forecasts, and nothing here is a recommendation to trade. Data comes from Yahoo Finance and can be delayed or wrong.

## What it does
- **Universe:** S&P 500, Nasdaq 100, Dow, Russell 2000 and the major UK, European, Asian, Canadian, Brazilian and Indian indexes (see `scanner/universe.py`).
- **Three views of every stock:**
  - **Mispricing** (-100 to +100): valuation vs sector peers (P/E, EV/EBITDA, P/B, FCF yield), quality, the Street target gap and stretch vs the recent move, with a plain "why". With an Anthropic key, Claude writes a thesis with catalysts and risks from the numbers and headlines.
  - **Short-term** (0 to 100): 20-day average, 5 and 10 day momentum, RSI, volume. Three plain reasons per name.
  - **Swing** (0 to 100): 50 and 200-day averages, their slope, 3-month strength vs the S&P 500, distance from the 52-week high.
- **Labels:** every call is **Bullish**, **Bearish** or **Neutral**. (Older logs used BUY/SELL/WATCH; those still load and map to the new names.)
- **Funnel:** universe, stocks with data, passed data checks (history, freshness, liquidity), scored, picks.
- **Track record:** every Bullish or Bearish call is logged and graded vs SPY.

## How calls are graded
- **Entry is the next trading day's close** after the signal date, never the signal's own close. SPY uses the same entry day.
- **Windows are 5, 20 and 60 trading days** counted from that entry close.
- A Bullish call wins by beating SPY over the window, a Bearish call by lagging it. Neutral is never graded.
- **Still noise:** until the log covers 21 trading days the whole record is labeled "still noise".
- Rows logged before this rule (blank `entry_rule` in `data/picks.csv`) keep their original same-day entry, so history is not rewritten.

## Run it
```bash
pip install -r requirements.txt pytest
python run_scan.py                  # full scan, writes reports/<date>.md and data/latest_scan.json
python run_scan.py --max 150        # quick test run
python scripts/export_site.py       # data/latest_scan.json -> site/data/latest.json and track.json
python scripts/export_site.py --sample   # regenerate the labeled sample data (synthetic, no network)
streamlit run app.py                # optional analyst dashboard
python -m pytest -q                 # offline tests, no network
```
`ANTHROPIC_API_KEY` is optional. In GitHub Actions it is read from the repo secret `MARKET_TEAM_ANTHROPIC_API_KEY` (Settings, Secrets and variables, Actions) and only the scan step sees it. No other secrets are needed.

## The website
`site/` is plain static files (`index.html`, `style.css`, `app.js`, `data/*.json`) with no build step. Tabs: Mispricing, Short-term, Swing, plus a ticker lookup and the track record ring.

- **Vercel:** import the repo, set the output directory to `site`, no build command.
- **GitHub Pages:** publish the `site/` folder (Pages action, or a `gh-pages` branch from it).
- Preview locally: `python -m http.server -d site 8000`.

The committed `site/data/` is **Sample data** (synthetic prices, labeled with a banner) until the first real daily run overwrites it.

## Automation
`.github/workflows/daily-scan.yml` runs every weekday after the US close: scan, export site data, run tests, then commit `reports/`, `data/picks.csv`, `data/latest_scan.json` and `site/data/` (contents: write, no force push). Your host redeploys `site/` on each commit.

## Layout
`scanner/` engine: `data.py` (yfinance), `universe.py`, `valuation.py` (mispricing), `technical.py` (short-term and swing rules), `news_ai.py`, `tracker.py` (ledger and grading), `labels.py`, `pipeline.py`. `scripts/export_site.py` feeds `site/`.
