"""v5 site data: stock pages, "what changed" diff and the lens report card.

Built only from the scan's evaluated ledger (data/picks.csv graded by scanner.tracker) and the
scan's per-ticker lookup. Writes site/data/v5.json. Nothing here is synthetic.
A stock page exists only for tickers that appear in the ledger (the scanner made a call on them).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scanner import charts as charts_mod
from scanner import tracker
from scanner.labels import BANNED, BEARISH, BULLISH, normalize

LENSES = tracker.LENSES
DISCLAIMER = "Not investment advice."


def _plain(x):
    return x.replace("—", "-").replace("–", "-") if isinstance(x, str) else x


def _clean(v):
    return None if v is None or (isinstance(v, float) and v != v) else v


def _dstr(d) -> str:
    return str(d)[:10]


def _ledger(scan: dict) -> pd.DataFrame:
    led = pd.DataFrame(scan.get("ledger") or [])
    if led.empty:
        return led
    led["call"] = led["call"].map(normalize)
    led["lens"] = led["lens"].fillna("mispricing")
    led["d"] = led["date"].map(_dstr)
    return led


def _score(r) -> float | None:
    v = _clean(r.get("mispricing") if r.get("lens") == "mispricing" else r.get("score"))
    if v is None:
        v = _clean(r.get("score")) if r.get("lens") == "mispricing" else None
    return None if v is None else round(float(v), 1)


def diff_calls(led: pd.DataFrame) -> dict:
    """New and flipped calls on the latest logged date vs the previous logged date."""
    out = {"date": None, "previous": None, "new": [], "flipped": [], "empty": True}
    if led.empty:
        return out
    dates = sorted(led["d"].unique())
    out["date"] = dates[-1]
    if len(dates) < 2:
        return out
    out["previous"], out["empty"] = dates[-2], False
    prev = {(r.ticker, r.lens): r.call for r in led[led["d"] == dates[-2]].itertuples()}
    for r in led[led["d"] == dates[-1]].sort_values(["lens", "ticker"]).itertuples():
        old = prev.get((r.ticker, r.lens))
        if old is None:
            out["new"].append({"ticker": r.ticker, "lens": r.lens, "call": r.call})
        elif old != r.call:
            out["flipped"].append({"ticker": r.ticker, "lens": r.lens, "from": old, "to": r.call})
    return out


def report_card(led: pd.DataFrame, trading_days: int) -> dict:
    """Per lens graded count, hit rate and average excess return, using tracker.scorecard's own math."""
    sc = tracker.scorecard(led, trading_days) if not led.empty else {"by_lens": {}}
    lenses = {}
    for lens in LENSES:
        v = sc.get("by_lens", {}).get(lens, {})
        w = {}
        for h, n in tracker.HORIZONS.items():
            hr, al = v.get(f"hit_rate_{h}"), v.get(f"avg_alpha_{h}")
            w[str(n)] = {"graded": v.get(f"n_{h}", 0),
                         "hit_rate_pct": None if hr is None else round(100 * hr, 1),
                         "avg_excess_pct": None if al is None else round(100 * al, 2)}
        lenses[lens] = {"calls": v.get("calls", 0), "windows": w}
    return {"trading_days": int(trading_days), "min_days": tracker.MIN_DAYS,
            "still_noise": trading_days < tracker.MIN_DAYS, "lenses": lenses}


def _f(v, d=2):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, d) if v == v and abs(v) != float("inf") else None


def fundamentals(row: dict | None) -> dict:
    """Valuation figures the scan already holds (Yahoo Finance fields). Missing stays None."""
    r = row or {}
    px, avg, n = _f(r.get("price")), _f(r.get("targetMeanPrice")), r.get("numberOfAnalystOpinions")
    gap = round(avg / px - 1, 4) if px and avg and (n or 0) > 0 else None
    pe = lambda v: v if v is not None and 0 < v < 2000 else None  # negative or absurd P/E is not meaningful
    return {"fwd_pe": pe(_f(r.get("forwardPE"), 1)), "ttm_pe": pe(_f(r.get("trailingPE"), 1)),
            "ev_ebitda": _f(r.get("enterpriseToEbitda"), 1), "consensus_gap": gap,
            "analysts": int(n) if n is not None and n == n else None, "sector": _plain(r.get("sector")),
            "mcap": _f(r.get("marketCap"), 0), "cur": r.get("currency")}


def stock_pages(led: pd.DataFrame, lookup: dict, table: dict | None = None) -> dict:
    pages = {}
    if led.empty:
        return pages
    for t, g in led.groupby("ticker"):
        rec = lookup.get(t) or {}
        cur = {}
        for lens, key in (("mispricing", "mp"), ("short_term", "st"), ("swing", "sw")):
            r = rec.get(key)
            if r:
                cur[lens] = {"label": r["label"], "score": r.get("score"),
                             "reasons": [_plain(x) for x in r.get("reasons", []) if not BANNED.search(x)]}
        hist, graded = [], []
        for r in g.sort_values(["d", "lens"]).to_dict("records"):
            hist.append({"date": r["d"], "lens": r["lens"], "call": r["call"], "score": _score(r)})
            for h, n in tracker.HORIZONS.items():
                if _clean(r.get(f"ret_{h}")) is not None:
                    graded.append({"date": r["d"], "lens": r["lens"], "call": r["call"], "window": n,
                                   "stock_return": round(float(r[f"ret_{h}"]), 4),
                                   "excess": round(float(r[f"alpha_{h}"]), 4)})
        pages[t] = {"name": _plain(rec.get("n") or t), "index": rec.get("i") or _clean(g["index"].iloc[0]),
                    "sector": rec.get("s"), "current": cur, "history": hist, "graded": graded,
                    "fund": fundamentals((table or {}).get(t))}
    return pages


def build_v5(scan: dict, lookup: dict) -> dict:
    led = _ledger(scan)
    days = (scan.get("scorecard") or {}).get("trading_days", 0)
    return {"asof": scan.get("date"), "disclaimer": DISCLAIMER, "changes": diff_calls(led),
            "report": report_card(led, days),
            "stocks": stock_pages(led, lookup, {r["ticker"]: r for r in scan.get("table") or []})}


def write_charts(stocks: dict, store: dict, site_dir) -> list[str]:
    """One small file per called ticker: site/data/charts/<TICKER>.json. Stale files are removed."""
    d = Path(site_dir) / "data" / "charts"
    d.mkdir(parents=True, exist_ok=True)
    done = []
    for t in sorted(stocks):
        p = store.get(t)
        if not p:
            continue
        (d / f"{t}.json").write_text(json.dumps(p, separators=(",", ":"), sort_keys=True))
        done.append(t)
    for f in d.glob("*.json"):
        if f.stem not in done:
            f.unlink()
    return done


def export(scan: dict, latest: dict, site_dir, store: dict | None = None) -> dict:
    v5 = build_v5(scan, latest.get("lookup", {}))
    if store is None:
        store = {} if latest.get("sample") else charts_mod.load()
    for t in write_charts(v5["stocks"], store, site_dir):
        v5["stocks"][t]["chart"] = True
    d = Path(site_dir) / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "v5.json").write_text(json.dumps(v5, separators=(",", ":"), sort_keys=True))
    return v5
