"""Widen or narrow a model's ranges by its own track record, so its 10 to 90 range holds about 8 times in 10.

Uses only forecasts whose outcome was already known on the day the new forecast is made (no look-ahead).
"""
from __future__ import annotations

import numpy as np

from .core import LEVELS

GRID = np.round(np.arange(0.25, 4.01, 0.05), 2)
TARGET = 0.80
MIN_HISTORY = 20


def stretch(qs, factor: float, levels=LEVELS) -> np.ndarray:
    """Scale every quantile's distance from the median by `factor`."""
    qs = np.asarray(qs, float)
    med = qs[..., list(levels).index(0.5)][..., None]
    return med + factor * (qs - med)


def fit_factor(history: list[tuple[np.ndarray, float]], levels=LEVELS, target: float = TARGET) -> float:
    """history = [(quantiles at the horizon, realized log return), ...] from already-scored forecasts.
    Returns the smallest stretch whose 10 to 90 range would have held at least `target` of the time
    (1.0 when there is too little history)."""
    if len(history) < MIN_HISTORY:
        return 1.0
    lv = list(levels)
    i10, i50, i90 = lv.index(0.1), lv.index(0.5), lv.index(0.9)
    qs = np.array([h[0] for h in history], float)
    y = np.array([h[1] for h in history], float)
    med, lo, hi = qs[:, i50], qs[:, i10], qs[:, i90]
    for f in GRID:
        held = np.mean((y >= med + f * (lo - med)) & (y <= med + f * (hi - med)))
        if held >= target:
            return float(f)
    return float(GRID[-1])
