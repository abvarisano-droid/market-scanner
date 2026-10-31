import json
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
BAD = ("—", "–")


def test_committed_site_data_keys_and_label():
    lat = json.loads((SITE / "data/latest.json").read_text())
    tr = json.loads((SITE / "data/track.json").read_text())
    assert {"asof", "funnel", "horizons", "lookup", "disclaimer", "sample", "indexes"} <= set(lat)
    assert {"asof", "status", "trading_days", "min_days", "by_lens", "graded", "pending"} <= set(tr)
    if lat["sample"]:
        assert lat["banner"].startswith("Sample data") and tr["banner"].startswith("Sample data")
    t, r = next(iter(lat["lookup"].items()))
    assert {"n", "c", "spark"} <= set(r) and len(r["spark"]) <= 60 and r["st"]["reasons"]
    # Limit raised from 1.5MB: the Russell 2000 adds ~1,800 lookup rows (~1KB each, ~2.5MB real). Hosts serve gzip (~4x smaller).
    assert (SITE / "data/latest.json").stat().st_size < 3_000_000
    assert "Not investment advice" in lat["disclaimer"]


def test_no_dashes_or_advice_words():
    for f in (p for p in SITE.rglob("*.*") if p.suffix != ".png"):
        txt = f.read_text()
        assert not any(c in txt for c in BAD), f
        if f.suffix in (".html", ".js", ".css"):
            assert not re.search(r"\b(buy|sell|price target)\b", txt, re.I), f
    assert "Not investment advice" in (SITE / "index.html").read_text()
    assert all(t in (SITE / "app.js").read_text() for t in ("Mispricing", "Short-term", "Swing"))


def test_bearish_score_uses_bear_color():
    assert ".hz .big.neg{color:var(--bear)}" in (SITE / "style.css").read_text()


def test_app_js_handles_null_close_and_index_change():
    js = (SITE / "app.js").read_text()
    assert 'r.c == null ? "n/a"' in js  # lookup with a null last close shows n/a
    assert "i.chg_1d == null" in js and 'return "n/a"' in js  # index chip with no 1d change is neutral n/a
    assert "view failed" in js  # one view failing must not blank the whole app


def test_lookup_close_falls_back_to_sparkline_and_exports_currency():
    from scripts.export_site import build_latest
    scan = {"date": "2026-10-30", "funnel": {"dropped": {}}, "indexes": [], "picks": [], "sectors": [],
            "table": [{"ticker": "AAA", "price": float("nan"), "currency": "INR", "shortName": "A", "sector": "X",
                       "index": "i", "mispricing": 5}],
            "technical": {"spark": {"AAA": [1.0, 2.0, 3.5]}, "scores": {"short_term": {}, "swing": {}},
                          "horizons": {k: {"counts": {}, "top_bull": [], "top_bear": []} for k in ("short_term", "swing")}}}
    row = build_latest(scan, False)["lookup"]["AAA"]
    assert row["c"] == 3.5 and row["cur"] == "INR"


def test_wording_extras():
    js = (SITE / "app.js").read_text()
    assert "local currency returns" in js and "Street" not in js
    assert "Graded results are illustrative only" in __import__("scripts.export_site", fromlist=["x"]).SAMPLE_NOTE
    root = SITE.parent
    assert "target_return" not in (root / "scanner/news_ai.py").read_text()
    assert "4:30pm ET" in (root / ".github/workflows/daily-scan.yml").read_text()


def test_how_it_works_matches_code_constants():
    from scanner import pipeline, tracker, technical as tc, valuation
    from scripts.export_site import BULL_AT, build_method
    m = json.loads((SITE / "data/method.json").read_text())
    assert m == build_method()  # committed page data equals what the code produces
    t, f, g = m["technical"], m["funnel"], m["grading"]
    assert (t["bull_at"], t["bear_at"], t["min_short"], t["min_swing"]) == (tc.BULL, tc.BEAR, tc.MIN_SHORT, tc.MIN_SWING)
    assert (f["min_bars"], f["stale_days"], f["min_dollar_vol"], f["top_n"]) == (tc.MIN_BARS, tc.STALE_DAYS, tc.MIN_DOLLAR_VOL, tc.TOP_N)
    assert f["min_coverage_pct"] == round(pipeline.MIN_COVERAGE * 100)
    assert g["windows"] == list(tracker.HORIZONS.values()) and g["min_days"] == tracker.MIN_DAYS
    assert m["mispricing"]["call_at"] == BULL_AT
    assert m["mispricing"]["weights_pct"] == {k: round(v * 100) for k, v in valuation.WEIGHTS.items()}
    assert sum(m["mispricing"]["weights_pct"].values()) == 100
    assert sum(t["short_weights_pct"].values()) == 100 and sum(t["swing_weights_pct"].values()) == 100
    js, html = (SITE / "app.js").read_text(), (SITE / "index.html").read_text()
    assert 'data-nav="how"' in html and "How it works" in html
    assert "methodology()" in js and "Not investment advice" in js and "still noise" in js
    for k in ("bull_at", "bear_at", "min_dollar_vol", "call_at", "windows", "min_days"):
        assert "." + k in js  # the page reads these values rather than hardcoding them
