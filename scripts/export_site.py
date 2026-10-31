"""Turn the engine's latest scan (data/latest_scan.json) into the files the static site reads:
site/data/latest.json and site/data/track.json.

Live:    python scripts/export_site.py
Sample:  python scripts/export_site.py --sample   (synthetic data, labeled "Sample data")

No network. The scan already holds the prices summary, scores and graded ledger.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from scanner import tracker  # noqa: E402
from scanner.labels import BEARISH, BULLISH, NEUTRAL, normalize  # noqa: E402

BULL_AT = 35  # mispricing score that counts as Bullish / Bearish (before news adjustment)
SAMPLE_NOTE = "Sample data. Synthetic prices, replaced by the first real daily scan."
DISCLAIMER = "Not investment advice."
BANNED = re.compile(r"\b(buy|buys|buying|sell|sells|selling|price targets?)\b", re.I)
TOP_REASONS = 3


def plain(x):
    """Strip dash characters from text going to the site."""
    return x.replace("—", "-").replace("–", "-") if isinstance(x, str) else x


def num(x, d=2):
    return None if x is None or (isinstance(x, float) and x != x) else round(float(x), d)


def mp_label(score) -> str:
    return BULLISH if score >= BULL_AT else BEARISH if score <= -BULL_AT else NEUTRAL


def _name(t, rec):
    return plain(rec.get("shortName") or t)


def _tech_rows(scan, hz, table):
    h = scan["technical"]["horizons"][hz]
    def row(r):
        m = table.get(r["ticker"], {})
        return {"ticker": r["ticker"], "name": _name(r["ticker"], m), "sector": plain(m.get("sector") or ""),
                "index": m.get("index"), "close": num(m.get("price")), "score": r["score"], "bar": r["score"],
                "label": r["label"], "reasons": [plain(x) for x in r["reasons"]]}
    return {"counts": h["counts"], "top_bull": [row(r) for r in h["top_bull"]],
            "top_bear": [row(r) for r in h["top_bear"]]}


def _mispricing_rows(scan, table):
    picks = [p for p in scan["picks"] if p.get("lens", "mispricing") == "mispricing"]
    def row(p):
        reasons = [plain(x) for x in (p.get("valuation_reasons") or [])[:TOP_REASONS]]
        thesis = plain(p.get("thesis") or "")
        ok_thesis = thesis and not BANNED.search(thesis)
        if not reasons and ok_thesis:
            reasons = [thesis[:200]]
        return {"ticker": p["ticker"], "name": _name(p["ticker"], p), "sector": plain(p.get("sector") or ""),
                "index": p.get("index"), "close": num(p.get("price")), "score": p["mispricing"],
                "bar": round((p["mispricing"] + 100) / 2, 1), "label": normalize(p["call"]),
                "confidence": p.get("confidence"), "reasons": reasons,
                "thesis": thesis[:400] if ok_thesis and p.get("source") == "ai" else ""}
    rows = [row(p) for p in picks]
    bull = sorted((r for r in rows if r["label"] == BULLISH), key=lambda r: -r["score"])
    bear = sorted((r for r in rows if r["label"] == BEARISH), key=lambda r: r["score"])
    scored = [t["mispricing"] for t in table.values() if (t.get("coverage") or 0) >= 0.4 and t.get("mispricing") is not None]
    counts = {BULLISH: sum(s >= BULL_AT for s in scored), BEARISH: sum(s <= -BULL_AT for s in scored)}
    counts[NEUTRAL] = len(scored) - counts[BULLISH] - counts[BEARISH]
    return {"counts": counts, "top_bull": bull, "top_bear": bear}


def _spy_ret(spark, n):
    return float(spark[-1] / spark[-1 - n] - 1) if len(spark) > n and spark[-1 - n] else None


def _sectors(scan, table, lookup):
    """Per sector: mean 1 week and 1 month move minus SPY's, plus Bullish and Bearish call counts per view."""
    spy = scan.get("spy_spark") or []
    r1w, r1m = _spy_ret(spy, 5), _spy_ret(spy, 21)
    groups = {}
    for t, m in table.items():
        if m.get("sector"):
            groups.setdefault(plain(m["sector"]), []).append(m)

    def rel(vals, ref):
        vals = [v for v in vals if v is not None and v == v]
        return None if ref is None or not vals else round(sum(vals) / len(vals) - ref, 4)

    out = []
    for name, ms in groups.items():
        calls = {k: {BULLISH: 0, BEARISH: 0} for k in ("mispricing", "short_term", "swing")}
        for m in ms:
            row = lookup.get(m["ticker"], {})
            for k, key in (("mispricing", "mp"), ("short_term", "st"), ("swing", "sw")):
                lab = (row.get(key) or {}).get("label")
                if lab in (BULLISH, BEARISH):
                    calls[k][lab] += 1
        out.append({"name": name, "n": len(ms), "rel_1w": rel([m.get("chg_5d") for m in ms], r1w),
                    "rel_1m": rel([m.get("chg_1m") for m in ms], r1m),
                    "bullish": calls["mispricing"][BULLISH], "bearish": calls["mispricing"][BEARISH], "calls": calls})
    out.sort(key=lambda x: (x["rel_1m"] is None, -(x["rel_1m"] or 0), x["name"]))
    return out


def build_latest(scan: dict, sample: bool) -> dict:
    table = {r["ticker"]: r for r in scan["table"]}
    tech = scan["technical"]
    lookup = {}
    for t, spark in tech["spark"].items():
        m = table.get(t)
        if not m:
            continue
        c = num(m.get("price"))
        if c is None and spark:  # no usable last close: fall back to the last point of the sparkline
            c = num(spark[-1])
        row = {"n": _name(t, m), "s": plain(m.get("sector") or ""), "i": m.get("index"),
               "c": c, "cur": m.get("currency") or None, "spark": spark}
        if m.get("mispricing") is not None:
            row["mp"] = {"score": m["mispricing"], "label": mp_label(m["mispricing"]),
                         "reasons": [plain(x) for x in (m.get("valuation_reasons") or [])[:TOP_REASONS]]}
        for key, hz in (("st", "short_term"), ("sw", "swing")):
            r = tech["scores"][hz].get(t)
            if r:
                row[key] = {"score": r["score"], "label": r["label"], "reasons": [plain(x) for x in r["reasons"]]}
        lookup[t] = row
    return {"asof": scan["date"], "sample": sample, "banner": SAMPLE_NOTE if sample else "",
            "disclaimer": DISCLAIMER, "funnel": scan["funnel"], "dropped": scan["funnel"]["dropped"],
            "indexes": [{"name": i["name"], "chg_1d": num(i["chg_1d"], 4), "chg_1m": num(i["chg_1m"], 4)}
                        for i in scan["indexes"]],
            "horizons": {"mispricing": _mispricing_rows(scan, table),
                         "short_term": _tech_rows(scan, "short_term", table),
                         "swing": _tech_rows(scan, "swing", table)},
            "sectors": _sectors(scan, table, lookup),
            "lookup": lookup, "spy_spark": scan.get("spy_spark", [])}


def build_track(scan: dict, sample: bool) -> dict:
    sc = scan["scorecard"]
    led = pd.DataFrame(scan["ledger"])
    graded, pending = [], 0
    for r in led.to_dict("records"):
        done = [(h, n) for h, n in tracker.HORIZONS.items() if r.get(f"ret_{h}") is not None and r.get(f"ret_{h}") == r.get(f"ret_{h}")]
        if not done:
            pending += 1
            continue
        h, n = done[-1]
        graded.append({"ticker": r["ticker"], "date": str(r["date"])[:10], "lens": r.get("lens") or "mispricing",
                       "label": normalize(r["call"]), "window": n, "stock_return": num(r[f"ret_{h}"], 4),
                       "excess": num(r[f"alpha_{h}"], 4)})
    graded.sort(key=lambda g: (g["date"], g["ticker"]))
    days = sc.get("trading_days", 0)
    by_lens = {}
    for lens, v in sc.get("by_lens", {}).items():
        by_lens[lens] = {"calls": v.get("calls", 0),
                         "windows": {str(n): {"hit_rate_pct": None if f"hit_rate_{h}" not in v else round(100 * v[f"hit_rate_{h}"], 1),
                                              "avg_excess_pct": None if f"avg_alpha_{h}" not in v else round(100 * v[f"avg_alpha_{h}"], 2),
                                              "graded": v.get(f"n_{h}", 0)} for h, n in tracker.HORIZONS.items()}}
    return {"asof": scan["date"], "sample": sample, "banner": SAMPLE_NOTE if sample else "",
            "status": sc.get("status", "still noise"), "trading_days": days, "min_days": tracker.MIN_DAYS,
            "note": plain(sc.get("note", "")), "entry_rule": "next trading day close",
            "windows": list(tracker.HORIZONS.values()), "by_lens": by_lens,
            "calls_logged": len(led), "pending": pending, "graded": graded[-300:], "disclaimer": DISCLAIMER}


def export(scan: dict, site_dir, sample=False):
    latest, tr = build_latest(scan, sample), build_track(scan, sample)
    d = Path(site_dir) / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "latest.json").write_text(json.dumps(latest, separators=(",", ":"), sort_keys=True))
    (d / "track.json").write_text(json.dumps(tr, indent=1, sort_keys=True))
    return latest, tr


def make_sample(tmp: Path) -> dict:
    """Run the real engine on synthetic data, then back-date the calls so the track record has rows."""
    from unittest import mock

    from scanner import data, pipeline
    from tests.fixtures import synthetic as syn

    with mock.patch.object(tracker, "LEDGER", tmp / "picks.csv"), mock.patch.object(pipeline, "LATEST", tmp / "latest_scan.json"), \
            mock.patch.object(pipeline, "ROOT", tmp), mock.patch.object(data, "prices", syn.fake_prices), \
            mock.patch.object(data, "fundamentals", syn.fake_fund), mock.patch.object(data, "news", syn.fake_news), \
            mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
        res = pipeline.run(live_constituents=False)
        led = tracker.load()
        bars = pd.bdate_range(end=syn.END, periods=300)
        led["date"] = [bars[-13 + (i % 12)] for i in range(len(led))]  # spread over the last 12 trading days
        hist = {t: d["Close"] for t, d in syn.fake_prices(list(led.ticker.unique()) + ["SPY"]).items()}
        ev = tracker.evaluate(led, hist, hist["SPY"])
        res["scorecard"] = tracker.scorecard(ev, tracker.trading_days(led, hist["SPY"]))
        res["ledger"] = pipeline._clean_records(ev)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default=str(ROOT / "data" / "latest_scan.json"))
    ap.add_argument("--site-dir", default=str(ROOT / "site"))
    ap.add_argument("--sample", action="store_true")
    a = ap.parse_args()
    if a.sample:
        with tempfile.TemporaryDirectory() as t:
            scan = make_sample(Path(t))
    else:
        scan = json.loads(Path(a.scan).read_text())
    lat, tr = export(scan, a.site_dir, a.sample)
    print("exported", lat["asof"], len(lat["lookup"]), "tickers;", tr["status"], tr["trading_days"], "days")
