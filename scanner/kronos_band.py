"""Kronos model range for stock pages: the pure math (no torch, no network).

A model range, not a prediction. Not investment advice.
The nightly scan's Kronos job (scripts/kronos_bands.py, .github/workflows/daily-scan.yml) runs the open-source
Kronos-small model (pinned in kronos/MANIFEST.json) on the last 64 daily candles of each stock page and keeps every
sampled path. This module turns those paths into the fan the page draws, and keeps an honest walk-forward score:
each night's next-day 10th to 90th band is logged before that day happens, and the page says how often the real close
landed inside it over the last 20 trading days (or how many days are scored so far, when fewer than 20).
"""
from __future__ import annotations

import csv
import io
import math
from datetime import date, timedelta
from pathlib import Path

LOOKBACK = 64
HORIZON = 20       # trading days, the same window as the replay rounds
N_PATHS = 100
SHOW_PATHS = 16    # sample paths shipped for drawing
WINDOW = 20
LOG_FIELDS = ["made_date", "ticker", "base_date", "next_p10", "next_p50", "next_p90", "paths", "model"]
NOTE = "Kronos model range. A model range, not a prediction. Not investment advice."


def sig(x: float, n: int = 5) -> float:
    if x == 0 or not math.isfinite(x):
        return 0.0
    d = n - 1 - int(math.floor(math.log10(abs(x))))
    return round(float(x), d) if d > 0 else float(round(x, d))


def quantile(xs: list[float], q: float) -> float:
    """numpy's default (linear between closest ranks)."""
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def daily_rows(p: dict) -> list[tuple]:
    """(YYYY-MM-DD, open, high, low, close, volume) for the chart file's daily candles (the last six months), oldest first."""
    d0 = date.fromisoformat(p["d0"])
    out = []
    for i in range(int(p.get("daily_from") or 0), len(p.get("c") or [])):
        o, h, lo, c = p["o"][i], p["h"][i], p["l"][i], p["c"][i]
        if None in (o, h, lo, c) or min(o, h, lo, c) <= 0:
            continue
        v = p["v"][i] if p.get("v") and p["v"][i] is not None else 0
        out.append(((d0 + timedelta(days=int(p["x"][i]))).isoformat(), float(o), float(h), float(lo), float(c), float(v)))
    return out


def model_input(p: dict, lookback: int = LOOKBACK) -> list[tuple] | None:
    """The last `lookback` daily candles, ending exactly at the chart's as-of close (the scan's last completed session).
    Nothing after it exists in the file, so the model never sees a later candle. None when there are too few."""
    rows = daily_rows(p)
    if len(rows) < lookback or rows[-1][0] != p.get("asof"):
        return None
    return rows[-lookback:]


def future_dates(asof: str, n: int = HORIZON) -> list[str]:
    """The next n weekdays after the as-of date (used only for the model's calendar features and the x axis)."""
    d, out = date.fromisoformat(asof), []
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            out.append(d.isoformat())
    return out


def check_result(res, n_paths: int, horizon: int) -> str | None:
    if not isinstance(res, dict):
        return "result is not an object"
    for k in ("high", "low", "close"):
        m = res.get(k)
        if not isinstance(m, list) or len(m) != n_paths:
            return f"{k} does not hold {n_paths} paths"
        for row in m:
            if not isinstance(row, list) or len(row) != horizon:
                return f"{k} path is not {horizon} steps"
            for v in row:
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
                    return f"{k} has a value that is not a positive number"
    return None


def band(close_paths: list[list[float]], base: float) -> dict:
    """Per-step 10th, 50th and 90th percentile prices, the share of paths ending above the last close, the next-day band
    as returns (for the log), and the first SHOW_PATHS paths for drawing."""
    h = len(close_paths[0])
    steps = [[p[j] for p in close_paths] for j in range(h)]
    ends = [p[-1] for p in close_paths]
    nxt = [p[0] / base - 1 for p in close_paths]
    return {"p10": [sig(quantile(s, 0.1)) for s in steps], "p50": [sig(quantile(s, 0.5)) for s in steps],
            "p90": [sig(quantile(s, 0.9)) for s in steps], "up": sum(e > base for e in ends), "down": sum(e < base for e in ends),
            "n": len(ends), "next": {"p10": quantile(nxt, 0.1), "p50": quantile(nxt, 0.5), "p90": quantile(nxt, 0.9)},
            "paths": [[sig(v) for v in p] for p in close_paths[:SHOW_PATHS]]}


def held(log: list[dict], ticker: str, rows: list[tuple], window: int = WINDOW) -> dict:
    """Walk-forward score over the last `window` trading days of the chart: a logged band counts for the first daily
    candle after its base date; held when that candle's close / the base close - 1 is inside [p10, p90]."""
    dates = [r[0] for r in rows]
    close = {r[0]: r[4] for r in rows}
    last = set(dates[-window:])
    seen, n, k = set(), 0, 0
    for r in log:
        if r.get("ticker") != ticker or r.get("base_date") not in close:
            continue
        i = dates.index(r["base_date"])
        if i + 1 >= len(dates) or dates[i + 1] not in last or dates[i + 1] in seen:
            continue
        seen.add(dates[i + 1])
        ret = close[dates[i + 1]] / close[r["base_date"]] - 1
        n += 1
        k += float(r["next_p10"]) <= ret <= float(r["next_p90"])
    return {"held": k, "scored": n, "window": window}


def held_text(h: dict) -> str:
    if h["scored"] >= h["window"]:
        return f"Kronos held its p10 to p90 range on {h['held']} of the last {h['window']} days."
    if not h["scored"]:
        return f"No days scored yet: each night's range is checked against the next close, so the count builds to {h['window']} days."
    return (f"Kronos held its p10 to p90 range on {h['held']} of {h['scored']} scored day{'s' if h['scored'] != 1 else ''} so far "
            f"(fewer than {h['window']}; the count builds one day at a time).")


def read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_log(path: Path, rows: list[dict]) -> int:
    """Append-only; a (made_date, ticker) already present is never written again or rewritten."""
    old = read_log(path)
    seen = {(r["made_date"], r["ticker"]) for r in old}
    new = [r for r in rows if (r["made_date"], r["ticker"]) not in seen]
    if not new:
        return 0
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=LOG_FIELDS, lineterminator="\n", extrasaction="ignore")
    if not old and not (path.exists() and path.stat().st_size):
        w.writeheader()
    for r in new:
        w.writerow(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())
    return len(new)
