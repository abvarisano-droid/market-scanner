"""Simple forecasters every fancy model has to beat. Seeded, so the same input gives the same forecast."""
from __future__ import annotations

import zlib

import numpy as np

from .core import HORIZON, LEVELS, from_samples, log_returns

N_PATHS = 2000


def _rng(ticker: str, asof: str, name: str) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32(f"{name}|{ticker}|{asof}".encode()))


class RandomWalk:
    """No drift; spread from the last 60 daily moves (bell curve). The 'no skill' line for skill scores."""
    name = "random_walk"
    window = 60

    def forecast_q(self, df, ticker: str, asof: str, horizon: int = HORIZON) -> np.ndarray:
        r = log_returns(df)[-self.window:]
        if len(r) < 20:
            raise ValueError("need at least 21 closes")
        sd = float(np.std(r, ddof=1))
        from statistics import NormalDist
        z = np.array([NormalDist().inv_cdf(p) for p in LEVELS])
        steps = np.arange(1, horizon + 1)[:, None]
        return sd * np.sqrt(steps) * z[None, :]


class GBM:
    """Geometric Brownian motion: volatility from the last 20 days, drift from the last year (shrunk by half)."""
    name = "gbm"

    def forecast_q(self, df, ticker: str, asof: str, horizon: int = HORIZON) -> np.ndarray:
        r = log_returns(df)
        if len(r) < 60:
            raise ValueError("need at least 61 closes")
        sd = float(np.std(r[-20:], ddof=1))
        mu = 0.5 * float(np.mean(r[-252:]))
        from statistics import NormalDist
        z = np.array([NormalDist().inv_cdf(p) for p in LEVELS])
        steps = np.arange(1, horizon + 1)[:, None]
        return (mu - 0.5 * sd * sd) * steps + sd * np.sqrt(steps) * z[None, :]


class Bootstrap:
    """Next H days look like a random H-day stretch from the last 2 years (keeps fat tails and crash days)."""
    name = "bootstrap"
    window = 504

    def forecast_q(self, df, ticker: str, asof: str, horizon: int = HORIZON) -> np.ndarray:
        r = log_returns(df)[-self.window:]
        if len(r) < 60 + horizon:
            raise ValueError("need at least 66 closes")
        r = r - r.mean()  # no drift: past trend is not a forecast
        starts = _rng(ticker, asof, self.name).integers(0, len(r) - horizon + 1, size=N_PATHS)
        paths = np.cumsum(np.stack([r[s:s + horizon] for s in starts]), axis=1)
        return from_samples(paths)


BASELINES = {c.name: c for c in (RandomWalk, GBM, Bootstrap)}
