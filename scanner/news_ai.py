"""News sentiment and the analyst write-up.

Without an API key it uses a fast keyword sentiment model. With
ANTHROPIC_API_KEY set, Claude reads the numbers plus headlines and writes a
real analyst thesis (why it looks mispriced, catalysts, risks, a Bullish/Bearish/Neutral label).
"""
from __future__ import annotations

import json
import os
import re

from .labels import BEARISH, BULLISH, NEUTRAL, normalize

POS = {"beat", "beats", "raise", "raises", "raised", "upgrade", "upgraded", "record", "surge", "soar",
       "growth", "strong", "buyback", "outperform", "approval", "approved", "wins", "expands", "profit",
       "partnership", "rally", "jumps", "bullish", "accelerat", "tops"}
NEG = {"miss", "misses", "cut", "cuts", "downgrade", "downgraded", "lawsuit", "probe", "investigation",
       "recall", "plunge", "slump", "weak", "warns", "warning", "layoff", "layoffs", "fraud", "decline",
       "falls", "drops", "bearish", "tariff", "delay", "loss", "sinks", "underperform", "halt"}

MODEL = os.getenv("SCANNER_MODEL", "claude-sonnet-5-5")


def headline_sentiment(headlines: list[dict]) -> float:
    """-1..+1 average keyword sentiment."""
    scores = []
    for h in headlines:
        words = re.findall(r"[a-z]+", f"{h.get('title', '')} {h.get('summary', '')}".lower())
        p = sum(any(w.startswith(k) for k in POS) for w in words)
        n = sum(any(w.startswith(k) for k in NEG) for w in words)
        if p or n:
            scores.append((p - n) / (p + n))
    return round(sum(scores) / len(scores), 2) if scores else 0.0


def rule_based_call(row: dict, sentiment: float) -> dict:
    m = row.get("mispricing", 0) or 0
    adj = m + sentiment * 20
    if adj >= 35:
        call = BULLISH
    elif adj <= -35:
        call = BEARISH
    else:
        call = NEUTRAL
    conf = min(95, int(40 + abs(adj) * 0.6 * (row.get("coverage") or 0.5)))
    reasons = list(row.get("valuation_reasons") or [])
    if sentiment >= 0.3:
        reasons.append("News flow is positive")
    elif sentiment <= -0.3:
        reasons.append("News flow is negative, check whether it is already priced in")
    thesis = "; ".join(reasons) or "No strong valuation or news signal."
    return {"call": call, "confidence": conf, "thesis": thesis, "catalysts": "", "risks": "", "source": "rules"}


def ai_call(row: dict, headlines: list[dict]) -> dict | None:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    fields = ["shortName", "sector", "price", "forwardPE", "trailingPE", "enterpriseToEbitda", "fcf_yield",
              "returnOnEquity", "revenueGrowth", "analyst_upside", "chg_1m", "chg_3m", "rsi", "mispricing"]
    facts = {k: row.get(k) for k in fields}
    news = "\n".join(f"- {h['title']} ({h.get('publisher', '')})" for h in headlines[:8]) or "none"
    prompt = (
        "You are a sharp equity analyst. Using ONLY the data and headlines below, decide whether this stock "
        "is mispriced and why. Be specific and skeptical, consider whether news is already priced in.\n\n"
        f"Ticker: {row.get('ticker')}\nData: {json.dumps(facts, default=str)}\n"
        f"Model notes: {row.get('valuation_reasons')}\nHeadlines:\n{news}\n\n"
        'Reply with JSON only: {"call": "Bullish|Bearish|Neutral", "confidence": 0-100, '
        '"thesis": "2-3 sentences on why, plain words, no advice wording", "catalysts": "short", "risks": "short"}'
    )
    try:
        msg = anthropic.Anthropic(api_key=key).messages.create(
            model=MODEL, max_tokens=500, messages=[{"role": "user", "content": prompt}])
        text = msg.content[0].text
        out = json.loads(text[text.find("{"): text.rfind("}") + 1])
        out["call"] = normalize(out.get("call"))  # also accepts legacy BUY/SELL/WATCH
        out["source"] = "ai"
        return out
    except Exception:
        return None


def analyze(row: dict, headlines: list[dict]) -> dict:
    sentiment = headline_sentiment(headlines)
    result = ai_call(row, headlines) or rule_based_call(row, sentiment)
    result["sentiment"] = sentiment
    result["headlines"] = headlines
    return result
