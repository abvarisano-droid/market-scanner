from pathlib import Path

import pandas as pd

from scanner import tracker
from tests.fixtures.synthetic import trending


def series(slope, n=80):
    df = trending(n, slope)
    return pd.Series(df["close"].to_numpy(), index=pd.DatetimeIndex(df["date"]))


def ledger(call, date, rule="next_close", entry=None, bench_entry=None, ticker="AAA", lens="mispricing"):
    return pd.DataFrame([{"date": pd.Timestamp(date), "ticker": ticker, "index": "x", "call": call, "confidence": 1,
                          "entry": entry, "bench_entry": bench_entry, "mispricing": 10, "thesis": "", "source": "t",
                          "lens": lens, "score": None, "entry_rule": rule}])


def test_entry_is_next_trading_day_close():
    st, spy = series(0.01), series(0.0)
    d0 = st.index[-30]
    ev = tracker.evaluate(ledger("Bullish", d0), {"AAA": st}, spy)
    entry = st.iloc[-29]  # next bar, not the signal bar
    assert abs(ev["ret_5d"].iloc[0] - (st.iloc[-29 + 5] / entry - 1)) < 1e-12
    assert ev["hit_5d"].iloc[0] and ev["hit_20d"].iloc[0] and ev["hit_60d"].iloc[0] is None


def test_bearish_sign_and_pending():
    st, spy = series(0.01), series(0.0)
    ev = tracker.evaluate(ledger("Bearish", st.index[-30]), {"AAA": st}, spy)
    assert ev["alpha_5d"].iloc[0] < 0 and not ev["hit_5d"].iloc[0]
    last = tracker.evaluate(ledger("Bullish", st.index[-1]), {"AAA": st}, spy)
    assert last["ret_now"].iloc[0] is None and last["hit_5d"].iloc[0] is None


def test_legacy_rows_keep_same_day_entry():
    st, spy = series(0.01), series(0.0)
    d0 = st.index[-30]
    ev = tracker.evaluate(ledger("Bullish", d0, rule="", entry=st.loc[d0], bench_entry=spy.loc[d0]), {"AAA": st}, spy)
    assert abs(ev["ret_5d"].iloc[0] - (st.iloc[-30 + 5] / st.loc[d0] - 1)) < 1e-12


def test_still_noise_threshold():
    st, spy = series(0.01), series(0.0)
    led = ledger("Bullish", st.index[-61])
    ev = tracker.evaluate(led, {"AAA": st}, spy)
    assert tracker.trading_days(led, spy) == 60  # bars strictly after the signal date
    assert tracker.scorecard(ev, 59)["status"] == "still noise"
    assert tracker.scorecard(ev, 60)["status"] == "enough days to read"
    assert "noise" in tracker.scorecard(ev, 3)["note"]


def test_log_picks_dedupes_and_skips_neutral(tmp_path, monkeypatch):
    monkeypatch.setattr(tracker, "LEDGER", tmp_path / "p.csv")
    picks = [{"ticker": "A", "call": "BUY", "price": 1.0}, {"ticker": "B", "call": "Neutral", "price": 1.0},
             {"ticker": "A", "call": "Bullish", "price": 1.0, "lens": "swing"}]
    tracker.log_picks(picks, 400.0, today="2026-10-30")
    led = tracker.log_picks(picks, 400.0, today="2026-10-30")
    assert len(led) == 2 and set(led["call"]) == {"Bullish"} and set(led["entry_rule"]) == {"next_close"}


def test_scorecard_by_lens():
    st, spy = series(0.01), series(0.0)
    led = pd.concat([ledger("Bullish", st.index[-30]), ledger("Bullish", st.index[-30], lens="swing")], ignore_index=True)
    sc = tracker.scorecard(tracker.evaluate(led, {"AAA": st}, spy), 30)
    assert sc["by_lens"]["swing"]["calls"] == 1 and sc["by_lens"]["short_term"]["calls"] == 0
    assert sc["hit_rate_5d"] == 1.0


def test_later_run_cannot_replace_earlier_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(tracker, "LEDGER", tmp_path / "p.csv")
    first = [{"ticker": "A", "call": "Bullish", "price": 1.0, "thesis": "original"}]
    tracker.log_picks(first, 400.0, today="2026-10-30", run_id="run1")
    # same run rewrites its own rows
    led = tracker.log_picks([{"ticker": "A", "call": "Bullish", "price": 1.0, "thesis": "rewrite"}], 400.0,
                            today="2026-10-30", run_id="run1")
    assert list(led["thesis"]) == ["rewrite"]
    # a later run (or one with no id) cannot replace it, but can add new tickers
    later = [{"ticker": "A", "call": "Bearish", "price": 9.0, "thesis": "changed"},
             {"ticker": "B", "call": "Bullish", "price": 2.0}]
    led = tracker.log_picks(later, 400.0, today="2026-10-30", run_id="run2")
    a = led[led.ticker == "A"]
    assert len(a) == 1 and a.iloc[0]["thesis"] == "rewrite" and a.iloc[0]["call"] == "Bullish" and len(led) == 2
    assert len(tracker.log_picks(later, 400.0, today="2026-10-30")) == 2
    # legacy rows with no run_id are never replaced
    p = tmp_path / "p.csv"
    old = tracker.load().drop(columns=["run_id"])
    old.to_csv(p, index=False)
    led = tracker.log_picks(first, 400.0, today="2026-10-30", run_id="run3")
    assert len(led) == 2 and led[led.ticker == "A"].iloc[0]["thesis"] == "rewrite"


def test_site_points_to_full_ledger_and_says_300_shown():
    js = (Path(__file__).resolve().parent.parent / "site" / "app.js").read_text()
    assert "github.com/abvarisano-droid/market-scanner/blob/main/data/picks.csv" in js and "latest 300 graded" in js


def test_trading_days_strictly_after_first_signal_and_singular():
    spy = series(0.0)
    assert tracker.trading_days(ledger("Bullish", spy.index[-1]), spy) == 0
    led = ledger("Bullish", spy.index[-2])
    assert tracker.trading_days(led, spy) == 1
    note = tracker.scorecard(tracker.evaluate(led, {"AAA": series(0.01)}, spy), 1)["note"]
    assert "1 trading day " in note and "1 trading days" not in note


def test_readme_does_not_call_committed_data_sample():
    txt = (Path(__file__).resolve().parent.parent / "README.md").read_text()
    assert "is **Sample data**" not in txt and "Street target" not in txt
