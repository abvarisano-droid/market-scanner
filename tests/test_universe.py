"""Russell 2000 constituents: parser, cache and multi-index tags. No network."""
from pathlib import Path

import pytest

from scanner import universe

FIX = Path(__file__).resolve().parent / "fixtures" / "iwm_holdings_sample.csv"


def test_parse_keeps_us_equities_only():
    asof, rows = universe.parse_ishares_holdings(FIX.read_text())
    assert asof == "2026-10-29"
    assert [r["ticker"] for r in rows] == ["ABCD", "BF-B", "IJKL"]  # dots to dashes, deduped, no cash/futures/non-US


def test_parse_rejects_html():
    with pytest.raises(ValueError):
        universe.parse_ishares_holdings("<!DOCTYPE html><html><body>sign in</body></html>")


def test_cache_roundtrip(tmp_path):
    asof, rows = universe.parse_ishares_holdings(FIX.read_text())
    p = tmp_path / "russell2000.csv"
    universe.write_russell_cache(asof, rows, p)
    assert universe.read_russell_cache(p) == ("2026-10-29", ["ABCD", "BF-B", "IJKL"])
    assert universe.read_russell_cache(tmp_path / "missing.csv") == ("", [])


def test_failed_fetch_keeps_cache(tmp_path, monkeypatch):
    p = tmp_path / "russell2000.csv"
    universe.write_russell_cache("2026-10-29", [{"ticker": "ABCD", "name": "", "sector": "", "weight": ""}], p)
    monkeypatch.setattr(universe, "RUSSELL_CACHE", p)

    class Resp:
        text = FIX.read_text()  # valid file but far too small to trust

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp())
    assert universe.russell_constituents(live=True) == ["ABCD"]  # fell back to the cache
    assert universe.read_russell_cache(p)[0] == "2026-10-29"


def test_overlap_keeps_both_tags(tmp_path, monkeypatch):
    p = tmp_path / "russell2000.csv"
    universe.write_russell_cache("2026-10-29", [{"ticker": t, "name": "", "sector": "", "weight": ""} for t in ("AAPL", "ABCD")], p)
    monkeypatch.setattr(universe, "RUSSELL_CACHE", p)
    tags = universe.universe_tags(["S&P 500", "Russell 2000"], live=False)
    assert tags["AAPL"] == ["S&P 500", "Russell 2000"] and tags["ABCD"] == ["Russell 2000"]
    assert universe.full_universe(["S&P 500", "Russell 2000"], live=False)["AAPL"] == "S&P 500"
