"""CI check for the append-only call log. Exit 1 if history was edited.

    python scripts/check_call_log.py                      # chain + snapshot anchors
    python scripts/check_call_log.py --base origin/main --strict   # CI: no published row may change
    python scripts/check_call_log.py --base HEAD                   # daily scan: newest date may be rewritten

The base comparison catches an edit that also recomputed the chain. If the base ref has no log
yet (first commit of this feature), only the chain and snapshots are checked.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scanner import calllog, tracker  # noqa: E402

SNAP_DIR = ROOT / "data" / "snapshots"


def check_snapshots(text: str, snap_dir: Path = SNAP_DIR) -> list[str]:
    """Every weekly snapshot's head hash must still sit at its row count in the chain (see below for the newest-date exception)."""
    chain = calllog.read_chain(text)
    settled = calllog.settled_count(calllog.read_raw(text, tracker.COLS))
    problems = []
    for f in sorted(snap_dir.glob("*.json")) if snap_dir.exists() else []:
        s = json.loads(f.read_text())
        n, head = s.get("rows"), s.get("head")
        # Rows of the newest date can be replaced by a same-day re-run, so a snapshot reaching into
        # them is not checkable yet. It is checked normally once a later-dated row exists.
        if isinstance(n, int) and n > settled:
            continue
        if not isinstance(n, int) or n < 0 or n > len(chain) or (n and chain[n - 1] != head) or (n == 0 and head != calllog.GENESIS):
            problems.append(f"snapshot {f.name} no longer matches the log (rows {n})")
    return problems


def run(text: str, base_text: str | None = None, snap_dir: Path = SNAP_DIR, strict: bool = False) -> list[str]:
    v = calllog.verify(text, tracker.COLS)
    problems = [] if v["ok"] else [v["error"]]
    if v["ok"]:
        problems += check_snapshots(text, snap_dir)
    if base_text:
        problems += calllog.compare_to_base(base_text, text, tracker.COLS, strict=strict)
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="git ref holding the published log, e.g. origin/main")
    ap.add_argument("--strict", action="store_true",
                    help="freeze every base row, including the newest date (CI); without it the newest date's rows may change (daily scan)")
    a = ap.parse_args()
    path = tracker.LEDGER
    base = None
    if a.base:
        r = subprocess.run(["git", "show", f"{a.base}:data/picks.csv"], cwd=ROOT, capture_output=True, text=True)
        base = r.stdout if r.returncode == 0 else None
    problems = run(path.read_text(encoding="utf-8"), base, strict=a.strict)
    if problems:
        print("CALL LOG CHECK FAILED")
        for p in problems:
            print(" -", p)
        return 1
    v = calllog.verify(path.read_text(encoding="utf-8"), tracker.COLS)
    print(f"call log ok: {v['n']} rows, head {v['head'][:12]}" + (", compared with " + a.base if base else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
