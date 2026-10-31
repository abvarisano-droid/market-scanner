"""Compact price charts for called tickers: 3 years of candles, 50 and 200 day averages, and a
one-year volatility range.

The range is an illustration from the stock's own past volatility, not a forecast. It is centered
on no change (zero drift) so it never implies an expected return or a price level to aim at:
  sigma = standard deviation of daily log returns over the history, times sqrt(252), which is the
          usual estimate of one standard deviation of the stock's yearly log moves
  Flat  = 0%   (DRIFT = 0)
  Upper = exp(+sigma) - 1
  Lower = exp(-sigma) - 1
Each path is drawn as close * exp(DRIFT * t + k * sigma * sqrt(t)) for t in years (k = +1, 0, -1).

Candles are daily for the last DAILY_BARS sessions and weekly (Friday weeks) before that so each
file stays small. The full daily close series ("dc") ships too, so the page computes the 50 and
200 day averages, Bollinger Bands, RSI and MACD on daily data (site/indicators.js) and samples them
at each candle ("ix" is each candle's index into "dc").
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "charts.json"
PERIOD = "3y"
DAILY_BARS = 126       # about six months of daily candles
YEAR = 252             # trading days in a year
MIN_BARS = YEAR + 20   # need a bit more than a year of history to draw a fan
DRIFT = 0.0           # no drift: the range is centered on the last close, never on a past return
LEVELS = (("up", 1.0, "Upper"), ("flat", 0.0, "Flat"), ("down", -1.0, "Lower"))


def _sig(x: float, n: int = 5) -> float:
    """Round to n significant figures (keeps files small, fine for drawing)."""
    if x is None or not math.isfinite(x) or x == 0:
        return 0.0 if x == 0 else None
    d = n - 1 - int(math.floor(math.log10(abs(x))))
    return round(float(x), max(d, 0)) if d > 0 else float(round(x, d))


def levels(last: float, sigma: float) -> dict:
    """Upper / Flat / Lower one year out from the last close and a yearly sigma (zero drift)."""
    out = {"sigma": round(sigma, 4), "drift": DRIFT}
    for key, k, _ in LEVELS:
        g = math.exp(DRIFT + k * sigma) - 1
        out[key + "_pct"] = round(100 * g, 1)
        out[key] = _sig(last * (1 + g))
    return out


def fan(close: pd.Series) -> dict | None:
    """One-year volatility range from past daily closes. None if under MIN_BARS of history."""
    c = pd.Series(close, dtype=float).dropna()
    c = c[c > 0]
    if len(c) < MIN_BARS:
        return None
    lr = np.log(c).diff().dropna()
    sigma = float(lr.std(ddof=1) * math.sqrt(YEAR))
    out = levels(float(c.iloc[-1]), sigma)
    out["years"] = round(len(lr) / YEAR, 2)
    return out


def refan(store: dict) -> dict:
    """Recompute every stored range with the current formula from its stored sigma and last close.
    Offline: no download, so committed files can be regenerated from committed data."""
    for p in store.values():
        f = p.get("fan")
        if f and f.get("sigma") is not None and p.get("last"):
            p["fan"] = {**levels(float(p["last"]), float(f["sigma"])), "years": f.get("years")}
    return store


def path(last: float, sigma: float, k: float, steps: int = 12) -> list[float]:
    """Points of one range path at t = 0, 1/steps, ..., 1 years (zero drift)."""
    return [last * math.exp(DRIFT * (i / steps) + k * sigma * math.sqrt(i / steps)) for i in range(steps + 1)]


def _naive(idx) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(idx)
    return idx.tz_localize(None) if idx.tz is not None else idx


def build(df: pd.DataFrame, ticker: str = "", currency: str | None = None, event: dict | None = None) -> dict | None:
    """Chart payload from daily OHLCV (columns Open, High, Low, Close, optional Volume)."""
    if df is None or "Close" not in df:
        return None
    df = df.copy()
    df.index = _naive(df.index)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["Close"])
    for col in ("Open", "High", "Low"):
        if col not in df:
            df[col] = df["Close"]
        df[col] = df[col].fillna(df["Close"])
    if "Volume" not in df:
        df["Volume"] = np.nan
    if len(df) < 60:
        return None
    df["High"] = df[["Open", "High", "Low", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "High", "Low", "Close"]].min(axis=1)
    pos = pd.Series(np.arange(len(df)), index=df.index)  # daily index of every bar
    cut = df.index[-DAILY_BARS] if len(df) > DAILY_BARS else df.index[0]
    old, new = df[df.index < cut], df[df.index >= cut]
    rows = []
    if len(old):
        for _, g in old.groupby(old.index.to_period("W-FRI")):
            rows.append((g.index[-1], g["Open"].iloc[0], g["High"].max(), g["Low"].min(), g["Close"].iloc[-1],
                         g["Volume"].mean()))  # weekly candle; volume is the week's average day
    for t, r in new.iterrows():
        rows.append((t, r["Open"], r["High"], r["Low"], r["Close"], r["Volume"]))

    d0 = rows[0][0]
    last = float(df["Close"].iloc[-1])
    yr = df.iloc[-YEAR:]

    def ser(vals):
        return [None if v is None or not np.isfinite(v) else _sig(float(v)) for v in vals]

    return {
        "t": ticker, "asof": str(df.index[-1].date()), "cur": currency, "d0": str(d0.date()),
        "x": [int((r[0] - d0).days) for r in rows],
        "ix": [int(pos[r[0]]) for r in rows],
        "o": ser([r[1] for r in rows]), "h": ser([r[2] for r in rows]),
        "l": ser([r[3] for r in rows]), "c": ser([r[4] for r in rows]),
        "v": [None if v is None or not np.isfinite(v) else int(_sig(float(v), 3)) for v in (r[5] for r in rows)],
        "dc": ser(df["Close"].tolist()),
        "daily_from": len(rows) - len(new),
        "last": round(last, 2), "hi52": _sig(float(yr["High"].max())), "lo52": _sig(float(yr["Low"].min())),
        "chg_1y": round(100 * (last / float(df["Close"].iloc[-YEAR - 1]) - 1), 1) if len(df) > YEAR else None,
        "fan": fan(df["Close"]), "event": event,
        "source": "Yahoo Finance daily bars (split and dividend adjusted)",
    }


def next_earnings(ticker: str, asof: date, lookup=None) -> dict | None:
    """Next published earnings date (Yahoo Finance calendar), only if it is after the as-of date."""
    if lookup is None:
        from . import data
        lookup = data.earnings_dates
    try:
        ds = lookup(ticker) or []
    except Exception as exc:  # optional extra: a failure just means no date is shown
        log.debug("calendar %s failed: %s", ticker, exc)
        return None
    ds = sorted(d for d in ds if isinstance(d, date) and d > asof)
    return {"label": "Earnings", "date": ds[0].isoformat()} if ds else None


def collect(tickers: list[str], fetch=None, events: bool = True, currencies: dict | None = None) -> dict:
    """Fetch 3 years of daily OHLCV for the called tickers and build each payload.

    One extra batched download (about 70 tickers) on top of the scan's own 2 year download.
    """
    if fetch is None:
        from . import data
        fetch = data.prices
    px = fetch(sorted(set(tickers)), period=PERIOD)
    out = {}
    for t in sorted(px):
        try:
            df = px[t]
            asof = _naive(df.index)[-1].date()
            ev = next_earnings(t, asof) if events else None
            p = build(df, t, (currencies or {}).get(t), ev)
        except Exception as exc:  # one bad ticker never breaks the set
            log.warning("chart %s skipped (%s)", t, exc)
            continue
        if p:
            out[t] = p
    return out


def save(charts: dict, path: Path | None = None) -> Path:
    path = path or STORE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(charts, separators=(",", ":"), sort_keys=True))
    return path


def load(path: Path = STORE) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}
