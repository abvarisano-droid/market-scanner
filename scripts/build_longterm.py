"""Build site/data/longterm.json from cached SEC companyfacts (run scripts/fetch_sec.py first).

Reads the S&P 500 names from site/data/latest.json (name, sector, last price), extracts the
10-K figures with scanner/longterm.py and writes one compact file the Long-term tab reads.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scanner import longterm as lt  # noqa: E402
from scripts.fetch_sec import CACHE, sp500_tickers  # noqa: E402

KEYS = ["rev_cagr", "op_margin", "fcf_margin", "roic", "shares", "debt_ebitda", "fcf_yield", "ev_ebitda"]


def build(cache: Path = CACHE, latest: dict | None = None, ciks: dict | None = None) -> dict:
    latest = latest or json.loads((ROOT / "site" / "data" / "latest.json").read_text())
    if ciks is None:
        raw = json.loads((cache / "company_tickers.json").read_text())
        tm = {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}
        ciks = {t: tm.get(t.upper()) or tm.get(t.upper().replace("-", ".")) for t in sp500_tickers()}
    rows, missing = [], []
    for t, cik in sorted(ciks.items()):
        f = cache / f"CIK{cik:010d}.json" if cik else None
        meta = latest["lookup"].get(t, {})
        ex = lt.extract(json.loads(f.read_text()), meta.get("s")) if f and f.exists() else None
        if not ex:
            missing.append(t)
            continue
        lt.add_valuation(ex, meta.get("c"), meta.get("mc"))
        chk = lt.rule_checks(ex)
        row = {"t": t, "n": meta.get("n", t), "s": meta.get("s", ""), "cik": cik, "fy": ex["fy"], "a": ex["a"],
               "ck": chk["passed"], "cm": chk["measured"], "cf": chk["flags"]}
        if ex.get("nr"):
            row["nr"] = ex["nr"]
        for k in KEYS:
            if ex.get(k):
                row[k] = ex[k]
        rows.append(row)
    cov = _coverage(rows)
    return {
        "asof": latest.get("asof"),
        "built": date.today().isoformat(),
        "source": "SEC EDGAR XBRL companyfacts, 10-K annual facts only. Prices from the daily scan.",
        "universe": len(ciks),
        "count": len(rows),
        "missing": missing,
        "coverage": cov,
        "rules": [label for _k, label, _t in lt.RULES],
        "disclaimer": "Not investment advice. Mechanical rules on reported 10-K numbers. Not forecasts.",
        "rows": rows,
    }


def _coverage(rows: list[dict]) -> dict:
    return {k: sum(1 for r in rows if k in r) for k in KEYS}


def _capital_ok(roic: dict, om: dict | None) -> bool:
    """True when the shipped numbers show invested capital of at least 10% of revenue (the exact build rule).

    ROIC = op income x (1 - rate) / capital and op margin = op income / revenue for the same 10-K, so
    capital / revenue = op margin x (1 - rate) / ROIC. Without an op margin the offline guard cannot tell,
    so it falls back to treating ROIC over 100% as not meaningful. A small tolerance absorbs the 4-decimal rounding.
    """
    if not om or om.get("v") is None or om["v"] <= 0 or roic["v"] <= 0:
        return False
    return om["v"] * (1 - roic.get("rate", 0.21)) / roic["v"] >= lt.MIN_CAP_VS_REV * 0.98


def reguard(data: dict, latest: dict | None = None) -> dict:
    """Apply the same guards as scanner/longterm.py to an already built longterm.json, without the raw SEC cache.

    Used when the cache is not available (offline). It works from the numbers shipped in each row, so two rules are
    approximations of the exact build-time ones: a market cap check from FCF / FCF yield (or EV less debt), and
    ROIC over 100% is kept only when the shipped op margin, tax rate and ROIC imply invested capital of at least 10% of
    revenue (the exact rule); otherwise it stands in for negative equity or tiny invested capital. The weekly SEC refresh
    recomputes everything exactly and replaces this output.
    """
    latest = latest or json.loads((ROOT / "site" / "data" / "latest.json").read_text())
    for r in data["rows"]:
        nr = dict(r.get("nr") or {})
        fin = (r.get("s") or "") == "Financial Services"
        if fin:
            for k in ("debt_ebitda", "ev_ebitda", "roic"):
                if r.pop(k, None) is not None or k not in nr:
                    nr[k] = lt.FIN_NR
        ref = latest["lookup"].get(r["t"], {}).get("mc")
        fcf, fy, de, ev = (r.get("fcf_margin") or {}).get("f"), r.get("fcf_yield"), r.get("debt_ebitda"), r.get("ev_ebitda")
        calc = None
        if fcf and fy:
            calc = fcf / fy["v"] if fy["v"] != 0 else float("inf")  # negative FCF gives a negative yield: same sign, valid cap
        elif ev and de:
            calc = ev["v"] * de["ebitda"] - de["debt"]
        if ref and calc is not None and not lt.MCAP_RATIO[0] <= calc / ref <= lt.MCAP_RATIO[1]:
            for k in ("fcf_yield", "ev_ebitda"):
                if r.pop(k, None) is not None or k not in nr:
                    nr[k] = lt.SPLIT_NR
        ev = r.get("ev_ebitda")
        if ev and ev["v"] > lt.MAX_EV_EBITDA:
            r.pop("ev_ebitda")
            nr["ev_ebitda"] = lt.SMALL_EBITDA_NR
        roic = r.get("roic")
        if roic and roic["v"] > 1 and not _capital_ok(roic, r.get("op_margin")):
            r.pop("roic")
            nr["roic"] = "Invested capital is tiny or equity is negative, so return on invested capital is not meaningful"
        if nr:
            r["nr"] = nr
        chk = lt.rule_checks(r)
        r["ck"], r["cm"], r["cf"] = chk["passed"], chk["measured"], chk["flags"]
    data["coverage"] = _coverage(data["rows"])
    return data


def main() -> int:
    if "--reguard" in sys.argv:
        path = ROOT / "site" / "data" / "longterm.json"
        out = reguard(json.loads(path.read_text()))
        path.write_text(json.dumps(out, separators=(",", ":"), sort_keys=True))
        print("reguarded; coverage", out["coverage"])
        return 0
    out = build()
    (ROOT / "site" / "data" / "longterm.json").write_text(json.dumps(out, separators=(",", ":"), sort_keys=True))
    print(f"{out['count']} of {out['universe']} companies; coverage {out['coverage']}; missing {out['missing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
