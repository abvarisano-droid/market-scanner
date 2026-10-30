import json
from pathlib import Path

import pytest

from scanner import longterm as lt
from scripts import fetch_sec
from scripts.build_longterm import build

SITE = Path(__file__).resolve().parent.parent / "site"


def f(val, end, start=None, form="10-K", accn="0000000000-24-000001", filed="2024-02-01"):
    d = {"val": val, "end": end, "form": form, "accn": accn, "filed": filed}
    if start:
        d["start"] = start
    return d


def facts(**tags):
    gaap = {}
    for tag, (unit, items) in tags.items():
        gaap[tag] = {"units": {unit: items}}
    return {"facts": {"us-gaap": gaap, "dei": {}}}


def years(first, n, fn, tag_kw=None):
    out = []
    for i in range(n):
        y = first + i
        out.append(f(fn(i), f"{y}-12-31", f"{y}-01-01", accn=f"0000000000-{str(y + 1)[2:]}-000001", filed=f"{y + 1}-02-01", **(tag_kw or {})))
    return out


def sample_facts():
    rev = years(2013, 11, lambda i: 1000 * 1.1 ** i)
    return facts(
        Revenues=("USD", rev),
        OperatingIncomeLoss=("USD", years(2013, 11, lambda i: 200 + 5 * i)),
        DepreciationAndAmortization=("USD", years(2013, 11, lambda i: 50)),
        NetCashProvidedByUsedInOperatingActivities=("USD", years(2013, 11, lambda i: 300)),
        PaymentsToAcquirePropertyPlantAndEquipment=("USD", years(2013, 11, lambda i: 100)),
        StockholdersEquity=("USD", [f(1500, "2023-12-31", accn="0000000000-24-000001")]),
        CashAndCashEquivalentsAtCarryingValue=("USD", [f(100, "2023-12-31")]),
        LongTermDebt=("USD", [f(600, "2023-12-31")]),
        WeightedAverageNumberOfDilutedSharesOutstanding=("shares", years(2021, 3, lambda i: 100 - 2 * i)),
    )


def test_filters_and_dedupe():
    items = [f(1, "2023-12-31", "2023-01-01", form="10-Q"), f(2, "2023-12-31", "2023-01-01"),
             f(3, "2023-06-30", "2023-04-01"), f(4, "2023-12-31", "2023-01-01", filed="2024-03-01", accn="b")]
    ann = lt.annual_10k(items, "duration")
    assert [x["val"] for x in ann] == [2, 4]
    assert lt.dedupe(ann)[0]["val"] == 4  # restatement wins


def test_tag_fallback_per_period():
    old = f(10, "2014-12-31", "2014-01-01")
    new = f(20, "2023-12-31", "2023-01-01")
    s = lt.series(facts(SalesRevenueNet=("USD", [old]), Revenues=("USD", [new])), lt.TAGS["revenue"], "duration")
    assert s["2014-12-31"]["tag"] == "SalesRevenueNet" and s["2023-12-31"]["tag"] == "Revenues"


def test_extract_figures():
    ex = lt.extract(sample_facts())
    assert ex["fy"] == "2023-12-31"
    assert ex["rev_cagr"]["v"] == pytest.approx(0.10, abs=0.001) and ex["rev_cagr"]["yrs"] == 10
    assert ex["fcf_margin"]["v"] == pytest.approx(200 / (1000 * 1.1 ** 10), abs=0.001)
    assert ex["shares"]["v"] == pytest.approx(-0.04, abs=0.001)
    assert ex["debt_ebitda"]["v"] == pytest.approx(600 / 300, abs=0.01)
    assert 0 < ex["roic"]["v"] < 0.3
    assert ex["op_margin"]["d"] != 0 and ex["a"].startswith("0000000000-24")


def test_missing_data_is_none_not_invented():
    ex = lt.extract(facts(Revenues=("USD", years(2020, 4, lambda i: 100))))
    assert ex["rev_cagr"] is None and ex["op_margin"] is None and ex["debt_ebitda"] is None and ex["roic"] is None
    assert lt.extract({"facts": {}}) is None


def test_negative_ebitda_not_meaningful():
    fx = sample_facts()
    fx["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"] = years(2013, 11, lambda i: -500)
    assert lt.extract(fx)["debt_ebitda"] is None


def test_rule_checks_and_valuation():
    ex = lt.extract(sample_facts())
    ex["_cover"] = {"val": 100.0, "accn": "0000000000-24-000001"}
    lt.add_valuation(ex, 50.0)
    assert ex["fcf_yield"]["v"] == pytest.approx(ex["fcf_margin"]["f"] / 5000, abs=0.001)
    chk = lt.rule_checks(ex)
    assert chk["measured"] == 6 and 0 <= chk["passed"] <= 6 and len(chk["flags"]) == 6
    lt.add_valuation(ex, None)
    assert ex["fcf_yield"] is None


def test_filing_url():
    assert lt.filing_url("0000320193", "0000320193-23-000106") == "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/"


class FakeResp:
    def __init__(self, code, body=None):
        self.status_code, self.body = code, body

    def json(self):
        return self.body

    def raise_for_status(self):
        raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, timeout=0):
        self.calls.append(url)
        return self.routes[url]


def test_fetch_caches_and_rate_limits(tmp_path):
    ticks = []
    clock = {"t": 0.0}
    lim = fetch_sec.Limiter(8, clock=lambda: clock["t"], sleep=lambda s: (ticks.append(s), clock.__setitem__("t", clock["t"] + s)))
    routes = {fetch_sec.TICKERS_URL: FakeResp(200, {"0": {"cik_str": 1, "ticker": "AAA", "title": "A"}, "1": {"cik_str": 2, "ticker": "BRK-B", "title": "B"}}),
              fetch_sec.FACTS_URL.format(cik=1): FakeResp(200, {"facts": {}}),
              fetch_sec.FACTS_URL.format(cik=2): FakeResp(404)}
    s = FakeSession(routes)
    res = fetch_sec.fetch_all(["AAA", "BRK-B", "ZZZ"], s, tmp_path, lim)
    assert res["fetched"] == 1 and res["missing"] == ["BRK-B", "ZZZ"]
    assert (tmp_path / "CIK0000000001.json").exists()
    assert all(t >= 0.125 - 1e-9 for t in ticks)  # never faster than 8 a second
    n = len(s.calls)
    fetch_sec.fetch_all(["AAA"], s, tmp_path, lim)
    assert len(s.calls) == n  # cache hit, no network


def test_fetch_requires_user_agent(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    assert fetch_sec.main() == 2


def test_no_hardcoded_contact():
    for p in ("scripts/fetch_sec.py", "scanner/longterm.py", "scripts/build_longterm.py"):
        assert "@" not in (Path(__file__).resolve().parent.parent / p).read_text()


def test_build_from_cache(tmp_path):
    (tmp_path / "CIK0000000001.json").write_text(json.dumps(sample_facts()))
    latest = {"asof": "2026-10-30", "lookup": {"AAA": {"n": "Alpha", "s": "Tech", "c": 50.0, "i": "S&P 500"}}}
    out = build(tmp_path, latest, {"AAA": 1, "NOPE": 2})
    assert out["count"] == 1 and out["missing"] == ["NOPE"] and out["universe"] == 2
    assert out["rows"][0]["cik"] == 1 and "not investment advice" in out["disclaimer"].lower()


def test_committed_longterm_json():
    d = json.loads((SITE / "data/longterm.json").read_text())
    assert d["count"] >= 400 and "Not investment advice" in d["disclaimer"]
    assert (SITE / "data/longterm.json").stat().st_size < 1_500_000
    for r in d["rows"]:
        assert r["a"].count("-") == 2 and r["cik"] > 0 and r["cm"] <= 6
    assert not any(c in (SITE / "data/longterm.json").read_text() for c in ("—", "–"))


def test_fcf_margin_over_100_percent_is_na():
    fx = sample_facts()
    fx["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"] = years(2013, 11, lambda i: 90000)
    ex = lt.extract(fx)
    assert ex["fcf_margin"] is None and "100%" in ex["nr"]["fcf_margin"]
    ex["_cover"] = {"val": 100.0, "accn": "x"}
    lt.add_valuation(ex, 50.0)
    assert ex["fcf_yield"] is not None  # dollars still usable for yield


def test_financial_sector_fcf_margin_is_na():
    ex = lt.extract(sample_facts(), "Financial Services")
    assert ex["fcf_margin"] is None and "Financial" in ex["nr"]["fcf_margin"]
    ex["_cover"] = {"val": 100.0, "accn": "x"}
    lt.add_valuation(ex, 50.0)
    assert ex["fcf_yield"] is None
    assert lt.extract(sample_facts(), "Technology")["fcf_margin"] is not None


def test_stale_revenue_does_not_mix_periods():
    # revenue stops in 2023 but cash flow runs to 2025: anchor is 2025, revenue figures are n/a, not 2023 numbers
    fx = sample_facts()
    g = fx["facts"]["us-gaap"]
    g["Revenues"]["units"]["USD"] = years(2013, 11, lambda i: 1000)[:-2]
    g["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"] = years(2013, 13, lambda i: 300)
    g["PaymentsToAcquirePropertyPlantAndEquipment"]["units"]["USD"] = years(2013, 13, lambda i: 100)
    ex = lt.extract(fx)
    assert ex["fy"] == "2025-12-31"
    assert ex["rev_cagr"] is None and ex["fcf_margin"] is None and ex["op_margin"] is None
    assert "revenue" in ex["nr"]["fcf_margin"].lower()


def test_fcf_needs_capex_in_same_period():
    fx = sample_facts()
    fx["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]["units"]["USD"] = years(2013, 10, lambda i: 100)  # none for 2023
    ex = lt.extract(fx)
    assert ex["fcf_margin"] is None and "same fiscal year" in ex["nr"]["fcf_margin"]


def test_max_age_refetches_only_stale(tmp_path):
    import os
    routes = {fetch_sec.TICKERS_URL: FakeResp(200, {"0": {"cik_str": 1, "ticker": "AAA", "title": "A"}}),
              fetch_sec.FACTS_URL.format(cik=1): FakeResp(200, {"facts": {"new": 1}})}
    s = FakeSession(routes)
    lim = fetch_sec.Limiter(8, clock=lambda: 0.0, sleep=lambda s_: None)
    fetch_sec.fetch_all(["AAA"], s, tmp_path, lim)
    n = len(s.calls)
    fetch_sec.fetch_all(["AAA"], s, tmp_path, lim, max_age_days=25)
    assert len(s.calls) == n  # fresh, no refetch
    old = 1_000_000_000
    for f in tmp_path.iterdir():
        os.utime(f, (old, old))
    fetch_sec.fetch_all(["AAA"], s, tmp_path, lim, max_age_days=25)
    assert len(s.calls) == n + 2  # tickers list and company facts fetched again


def test_stale_copy_kept_when_refetch_404s(tmp_path):
    import os
    (tmp_path / "company_tickers.json").write_text(json.dumps({"0": {"cik_str": 1, "ticker": "AAA", "title": "A"}}))
    f = tmp_path / "CIK0000000001.json"
    f.write_text("{}")
    os.utime(f, (1_000_000_000, 1_000_000_000))
    s = FakeSession({fetch_sec.FACTS_URL.format(cik=1): FakeResp(404)})
    lim = fetch_sec.Limiter(8, clock=lambda: 0.0, sleep=lambda s_: None)
    res = fetch_sec.fetch_all(["AAA"], s, tmp_path, lim, max_age_days=25)
    assert res["missing"] == [] and f.exists()


def test_built_date_is_iso_in_build_and_committed_json(tmp_path):
    from datetime import date
    out = build(tmp_path, {"asof": "2026-10-30", "lookup": {}}, {})
    assert date.fromisoformat(out["built"]) == date.today()
    d = json.loads((SITE / "data/longterm.json").read_text())
    assert date.fromisoformat(d["built"])


def test_long_term_tab_shows_as_of_from_built():
    js = (SITE / "app.js").read_text()
    assert 'id="lt-asof"' in js and "Long-term data as of " in js and "D.built" in js
