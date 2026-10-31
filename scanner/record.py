"""Honest hit-rate stats for the public track record.

Every hit rate comes with its sample size n and a 95 percent Wilson interval, because a handful of
calls says little. Calls logged on the same day share market conditions, so the real uncertainty is
wider than the interval shows.
"""
from __future__ import annotations

import math

Z95 = 1.96


def wilson(hits: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = hits / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def interval_pct(rate: float | None, n: int) -> dict:
    """{hits, ci_low_pct, ci_high_pct} for a hit rate (share 0 to 1) over n graded calls."""
    if not n or rate is None:
        return {"hits": 0, "ci_low_pct": None, "ci_high_pct": None}
    hits = int(round(rate * n))
    lo, hi = wilson(hits, n)
    return {"hits": hits, "ci_low_pct": round(100 * lo, 1), "ci_high_pct": round(100 * hi, 1)}
