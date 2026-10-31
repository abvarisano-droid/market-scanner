"""Technical scan signals computed from daily price history."""
from __future__ import annotations

import numpy as np
import pandas as pd


def technicals(df: pd.DataFrame) -> dict:
    c = df["Close"].dropna()  # a trailing NaN close (partial or missing bar) must not become the "last close"
    v = df["Volume"].reindex(c.index)
    o = df["Open"].reindex(c.index)
    last = float(c.iloc[-1])
    hi52, lo52 = float(c.tail(252).max()), float(c.tail(252).min())
    ret = lambda n: float(c.iloc[-1] / c.iloc[-1 - n] - 1) if len(c) > n else np.nan
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = float(100 - 100 / (1 + gain.iloc[-1] / loss.iloc[-1])) if loss.iloc[-1] else 100.0
    avg_vol = float(v.iloc[-21:-1].mean()) if len(v) > 21 else np.nan
    prev_close = float(c.iloc[-2])
    return {
        "price": last,
        "chg_1d": ret(1), "chg_5d": ret(5), "chg_1m": ret(21), "chg_3m": ret(63), "chg_6m": ret(126),
        "gap": float(o.iloc[-1] / prev_close - 1),
        "vol_ratio": float(v.iloc[-1] / avg_vol) if avg_vol else np.nan,
        "rsi": rsi,
        "pct_from_high": last / hi52 - 1,
        "pct_from_low": last / lo52 - 1,
        "above_200dma": bool(last > c.tail(200).mean()) if len(c) >= 200 else None,
        "volatility": float(c.pct_change().tail(63).std() * np.sqrt(252)),
    }


def flags(t: dict) -> list[str]:
    f = []
    if t["vol_ratio"] >= 2:
        f.append(f"Unusual volume {t['vol_ratio']:.1f}x")
    if abs(t["gap"]) >= 0.03:
        f.append(f"Gap {'up' if t['gap'] > 0 else 'down'} {t['gap']:+.1%}")
    if t["pct_from_high"] >= -0.01:
        f.append("At 52-week high")
    if t["pct_from_low"] <= 0.01:
        f.append("At 52-week low")
    if t["rsi"] >= 70:
        f.append(f"Overbought RSI {t['rsi']:.0f}")
    if t["rsi"] <= 30:
        f.append(f"Oversold RSI {t['rsi']:.0f}")
    if abs(t["chg_1d"]) >= 0.05:
        f.append(f"Big move {t['chg_1d']:+.1%}")
    return f


def sector_rotation(table: pd.DataFrame) -> pd.DataFrame:
    """Average 1m vs 3m returns by sector: who is gaining leadership."""
    g = table.dropna(subset=["sector"]).groupby("sector")[["chg_1m", "chg_3m"]].mean()
    g["acceleration"] = g["chg_1m"] - g["chg_3m"] / 3
    return g.sort_values("acceleration", ascending=False)
