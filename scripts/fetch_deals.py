"""Find pending US public-company acquisitions on SEC EDGAR (merger arb desk candidates).

Two jobs:
  python scripts/fetch_deals.py               # candidates from full-text search -> data/cache/arb/candidates.json
  python scripts/fetch_deals.py --check       # is every deal in data/arb/deals.json still pending?
  python scripts/fetch_deals.py --terms       # also fetch each candidate's document and try to read its terms

Candidates come from EDGAR full-text search (efts.sec.gov) over the last 12 months: 8-K item 1.01 merger agreements,
DEFM14A, PREM14A, SC TO-T, S-4 and 425. Term parsing from filing text is best effort only: anything not parsed is None
(shown as Unknown). Nothing a script finds goes onto the page until a person checks it against the filing and adds it to
data/arb/deals.json with a source_url, as_of and verified flag on every term.

--check looks for a completion (Item 2.01) or termination (Item 1.02) 8-K filed by each target since its announce date
and exits 1 if it finds one, so a closed or broken deal is not left on the page.

User-Agent: SEC_USER_AGENT if set, otherwise a generic project string. No personal contact is ever put in code.
Rate: at most 8 requests a second (the SEC allows 10), using the limiter from scripts/fetch_sec.py.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fetch_sec import Limiter, get_json  # noqa: E402

DEALS = ROOT / "data" / "arb" / "deals.json"
OUT = ROOT / "data" / "cache" / "arb" / "candidates.json"
EFTS = "https://efts.sec.gov/LATEST/search-index"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
GENERIC_UA = "market-scanner research (github.com/abvarisano-droid/market-scanner)"
MAX_RPS = 8
# (query phrase, forms) pairs; the 8-K query keeps only hits that carry item 1.01
QUERIES = [
    ('"Agreement and Plan of Merger"', "8-K"),
    ('"Agreement and Plan of Merger"', "DEFM14A,PREM14A"),
    ('"Offer to Purchase"', "SC TO-T"),
    ('"Agreement and Plan of Merger"', "S-4,425"),
]
SPAC = re.compile(r"\bacquisition corp|\bspac\b|blank check|\bmerger corp\b", re.I)
_NAME = re.compile(r"^(?P<name>.*?)\s*(?:\((?P<tickers>[^)]*)\))?\s*\(CIK (?P<cik>\d+)\)\s*$")


def user_agent() -> str:
    return os.environ.get("SEC_USER_AGENT", "").strip() or GENERIC_UA


def search_url(q: str, forms: str, start: date, end: date, offset: int = 0) -> str:
    p = {"q": q, "forms": forms, "dateRange": "custom", "startdt": start.isoformat(), "enddt": end.isoformat()}
    if offset:
        p["from"] = offset
    return EFTS + "?" + urlencode(p)


def parse_display_name(s: str) -> dict:
    """'MARKETAXESS HOLDINGS INC  (MKTX)  (CIK 0001278021)' -> name, first ticker, cik."""
    m = _NAME.match(s.strip())
    if not m:
        return {"name": s.strip(), "ticker": None, "cik": None}
    tick = [t.strip() for t in (m.group("tickers") or "").split(",") if t.strip()]
    return {"name": m.group("name").strip(), "ticker": tick[0] if tick else None, "cik": int(m.group("cik"))}


def doc_url(cik: int, adsh: str, doc: str) -> str:
    return ARCHIVE.format(cik=cik, acc=adsh.replace("-", ""), doc=doc)


def candidates_from_hits(hits: list[dict], form_filter: str | None = None) -> list[dict]:
    """EFTS hits -> one candidate row per filing (first filer named). Drops SPACs and 8-Ks without item 1.01."""
    out, seen = [], set()
    for h in hits:
        src = h.get("_source", {})
        adsh, _, doc = h.get("_id", "").partition(":")
        if not adsh or adsh in seen:
            continue
        form = src.get("form") or src.get("root_form") or ""
        if form.startswith("8-K") and "1.01" not in (src.get("items") or []):
            continue
        names = src.get("display_names") or []
        if not names:
            continue
        who = parse_display_name(names[0])
        if who["cik"] is None or SPAC.search(who["name"]):
            continue
        seen.add(adsh)
        out.append({"cik": who["cik"], "name": who["name"], "ticker": who["ticker"], "form": form,
                    "file_date": src.get("file_date"), "adsh": adsh,
                    "url": doc_url(who["cik"], adsh, doc), "other_filers": [parse_display_name(n)["name"] for n in names[1:]]})
    return out


def merge_candidates(rows: list[dict]) -> list[dict]:
    """One row per company: the newest filing, plus every form type seen."""
    by = {}
    for r in sorted(rows, key=lambda r: r.get("file_date") or ""):
        cur = by.setdefault(r["cik"], {**r, "forms": []})
        cur.update({k: r[k] for k in ("form", "file_date", "adsh", "url")})
        if r["form"] not in cur["forms"]:
            cur["forms"].append(r["form"])
    return sorted(by.values(), key=lambda r: r["file_date"] or "", reverse=True)


# ---------- best-effort term parsing (never guessed: None when not found) ----------
_MONEY = r"\$\s?(\d{1,4}(?:,\d{3})*(?:\.\d{1,4})?)"
_CASH = [re.compile(_MONEY + r"\s+(?:per share\s+)?in cash", re.I),
         re.compile(r"(?:right to receive|for)\s+" + _MONEY + r"\s+per share,?\s+in cash", re.I),
         re.compile(r"(?:right to receive|for)\s+" + _MONEY + r"\s+per (?:share|common share)", re.I)]
_RATIO = [re.compile(r"exchange ratio[^.]{0,40}?(?:is|of|equal to|fixed at)\s+(\d+\.\d{2,6})", re.I),
          re.compile(r"right to receive\s+(\d+\.\d{2,6})\s+(?:shares|validly issued)", re.I)]
_CVR = re.compile(r"contingent value right", re.I)


def parse_terms(text: str) -> dict:
    """{cash_per_share, exchange_ratio, cvr_mentioned} from filing text. Values are None when not found."""
    t = re.sub(r"\s+", " ", text or "")
    cash = ratio = None
    for rx in _CASH:
        m = rx.search(t)
        if m:
            cash = float(m.group(1).replace(",", ""))
            break
    for rx in _RATIO:
        m = rx.search(t)
        if m:
            ratio = float(m.group(1))
            break
    return {"cash_per_share": cash, "exchange_ratio": ratio, "cvr_mentioned": bool(_CVR.search(t))}


def html_text(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html or "")).replace("&nbsp;", " ").replace("&#160;", " ")


# ---------- still pending? ----------
DONE_ITEMS = {"2.01": "completed", "1.02": "terminated"}


def closing_events(hits: list[dict], since: str) -> list[dict]:
    """8-K hits on or after `since` that report a completion (2.01) or a terminated agreement (1.02)."""
    out, seen = [], set()
    for h in hits:
        src = h.get("_source", {})
        adsh = h.get("_id", "").partition(":")[0]
        if adsh in seen or (src.get("file_date") or "") < since:
            continue
        found = [DONE_ITEMS[i] for i in (src.get("items") or []) if i in DONE_ITEMS]
        if found:
            seen.add(adsh)
            out.append({"adsh": adsh, "file_date": src.get("file_date"), "events": found})
    return out


def _hits(session, url, limiter):
    data = get_json(session, url, limiter)
    if not data:
        return [], 0
    hh = data.get("hits", {})
    total = hh.get("total", {})
    return hh.get("hits", []), total.get("value", 0) if isinstance(total, dict) else int(total or 0)


def search_all(session, limiter, today: date, days: int = 365, max_pages: int = 5) -> list[dict]:
    start = today - timedelta(days=days)
    rows = []
    for q, forms in QUERIES:
        for page in range(max_pages):
            hits, total = _hits(session, search_url(q, forms, start, today, page * 100), limiter)
            rows += candidates_from_hits(hits)
            if not hits or (page + 1) * 100 >= total:
                break
    return merge_candidates(rows)


def check_pending(session, limiter, book: dict, today: date) -> list[dict]:
    bad = []
    for d in book.get("deals", []):
        since = (d.get("announce_date") or {}).get("value") or (today - timedelta(days=365)).isoformat()
        url = EFTS + "?" + urlencode({"q": '"merger"', "ciks": f"{int(d['target_cik']):010d}", "forms": "8-K",
                                      "dateRange": "custom", "startdt": since, "enddt": today.isoformat()})
        hits, _ = _hits(session, url, limiter)
        ev = closing_events(hits, since)
        if ev:
            bad.append({"id": d["id"], "events": ev})
    return bad


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"})
    lim, today = Limiter(MAX_RPS), date.today()
    try:
        if "--check" in args:
            bad = check_pending(s, lim, json.loads(DEALS.read_text()), today)
            for b in bad:
                print(f"{b['id']}: {', '.join(e for x in b['events'] for e in x['events'])} ({b['events'][0]['adsh']})", file=sys.stderr)
            print(f"checked {len(json.loads(DEALS.read_text())['deals'])} deals, {len(bad)} no longer pending")
            return 1 if bad else 0
        rows = search_all(s, lim, today)
        if "--terms" in args:
            for r in rows:
                lim.wait()
                resp = s.get(r["url"], timeout=60)
                r["parsed"] = parse_terms(html_text(resp.text)) if resp.status_code == 200 else None
    except requests.RequestException as e:
        print(f"EDGAR request failed: {e}", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"as_of": today.isoformat(), "candidates": rows}, indent=1) + "\n")
    print(f"{len(rows)} candidate companies -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
