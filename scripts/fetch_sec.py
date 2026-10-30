"""Fetch SEC companyfacts JSON for the S&P 500 into data/cache/sec/ (git-ignored).

Needs a contact User-Agent in the SEC_USER_AGENT environment variable, as the SEC requires.
Never hardcode a contact. Rate limited to 8 requests a second. Already cached files are skipped.
    SEC_USER_AGENT="<name and contact email>" python scripts/fetch_sec.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "sec"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
MAX_RPS = 8


class Limiter:
    def __init__(self, rps: float = MAX_RPS, clock=time.monotonic, sleep=time.sleep):
        self.gap, self.clock, self.sleep, self.last = 1.0 / rps, clock, sleep, None

    def wait(self) -> None:
        now = self.clock()
        if self.last is not None and now - self.last < self.gap:
            self.sleep(self.gap - (now - self.last))
            now = self.clock()
        self.last = now


def sp500_tickers() -> list[str]:
    lat = json.loads((ROOT / "site" / "data" / "latest.json").read_text())
    return sorted(t for t, r in lat["lookup"].items() if r.get("i") == "S&P 500")


def get_json(session, url: str, limiter: Limiter, tries: int = 4):
    for i in range(tries):
        limiter.wait()
        r = session.get(url, timeout=60)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            limiter.sleep(2 ** i)
            continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
    return None


def ticker_map(session, limiter: Limiter, cache: Path = CACHE) -> dict[str, int]:
    f = cache / "company_tickers.json"
    if f.exists():
        raw = json.loads(f.read_text())
    else:
        raw = get_json(session, TICKERS_URL, limiter)
        cache.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(raw))
    return {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}


def fetch_all(tickers: list[str], session, cache: Path = CACHE, limiter: Limiter | None = None) -> dict:
    limiter = limiter or Limiter()
    cache.mkdir(parents=True, exist_ok=True)
    tmap = ticker_map(session, limiter, cache)
    got, missing = 0, []
    for t in tickers:
        cik = tmap.get(t.upper()) or tmap.get(t.upper().replace("-", "."))
        if not cik:
            missing.append(t)
            continue
        f = cache / f"CIK{cik:010d}.json"
        if f.exists():
            got += 1
            continue
        data = get_json(session, FACTS_URL.format(cik=cik), limiter)
        if data is None:
            missing.append(t)
            continue
        f.write_text(json.dumps(data))
        got += 1
    return {"fetched": got, "missing": missing, "ciks": {t: tmap.get(t.upper()) or tmap.get(t.upper().replace("-", ".")) for t in tickers}}


def main() -> int:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        print("Set SEC_USER_AGENT to a contact string (your name and contact email).", file=sys.stderr)
        return 2
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
    res = fetch_all(sp500_tickers(), s)
    print(f"cached {res['fetched']} companies, missing {len(res['missing'])}: {res['missing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
