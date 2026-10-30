"""Deterministic synthetic prices and fundamentals for tests and the sample site. No network."""
import argparse, hashlib, sys
from pathlib import Path
import numpy as np
import pandas as pd

END = "2026-10-30"


def _seed(ticker: str, seed: int) -> int:
    return int(hashlib.sha256(f"{ticker}:{seed}".encode()).hexdigest()[:8], 16)


def make_prices(ticker, n=300, seed=0, end=END, drift=None, vol=0.015) -> pd.DataFrame:
    rng = np.random.default_rng(_seed(ticker, seed))
    mu = rng.normal(0.0003, 0.0008) if drift is None else drift
    r = rng.normal(mu, vol, n)
    close = 100 * np.exp(np.cumsum(r))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    volume = (rng.lognormal(14, 0.4, n)).astype(int)
    dates = pd.bdate_range(end=end, periods=n).strftime("%Y-%m-%d")
    return pd.DataFrame({"date": dates, "open": open_.round(2), "high": high.round(2),
                         "low": low.round(2), "close": close.round(2), "volume": volume})


def trending(n=300, slope=0.004, end=END) -> pd.DataFrame:
    """Clean steady trend, for rule tests. slope is daily log return."""
    close = 100 * np.exp(slope * np.arange(n))
    dates = pd.bdate_range(end=end, periods=n).strftime("%Y-%m-%d")
    return pd.DataFrame({"date": dates, "open": close, "high": close * 1.002, "low": close * 0.998,
                         "close": close, "volume": np.full(n, 1_000_000)})


def write_all(dir_, n_tickers=60, n=300, seed=0):
    d = Path(dir_)
    (d / "prices").mkdir(parents=True, exist_ok=True)
    tickers = [f"SYN{i:03d}" for i in range(n_tickers)]
    pd.DataFrame({"ticker": tickers, "name": [f"Synthetic Co {i}" for i in range(n_tickers)],
                  "sector": [["Tech", "Health", "Energy", "Finance"][i % 4] for i in range(n_tickers)]}
                 ).to_csv(d / "universe.csv", index=False)
    for t in ["SPY"] + tickers:
        make_prices(t, n, seed, vol=0.008 if t == "SPY" else 0.015).to_csv(d / "prices" / f"{t}.csv", index=False)
    return tickers


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--tickers", type=int, default=120)
    a = ap.parse_args()
    write_all(a.dir, a.tickers)
    print("wrote", a.tickers, "synthetic tickers to", a.dir)


# ---- engine-shaped fakes (Title-case OHLCV, date index) ---------------------
def fake_prices(tickers, period="1y", n=300):
    out = {}
    for t in tickers:
        rng = np.random.default_rng(_seed(t, 11))
        idx = pd.bdate_range(end=END, periods=n)
        c = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, n)))
        out[t] = pd.DataFrame({"Open": c * 1.001, "High": c * 1.01, "Low": c * 0.99, "Close": c,
                               "Volume": rng.integers(1_000_000, 5_000_000, n).astype(float)}, index=idx)
    return out


def fake_fund(tickers):
    rng = np.random.default_rng(1)
    k = len(tickers)
    sectors = ["Technology", "Health Care", "Energy", "Financials"]
    return pd.DataFrame({
        "shortName": [f"{t} Corp" for t in tickers], "sector": [sectors[i % 4] for i in range(k)],
        "marketCap": rng.uniform(1e10, 1e12, k), "trailingPE": rng.uniform(5, 60, k),
        "forwardPE": rng.uniform(5, 50, k), "priceToBook": rng.uniform(0.5, 15, k),
        "enterpriseToEbitda": rng.uniform(4, 40, k), "freeCashflow": rng.uniform(-1e9, 5e10, k),
        "profitMargins": rng.uniform(-0.1, 0.4, k), "revenueGrowth": rng.uniform(-0.2, 0.5, k),
        "returnOnEquity": rng.uniform(-0.1, 0.5, k), "debtToEquity": rng.uniform(0, 300, k),
        "targetMeanPrice": rng.uniform(60, 180, k), "numberOfAnalystOpinions": rng.integers(0, 40, k),
        "recommendationMean": 2.0, "earningsGrowth": 0.1, "pegRatio": 1.5, "country": "US", "currency": "USD",
        "industry": "x", "currentPrice": 100, "shortPercentOfFloat": 0.02,
    }, index=tickers)


def fake_news(t, limit=8):
    return [{"title": f"{t} beats estimates, raises guidance", "summary": "", "publisher": "Wire", "link": "#"}]


def patch_engine(monkeypatch, tmp_path):
    """Point the engine at fake data and a temp folder. No network."""
    from scanner import data, pipeline, tracker
    monkeypatch.setattr(tracker, "LEDGER", tmp_path / "picks.csv")
    monkeypatch.setattr(pipeline, "LATEST", tmp_path / "latest_scan.json")
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(data, "prices", fake_prices)
    monkeypatch.setattr(data, "fundamentals", fake_fund)
    monkeypatch.setattr(data, "news", fake_news)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
