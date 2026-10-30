"""Long-term quality and valuation figures from SEC XBRL companyfacts (10-K annual facts only).

Pure functions, no network. Ported from the extraction approach in ai-comps-builder
(tag fallbacks, 10-K only, one fact per period keeping the latest filing). Every figure
carries the accession number of the filing it came from so the site can link to it.
Mechanical rules only: these are descriptive numbers, not forecasts or recommendations.
"""
from __future__ import annotations

from datetime import date, timedelta

TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "RevenuesNetOfInterestExpense"],
    "operating_income": ["OperatingIncomeLoss"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
           "DepreciationAmortizationAndAccretionNet", "DepreciationAmortizationAndOther"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsForCapitalImprovements"],
    "tax": ["IncomeTaxExpenseBenefit"],
    "pretax": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "diluted_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "debt_total": ["DebtLongtermAndShorttermCombinedAmount"],
    "debt_long_total": ["LongTermDebt"],
    "debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermNotesPayable", "LongTermDebtAndCapitalLeaseObligations"],
    "debt_current": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "debt_current_all": ["DebtCurrent"],
    "debt_short": ["ShortTermBorrowings", "CommercialPaper"],
}

# Mechanical rule checks shown on the site. Each is (key, label, test on the row).
RULES = [
    ("rev_cagr", "Revenue growth of 5% a year or more", lambda r: r["rev_cagr"]["v"] >= 0.05),
    ("op_margin", "Operating margin not shrinking over 5 years", lambda r: r["op_margin"]["d"] >= 0),
    ("fcf_margin", "Free cash flow margin of 10% or more", lambda r: r["fcf_margin"]["v"] >= 0.10),
    ("roic", "Return on invested capital (proxy) of 10% or more", lambda r: r["roic"]["v"] >= 0.10),
    ("shares", "Share count not higher than 2 years ago", lambda r: r["shares"]["v"] <= 0),
    ("leverage", "Debt to EBITDA of 3 times or less", lambda r: r["debt_ebitda"]["v"] <= 3),
]


def _d(s: str) -> date:
    return date.fromisoformat(s)


def tag_facts(facts: dict, taxonomy: str, tag: str, unit: str = "USD") -> list[dict]:
    node = ((facts or {}).get("facts") or {}).get(taxonomy, {}).get(tag)
    return list(((node or {}).get("units") or {}).get(unit) or [])


def annual_10k(items: list[dict], kind: str) -> list[dict]:
    """Keep 10-K facts only. Duration facts must span about one year (52 and 53 week years included)."""
    out = []
    for f in items:
        if f.get("form") != "10-K":
            continue
        if kind == "instant":
            if not f.get("start"):
                out.append(f)
        elif f.get("start") and 340 <= (_d(f["end"]) - _d(f["start"])).days <= 380:
            out.append(f)
    return out


def dedupe(items: list[dict]) -> list[dict]:
    """One fact per period, keeping the latest filing (a restatement beats the original)."""
    best: dict[tuple, dict] = {}
    for f in items:
        key = (f.get("start") or "", f["end"])
        cur = best.get(key)
        if cur is None or (f["filed"], f.get("accn", "")) > (cur["filed"], cur.get("accn", "")):
            best[key] = f
    return list(best.values())


def series(facts: dict, tags: list[str], kind: str, unit: str = "USD") -> dict[str, dict]:
    """{period end: fact}. For each period the first tag (fallback order) that has a 10-K fact wins."""
    out: dict[str, dict] = {}
    for tag in tags:
        for f in dedupe(annual_10k(tag_facts(facts, "us-gaap", tag, unit), kind)):
            if f["end"] not in out:
                out[f["end"]] = {"val": f["val"], "end": f["end"], "accn": f["accn"], "filed": f["filed"], "tag": tag}
    return out


def anchor_end(facts: dict) -> str | None:
    ends = [e for k in ("revenue", "operating_income") for e in series(facts, TAGS[k], "duration")]
    return max(ends) if ends else None


def _near(ser: dict[str, dict], anchor: str, years: int, tol: int = 20) -> dict | None:
    try:
        target = _d(anchor).replace(year=_d(anchor).year - years)
    except ValueError:  # Feb 29
        target = _d(anchor).replace(year=_d(anchor).year - years, day=28)
    best = None
    for e, f in ser.items():
        gap = abs((_d(e) - target).days)
        if gap <= tol and (best is None or gap < best[0]):
            best = (gap, f)
    return best[1] if best else None


def _at(ser: dict[str, dict], anchor: str) -> dict | None:
    return ser.get(anchor)


def _debt(facts: dict, anchor: str) -> dict | None:
    """Total debt: a combined tag alone, else long-term debt (or noncurrent) plus current and short-term debt where tagged."""
    def get(key):
        return _at(series(facts, TAGS[key], "instant"), anchor)

    total = get("debt_total")
    if total:
        return {"val": total["val"], "accn": total["accn"]}
    long_total = get("debt_long_total")
    noncur = None if long_total else get("debt_noncurrent")
    base = long_total or noncur
    cur_all = get("debt_current_all") if base else None
    if not base and not cur_all:
        return None
    parts = [p for p in (base,) if p]
    if noncur:
        cur = cur_all or get("debt_current")
        if cur:
            parts.append(cur)
        if not cur_all:
            short = get("debt_short")
            if short:
                parts.append(short)
    elif long_total:
        short = get("debt_short")
        if short:
            parts.append(short)
    head = parts[0]
    return {"val": sum(p["val"] for p in parts), "accn": head["accn"]}


def cover_shares(facts: dict, anchor: str) -> dict | None:
    """Shares on the 10-K cover page (dei). Latest filing and date wins; share classes on the same date are added up."""
    items = [f for f in tag_facts(facts, "dei", "EntityCommonStockSharesOutstanding", "shares")
             if f.get("form") == "10-K" and f["end"] >= anchor]
    if not items:
        return None
    filed = max(f["filed"] for f in items)
    same = [f for f in items if f["filed"] == filed]
    end = max(f["end"] for f in same)
    last = [f for f in same if f["end"] == end]
    val = sum({f["val"] for f in last}) if len(last) > 1 else last[0]["val"]
    return {"val": val, "accn": last[0]["accn"]}


def _m(v: float | None, accn: str | None, anchor_accn: str, **extra) -> dict | None:
    if v is None:
        return None
    o = {"v": round(v, 4) if abs(v) < 1000 else round(v, 1)}
    if accn and accn != anchor_accn:
        o["a"] = accn
    o.update(extra)
    return o


def extract(facts: dict) -> dict | None:
    """Long-term figures for one company from its companyfacts JSON. Missing figures are None."""
    anchor = anchor_end(facts)
    if not anchor:
        return None
    rev = series(facts, TAGS["revenue"], "duration")
    opi = series(facts, TAGS["operating_income"], "duration")
    da = series(facts, TAGS["da"], "duration")
    cfo = series(facts, TAGS["cfo"], "duration")
    capex = series(facts, TAGS["capex"], "duration")
    shs = series(facts, TAGS["diluted_shares"], "duration", "shares")
    r0 = _at(rev, anchor)
    o0 = _at(opi, anchor)
    main = r0 or o0
    aa = main["accn"]  # the anchor-year 10-K, used as the default filing link
    out: dict = {"fy": anchor, "a": aa}

    # 10-year revenue CAGR (uses the longest span up to 10 years, at least 5)
    cagr = None
    if r0 and r0["val"] > 0:
        for yrs in range(10, 4, -1):
            base = _near(rev, anchor, yrs)
            if base and base["val"] > 0:
                cagr = _m((r0["val"] / base["val"]) ** (1 / yrs) - 1, r0["accn"], aa, yrs=yrs)
                break
    out["rev_cagr"] = cagr

    # operating margin now and the change in points over 5 years
    om = None
    if r0 and o0 and r0["val"] > 0:
        now = o0["val"] / r0["val"]
        r5, o5 = _near(rev, anchor, 5), _near(opi, anchor, 5)
        d = (now - o5["val"] / r5["val"]) if r5 and o5 and r5["val"] > 0 else None
        if d is not None:
            om = _m(now, o0["accn"], aa, d=round(d, 4))
    out["op_margin"] = om

    # free cash flow margin and the dollar FCF
    fcf = None
    c0, x0 = _at(cfo, anchor), _at(capex, anchor)
    if r0 and c0 and x0 and r0["val"] > 0:
        f = c0["val"] - abs(x0["val"])
        fcf = _m(f / r0["val"], c0["accn"], aa, f=round(f))
    out["fcf_margin"] = fcf

    # ROIC proxy: operating income after a tax rate over (debt + equity - cash)
    debt = _debt(facts, anchor)
    eq = _at(series(facts, TAGS["equity"], "instant"), anchor)
    cash = _at(series(facts, TAGS["cash"], "instant"), anchor)
    roic = None
    if o0 and eq:
        tax = _at(series(facts, TAGS["tax"], "duration"), anchor)
        pre = _at(series(facts, TAGS["pretax"], "duration"), anchor)
        rate = 0.21
        if tax and pre and pre["val"] > 0:
            rate = min(max(tax["val"] / pre["val"], 0.0), 0.35)
        cap = (debt["val"] if debt else 0) + eq["val"] - (cash["val"] if cash else 0)
        if cap > 0:
            roic = _m(o0["val"] * (1 - rate) / cap, o0["accn"], aa, rate=round(rate, 3))
    out["roic"] = roic

    # share count change over 2 years (diluted weighted average, both ends from the newest filing so splits line up)
    sh = None
    s0, s2 = _at(shs, anchor), _near(shs, anchor, 2)
    if s0 and s2 and s2["val"] > 0:
        sh = _m(s0["val"] / s2["val"] - 1, s0["accn"], aa)
    out["shares"] = sh

    # debt to EBITDA (operating income plus D&A); not meaningful when EBITDA is not positive
    de = None
    d0 = _at(da, anchor)
    if debt and o0 and d0:
        ebitda = o0["val"] + abs(d0["val"])
        if ebitda > 0:
            de = _m(debt["val"] / ebitda, debt["accn"], aa, debt=round(debt["val"]), ebitda=round(ebitda))
    out["debt_ebitda"] = de
    out["_cash"] = cash["val"] if cash else None
    out["_cover"] = cover_shares(facts, anchor)
    return out


def add_valuation(row: dict, price: float | None) -> None:
    """FCF yield and EV/EBITDA from the latest price and the 10-K cover share count. Needs a price."""
    cover = row.get("_cover")
    row["fcf_yield"] = row["ev_ebitda"] = None
    if not price or not cover or cover["val"] <= 0:
        return
    mcap = price * cover["val"]
    a = row["a"]
    fcf = row.get("fcf_margin")
    if fcf and "f" in fcf and mcap > 0:
        row["fcf_yield"] = {"v": round(fcf["f"] / mcap, 4), **({"a": cover["accn"]} if cover["accn"] != a else {})}
    de = row.get("debt_ebitda")
    if de and de.get("ebitda", 0) > 0:
        ev = mcap + de["debt"] - (row.get("_cash") or 0)
        row["ev_ebitda"] = {"v": round(ev / de["ebitda"], 2), **({"a": cover["accn"]} if cover["accn"] != a else {})}


def rule_checks(row: dict) -> dict:
    """How many of the six mechanical checks pass, out of those that can be measured."""
    passed = measured = 0
    flags = []
    for key, _label, test in RULES:
        try:
            ok = test(row)
        except (TypeError, KeyError):
            flags.append(None)
            continue
        measured += 1
        passed += 1 if ok else 0
        flags.append(1 if ok else 0)
    return {"passed": passed, "measured": measured, "flags": flags}


def filing_url(cik: int | str, accn: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{str(accn).replace('-', '')}/"
