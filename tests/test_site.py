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


def test_track_page_shows_record_and_raw_log_link():
    js = (SITE / "app.js").read_text()
    assert "recordSection" in js and "Graded (n)" in js and "raw call log" in js and "still noise" in js
