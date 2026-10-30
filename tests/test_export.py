import json

from scripts import export_site as ex
from scanner import pipeline
from tests.fixtures.synthetic import patch_engine


def test_export_schema(tmp_path, monkeypatch):
    patch_engine(monkeypatch, tmp_path)
    scan = pipeline.run(live_constituents=False)
    lat, tr = ex.export(scan, tmp_path / "site", sample=False)
    assert lat["sample"] is False and lat["banner"] == ""
    assert {"asof", "funnel", "horizons", "lookup", "indexes", "disclaimer", "spy_spark"} <= set(lat)
    assert set(lat["horizons"]) == {"mispricing", "short_term", "swing"}
    for hz, h in lat["horizons"].items():
        assert set(h) == {"counts", "top_bull", "top_bear"}
        for r in h["top_bull"] + h["top_bear"]:
            assert {"ticker", "name", "score", "bar", "label", "reasons"} <= set(r)
            assert r["label"] in ("Bullish", "Bearish") and 0 <= r["bar"] <= 100
    assert all(r["label"] == "Bullish" for r in lat["horizons"]["mispricing"]["top_bull"])
    mp = lat["horizons"]["mispricing"]["top_bull"]
    assert [r["score"] for r in mp] == sorted((r["score"] for r in mp), reverse=True)
    for k in ("mispricing", "short_term", "swing"):
        assert {"universe", "with_data", "passed_checks", "scored", "picks"} <= set(lat["funnel"][k])
    t, row = next(iter(lat["lookup"].items()))
    assert {"n", "c", "spark", "mp", "st", "sw"} <= set(row) and len(row["spark"]) <= 60
    assert {"asof", "status", "trading_days", "min_days", "by_lens", "graded", "pending", "calls_logged",
            "entry_rule", "windows"} <= set(tr)
    assert tr["status"] == "still noise" and tr["windows"] == [5, 20, 60]
    assert set(tr["by_lens"]) == {"mispricing", "short_term", "swing"}
    assert json.loads((tmp_path / "site/data/latest.json").read_text())["asof"] == lat["asof"]


def test_sample_is_labeled(tmp_path):
    scan = ex.make_sample(tmp_path)
    lat, tr = ex.export(scan, tmp_path / "site", sample=True)
    assert lat["sample"] and lat["banner"].startswith("Sample data") and tr["banner"].startswith("Sample data")
    assert tr["graded"], "sample track record should have graded rows"
    assert all(g["label"] in ("Bullish", "Bearish") for g in tr["graded"])


def test_scrub_dashes_and_advice_words():
    assert ex.plain("a — b – c") == "a - b - c"
    assert ex.BANNED.search("a Buy rating") and ex.BANNED.search("price target") and not ex.BANNED.search("buyback")
