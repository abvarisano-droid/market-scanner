"""Write the weekly snapshot of the track record to data/snapshots/<ISO year>-W<week>.json.

Written once per ISO week by the daily scan (the first run of the week) and never overwritten. The
snapshot stores the log's row count and head hash, so a later edit to any logged row is caught by
scripts/check_call_log.py, plus the headline record so the numbers published each week stay on file.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scanner import calllog, tracker  # noqa: E402

SNAP_DIR = ROOT / "data" / "snapshots"
TRACK = ROOT / "site" / "data" / "track.json"


def snapshot(track: dict, ledger_text: str, today: date, snap_dir: Path = SNAP_DIR) -> Path | None:
    iso = today.isocalendar()
    out = snap_dir / f"{iso[0]}-W{iso[1]:02d}.json"
    if out.exists():
        return None
    v = calllog.verify(ledger_text, tracker.COLS)
    if not v["ok"]:
        raise SystemExit("refusing to snapshot a log that fails its chain check: " + v["error"])
    rec = track.get("record", {})
    body = {"week": f"{iso[0]}-W{iso[1]:02d}", "taken": today.isoformat(), "scan_asof": track.get("asof"),
            "rows": v["n"], "head": v["head"], "first_logged": rec.get("first_logged"),
            "trading_days": track.get("trading_days"), "status": track.get("status"),
            "windows": rec.get("windows", []),
            "note": "Not investment advice. Calls are mechanical and graded versus SPY; nothing here is edited after the fact."}
    snap_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n")
    return out


if __name__ == "__main__":
    p = snapshot(json.loads(TRACK.read_text()), tracker.LEDGER.read_text(encoding="utf-8"), date.today())
    print("snapshot written:" if p else "snapshot for this week already exists", p or "")
