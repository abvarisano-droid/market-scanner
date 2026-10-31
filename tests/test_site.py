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
    assert (SITE / "data/latest.json").stat().st_size < 1_500_000
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
