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


def test_asof_is_latest_bar_across_markets_and_skips_relog(tmp_path, monkeypatch):
    from scanner import data
    from tests.fixtures.synthetic import make_prices, patch_engine
    patch_engine(monkeypatch, tmp_path)

    def prices_with_later_bar(tickers, period="1y", n=300):
        out = fake_prices(tickers, period, n)
        for t, df in out.items():
            if t == "SPY":
                continue
            extra = df.iloc[[-1]].copy()
            extra.index = extra.index + pd.Timedelta(days=1)  # a market with one bar after SPY's last date
            out[t] = pd.concat([df, extra])
            break
        return out

    monkeypatch.setattr(data, "prices", prices_with_later_bar)
    spy_last = pd.Timestamp(fake_prices(["SPY"])["SPY"].index[-1]).normalize()
    res = pipeline.run(live_constituents=False)
    assert pd.Timestamp(res["date"]) == spy_last + pd.Timedelta(days=1)
    import datetime as dt

    class Later(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 5)
    monkeypatch.setattr(pipeline, "date", Later)
    led0 = tracker.load()
    led0["thesis"] = "marker"
    led0.to_csv(tracker.LEDGER, index=False)
    n = len(led0)
    pipeline.run(live_constituents=False)  # same as-of date, earlier than today: not logged again
    assert len(tracker.load()) == n and set(tracker.load()["thesis"]) == {"marker"}  # untouched


def test_evaluate_aligns_benchmark_by_date_not_position():
    from scanner import tracker as tr
    idx = pd.bdate_range("2026-01-01", periods=60)
    st = pd.Series(100.0, index=idx)
    st.iloc[10:] = 110.0
    bench = pd.Series(100.0, index=idx.delete(5))  # benchmark missing one day: positions would shift by one
    bench[bench.index >= idx[11]] = 120.0
    led = pd.DataFrame([{"date": idx[2], "ticker": "AAA", "index": "x", "call": "Bullish", "confidence": 1, "entry": None,
                         "bench_entry": None, "mispricing": 1, "thesis": "", "source": "t", "lens": "mispricing",
                         "score": None, "entry_rule": "next_close"}])
    ev = tr.evaluate(led, {"AAA": st}, bench)
    # entry idx[3]; 5d window ends idx[8]: stock flat 0%, benchmark flat 0% on the same dates
    assert abs(ev["ret_5d"].iloc[0]) < 1e-12 and abs(ev["alpha_5d"].iloc[0]) < 1e-12
