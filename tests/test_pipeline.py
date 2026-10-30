"""Offline end-to-end test with fake market data. No network."""
import pandas as pd

from scanner import pipeline, tracker, universe
from tests.fixtures.synthetic import fake_prices, patch_engine


def test_run(tmp_path, monkeypatch):
    patch_engine(monkeypatch, tmp_path)
    res = pipeline.run(live_constituents=False)
    assert len(res["table"]) > 150 and len(res["indexes"]) == len(universe.INDEXES)
    assert {p["call"] for p in res["picks"]} <= {"Bullish", "Bearish", "Neutral"}
    assert all(p["thesis"] for p in res["picks"])
    assert (tmp_path / "reports" / "latest.md").exists()
    f = res["funnel"]
    for k in ("mispricing", "short_term", "swing"):
        assert f[k]["universe"] >= f[k]["with_data"] >= f[k]["passed_checks"] >= f[k]["scored"] >= 0
    assert sum(f["by_index"].values()) == f["mispricing"]["universe"]
    assert res["scorecard"]["status"] == "still noise"
    led = tracker.load()
    assert set(led["lens"]) == {"mispricing", "short_term", "swing"}
    # backdate calls 70 days and confirm the scorecard grades them on 5/20/60 windows
    led["date"] = pd.Timestamp("2026-07-01")
    led.to_csv(tracker.LEDGER, index=False)
    hist = {t: d["Close"] for t, d in fake_prices(list(led.ticker) + ["SPY"]).items()}
    ev = tracker.evaluate(tracker.load(), hist, hist["SPY"])
    sc = tracker.scorecard(ev, tracker.trading_days(tracker.load(), hist["SPY"]))
    assert 0 <= sc["hit_rate_60d"] <= 1 and sc["status"] == "enough days to read"
