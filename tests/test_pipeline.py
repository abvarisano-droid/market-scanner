"""Offline end-to-end test with fake market data. No network."""
import json
import pandas as pd

from scanner import pipeline, tracker, universe
from tests.fixtures.synthetic import fake_prices, patch_engine


def test_run(tmp_path, monkeypatch):
    patch_engine(monkeypatch, tmp_path)
    rows = [{"ticker": t, "name": "", "sector": "", "weight": ""} for t in ["AAPL"] + [f"RUT{i:03d}" for i in range(40)]]
    universe.write_russell_cache("2026-10-29", rows, tmp_path / "r.csv")
    monkeypatch.setattr(universe, "RUSSELL_CACHE", tmp_path / "r.csv")
    res = pipeline.run(live_constituents=False)
    assert len(res["table"]) > 150 and len(res["indexes"]) == len(universe.INDEXES)
    assert {p["call"] for p in res["picks"]} <= {"Bullish", "Bearish", "Neutral"}
    assert all(p["thesis"] for p in res["picks"])
    assert (tmp_path / "reports" / "latest.md").exists()
    ch = json.loads((tmp_path / "data" / "charts.json").read_text())  # candles for every called ticker
    assert set(ch) == {r["ticker"] for r in res["ledger"]} and all(c["fan"] for c in ch.values())
    f = res["funnel"]
    for k in ("mispricing", "short_term", "swing"):
        assert f[k]["universe"] >= f[k]["with_data"] >= f[k]["passed_checks"] >= f[k]["scored"] >= 0
    # Russell 2000 is scanned; AAPL is in both S&P 500 and Russell (here) so it keeps both tags
    assert f["by_index"]["Russell 2000"] == 41 and f["by_index_stages"]["passed_checks"]["Russell 2000"] <= 41
    assert sum(f["by_index"].values()) > f["mispricing"]["universe"]  # overlaps count in every index
    assert next(r for r in res["table"] if r["ticker"] == "AAPL")["indexes"][0] == "S&P 500" and "Russell 2000" in next(r for r in res["table"] if r["ticker"] == "AAPL")["indexes"]
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


def test_scan_survives_stage_failures(tmp_path, monkeypatch):
    """A bad ticker, a failing news step, tracker and report must be logged and skipped, never kill the run."""
    import numpy as np
    from scanner import data, news_ai
    from tests.fixtures.synthetic import patch_engine
    patch_engine(monkeypatch, tmp_path)

    def nan_tail_prices(tickers, period="1y", n=300):
        out = fake_prices(tickers, period, n)
        for t in list(out)[:15]:
            if t != "SPY":
                out[t] = out[t].copy()
                out[t].iloc[-1, :] = np.nan  # partial final bar: NaN close and volume
        return out

    monkeypatch.setattr(data, "prices", nan_tail_prices)
    monkeypatch.setattr(news_ai, "analyze", lambda row, h: (_ for _ in ()).throw(RuntimeError("api down")))
    monkeypatch.setattr(tracker, "evaluate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(pipeline, "write_report", lambda res: (_ for _ in ()).throw(RuntimeError("fmt")))
    res = pipeline.run(live_constituents=False)
    assert res["picks"] and all(p["thesis"] for p in res["picks"])
    assert res["scorecard"]["status"] == "still noise" and res["ledger"] == []
    assert (tmp_path / "latest_scan.json").exists()


def test_report_handles_missing_numbers(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    res = {"date": "2026-10-30", "indexes": [{"name": "X", "level": None, "chg_1d": None, "chg_1m": None,
                                              "chg_3m": None, "pct_from_high": None}],
           "picks": [{"ticker": "A", "call": "Bullish", "mispricing": None, "price": None}],
           "technical": {"horizons": {"short_term": {"top_bull": [], "top_bear": []},
                                      "swing": {"top_bull": [], "top_bear": []}}},
           "movers": [], "scorecard": {}}
    assert pipeline.write_report(res).exists()
