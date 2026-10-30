"""Daily OHLCV fetcher (Yahoo chart API). Built for the nightly GitHub Actions run.

Not meant to be run in bulk from a restricted network: Yahoo rate limits (HTTP 429) hard.
"""
import argparse, json, sys, time, urllib.error, urllib.request
from pathlib import Path
import pandas as pd

API = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?range={rng}&interval=1d&events=history"
COLS = ["date", "open", "high", "low", "close", "volume"]


def parse_chart(payload: dict) -> pd.DataFrame:
    res = payload["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
    close = adj if adj else q["close"]
    df = pd.DataFrame({
        "date": pd.to_datetime(res["timestamp"], unit="s").normalize(),
        "open": q["open"], "high": q["high"], "low": q["low"], "close": close, "volume": q["volume"],
    }).dropna(subset=["close"])
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df[COLS].drop_duplicates("date").reset_index(drop=True)


def fetch_one(ticker: str, rng="2y", retries=5, base_delay=2.0) -> pd.DataFrame:
    url = API.format(t=ticker, rng=rng)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (market-scanner)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return parse_chart(json.load(r))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(base_delay * 2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(base_delay * 2 ** attempt)
                continue
            raise


def load_prices(data_dir, ticker):
    p = Path(data_dir) / "prices" / f"{ticker}.csv"
    return pd.read_csv(p) if p.exists() else None


def fetch_all(tickers, data_dir="data", pause=0.25):
    out = Path(data_dir) / "prices"
    out.mkdir(parents=True, exist_ok=True)
    ok, failed = 0, []
    for t in tickers:
        try:
            fetch_one(t).to_csv(out / f"{t}.csv", index=False)
            ok += 1
        except Exception as e:  # keep going; scan reports failures in the funnel
            failed.append(t)
            print(f"fail {t}: {e}", file=sys.stderr)
        time.sleep(pause)
    return ok, failed


if __name__ == "__main__":
    from universe import load_universe
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    tickers = ["SPY"] + list(load_universe(f"{a.data_dir}/universe.csv")["ticker"])
    if a.limit:
        tickers = tickers[: a.limit]
    ok, failed = fetch_all(tickers, a.data_dir)
    print(f"fetched {ok}, failed {len(failed)}")
    if ok == 0:
        sys.exit(1)
