"""Merger arb desk math and deal validation. Pure functions: no network, no files.

Definitions (also shown on site/arb.html under "How to read this"):
- offer value      = cash per share + exchange ratio x acquirer price (a CVR is noted as text, never valued)
- gross spread     = (offer value - target price) / target price
- annualized       = gross spread x 365 / days to the stated expected close (simple, not compounded);
                     None when the close date is unknown or already past
- implied chance   = (target price - unaffected price) / (offer value - unaffected price), clipped to [0, 1].
                     Rough: it assumes the target falls back to its unaffected price if the deal breaks.
Not investment advice.
"""
from __future__ import annotations

import re
from datetime import date

# Every deal term in data/arb/deals.json is a "fact": {value, source_url, as_of, verified, note?}.
TERM_FIELDS = ("acquirer", "acquirer_ticker", "target", "target_ticker", "cash_per_share", "exchange_ratio",
               "cvr", "agreement_date", "announce_date", "announced_after_close", "expected_close", "unaffected_price")
STEP_STATUS = ("open", "done")
DEAL_STATUS = ("pending",)
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def unaffected_date(announce: date | str, after_close: bool, trading_days) -> date:
    """The session whose close is the unaffected price: the announcement day itself when the deal was announced after
    that day's close, otherwise the last trading day before the announcement. `trading_days` is any iterable of dates
    with a close (for example the target's price history index)."""
    if isinstance(announce, str):
        announce = date.fromisoformat(announce)
    days = sorted(d for d in trading_days if (d <= announce if after_close else d < announce))
    if not days:
        raise ValueError(f"no trading day on or before {announce}")
    return days[-1]


def offer_value(cash: float | None, ratio: float | None, acquirer_price: float | None) -> float | None:
    """Cash plus ratio times the acquirer's price. None when nothing is known, or a stock leg has no price."""
    if cash is None and ratio is None:
        return None
    total = float(cash or 0.0)
    if ratio:
        if acquirer_price is None:
            return None
        total += float(ratio) * float(acquirer_price)
    return total


def gross_spread(price: float | None, offer: float | None) -> float | None:
    """(offer - price) / price as a fraction. Negative when the target trades above the offer."""
    if price is None or offer is None or price <= 0:
        return None
    return (offer - price) / price


def days_to_close(close: date | str | None, today: date) -> int | None:
    if close is None:
        return None
    if isinstance(close, str):
        close = date.fromisoformat(close)
    return (close - today).days


def annualized_spread(spread: float | None, days: int | None) -> float | None:
    """Simple annualization to the stated close. None when the close date is unknown or not in the future."""
    if spread is None or days is None or days <= 0:
        return None
    return spread * 365.0 / days


def implied_close_chance(price: float | None, offer: float | None, unaffected: float | None) -> float | None:
    """(price - unaffected) / (offer - unaffected), clipped to [0, 1]. None when offer equals unaffected."""
    if price is None or offer is None or unaffected is None:
        return None
    if abs(offer - unaffected) < 1e-12:
        return None
    x = (price - unaffected) / (offer - unaffected)
    return max(0.0, min(1.0, x))


def _fact_errors(where: str, f) -> list[str]:
    if not isinstance(f, dict):
        return [f"{where}: missing"]
    out = []
    if "value" not in f:
        out.append(f"{where}: no value key")
    if not isinstance(f.get("source_url"), str) or not f["source_url"].startswith("https://"):
        out.append(f"{where}: source_url missing or not https")
    if not isinstance(f.get("as_of"), str) or not _ISO.match(f["as_of"]):
        out.append(f"{where}: as_of missing or not YYYY-MM-DD")
    if not isinstance(f.get("verified"), bool):
        out.append(f"{where}: verified must be true or false")
    elif f["verified"] is False and not f.get("note"):
        out.append(f"{where}: unverified facts need a note")
    return out


def validate_deal(d: dict) -> list[str]:
    """Problems with one deal (empty list when it is fine)."""
    name = d.get("id", "?")
    errs = []
    if d.get("status") not in DEAL_STATUS:
        errs.append(f"{name}: status must be one of {DEAL_STATUS}")
    for k in TERM_FIELDS:
        errs += _fact_errors(f"{name}.{k}", d.get(k))
    cash, ratio = (d.get("cash_per_share") or {}).get("value"), (d.get("exchange_ratio") or {}).get("value")
    if cash is None and ratio is None:
        errs.append(f"{name}: needs cash_per_share or exchange_ratio (use a verified false fact with a note if unknown)")
    if ratio and not (d.get("acquirer_ticker") or {}).get("value"):
        errs.append(f"{name}: a stock deal needs the acquirer ticker for pricing")
    if not isinstance((d.get("announced_after_close") or {}).get("value"), bool):
        errs.append(f"{name}.announced_after_close must be true or false")
    ud = (d.get("unaffected_price") or {}).get("date")
    if not (isinstance(ud, str) and _ISO.match(ud)):
        errs.append(f"{name}.unaffected_price.date must be YYYY-MM-DD")
    ec = d.get("expected_close") or {}
    if ec.get("by_date") is not None and not (isinstance(ec["by_date"], str) and _ISO.match(ec["by_date"])):
        errs.append(f"{name}.expected_close.by_date must be YYYY-MM-DD or null")
    steps = d.get("steps")
    if not isinstance(steps, list) or not steps:
        errs.append(f"{name}: steps missing")
    else:
        for i, s in enumerate(steps):
            w = f"{name}.steps[{i}]"
            if not s.get("name"):
                errs.append(f"{w}: no name")
            if s.get("status") not in STEP_STATUS:
                errs.append(f"{w}: status must be open or done")
            errs += _fact_errors(w, {"value": s.get("status"), **s})
    return errs


def validate_book(book: dict) -> list[str]:
    errs, seen = [], set()
    for d in book.get("deals", []):
        if d.get("id") in seen:
            errs.append(f"duplicate id {d.get('id')}")
        seen.add(d.get("id"))
        errs += validate_deal(d)
    return errs


def _r(x, n):
    return None if x is None else round(x, n)


def compute(d: dict, target_price: float | None, acquirer_price: float | None, today: date) -> dict:
    """One row for site/data/arb.json."""
    v = lambda k: (d.get(k) or {}).get("value")
    cash, ratio, unaff = v("cash_per_share"), v("exchange_ratio"), v("unaffected_price")
    offer = offer_value(cash, ratio, acquirer_price)
    spread = gross_spread(target_price, offer)
    days = days_to_close((d.get("expected_close") or {}).get("by_date"), today)
    return {
        "target_price": _r(target_price, 4), "acquirer_price": _r(acquirer_price, 4) if ratio else None,
        "offer_value": _r(offer, 4), "spread_usd": _r(None if offer is None or target_price is None else offer - target_price, 4),
        "spread": _r(spread, 6), "days_to_close": days, "annualized": _r(annualized_spread(spread, days), 6),
        "implied_chance": _r(implied_close_chance(target_price, offer, unaff), 4),
        "open_steps": sum(1 for s in d.get("steps", []) if s.get("status") == "open"),
        "kind": "cash" if cash and not ratio else "stock" if ratio and not cash else "mixed" if cash and ratio else "unknown",
    }
