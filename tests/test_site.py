import json, re
from pathlib import Path
SITE = Path(__file__).resolve().parent.parent / "site"
BAD = ("—", "–")


def test_site_data_keys_and_size():
    lat = json.loads((SITE / "data/latest.json").read_text())
    tr = json.loads((SITE / "data/track.json").read_text())
    assert {"asof", "funnel", "horizons", "lookup", "disclaimer", "sample"} <= set(lat)
    assert {"asof", "status", "trading_days", "min_days", "by_horizon", "graded", "pending"} <= set(tr)
    t, r = next(iter(lat["lookup"].items()))
    assert {"n", "c", "spark"} <= set(r) and len(r["spark"]) <= 60 and r["st"]["reasons"]
    assert (SITE / "data/latest.json").stat().st_size < 1_500_000
    assert "Not investment advice" in lat["disclaimer"]


def test_no_dashes_or_advice_words():
    for f in list(SITE.rglob("*.*")):
        txt = f.read_text()
        assert not any(c in txt for c in BAD), f
        if f.suffix in (".html", ".js", ".css"):
            assert not re.search(r"\b(buy|sell|price target)\b", txt, re.I), f
    assert "Not investment advice" in (SITE / "index.html").read_text()
