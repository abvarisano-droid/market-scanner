import json
import re
from pathlib import Path

import pandas as pd

from scanner import tracker
from scripts import export_v5 as v5
from tests.test_tracker import ledger, series

ROOT = Path(__file__).resolve().parent.parent


def rows(*specs):
    return pd.DataFrame([{"date": d, "ticker": t, "lens": l, "call": c, "score": 10.0, "mispricing": None,
                          "index": "x"} for d, t, l, c in specs])


def prep(df):
    return v5._ledger({"ledger": df.to_dict("records")})


def test_diff_one_date_is_empty_state():
    c = v5.diff_calls(prep(rows(("2026-10-30", "AAA", "swing", "Bullish"))))
    assert c["empty"] and c["new"] == [] and c["flipped"] == [] and c["date"] == "2026-10-30"


def test_diff_new_and_flipped():
    led = prep(rows(("2026-10-29", "AAA", "swing", "Bullish"), ("2026-10-29", "BBB", "swing", "Bearish"),
                    ("2026-10-29", "CCC", "swing", "Bullish"),
                    ("2026-10-30", "AAA", "swing", "Bearish"),   # flipped
                    ("2026-10-30", "BBB", "swing", "Bearish"),   # unchanged
                    ("2026-10-30", "DDD", "swing", "Bullish"),   # new
                    ("2026-10-30", "AAA", "short_term", "Bullish")))  # new lens for AAA
    c = v5.diff_calls(led)
    assert not c["empty"] and c["previous"] == "2026-10-29"
    assert c["flipped"] == [{"ticker": "AAA", "lens": "swing", "from": "Bullish", "to": "Bearish"}]
    assert {(x["ticker"], x["lens"]) for x in c["new"]} == {("DDD", "swing"), ("AAA", "short_term")}


def test_report_card_matches_tracker_grading():
    st, spy = series(0.01), series(0.0)
    parts = [ledger("Bullish", st.index[-30], ticker="AAA"), ledger("Bearish", st.index[-30], ticker="AAA", lens="swing"),
             ledger("Bullish", st.index[-70], ticker="AAA")]
    ev = tracker.evaluate(pd.concat(parts, ignore_index=True), {"AAA": st}, spy)
    rc = v5.report_card(ev, 25)
    sc = tracker.scorecard(ev, 25)
    m = rc["lenses"]["mispricing"]["windows"]
    assert m["5"]["graded"] == sc["by_lens"]["mispricing"]["n_5d"] == 2
    assert m["5"]["hit_rate_pct"] == round(100 * sc["by_lens"]["mispricing"]["hit_rate_5d"], 1)
    assert m["20"]["avg_excess_pct"] == round(100 * sc["by_lens"]["mispricing"]["avg_alpha_20d"], 2)
    sw = rc["lenses"]["swing"]["windows"]["5"]
    assert sw["hit_rate_pct"] == 0.0 and sw["avg_excess_pct"] < 0  # Bearish on a riser loses
    assert rc["lenses"]["short_term"]["windows"]["5"]["graded"] == 0
    assert not rc["still_noise"] and v5.report_card(ev, 20)["still_noise"]


def test_stock_pages_only_for_called_tickers():
    led = prep(rows(("2026-10-30", "AAA", "swing", "Bullish")))
    look = {"AAA": {"n": "Alpha", "i": "x", "s": "Tech", "sw": {"label": "Bullish", "score": 5, "reasons": ["Price is up"]}},
            "ZZZ": {"n": "Zed", "sw": {"label": "Neutral", "score": 1, "reasons": []}}}
    pages = v5.stock_pages(led, look)
    assert set(pages) == {"AAA"} and pages["AAA"]["graded"] == []


def test_committed_v5_json():
    d = json.loads((ROOT / "site/data/v5.json").read_text())
    called = {t for t in pd.read_csv(ROOT / "data/picks.csv")["ticker"]}
    assert set(d["stocks"]) == called
    assert "Not investment advice" in d["disclaimer"]
    txt = json.dumps(d, ensure_ascii=False)
    assert "—" not in txt and "–" not in txt and not v5.BANNED.search(txt)
    assert d["report"]["still_noise"] == (d["report"]["trading_days"] < 21)
