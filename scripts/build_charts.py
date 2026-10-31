"""Refresh data/charts.json (3 year candles for every called ticker) without a full scan.

    python scripts/build_charts.py

The nightly scan does this itself (scanner.pipeline); this is for a one-off refresh. Real Yahoo
Finance bars only, the same fetcher the scan uses. Then run scripts/export_site.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scanner import charts  # noqa: E402

if __name__ == "__main__":
    scan = json.loads((ROOT / "data" / "latest_scan.json").read_text())
    called = sorted({r["ticker"] for r in scan.get("ledger") or []})
    cur = {r["ticker"]: r.get("currency") for r in scan["table"] if isinstance(r.get("currency"), str)}
    out = charts.collect(called, currencies=cur)
    charts.save(out)
    print("charts", len(out), "of", len(called), "called tickers")
