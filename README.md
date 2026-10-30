# market-scanner

An AI analyst for US and global markets. It scans the major indexes, finds stocks that look mispriced, explains why using the numbers and the news, makes a call, and then keeps score on whether it was right.

## What it does
- **Indexes:** S&P 500, Nasdaq 100, Dow, Russell 2000, FTSE, DAX, CAC, Euro Stoxx 50, Nikkei, Hang Seng, Shanghai, Sensex, ASX, TSX, Bovespa, KOSPI
- **Scans:** unusual volume, gaps, 52-week highs and lows, big moves, RSI extremes, sector rotation
- **Mispricing score (-100 to +100):** valuation vs sector peers (P/E, EV/EBITDA, P/B, FCF yield), quality, Street target gap, and stretch vs recent move
- **The why:** pulls recent headlines; with `ANTHROPIC_API_KEY` set, Claude writes a real thesis with catalysts and risks. Without a key, a rules model explains the call
- **Track record:** every BUY/SELL is logged and graded vs SPY at 5, 20 and 60 days

## Run it
```bash
pip install -r requirements.txt
python run_scan.py                 # full scan, writes reports/<date>.md
python run_scan.py --max 150       # quick test run
streamlit run app.py               # dashboard
```

Dashboard tabs: Indexes, Calls, Mispricing screener, Movers & Sectors, Track Record, Deep Dive (type any ticker).

## Automation
`.github/workflows/daily-scan.yml` runs every weekday after the US close and commits the report plus updated picks. Add `ANTHROPIC_API_KEY` under repo Settings, Secrets, Actions for AI write-ups.

## Notes
Data is from Yahoo Finance via yfinance (free, sometimes patchy for non-US fundamentals). Global picks are graded vs SPY in local currency for now. This is a research tool, not investment advice.
