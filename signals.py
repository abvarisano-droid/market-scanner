"""Pure scoring rules. Input: DataFrame with columns date, open, high, low, close, volume.

Every rule returns Rule(score 0..1, weight, text). A horizon score is 100 * weighted mean.
"""
from typing import NamedTuple, Optional
import numpy as np
import pandas as pd

BULL, BEAR = 65, 35
MIN_SHORT, MIN_SWING = 30, 252


class Rule(NamedTuple):
    score: float  # 0 bearish .. 1 bullish
    weight: float
    text: str


def clip01(x):
    return float(min(1.0, max(0.0, x)))


def label(score: float) -> str:
    if score >= BULL:
        return "Bullish"
    if score <= BEAR:
        return "Bearish"
    return "Neutral"


def rsi(close: pd.Series, n=14) -> float:
    """Wilder RSI: smoothing alpha 1/n (ewm, seeded from the first change, not an SMA)."""
    d = close.diff().dropna()
    if len(d) < n:
        return float("nan")
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    if l == 0:
        return 100.0 if g > 0 else 50.0
    return float(100 - 100 / (1 + g / l))


def pct(a, b):
    return a / b - 1


def _side(x, up, down):
    return up if x >= 0 else down


# ---- short-term rules -------------------------------------------------------
def rule_ma20(close: pd.Series) -> Rule:
    p = pct(close.iloc[-1], close.tail(20).mean())
    return Rule(clip01(0.5 + p / 0.10), 0.30,
                f"Price is {abs(p)*100:.1f}% {_side(p, 'above', 'below')} its 20-day average")


def rule_momentum(close: pd.Series) -> Rule:
    r5, r10 = pct(close.iloc[-1], close.iloc[-6]), pct(close.iloc[-1], close.iloc[-11])
    s = (clip01(0.5 + r5 / 0.06) + clip01(0.5 + r10 / 0.10)) / 2
    return Rule(s, 0.30, f"Momentum: {r5*100:+.1f}% over 5 days, {r10*100:+.1f}% over 10 days")


def rule_rsi(close: pd.Series) -> Rule:
    v = rsi(close)
    note = " (stretched)" if v >= 70 else " (washed out)" if v <= 30 else ""
    return Rule(clip01((v - 30) / 40), 0.20, f"RSI(14) is {v:.0f}{note}")


def rule_volume(df: pd.DataFrame) -> Rule:
    ratio = df["volume"].iloc[-1] / max(df["volume"].tail(20).mean(), 1)
    day = pct(df["close"].iloc[-1], df["close"].iloc[-2])
    sign = 1 if day >= 0 else -1
    s = clip01(0.5 + sign * clip01(ratio - 1) * 0.5)
    return Rule(s, 0.20, f"Volume is {ratio:.1f}x its 20-day average on a {_side(day, 'up', 'down')} day")


# ---- swing rules ------------------------------------------------------------
def rule_ma50(close):
    p = pct(close.iloc[-1], close.tail(50).mean())
    return Rule(clip01(0.5 + p / 0.20), 0.20, f"Price is {abs(p)*100:.1f}% {_side(p, 'above', 'below')} its 50-day average")


def rule_ma200(close):
    p = pct(close.iloc[-1], close.tail(200).mean())
    return Rule(clip01(0.5 + p / 0.30), 0.20, f"Price is {abs(p)*100:.1f}% {_side(p, 'above', 'below')} its 200-day average")


def rule_slope(close):
    s50 = close.rolling(50).mean()
    s200 = close.rolling(200).mean()
    a = pct(s50.iloc[-1], s50.iloc[-21])
    b = pct(s200.iloc[-1], s200.iloc[-21])
    sc = (clip01(0.5 + a / 0.10) + clip01(0.5 + b / 0.06)) / 2
    return Rule(sc, 0.20, f"50-day average is {_side(a, 'rising', 'falling')} ({a*100:+.1f}%/month), 200-day is {_side(b, 'rising', 'falling')} ({b*100:+.1f}%/month)")


def rule_rs(close, spy_close):
    r = pct(close.iloc[-1], close.iloc[-64]) - pct(spy_close.iloc[-1], spy_close.iloc[-64])
    return Rule(clip01(0.5 + r / 0.30), 0.25,
                f"3-month return is {abs(r)*100:.1f} points {_side(r, 'ahead of', 'behind')} the S&P 500")


def rule_high52(close):
    d = pct(close.iloc[-1], close.tail(252).max())
    return Rule(clip01(1 + d / 0.30), 0.15, f"Price is {abs(d)*100:.1f}% below its 52-week high" if d < -0.0005 else "Price is at its 52-week high")


# ---- horizon assembly -------------------------------------------------------
def _assemble(rules) -> dict:
    total_w = sum(r.weight for r in rules)
    score = round(100 * sum(r.score * r.weight for r in rules) / total_w, 1)
    lab = label(score)
    # reasons: strongest pull away from neutral first, weighted
    ranked = sorted(rules, key=lambda r: abs(r.score - 0.5) * r.weight, reverse=True)
    return {"score": score, "label": lab, "reasons": [r.text for r in ranked[:3]]}


def short_term(df: pd.DataFrame) -> Optional[dict]:
    if df is None or len(df) < MIN_SHORT:
        return None
    c = df["close"].reset_index(drop=True)
    d = df.reset_index(drop=True)
    return _assemble([rule_ma20(c), rule_momentum(c), rule_rsi(c), rule_volume(d)])


def swing(df: pd.DataFrame, spy: pd.DataFrame) -> Optional[dict]:
    if df is None or spy is None or len(df) < MIN_SWING or len(spy) < 64:
        return None
    c = df["close"].reset_index(drop=True)
    # relative strength compares the same calendar dates for stock and SPY
    m = df[["date", "close"]].merge(spy[["date", "close"]], on="date", suffixes=("", "_spy"))
    if len(m) < 64:
        return None
    return _assemble([rule_ma50(c), rule_ma200(c), rule_slope(c),
                      rule_rs(m["close"].reset_index(drop=True), m["close_spy"].reset_index(drop=True)),
                      rule_high52(c)])
