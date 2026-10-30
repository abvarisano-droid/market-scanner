"""Call labels. User-facing names are Bullish / Bearish / Neutral.

Older versions logged BUY / SELL / WATCH. Those values still load: normalize()
maps them to the new names so existing picks.csv rows keep working.
"""
from __future__ import annotations

BULLISH, BEARISH, NEUTRAL = "Bullish", "Bearish", "Neutral"
LABELS = (BULLISH, BEARISH, NEUTRAL)
LEGACY = {"BUY": BULLISH, "SELL": BEARISH, "WATCH": NEUTRAL}
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
