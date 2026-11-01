"""Audit 2026-11-01: one test per behavior fix (docs/audit-2026-11-01.md). Each failed on main before its fix."""
import json

import pandas as pd

from scanner import labels, pipeline, tracker
from tests.fixtures.synthetic import patch_engine
from tests.test_backend_1101 import ROW, _FakeClient, _msg


# MS-01: an AI reply that still uses advice words is dropped, so it never reaches picks.csv or the site
def test_ai_reply_with_advice_words_falls_back_to_rules(monkeypatch):
    from scanner import news_ai
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    for field, text in (("thesis", "A clear buy at these levels."), ("catalysts", "Analyst price target raised"),
                        ("risks", "Rating cut by a broker")):
        news_ai.start_run()
        reply = {"call": "Bullish", "confidence": 70, "thesis": "Cheap vs peers.", "catalysts": "earnings", "risks": "margins"}
        reply[field] = text
        assert news_ai.ai_call(ROW, [], client=_FakeClient(_msg(json.dumps(reply)))) is None, field
        assert news_ai.USAGE["errors"] == {"banned_words": 1} and news_ai.USAGE["ok"] == 0
    # analyze() then writes the pick with the rules model
    news_ai.start_run()
    bad = json.dumps({"call": "Bullish", "confidence": 70, "thesis": "Sell before earnings.", "catalysts": "", "risks": ""})
    out = news_ai.ai_call(ROW, [], client=_FakeClient(_msg(bad))) or news_ai.rule_based_call(ROW, 0.0)
    assert out["source"] == "rules" and not labels.BANNED.search(out["thesis"])


def test_ai_reply_that_is_not_an_object_is_bad_json(monkeypatch):
    from scanner import news_ai
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    news_ai.start_run()
    assert news_ai.ai_call(ROW, [], client=_FakeClient(_msg('["Bullish"]'))) is None
    assert news_ai.USAGE["errors"] == {"bad_json": 1}


# MS-02: both site exports use the same advice-word pattern (export_v5 missed rating and target)
def test_exports_share_one_banned_pattern():
    from scripts import export_site, export_v5
    assert export_site.BANNED is labels.BANNED and export_v5.BANNED is labels.BANNED
    for w in ("rating", "targets", "price target", "buy", "selling"):
        assert labels.BANNED.search(f"the {w} is"), w
    assert not labels.BANNED.search("buyback and Best Buyers")


# MS-03: a legacy row (same-day entry) with no price bars on or after its signal date used to raise IndexError,
# which took down the whole tracker stage, so the scan published no scorecard at all
def test_legacy_row_without_bars_after_signal_is_ungraded_not_a_crash():
    led = pd.DataFrame([
        {"date": pd.Timestamp("2026-10-30"), "ticker": "OLD", "call": "Bullish", "entry": 10.0, "bench_entry": 100.0,
         "entry_rule": "", "lens": "mispricing"},
        {"date": pd.Timestamp("2026-10-20"), "ticker": "NEW", "call": "Bullish", "entry": 10.0, "bench_entry": 100.0,
         "entry_rule": "", "lens": "mispricing"},
    ])
    old = pd.Series([10.0, 11.0], index=pd.to_datetime(["2026-10-27", "2026-10-28"]))
    days = pd.bdate_range("2026-10-20", periods=8)
    new = pd.Series([10.0 + i for i in range(8)], index=days)
    bench = pd.Series([100.0] * 8, index=days)
    ev = tracker.evaluate(led, {"OLD": old, "NEW": new}, bench)
    assert pd.isna(ev.loc[0, "ret_now"]) and pd.isna(ev.loc[0, "hit_5d"])
    assert abs(ev.loc[1, "ret_5d"] - 0.5) < 1e-9  # the other row is still graded


# MS-04: with a small eligible field the top and bottom lists overlap; a name must be analyzed and logged once
def test_mispricing_candidates_are_unique(tmp_path, monkeypatch):
    patch_engine(monkeypatch, tmp_path)
    res = pipeline.run(indexes=["Dow Jones"], live_constituents=False, top_n=40)
    mp = [p["ticker"] for p in res["picks"] if p["lens"] == "mispricing"]
    assert mp and len(mp) == len(set(mp))
    led = tracker.load()
    assert not led.duplicated(["date", "ticker", "lens"]).any()
