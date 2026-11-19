"""The one shape every contestant returns, and the math on it.

A forecast is a set of quantiles of the LOG RETURN from the last close, for each step 1..H ahead.
Everything downstream (the page, the paper desk, the scorecard) reads only this, so contestants can be
swapped and compared fairly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Deciles: what TimesFM and Chronos give natively; sample-based models are cut to the same levels.
LEVELS: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
HORIZON = 5  # trading days


class ContestantUnavailable(RuntimeError):
    """The model's package or weights are not installed here. The contest skips it and says so."""


@dataclass
class Forecast:
    model: str
    ticker: str
    asof: str                 # date of the last close the model saw (YYYY-MM-DD)
    last_close: float
    q: np.ndarray             # shape (H, len(LEVELS)): log-return quantiles per step
    levels: tuple[float, ...] = LEVELS
    seconds: float = 0.0
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self.q = np.asarray(self.q, dtype=float)
        if self.q.ndim != 2 or self.q.shape[1] != len(self.levels):
            raise ValueError(f"{self.model}: q must be (horizon, {len(self.levels)})")
        if not np.isfinite(self.q).all():
            raise ValueError(f"{self.model}: forecast has missing values")
        # Quantiles must not cross; sort per step (some models return tiny crossings).
        self.q = np.sort(self.q, axis=1)

    @property
    def horizon(self) -> int:
        return self.q.shape[0]

    def at(self, step: int | None = None) -> np.ndarray:
        """Log-return quantiles at a step (1-based); default the last step."""
        return self.q[(step or self.horizon) - 1]

    def prices(self, step: int | None = None) -> np.ndarray:
        return self.last_close * np.exp(self.at(step))

    def p_up(self, step: int | None = None) -> float:
        """Probability the close ends above the last close."""
        return 1.0 - cdf(self.at(step), 0.0, self.levels)

    def to_dict(self) -> dict:
        return {"model": self.model, "ticker": self.ticker, "asof": self.asof, "last_close": round(self.last_close, 6),
                "levels": list(self.levels), "q": [[round(float(v), 6) for v in row] for row in self.q],
                "seconds": round(self.seconds, 3), "meta": self.meta}


def cdf(qs, x: float, levels=LEVELS) -> float:
    """P(value <= x) from quantiles, linear between levels, linear tails clamped to [0.005, 0.995]."""
    qs = np.asarray(qs, dtype=float)
    lv = np.asarray(levels, dtype=float)
    if x <= qs[0]:
        span = qs[1] - qs[0]
        p = lv[0] - (qs[0] - x) / span * (lv[1] - lv[0]) if span > 0 else 0.0
    elif x >= qs[-1]:
        span = qs[-1] - qs[-2]
        p = lv[-1] + (x - qs[-1]) / span * (lv[-1] - lv[-2]) if span > 0 else 1.0
    else:
        p = float(np.interp(x, qs, lv))
    return float(min(0.995, max(0.005, p)))


def from_samples(samples, levels=LEVELS) -> np.ndarray:
    """(n_paths, H) log-return paths -> (H, len(levels)) quantiles."""
    s = np.asarray(samples, dtype=float)
    if s.ndim != 2 or len(s) < 10:
        raise ValueError("need at least 10 sampled paths of shape (n, H)")
    return np.quantile(s, levels, axis=0).T


def closes(df: pd.DataFrame | pd.Series) -> pd.Series:
    s = df["close"] if isinstance(df, pd.DataFrame) else df
    s = s.astype(float).dropna()
    if (s <= 0).any():
        raise ValueError("closes must be positive")
    return s


def log_returns(df) -> np.ndarray:
    return np.diff(np.log(closes(df).to_numpy()))


def next_trading_days(last: pd.Timestamp, n: int) -> list[pd.Timestamp]:
    """Weekdays after `last` (exchange holidays are not modelled; daily models only need the count and weekday)."""
    return list(pd.bdate_range(pd.Timestamp(last) + pd.Timedelta(days=1), periods=n))
