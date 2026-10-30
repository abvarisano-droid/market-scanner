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
        lt.add_valuation(ex, meta.get("c"))
        chk = lt.rule_checks(ex)
        row = {"t": t, "n": meta.get("n", t), "s": meta.get("s", ""), "cik": cik, "fy": ex["fy"], "a": ex["a"],
               "ck": chk["passed"], "cm": chk["measured"], "cf": chk["flags"]}
        if ex.get("nr"):
            row["nr"] = ex["nr"]
        for k in KEYS:
            if ex.get(k):
                row[k] = ex[k]
        rows.append(row)
    cov = {k: sum(1 for r in rows if k in r) for k in KEYS}
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


def main() -> int:
    out = build()
    (ROOT / "site" / "data" / "longterm.json").write_text(json.dumps(out, separators=(",", ":"), sort_keys=True))
    print(f"{out['count']} of {out['universe']} companies; coverage {out['coverage']}; missing {out['missing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
