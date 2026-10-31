"""Tamper-evident call log.

``data/picks.csv`` is the public, append-only record of every Bullish or Bearish call. Each row
carries a ``chain`` value: sha256 of the previous row's chain value plus this row's fields, so
changing, removing or reordering any past row breaks every chain value after it. Hashes are taken
over the raw CSV text of each field, never over parsed numbers, so formatting cannot drift.

Two checks use this module:

* ``verify`` recomputes the chain of one file (catches a hand edit to a past row).
* ``compare_to_base`` compares a candidate file with the version on the main branch (catches an
  edit that also recomputes the chain). Rows dated before the newest base date are frozen. The
  newest date's rows may be replaced, because a same-day re-run of the scan replaces that day.
  New rows must be dated on or after the newest base date.
"""
from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

GENESIS = "0" * 64
CHAIN = "chain"
SEP = "\x1f"


def row_hash(prev: str, fields: list[str]) -> str:
    return hashlib.sha256((prev + SEP + SEP.join(fields)).encode("utf-8")).hexdigest()


def read_raw(path_or_text, cols: list[str]) -> list[list[str]]:
    """Raw field strings per row, in ``cols`` order, ignoring any chain column."""
    text = path_or_text.read_text(encoding="utf-8") if isinstance(path_or_text, Path) else path_or_text
    rd = csv.DictReader(io.StringIO(text))
    return [[r.get(c) or "" for c in cols] for r in rd]


def read_chain(text: str) -> list[str]:
    return [r.get(CHAIN) or "" for r in csv.DictReader(io.StringIO(text))]


def chain_values(rows: list[list[str]]) -> list[str]:
    out, prev = [], GENESIS
    for fields in rows:
        prev = row_hash(prev, fields)
        out.append(prev)
    return out


def render(rows: list[list[str]], cols: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols + [CHAIN])
    for fields, c in zip(rows, chain_values(rows)):
        w.writerow(fields + [c])
    return buf.getvalue()


def write_sealed(path: Path, rows: list[list[str]], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(rows, cols), encoding="utf-8", newline="")


def seal(path: Path, cols: list[str]) -> None:
    """One-time migration: add the chain column to an existing log without touching row text."""
    write_sealed(path, read_raw(path, cols), cols)


def verify(text: str, cols: list[str]) -> dict:
    """Return {ok, n, head, first_bad, error}. first_bad is the 1-based data row where the chain breaks."""
    rd = csv.DictReader(io.StringIO(text))
    if rd.fieldnames is None or list(rd.fieldnames) != cols + [CHAIN]:
        return {"ok": False, "n": 0, "head": GENESIS, "first_bad": None, "error": "header is not the expected columns plus chain"}
    rows = [[r.get(c) or "" for c in cols] for r in csv.DictReader(io.StringIO(text))]
    stored, want = read_chain(text), chain_values(rows)
    for i, (a, b) in enumerate(zip(stored, want), start=1):
        if a != b:
            return {"ok": False, "n": len(rows), "head": want[-1], "first_bad": i,
                    "error": f"row {i} does not match its chain value (edited, removed or reordered)"}
    return {"ok": True, "n": len(rows), "head": want[-1] if want else GENESIS, "first_bad": None, "error": ""}


def compare_to_base(base_text: str, head_text: str, cols: list[str], date_col: str = "date") -> list[str]:
    """List problems if head rewrites history relative to base. Empty list means append-only."""
    if not base_text.strip():
        return []
    di = cols.index(date_col)
    base, head = read_raw(base_text, cols), read_raw(head_text, cols)
    if not base:
        return []
    newest = max(r[di] for r in base)
    frozen = [r for r in base if r[di] < newest]
    problems = []
    if head[:len(frozen)] != frozen:
        for i, (a, b) in enumerate(zip(frozen, head), start=1):
            if a != b:
                problems.append(f"frozen row {i} changed (dated {a[di]}, ticker {a[1]})")
                break
        else:
            problems.append(f"{len(frozen) - len(head)} frozen rows were removed")
    rest = head[len(frozen):]
    if any(r[di] < newest for r in rest):
        problems.append(f"a new row is dated before {newest}, the newest date already published")
    return problems
