"""Daily merger arb refresh: data/arb/deals.json + latest Yahoo prices -> site/data/arb.json.

    python scripts/refresh_arb.py

Prices: the last daily close (yfinance, unadjusted) for every target and for the acquirer of every stock deal.
On any failure (deal file invalid, price download failed, a target without a price) it prints the reason to stderr,
leaves the last good site/data/arb.json untouched and exits 1, so the workflow step fails and GitHub emails the owner.
The scan watchdog (scanner/watchdog.py) also flags site/data/arb.json when its prices fall behind.
Not investment advice.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scanner import arb  # noqa: E402

DEALS = ROOT / "data" / "arb" / "deals.json"
OUT = ROOT / "site" / "data" / "arb.json"
DISCLAIMER = ("Not investment advice. Spreads and the implied chance are mechanical arithmetic on public prices and filed "
              "terms, not forecasts or recommendations. Prices can be delayed or wrong.")


class RefreshError(Exception):
    pass


def tickers_needed(book: dict) -> list[str]:
    out = set()
    for d in book["deals"]:
        out.add(d["target_ticker"]["value"])
        if d["exchange_ratio"]["value"]:
            out.add(d["acquirer_ticker"]["value"])
    return sorted(out)


def yahoo_closes(tickers: list[str]) -> dict[str, tuple[str, float]]:
    """{ticker: (date, close)} from the last 10 trading days."""
    import yfinance as yf

    raw = yf.download(tickers, period="10d", interval="1d", auto_adjust=False, progress=False, threads=True,
                      group_by="ticker", timeout=60)
    out = {}
    for t in tickers:
        try:
            s = (raw[t] if len(tickers) > 1 else raw)["Close"].dropna()
            if hasattr(s, "columns"):  # newer yfinance keeps a ticker level even for one name
                s = s.iloc[:, 0].dropna()
        except KeyError:
            continue
        if len(s):
            out[t] = (s.index[-1].date().isoformat(), float(s.iloc[-1]))
    return out


def public_deal(d: dict) -> dict:
    """The deal as the page shows it: every fact keeps its source_url, as_of and verified flag."""
    keep = ("id", "status") + arb.TERM_FIELDS + ("steps", "proxy_url")
    return {k: d[k] for k in keep if k in d}


def build(book: dict, closes: dict[str, tuple[str, float]], today: date, now: datetime | None = None) -> dict:
    errs = arb.validate_book(book)
    if errs:
        raise RefreshError("deals.json is invalid: " + "; ".join(errs[:5]))
    rows, dates = [], []
    for d in book["deals"]:
        t = d["target_ticker"]["value"]
        if t not in closes:
            raise RefreshError(f"no price for target {t}")
        a = d["acquirer_ticker"]["value"] if d["exchange_ratio"]["value"] else None
        if a and a not in closes:
            raise RefreshError(f"no price for acquirer {a} ({t} is a stock deal)")
        for tk in (t, a) if a else (t,):
            px = closes[tk][1]
            if not isinstance(px, (int, float)) or not math.isfinite(px) or px <= 0:
                raise RefreshError(f"bad price for {tk}: {px!r}")
        if a and closes[a][0] != closes[t][0]:
            # a stock deal's offer value must use the acquirer's close from the same session as the target's
            raise RefreshError(f"price dates differ for {t} ({closes[t][0]}) and acquirer {a} ({closes[a][0]})")
        dates.append(closes[t][0])
        row = public_deal(d)
        row["calc"] = arb.compute(d, closes[t][1], closes[a][1] if a else None, today)
        row["calc"]["price_date"] = closes[t][0]
        rows.append(row)
    now = now or datetime.now(timezone.utc)
    return {"as_of": max(dates) if dates else None, "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "deals_as_of": book.get("as_of"), "about": book.get("about"), "close_date_rule": book.get("close_date_rule"),
            "unaffected_rule": book.get("unaffected_rule"), "disclaimer": DISCLAIMER, "deals": rows}


def main(argv=None, fetch=yahoo_closes, out: Path = OUT, deals: Path = DEALS) -> int:
    try:
        book = json.loads(deals.read_text())
        try:
            closes = fetch(tickers_needed(book))
        except Exception as e:  # network, Yahoo or parsing trouble
            raise RefreshError(f"price download failed: {e}") from e
        page = build(book, closes, date.today())
    except (RefreshError, OSError, ValueError, KeyError) as e:
        print(f"Arb refresh failed: {e}. site/data/arb.json was not changed.", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(page, indent=1, allow_nan=False) + "\n"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(text)
    os.replace(tmp, out)  # atomic: a crash never leaves a half-written arb.json
    print(f"arb.json: {len(page['deals'])} deals, prices as of {page['as_of']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
