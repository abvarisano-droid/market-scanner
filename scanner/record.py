"""Honest hit-rate stats for the public track record.

Hit rate = share of graded calls that beat SPY (Bullish) or lagged it (Bearish) over the window,
using the grading rules in ``tracker``. Each rate comes with its sample size n and a 95 percent
Wilson interval, because a handful of calls says little. Calls logged on the same day share market
conditions, so the real uncertainty is wider than the interval shows.
"""
from __future__ import annotations

import math

import pandas as pd

from . import tracker

Z95 = 1.96
SMALL_N = 30  # under this many graded calls in a window the interval is flagged as very wide


def wilson(hits: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = hits / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def window_stats(ev: pd.DataFrame, days: int, min_days: int = tracker.MIN_DAYS) -> list[dict]:
    """One row per grading window across all lenses. ``label`` is 'still noise' until the record
    covers ``min_days`` trading days; separately ``small_sample`` flags n under SMALL_N."""
    out = []
    noise = days < min_days
    for h, n_days in tracker.HORIZONS.items():
        col = f"hit_{h}"
        s = ev[col].dropna() if (ev is not None and not ev.empty and col in ev) else pd.Series(dtype=bool)
        n = int(len(s))
        hits = int(s.astype(bool).sum()) if n else 0
        ci = wilson(hits, n)
        alpha = ev[f"alpha_{h}"].dropna() if n else pd.Series(dtype=float)
        out.append({
            "window": n_days, "n": n, "hits": hits,
            "hit_rate_pct": round(100 * hits / n, 1) if n else None,
            "ci_low_pct": round(100 * ci[0], 1) if ci else None,
            "ci_high_pct": round(100 * ci[1], 1) if ci else None,
            "avg_excess_pct": round(100 * float(alpha.mean()), 2) if len(alpha) else None,
            "small_sample": n < SMALL_N,
            "label": "still noise" if noise else ("not graded yet" if n == 0 else "readable, small sample" if n < SMALL_N else "readable"),
        })
    return out
