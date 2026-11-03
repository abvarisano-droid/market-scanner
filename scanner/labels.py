"""Call labels. User-facing names are Bullish / Bearish / Neutral.

Older versions logged BUY / SELL / WATCH. Those values still load: normalize()
maps them to the new names so existing picks.csv rows keep working.
"""
from __future__ import annotations

import re

BULLISH, BEARISH, NEUTRAL = "Bullish", "Bearish", "Neutral"
LABELS = (BULLISH, BEARISH, NEUTRAL)
LEGACY = {"BUY": BULLISH, "SELL": BEARISH, "WATCH": NEUTRAL}
# Advice words that must never reach the public site or the call log (honesty rule: no buy, sell, rating or target
# language). One pattern, shared by the AI thesis check and both site exports.
BANNED = re.compile(r"\b(buy|buys|buying|sell|sells|selling|price targets?|ratings?|targets?)\b", re.I)
COLOR = {BULLISH: "#16a34a", BEARISH: "#dc2626", NEUTRAL: "#ca8a04"}


def normalize(label) -> str:
    """Map any current or legacy label (any case) to Bullish, Bearish or Neutral."""
    s = str(label or "").strip()
    if s.upper() in LEGACY:
        return LEGACY[s.upper()]
    for lab in LABELS:
        if s.lower() == lab.lower():
            return lab
    return NEUTRAL


def sign(label) -> int:
    lab = normalize(label)
    return 1 if lab == BULLISH else -1 if lab == BEARISH else 0


def round_price(x, sig: int = 4):
    """Round a share price for display: 2 decimals at $1 and up, at least `sig` significant
    figures below $1 (so a $0.112 stock is not shown as $0.11). None and non-finite give None."""
    import math
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    if x == 0 or abs(x) >= 1:
        return round(x, 2)
    return round(x, sig - 1 - int(math.floor(math.log10(abs(x)))))
