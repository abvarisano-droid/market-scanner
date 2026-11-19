"""Walk-forward contest: on each test date every contestant forecasts from the closes up to that date only,
then is graded on the close `horizon` trading days later.

Calibration uses only forecasts whose outcome date is on or before the date being forecast, pooled across
tickers for that model, so the '+cal' rows are exactly what the model would have shown live.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .calibrate import fit_factor, stretch
from .core import HORIZON, LEVELS, ContestantUnavailable
from .scoring import grade

MIN_HISTORY = 300  # closes a ticker needs before its first test date
CAL_WINDOW = 250   # most recent scored forecasts per model used to fit its stretch


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    d = df.rename(columns=str.lower)
    d = d[[c for c in ("open", "high", "low", "close", "volume") if c in d.columns]].dropna(subset=["close"])
    d.index = pd.DatetimeIndex(pd.to_datetime(d.index)).tz_localize(None).normalize()
    return d[~d.index.duplicated(keep="last")].sort_index()


def test_dates(prices: dict[str, pd.DataFrame], weeks: int, step: int, horizon: int) -> list[pd.Timestamp]:
    cal = sorted(set().union(*[set(d.index) for d in prices.values()]))
    last_usable = len(cal) - 1 - horizon
    first = max(0, last_usable - weeks * 5)
    return cal[first:last_usable + 1][::step]


def run(prices: dict[str, pd.DataFrame], contestants: dict, *, weeks: int = 52, step: int = 5,
        horizon: int = HORIZON, calibrate: bool = True, log=print) -> dict:
    prices = {t: normalize(d) for t, d in prices.items()}
    dates = test_dates(prices, weeks, step, horizon)
    skipped: dict[str, str] = {}
    graded: list[dict] = []
    scored: dict[str, list[tuple[pd.Timestamp, np.ndarray, float]]] = {}  # model -> (outcome date, q_h, y)
    for name, c in contestants.items():
        if getattr(c, "live_only", False):
            skipped[name] = "live only (no free history of option prices)"
    for day in dates:
        for ticker, d in prices.items():
            if day not in d.index:
                continue
            i = d.index.get_loc(day)
            if i + 1 < MIN_HISTORY or i + horizon >= len(d):
                continue
            hist = d.iloc[:i + 1].copy()  # the model sees nothing after `day`
            y = float(np.log(d["close"].iloc[i + horizon] / d["close"].iloc[i]))
            out_date = d.index[i + horizon]
            asof = day.date().isoformat()
            for name, c in contestants.items():
                if name in skipped:
                    continue
                t0 = time.perf_counter()
                try:
                    q = np.sort(np.asarray(c.forecast_q(hist, ticker, asof, horizon), float), axis=1)
                except ContestantUnavailable as e:
                    skipped[name] = str(e)
                    log(f"skip {name}: {e}")
                    continue
                except Exception as e:  # one bad series never stops the contest
                    log(f"{name} {ticker} {asof}: {type(e).__name__}: {e}")
                    continue
                secs = time.perf_counter() - t0
                if q.shape != (horizon, len(LEVELS)) or not np.isfinite(q).all():
                    log(f"{name} {ticker} {asof}: bad forecast shape {q.shape}")
                    continue
                q_h = q[-1]
                base = {"ticker": ticker, "asof": asof, "outcome_date": out_date.date().isoformat(),
                        "levels": LEVELS, "realized": y, "seconds": secs}
                graded.append(grade({**base, "model": name, "q_h": q_h}))
                if calibrate:
                    past = [(qq, yy) for od, qq, yy in scored.get(name, []) if od <= day][-CAL_WINDOW:]
                    f = fit_factor(past)
                    graded.append(grade({**base, "model": f"{name}+cal", "q_h": stretch(q_h, f), "stretch": f}))
                scored.setdefault(name, []).append((out_date, q_h, y))
        log(f"{day.date()}: {len(graded)} graded so far")
    return {"dates": [d.date().isoformat() for d in dates], "tickers": sorted(prices), "horizon": horizon,
            "graded": graded, "skipped": skipped}
