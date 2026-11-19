"""The market's own forecast: the expected move priced into at-the-money options.

Live only: free historical option prices do not exist, so this contestant joins from the first live night and
is not in the walk-forward backtest. The data source is Yahoo Finance option chains through yfinance, the same
unofficial feed the scanner already uses for prices. Cboe's delayed-quotes JSON is NOT used: its terms forbid
automated downloads.
"""
from __future__ import annotations

import math
from datetime import date
from statistics import NormalDist

import numpy as np

from .core import HORIZON, LEVELS, ContestantUnavailable, closes

STRADDLE_TO_SIGMA = math.sqrt(math.pi / 2)  # E|X| = sigma * sqrt(2/pi) for a normal move, so sigma = straddle * 1.2533


def sigma_from_straddle(straddle: float, spot: float) -> float:
    """One standard deviation of the log return to expiry, from the ATM call + put mid."""
    if straddle <= 0 or spot <= 0:
        raise ValueError("straddle and spot must be positive")
    return STRADDLE_TO_SIGMA * straddle / spot


def quantiles_from_sigma(sigma_to_expiry: float, days_to_expiry: int, horizon: int = HORIZON) -> np.ndarray:
    """Normal log-return quantiles for steps 1..horizon, with the variance spread evenly over trading days."""
    if days_to_expiry < 1:
        raise ValueError("expiry must be at least one trading day away")
    daily = sigma_to_expiry / math.sqrt(days_to_expiry)
    z = np.array([NormalDist().inv_cdf(p) for p in LEVELS])
    steps = np.arange(1, horizon + 1)[:, None]
    return -0.5 * (daily ** 2) * steps + daily * np.sqrt(steps) * z[None, :]


def pick_expiry(expiries: list[str], today: date, horizon: int = HORIZON) -> str:
    """The first expiry at least `horizon` trading days out (weeklies usually give one 5 to 9 days away)."""
    import numpy as _np
    for e in sorted(expiries):
        if _np.busday_count(today, date.fromisoformat(e)) >= horizon:
            return e
    raise ContestantUnavailable("no option expiry far enough out")


def atm_straddle(calls, puts, spot: float) -> float:
    """Mid of the call + put at the strike nearest spot. Quotes with no bid or no ask are refused."""
    k = min(set(calls["strike"]) & set(puts["strike"]), key=lambda s: abs(s - spot))
    c, p = calls[calls["strike"] == k].iloc[0], puts[puts["strike"] == k].iloc[0]
    if min(c["bid"], c["ask"], p["bid"], p["ask"]) <= 0:
        raise ContestantUnavailable("no two-sided quote at the money")
    return (c["bid"] + c["ask"]) / 2 + (p["bid"] + p["ask"]) / 2


class OptionsMove:
    name = "options_implied"
    live_only = True  # skipped by the walk-forward backtest

    def forecast_q(self, df, ticker: str, asof: str, horizon: int = HORIZON) -> np.ndarray:
        try:
            import yfinance as yf
        except Exception as e:
            raise ContestantUnavailable("yfinance is not installed") from e
        t = yf.Ticker(ticker)
        spot = float(closes(df).iloc[-1])
        today = date.fromisoformat(asof)
        exp = pick_expiry(list(t.options or []), today, horizon)
        ch = t.option_chain(exp)
        sig = sigma_from_straddle(atm_straddle(ch.calls, ch.puts, spot), spot)
        import numpy as _np
        return quantiles_from_sigma(sig, int(_np.busday_count(today, date.fromisoformat(exp))), horizon)
