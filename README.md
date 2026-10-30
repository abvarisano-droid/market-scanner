# Market Scanner

A nightly scan of the S&P 500 that says Bullish, Neutral or Bearish for each stock on two horizons: Short-term (days) and Swing (1 to 3 months). Long-term comes later. It funnels about 500 names down to the 15 strongest bull and 15 strongest bear setups per horizon, and it grades its own published calls against the S&P 500 (SPY) every day.

**Not investment advice.** This is a research tool. Scores are mechanical rules on price and volume, not forecasts. The track record says "still noise" until there are 21 trading days of calls.

## How it works
1. `universe.py`: S&P 500 list from Wikipedia, cached to `data/universe.csv`.
2. `prices.py`: daily OHLCV from the Yahoo chart API (no key) into `data/prices/<TICKER>.csv`, with SPY. Retries with exponential backoff on 429 and 5xx.
3. `signals.py`: pure scoring rules, each 0 to 100 per horizon. Bullish at 65 or more, Bearish at 35 or less, else Neutral. Each result carries its top 3 reasons in plain English.
   - Short-term: price vs 20-day average (30%), 5 and 10-day momentum (30%), RSI(14) (20%), volume vs 20-day average, signed by the day's direction (20%).
   - Swing: price vs 50-day (20%) and 200-day (20%) averages, their one-month slopes (20%), 3-month return vs SPY (25%), distance from 52-week high (15%).
4. `scan.py`: runs the funnel (universe, passed data checks, scored, picks), writes `out/scan-YYYY-MM-DD.json` and `out/latest.json`. The file includes an `inputs_hash` of the price data used, so a scan can be reproduced.
5. `track.py`: logs each published pick to `data/calls.csv`, grades it vs SPY (Bullish wins by beating SPY, Bearish by lagging it; short-term window 10 trading days, swing 63), writes `out/track.json`.
6. `.github/workflows/nightly.yml`: weekdays 21:30 UTC, runs tests, fetch, scan, track, then commits `out/` and `data/`. No secrets needed.

## Run locally with synthetic data
```
pip install -r requirements.txt
python tests/fixtures/synthetic.py --dir /tmp/synth
python scan.py --data-dir /tmp/synth --out-dir /tmp/synth-out
python track.py --data-dir /tmp/synth --out-dir /tmp/synth-out
python -m pytest -q
```
Live data (`universe.py`, `prices.py`) is meant for GitHub Actions; Yahoo rate limits heavy use from many networks.

## Later
Long-term tab (SEC data), earnings revisions, the website (reads `out/latest.json` and `out/track.json`).
