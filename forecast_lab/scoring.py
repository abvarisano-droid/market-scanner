"""How each forecast is graded once its day arrives, and the weekly table per model.

All scores use the log return from the last close the model saw to the close `horizon` trading days later.
"""
from __future__ import annotations

import math

import numpy as np

from .core import LEVELS, cdf


def pinball(qs, levels, y: float) -> float:
    """Mean quantile (pinball) loss over the levels. Lower is better."""
    qs, lv = np.asarray(qs, float), np.asarray(levels, float)
    d = y - qs
    return float(np.mean(np.maximum(lv * d, (lv - 1) * d)))


def crps(qs, levels, y: float) -> float:
    """CRPS approximated from quantiles: 2 x mean pinball loss over evenly spaced levels. Lower is better."""
    return 2.0 * pinball(qs, levels, y)


def inside(qs, levels, y: float, lo: float = 0.1, hi: float = 0.9) -> bool:
    lv = list(levels)
    return bool(qs[lv.index(lo)] <= y <= qs[lv.index(hi)])


def brier(p_up: float, y: float) -> float:
    return float((p_up - (1.0 if y > 0 else 0.0)) ** 2)


def pit(qs, levels, y: float) -> float:
    """Where the outcome fell inside the forecast (0 to 1). Calibrated models spread these evenly."""
    return cdf(qs, y, levels)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% range for a hit rate of k out of n."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


def grade(rec: dict) -> dict:
    """Add the per-forecast scores to a record that holds q_h (quantiles at the horizon), levels and realized."""
    qs, lv, y = rec["q_h"], rec.get("levels", LEVELS), rec["realized"]
    p = 1.0 - cdf(qs, 0.0, lv)
    return {**rec, "p_up": p, "crps": crps(qs, lv, y), "brier": brier(p, y), "in80": inside(qs, lv, y, 0.1, 0.9),
            "in40": inside(qs, lv, y, 0.3, 0.7), "pit": pit(qs, lv, y),
            "dir_hit": (y > 0) == (p > 0.5) if abs(p - 0.5) > 1e-9 else None}


def summarize(graded: list[dict], reference: str = "random_walk") -> list[dict]:
    """One row per model: how often ranges held, Brier, CRPS and CRPS skill against the reference model.

    Skill is computed only on forecasts both models made (same ticker and date), so a model that skipped hard
    names cannot look better by skipping.
    """
    by_model: dict[str, list[dict]] = {}
    for g in graded:
        by_model.setdefault(g["model"], []).append(g)
    ref = {(g["ticker"], g["asof"]): g["crps"] for g in by_model.get(reference, [])}
    rows = []
    for m, gs in sorted(by_model.items()):
        n = len(gs)
        hits = [g["dir_hit"] for g in gs if g["dir_hit"] is not None]
        k80 = sum(g["in80"] for g in gs)
        paired = [(g["crps"], ref[(g["ticker"], g["asof"])]) for g in gs if (g["ticker"], g["asof"]) in ref]
        skill = (1 - sum(a for a, _ in paired) / sum(b for _, b in paired)) if paired and sum(b for _, b in paired) > 0 else None
        lo, hi = wilson(sum(hits), len(hits))
        rows.append({"model": m, "n": n,
                     "held80": k80 / n, "held80_range": wilson(k80, n),
                     "held40": sum(g["in40"] for g in gs) / n,
                     "brier": float(np.mean([g["brier"] for g in gs])),
                     "crps": float(np.mean([g["crps"] for g in gs])),
                     "skill": skill, "paired": len(paired),
                     "hit_rate": (sum(hits) / len(hits)) if hits else None, "hit_range": (lo, hi),
                     "seconds": float(np.mean([g.get("seconds", 0.0) for g in gs]))})
    # Rank: best CRPS skill first (higher is better); models without a skill score last.
    rows.sort(key=lambda r: (r["skill"] is None, -(r["skill"] or 0.0), r["crps"]))
    return rows
