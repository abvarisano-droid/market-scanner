"""Merger arb desk: spread math, deal file checks, the refresh script, the EDGAR helpers and the page."""
import copy
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from scanner import arb
from scanner import watchdog as w
from scripts import fetch_deals as fd
from scripts import refresh_arb as ra

ROOT = Path(__file__).resolve().parent.parent
BOOK = json.loads((ROOT / "data/arb/deals.json").read_text())
TODAY = date(2026, 11, 3)


# ---------- math ----------
def test_cash_deal():
    o = arb.offer_value(50.0, None, None)
    assert o == 50.0
    s = arb.gross_spread(48.0, o)
    assert s == pytest.approx(2 / 48)
    assert arb.annualized_spread(s, 73) == pytest.approx(2 / 48 * 5)
    assert arb.implied_close_chance(48.0, o, 40.0) == pytest.approx(0.8)


def test_stock_deal_uses_acquirer_price():
    assert arb.offer_value(None, 0.5, 80.0) == 40.0
    assert arb.offer_value(None, 0.5, None) is None  # stock leg without a price is unknown, not zero
    assert arb.gross_spread(38.0, arb.offer_value(None, 0.5, 80.0)) == pytest.approx(2 / 38)


def test_mixed_deal():
    assert arb.offer_value(10.0, 0.25, 100.0) == 35.0
    assert arb.offer_value(10.0, 0.25, None) is None


def test_nothing_known_is_none():
    assert arb.offer_value(None, None, 100.0) is None
    assert arb.gross_spread(None, 10.0) is None and arb.gross_spread(10.0, None) is None
    assert arb.gross_spread(0.0, 10.0) is None


def test_negative_spread():
    s = arb.gross_spread(52.0, 50.0)
    assert s < 0 and s == pytest.approx(-2 / 52)
    assert arb.annualized_spread(s, 365) == pytest.approx(s)


def test_unknown_or_past_close_date():
    assert arb.days_to_close(None, TODAY) is None
    assert arb.annualized_spread(0.02, None) is None
    assert arb.days_to_close("2026-11-01", TODAY) == -2
    assert arb.annualized_spread(0.02, -2) is None and arb.annualized_spread(0.02, 0) is None
    assert arb.days_to_close("2027-03-31", TODAY) == 148


def test_implied_chance_clipped_and_undefined():
    assert arb.implied_close_chance(55.0, 50.0, 40.0) == 1.0  # above the offer
    assert arb.implied_close_chance(35.0, 50.0, 40.0) == 0.0  # below unaffected
    assert arb.implied_close_chance(45.0, 40.0, 40.0) is None  # offer == unaffected
    assert arb.implied_close_chance(45.0, None, 40.0) is None and arb.implied_close_chance(45.0, 50.0, None) is None


def test_compute_row():
    d = copy.deepcopy(next(x for x in BOOK["deals"] if x["id"] == "CSR"))
    r = arb.compute(d, 55.0, 15.0, TODAY)
    assert r["kind"] == "stock" and r["offer_value"] == pytest.approx(57.0)
    assert r["spread_usd"] == pytest.approx(2.0) and r["days_to_close"] == 58
    assert r["open_steps"] == sum(s["status"] == "open" for s in d["steps"])


# ---------- validation ----------
def test_missing_source_fails_validation():
    d = copy.deepcopy(BOOK["deals"][0])
    assert arb.validate_deal(d) == []
    del d["cash_per_share"]["source_url"]
    d["announce_date"]["as_of"] = "Nov 3"
    d["steps"][0]["verified"] = "yes"
    errs = arb.validate_deal(d)
    assert any("cash_per_share: source_url" in e for e in errs)
    assert any("announce_date: as_of" in e for e in errs)
    assert any("steps[0]: verified" in e for e in errs)


def test_unverified_needs_note_and_terms_needed():
    d = copy.deepcopy(BOOK["deals"][0])
    d["target"]["verified"] = False
    d["target"].pop("note", None)
    d["cash_per_share"]["value"] = None
    d["exchange_ratio"]["value"] = None
    errs = arb.validate_deal(d)
    assert any("target: unverified facts need a note" in e for e in errs)
    assert any("needs cash_per_share or exchange_ratio" in e for e in errs)


def test_every_deal_has_source_as_of_verified_on_every_term():
    deals = BOOK["deals"]
    assert len(deals) >= 10 and arb.validate_book(BOOK) == []
    for d in deals:
        assert d["status"] == "pending"
        for k in arb.TERM_FIELDS:
            f = d[k]
            assert f["source_url"].startswith("https://") and re.match(r"\d{4}-\d{2}-\d{2}$", f["as_of"])
            assert isinstance(f["verified"], bool), (d["id"], k)
        for s in d["steps"]:
            assert s["source_url"].startswith("https://") and isinstance(s["verified"], bool) and s["status"] in ("open", "done")
    # term sources are SEC filings or company releases; only unaffected prices may point at a price history
    for d in deals:
        for k in arb.TERM_FIELDS:
            url = d[k]["source_url"]
            assert url.startswith("https://www.sec.gov/Archives/") or (k == "unaffected_price" and not d[k]["verified"]), (d["id"], k)


def test_deal_file_has_no_contacts_or_dashes():
    txt = (ROOT / "data/arb/deals.json").read_text()
    assert "@" not in txt and "\u2014" not in txt and "\u2013" not in txt


# ---------- refresh ----------
def _closes(tickers):
    return {t: ("2026-11-02", 10.0) for t in tickers}


def test_refresh_needs_acquirer_only_for_stock_deals():
    need = ra.tickers_needed(BOOK)
    assert "IRT" in need and "TDY" not in need and "MKTX" in need


def test_refresh_build_and_main(tmp_path):
    out = tmp_path / "arb.json"
    assert ra.main(fetch=_closes, out=out) == 0
    page = json.loads(out.read_text())
    assert page["as_of"] == "2026-11-02" and len(page["deals"]) == len(BOOK["deals"])
    assert "Not investment advice" in page["disclaimer"]
    row = page["deals"][0]
    assert {"spread", "annualized", "implied_chance", "days_to_close", "price_date"} <= set(row["calc"])
    assert row["target"]["source_url"] and "target_cik" not in row


def test_refresh_failure_exits_nonzero_and_keeps_old_file(tmp_path, capsys):
    out = tmp_path / "arb.json"
    out.write_text('{"old": true}')

    def boom(_):
        raise ConnectionError("yahoo down")
    assert ra.main(fetch=boom, out=out) == 1
    assert "Arb refresh failed: price download failed" in capsys.readouterr().err
    assert json.loads(out.read_text()) == {"old": True}
    partial = lambda t: {k: v for k, v in _closes(t).items() if k != "MKTX"}
    assert ra.main(fetch=partial, out=out) == 1
    assert "no price for target MKTX" in capsys.readouterr().err


def test_refresh_rejects_invalid_deals(tmp_path):
    bad = copy.deepcopy(BOOK)
    del bad["deals"][0]["target"]["as_of"]
    f = tmp_path / "deals.json"
    f.write_text(json.dumps(bad))
    assert ra.main(fetch=_closes, out=tmp_path / "o.json", deals=f) == 1


def test_committed_page_data_matches_deals():
    page = json.loads((ROOT / "site/data/arb.json").read_text())
    assert [d["id"] for d in page["deals"]] == [d["id"] for d in BOOK["deals"]]
    for d in page["deals"]:
        assert all(d[k] == next(x for x in BOOK["deals"] if x["id"] == d["id"])[k] for k in arb.TERM_FIELDS)


# ---------- watchdog ----------
def test_watchdog_arb_freshness():
    now = datetime(2026, 11, 4, 13, 7, tzinfo=timezone.utc)  # newest closed session: Tue Nov 3
    assert w.arb_freshness("2026-11-03", now)["stale"] is False
    assert w.arb_freshness("2026-11-02", now)["stale"] is False  # one session of slack
    assert w.arb_freshness("2026-10-30", now)["stale"] is True
    assert w.arb_freshness(None, now)["stale"] is True
    mon = datetime(2026, 11, 2, 13, 7, tzinfo=timezone.utc)  # newest closed: Fri Oct 30; slack back to Thu
    assert w.arb_freshness("2026-10-29", mon)["stale"] is False
    rep = w.build_report([date(2026, 11, 3)], now, "2026-10-30")
    assert rep["arb"] == {"as_of": "2026-10-30", "stale": True} and rep["status"] == "ok"
    assert "arb" not in w.build_report([date(2026, 11, 3)], now)


# ---------- EDGAR helpers (offline) ----------
def test_user_agent_has_no_personal_contact(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    assert fd.user_agent() == fd.GENERIC_UA and "@" not in fd.GENERIC_UA
    monkeypatch.setenv("SEC_USER_AGENT", "Some Org ops")
    assert fd.user_agent() == "Some Org ops"
    assert "@" not in (ROOT / "scripts/fetch_deals.py").read_text()


def test_candidates_from_hits():
    hits = [
        {"_id": "0001193125-26-324933:d159148d8k.htm", "_source": {"form": "8-K", "items": ["1.01", "9.01"], "file_date": "2026-07-30",
                                                                  "display_names": ["MARKETAXESS HOLDINGS INC  (MKTX)  (CIK 0001278021)"]}},
        {"_id": "0001193125-26-324933:d159148dex991.htm", "_source": {"form": "8-K", "items": ["1.01"], "file_date": "2026-07-30",
                                                                     "display_names": ["MARKETAXESS HOLDINGS INC  (MKTX)  (CIK 0001278021)"]}},
        {"_id": "0001-26-1:x.htm", "_source": {"form": "8-K", "items": ["2.02"], "display_names": ["A (A) (CIK 1)"]}},
        {"_id": "0002-26-1:y.htm", "_source": {"form": "DEFM14A", "file_date": "2026-08-06",
                                               "display_names": ["Bleichroeder Acquisition Corp. II (BBCQ, BBCQU) (CIK 0002088295)"]}},
        {"_id": "0003-26-1:z.htm", "_source": {"form": "DEFM14A", "file_date": "2026-09-18",
                                               "display_names": ["MARKETAXESS HOLDINGS INC  (MKTX)  (CIK 0001278021)"]}},
    ]
    rows = fd.candidates_from_hits(hits)
    assert [r["form"] for r in rows] == ["8-K", "DEFM14A"]  # dup filing, non-1.01 8-K and SPAC dropped
    assert rows[0]["url"] == "https://www.sec.gov/Archives/edgar/data/1278021/000119312526324933/d159148d8k.htm"
    m = fd.merge_candidates(rows)
    assert len(m) == 1 and m[0]["ticker"] == "MKTX" and m[0]["forms"] == ["8-K", "DEFM14A"] and m[0]["file_date"] == "2026-09-18"


def test_search_url_and_display_name():
    u = fd.search_url('"Agreement and Plan of Merger"', "DEFM14A", date(2025, 11, 3), date(2026, 11, 3), 100)
    assert u.startswith(fd.EFTS + "?") and "forms=DEFM14A" in u and "startdt=2025-11-03" in u and "from=100" in u
    assert fd.parse_display_name("Centerspace (CSR) (CIK 0000798359)") == {"name": "Centerspace", "ticker": "CSR", "cik": 798359}
    assert fd.parse_display_name("Allegro Merger Corp. (CIK 0001720025)")["ticker"] is None


def test_parse_terms_best_effort():
    cash = fd.parse_terms("each Share will be converted into the right to receive $167.00 per Share in cash, without interest")
    assert cash == {"cash_per_share": 167.0, "exchange_ratio": None, "cvr_mentioned": False}
    stock = fd.parse_terms("The Exchange Ratio is fixed at 3.800 shares of IRT Common Stock")
    assert stock["exchange_ratio"] == 3.8 and stock["cash_per_share"] is None
    cvr = fd.parse_terms("$102.50 per share in cash, plus one contingent value right")
    assert cvr["cash_per_share"] == 102.5 and cvr["cvr_mentioned"]
    assert fd.parse_terms("nothing useful here") == {"cash_per_share": None, "exchange_ratio": None, "cvr_mentioned": False}
    assert "per share" in fd.html_text("<p>$1.00&nbsp;per share</p><script>x</script>")


def test_closing_events():
    hits = [{"_id": "a:1.htm", "_source": {"file_date": "2026-11-02", "items": ["2.01", "3.01"]}},
            {"_id": "b:1.htm", "_source": {"file_date": "2026-10-26", "items": ["1.02"]}},
            {"_id": "c:1.htm", "_source": {"file_date": "2026-10-20", "items": ["5.07"]}},
            {"_id": "d:1.htm", "_source": {"file_date": "2026-01-01", "items": ["2.01"]}}]
    ev = fd.closing_events(hits, "2026-08-01")
    assert [e["events"] for e in ev] == [["completed"], ["terminated"]]


# ---------- page ----------
def test_arb_page_basics():
    html = (ROOT / "site/arb.html").read_text()
    js = (ROOT / "site/arb.js").read_text()
    assert "Not investment advice" in html and "How to read this" in html
    assert 'data-nav="arb"' in html and 'aria-current="page"' in html
    assert 'href="arb.html" data-nav="arb"' in (ROOT / "site/index.html").read_text()
    assert 'load("data/arb.json")' in js or "data/arb.json" in js
    assert "Unverified" in js and "source_url" in js
    css = (ROOT / "site/arb.css").read_text()
    assert "prefers-reduced-motion" in css
    for f in ("arb.html", "arb.js", "arb.css"):
        t = (ROOT / "site" / f).read_text()
        assert not re.search(r"\b(buy|sell|price target)\b", t, re.I), f
        assert "\u2014" not in t and "\u2013" not in t, f
