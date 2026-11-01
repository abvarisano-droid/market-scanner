"""News sentiment and the analyst write-up.

Without an API key it uses a fast keyword sentiment model. With
ANTHROPIC_API_KEY set, Claude reads the numbers plus headlines and writes a
real analyst thesis (why it looks mispriced, catalysts, risks, a Bullish/Bearish/Neutral label).
"""
from __future__ import annotations

import json
import logging
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
log = logging.getLogger(__name__)


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


# ---- AI thesis (Claude API) -------------------------------------------------------------------
# One short structured call per mispricing pick (about 18 a night). Settings, checked against the Claude API
# reference on 2026-11-01:
# * Sonnet 5.5 runs adaptive thinking by default, so the reply starts with a thinking block and the JSON is in a
#   later text block. The old code read content[0].text, which raised on the thinking block, and every call fell
#   back to the rules model without a word. The text block is now found by type.
# * effort "low": a short classification-style answer, not a hard reasoning task. max_tokens 2000 leaves room for
#   thinking plus the JSON (500 could cut the reply off mid-JSON).
# * output_config.format: a JSON schema, so the reply is always parseable JSON.
# * fallbacks "default": if the model declines on a safety classifier, the API reruns the request on a fallback
#   model inside the same call. Turned off for the rest of the run if the API rejects the parameter.
# * Prompt caching: the fixed instructions sit in the system prompt, but they are about 200 tokens, under the
#   512 token minimum, so nothing is cached and no cache_control is sent. Per-ticker data changes every call.
# Every call's tokens and estimated cost go to USAGE, which the pipeline writes to data/ai_usage.json. Key values
# are never logged, only whether a key is present.
MAX_TOKENS = 2000
EFFORT = "low"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# USD per million tokens: input, output, cache read, 5 minute cache write (Claude API list prices, 2026-10-06)
PRICES = {"claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50), "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
          "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125)}
PROPOSED_CAP_USD = 0.50  # proposed per-run cap (about 5x the expected cost). Not enabled: set AI_RUN_COST_CAP_USD to use.
KEEP_RUNS = 120

SYSTEM = (
    "You are a skeptical equity analyst writing for a public stock scanner that grades its own calls. "
    "Using ONLY the data and headlines in the user message, decide whether the stock looks mispriced and why. "
    "Be specific, consider whether the news is already priced in, and say when the data is thin. "
    "Label the setup Bullish, Bearish or Neutral. Never give advice: do not use the words buy, sell, rating or "
    "price target, and do not name a price. thesis: 2 to 3 plain sentences. catalysts and risks: one short line each. "
    "confidence: 0 to 100."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "call": {"type": "string", "enum": [BULLISH, BEARISH, NEUTRAL]},
        "confidence": {"type": "integer"},
        "thesis": {"type": "string"},
        "catalysts": {"type": "string"},
        "risks": {"type": "string"},
    },
    "required": ["call", "confidence", "thesis", "catalysts", "risks"],
    "additionalProperties": False,
}

USAGE: dict = {}
_STATE = {"fallbacks": True}


def _cap() -> float | None:
    try:
        v = float(os.getenv("AI_RUN_COST_CAP_USD") or "")
    except ValueError:
        return None
    return v if v > 0 else None


def start_run() -> dict:
    """Reset the per-run counters (the pipeline calls this once before the picks)."""
    USAGE.clear()
    USAGE.update(model=MODEL, key_present=bool(os.getenv("ANTHROPIC_API_KEY")), calls=0, ok=0, skipped=0, errors={},
                 input_tokens=0, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0,
                 cost_usd=0.0, cap_usd=_cap(), stopped=None)
    _STATE["fallbacks"] = True
    return USAGE


def cost_usd(model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0) -> float | None:
    p = PRICES.get(model)
    if p is None:
        return None
    return (inp * p[0] + out * p[1] + cache_read * p[2] + cache_write * p[3]) / 1e6


def _err(kind: str) -> None:
    USAGE["errors"][kind] = USAGE["errors"].get(kind, 0) + 1


def _count(msg) -> None:
    u = getattr(msg, "usage", None)
    if u is None:
        return
    vals = {k: int(getattr(u, k, 0) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                     "cache_creation_input_tokens")}
    for k, v in vals.items():
        USAGE[k] += v
    c = cost_usd(MODEL, vals["input_tokens"], vals["output_tokens"], vals["cache_read_input_tokens"],
                 vals["cache_creation_input_tokens"])
    if c is not None:
        USAGE["cost_usd"] += c


def _request(row: dict, headlines: list[dict]) -> dict:
    fields = ["shortName", "sector", "price", "forwardPE", "trailingPE", "enterpriseToEbitda", "fcf_yield",
              "returnOnEquity", "revenueGrowth", "analyst_upside", "chg_1m", "chg_3m", "rsi", "mispricing"]
    facts = {k: row.get(k) for k in fields}
    news = "\n".join(f"- {h['title']} ({h.get('publisher', '')})" for h in headlines[:8]) or "none"
    prompt = (f"Ticker: {row.get('ticker')}\nData: {json.dumps(facts, default=str, sort_keys=True)}\n"
              f"Model notes: {row.get('valuation_reasons')}\nHeadlines:\n{news}")
    return {"model": MODEL, "max_tokens": MAX_TOKENS, "system": SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}}}


def _send(client, req: dict):
    import anthropic
    if _STATE["fallbacks"]:
        try:
            return client.beta.messages.create(**req, betas=[FALLBACK_BETA], fallbacks="default")
        except anthropic.BadRequestError:
            # most likely the fallback parameter itself was refused: retry once without it, and stop sending it
            _STATE["fallbacks"] = False
            _err("fallbacks_rejected")
    return client.messages.create(**req)


def ai_call(row: dict, headlines: list[dict], client=None) -> dict | None:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    if not USAGE:
        start_run()
    if USAGE["stopped"] or (USAGE["cap_usd"] is not None and USAGE["cost_usd"] >= USAGE["cap_usd"]):
        USAGE["skipped"] += 1
        if not USAGE["stopped"]:
            USAGE["stopped"] = "cost cap reached"
        return None
    client = client or anthropic.Anthropic(api_key=key)
    USAGE["calls"] += 1
    try:
        msg = _send(client, _request(row, headlines))
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError) as exc:
        kind = {anthropic.AuthenticationError: "auth", anthropic.PermissionDeniedError: "permission",
                anthropic.NotFoundError: "not_found"}[type(exc)]
        _err(kind)
        USAGE["stopped"] = kind  # these will fail for every ticker: stop paying for attempts this run
        log.warning("AI thesis off for this run: %s error (status %s)", kind, getattr(exc, "status_code", "?"))
        return None
    except anthropic.RateLimitError:
        _err("rate_limit")  # the SDK already retried twice
        return None
    except anthropic.APIStatusError as exc:
        _err(f"http_{exc.status_code}")
        return None
    except anthropic.APIConnectionError:
        _err("connection")
        return None
    _count(msg)
    if msg.stop_reason != "end_turn":
        _err(msg.stop_reason or "unknown_stop")  # max_tokens, refusal, ...: the rules model writes this one
        return None
    text = next((b.text for b in msg.content if getattr(b, "type", None) == "text"), "")
    try:
        out = json.loads(text)
    except ValueError:
        _err("bad_json")
        return None
    out["call"] = normalize(out.get("call"))  # also accepts legacy BUY/SELL/WATCH
    try:
        out["confidence"] = max(0, min(100, int(out.get("confidence") or 0)))
    except (TypeError, ValueError):
        out["confidence"] = None
    out["source"] = "ai"
    USAGE["ok"] += 1
    return out


def save_usage(path, date: str, run_id: str) -> dict:
    """Append this run's AI token and cost totals to a JSON log (kept to the last KEEP_RUNS runs)."""
    from pathlib import Path
    path = Path(path)
    u = USAGE or start_run()
    rec = {"date": date, "run_id": str(run_id), **{k: u[k] for k in (
        "model", "key_present", "calls", "ok", "skipped", "errors", "input_tokens", "output_tokens",
        "cache_read_input_tokens", "cache_creation_input_tokens", "cap_usd", "stopped")},
        "cost_usd": round(u["cost_usd"], 6)}
    try:
        old = json.loads(path.read_text())
        runs = [r for r in old.get("runs", []) if (r.get("date"), r.get("run_id")) != (date, str(run_id))]
    except (OSError, ValueError):
        runs = []
    runs = (runs + [rec])[-KEEP_RUNS:]
    body = {"model": MODEL, "prices_per_mtok": dict(zip(("input", "output", "cache_read", "cache_write_5m"),
                                                         PRICES.get(MODEL, (None,) * 4))),
            "proposed_cap_usd_per_run": PROPOSED_CAP_USD, "cap_enabled": u["cap_usd"] is not None,
            "note": "Estimated from response usage and list prices; the Claude Console bill is the source of truth.",
            "runs": runs}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1) + "\n")
    return body


def analyze(row: dict, headlines: list[dict]) -> dict:
    sentiment = headline_sentiment(headlines)
    result = ai_call(row, headlines) or rule_based_call(row, sentiment)
    result["sentiment"] = sentiment
    result["headlines"] = headlines
    return result
