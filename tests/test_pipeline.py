"""Offline end-to-end test with fake market data."""
import numpy as np
import pandas as pd

from scanner import data, pipeline, tracker, universe


def fake_prices(tickers, period="1y"):
    out = {}
    for i, t in enumerate(tickers):
        rng = np.random.default_rng(abs(hash(t)) % 2**32)
        idx = pd.bdate_range(end="2026-10-30", periods=300)
        c = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, 300)))
        out[t] = pd.DataFrame({"Open": c * 1.001, "High": c * 1.01, "Low": c * 0.99, "Close": c,
                               "Volume": rng.integers(1e6, 5e6, 300).astype(float)}, index=idx)
    return out


def fake_fund(tickers):
    rng = np.random.default_rng(1)
    sectors = ["Tech", "Health", "Energy", "Financials"]
    return pd.DataFrame({
        "shortName": tickers, "sector": [sectors[i % 4] for i in range(len(tickers))],
        "marketCap": rng.uniform(1e10, 1e12, len(tickers)), "trailingPE": rng.uniform(5, 60, len(tickers)),
        "forwardPE": rng.uniform(5, 50, len(tickers)), "priceToBook": rng.uniform(0.5, 15, len(tickers)),
        "enterpriseToEbitda": rng.uniform(4, 40, len(tickers)), "freeCashflow": rng.uniform(-1e9, 5e10, len(tickers)),
        "profitMargins": rng.uniform(-0.1, 0.4, len(tickers)), "revenueGrowth": rng.uniform(-0.2, 0.5, len(tickers)),
        "returnOnEquity": rng.uniform(-0.1, 0.5, len(tickers)), "debtToEquity": rng.uniform(0, 300, len(tickers)),
        "targetMeanPrice": rng.uniform(60, 180, len(tickers)), "numberOfAnalystOpinions": rng.integers(0, 40, len(tickers)),
        "recommendationMean": 2.0, "earningsGrowth": 0.1, "pegRatio": 1.5, "country": "US", "currency": "USD",
        "industry": "x", "currentPrice": 100, "shortPercentOfFloat": 0.02,
    }, index=tickers)


def test_run(tmp_path, monkeypatch):
    monkeypatch.setattr(tracker, "LEDGER", tmp_path / "picks.csv")
    monkeypatch.setattr(pipeline, "LATEST", tmp_path / "latest.json")
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    monkeypatch.setattr(data, "prices", fake_prices)
    monkeypatch.setattr(data, "fundamentals", fake_fund)
    monkeypatch.setattr(data, "news", lambda t, limit=8: [{"title": f"{t} beats estimates, raises guidance",
                                                          "summary": "", "publisher": "X", "link": "#"}])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = pipeline.run(live_constituents=False)
    assert len(res["table"]) > 150 and len(res["indexes"]) == len(universe.INDEXES)
    assert {p["call"] for p in res["picks"]} <= {"BUY", "SELL", "WATCH"}
    assert all(p["thesis"] for p in res["picks"])
    assert (tmp_path / "reports" / "latest.md").exists()
    # backdate picks 70 days and confirm the scorecard grades them
    led = tracker.load(); led["date"] = pd.Timestamp("2026-07-01"); led.to_csv(tracker.LEDGER, index=False)
    hist = {t: d["Close"] for t, d in fake_prices(list(led.ticker) + ["SPY"]).items()}
    ev = tracker.evaluate(tracker.load(), hist, hist["SPY"])
    sc = tracker.scorecard(ev)
    assert "hit_rate_60d" in sc and 0 <= sc["hit_rate_60d"] <= 1
    print(sc, res["picks"][0]["ticker"], res["picks"][0]["call"], res["picks"][0]["thesis"])
