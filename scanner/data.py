"""Market data fetching (Yahoo Finance via yfinance) with a simple disk cache."""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"

FUNDAMENTAL_FIELDS = [
    "shortName", "sector", "industry", "country", "currency", "marketCap",
    "trailingPE", "forwardPE", "priceToBook", "enterpriseToEbitda", "pegRatio",
    "freeCashflow", "profitMargins", "revenueGrowth", "earningsGrowth", "returnOnEquity",
    "debtToEquity", "targetMeanPrice", "recommendationMean", "numberOfAnalystOpinions",
    "currentPrice", "shortPercentOfFloat",
]


CHUNK = 250            # tickers per yf.download call
DOWNLOAD_TIMEOUT = 60  # seconds per call (passed to yfinance)
DOWNLOAD_BUDGET = 25 * 60  # stop starting new chunks after this many seconds in total


def _split(raw: pd.DataFrame, chunk: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    multi = isinstance(raw.columns, pd.MultiIndex)
    for t in chunk:
        try:
            df = raw[t] if multi else raw
            df = df.dropna(how="all")
        except KeyError:
            continue
        if len(df) > 30:
            out[t] = df
    return out


def prices(tickers: list[str], period: str = "1y", chunk_size: int = CHUNK,
           budget: float = DOWNLOAD_BUDGET) -> dict[str, pd.DataFrame]:
    """Daily OHLCV per ticker, downloaded in batches with threads, a per-call timeout and one retry.

    A failed batch is logged and skipped (those tickers count as "no data"), and no new batch starts
    once the total time budget is spent, so a slow Yahoo day cannot hang the nightly job.
    """
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    start = time.monotonic()
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        if time.monotonic() - start > budget:
            log.warning("download budget spent, skipping %d tickers", len(tickers) - i)
            break
        for attempt in (1, 2):
            try:
                raw = yf.download(chunk, period=period, interval="1d", group_by="ticker", auto_adjust=True,
                                  progress=False, threads=True, timeout=DOWNLOAD_TIMEOUT)
                out.update(_split(raw, chunk))
                break
            except Exception as exc:
                log.warning("batch %d-%d attempt %d failed: %s", i, i + len(chunk), attempt, exc)
    return out


def _info(ticker: str) -> dict:
    import yfinance as yf

    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"info_{ticker}.json"
    if f.exists() and time.time() - f.stat().st_mtime < 20 * 3600:
        return json.loads(f.read_text())
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        log.debug("info %s failed: %s", ticker, exc)
        info = {}
    row = {k: info.get(k) for k in FUNDAMENTAL_FIELDS}
    f.write_text(json.dumps(row))
    return row


def fundamentals(tickers: list[str], workers: int = 16) -> pd.DataFrame:
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(_info, tickers))
    return pd.DataFrame(rows, index=tickers)


def news(ticker: str, limit: int = 8) -> list[dict]:
    """Recent headlines: [{title, publisher, link, time}]."""
    import yfinance as yf

    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        return []
    out = []
    for it in items[:limit]:
        c = it.get("content", it)  # yfinance changed shape over versions
        out.append({
            "title": c.get("title", ""),
            "summary": c.get("summary", "") or "",
            "publisher": (c.get("provider") or {}).get("displayName", c.get("publisher", "")),
            "link": ((c.get("canonicalUrl") or {}).get("url") or c.get("link", "")),
            "time": c.get("pubDate") or c.get("providerPublishTime"),
        })
    return out


def earnings_dates(ticker: str, timeout: float = 10) -> list:
    """Published upcoming earnings date(s) from the Yahoo Finance calendar (may be empty or change).

    yfinance's calendar call takes no timeout argument, so it runs in a worker thread and is
    abandoned after `timeout` seconds (an empty list), so one slow ticker cannot stall the export."""
    import yfinance as yf
    from concurrent.futures import TimeoutError as FutTimeout

    ex = ThreadPoolExecutor(max_workers=1)
    try:
        cal = ex.submit(lambda: yf.Ticker(ticker).calendar).result(timeout=timeout) or {}
    except FutTimeout:
        log.warning("earnings calendar for %s timed out after %ss", ticker, timeout)
        return []
    finally:
        ex.shutdown(wait=False)
    return list(cal.get("Earnings Date") or []) if isinstance(cal, dict) else []
