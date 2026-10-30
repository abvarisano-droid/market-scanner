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


def prices(tickers: list[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    """Daily OHLCV per ticker."""
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), 100):
        chunk = tickers[i:i + 100]
        raw = yf.download(chunk, period=period, interval="1d", group_by="ticker",
                          auto_adjust=True, progress=False, threads=True)
        for t in chunk:
            try:
                df = raw[t] if len(chunk) > 1 else raw
                df = df.dropna(how="all")
                if len(df) > 30:
                    out[t] = df
            except KeyError:
                continue
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


def fundamentals(tickers: list[str], workers: int = 8) -> pd.DataFrame:
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
