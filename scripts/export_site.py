"""Turn the engine's latest scan (data/latest_scan.json) into the files the static site reads:
site/data/latest.json, site/data/summary.json (latest minus the heavy lookup, for the home page) and site/data/track.json.

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

from scanner import calllog, longterm, pipeline, record, tracker, universe, valuation  # noqa: E402
from scanner import technical as tech_rules  # noqa: E402
from scanner.labels import BANNED, BEARISH, BULLISH, NEUTRAL, normalize  # noqa: E402

BULL_AT = 35  # mispricing score that counts as Bullish / Bearish (before news adjustment)
SAMPLE_NOTE = "Sample data. Synthetic prices, replaced by the first real daily scan. Graded results are illustrative only."
DISCLAIMER = "Not investment advice."
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
        if num(m.get("marketCap"), 0):
            row["mc"] = num(m["marketCap"], 0)
        if len(m.get("indexes") or []) > 1:
            row["ix"] = m["indexes"]
        if m.get("mispricing") is not None:
            row["mp"] = {"score": m["mispricing"], "label": mp_label(m["mispricing"]),
                         "reasons": [plain(x) for x in (m.get("valuation_reasons") or [])[:TOP_REASONS]]}
        for key, hz in (("st", "short_term"), ("sw", "swing")):
            r = tech["scores"][hz].get(t)
            if r:
                row[key] = {"score": r["score"], "label": r["label"], "reasons": [plain(x) for x in r["reasons"]]}
        lookup[t] = row
    return {"asof": scan["date"], "sample": sample, "banner": SAMPLE_NOTE if sample else "",
            "disclaimer": DISCLAIMER, "funnel": scan["funnel"],
            "dropped_baskets": [{"name": d["name"], "date": scan["date"]} for d in scan.get("dropped_baskets") or []], "dropped": scan["funnel"]["dropped"],
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
    fresh = tracker.scorecard(pd.DataFrame(), days)  # status and note from the current threshold (tracker.MIN_DAYS)
    by_lens = {}
    for lens, v in sc.get("by_lens", {}).items():
        by_lens[lens] = {"calls": v.get("calls", 0),
                         "windows": {str(n): {"hit_rate_pct": None if f"hit_rate_{h}" not in v else round(100 * v[f"hit_rate_{h}"], 1),
                                              "avg_excess_pct": None if f"avg_alpha_{h}" not in v else round(100 * v[f"avg_alpha_{h}"], 2),
                                              "graded": v.get(f"n_{h}", 0),
                                              **record.interval_pct(v.get(f"hit_rate_{h}"), v.get(f"n_{h}", 0))}
                                     for h, n in tracker.HORIZONS.items()}}
    log = {"rows": len(led), "head": None, "verified": None}
    if not sample and tracker.LEDGER.exists():
        v = calllog.verify(tracker.LEDGER.read_text(encoding="utf-8"), tracker.COLS)
        log.update(rows=v["n"], head=v["head"], verified=v["ok"])
    return {"asof": scan["date"], "sample": sample, "banner": SAMPLE_NOTE if sample else "",
            "status": fresh["status"], "trading_days": days, "min_days": tracker.MIN_DAYS,
            "note": re.sub(r"\b1 trading days\b", "1 trading day", plain(fresh["note"])), "entry_rule": "next trading day close",
            "windows": list(tracker.HORIZONS.values()), "by_lens": by_lens,
            "first_logged": str(led["date"].min())[:10] if len(led) else None, "interval": "95% Wilson interval", "log": log,
            "calls_logged": len(led), "pending": pending, "graded": graded[-300:], "disclaimer": DISCLAIMER}


def build_method() -> dict:
    """Every threshold the How it works page shows, read from the code constants (no network)."""
    import numpy as np
    n = 300
    close = pd.Series(np.linspace(50, 100, n))
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n).strftime("%Y-%m-%d"), "close": close,
                       "volume": 1e6})
    def w(rules):
        return [[r.__name__.replace("rule_", ""), x.weight] for r, x in rules]
    short = [(tech_rules.rule_ma20, tech_rules.rule_ma20(close)), (tech_rules.rule_momentum, tech_rules.rule_momentum(close)),
             (tech_rules.rule_rsi, tech_rules.rule_rsi(close)), (tech_rules.rule_volume, tech_rules.rule_volume(df))]
    swing = [(tech_rules.rule_ma50, tech_rules.rule_ma50(close)), (tech_rules.rule_ma200, tech_rules.rule_ma200(close)),
             (tech_rules.rule_slope, tech_rules.rule_slope(close)), (tech_rules.rule_rs, tech_rules.rule_rs(close, close)),
             (tech_rules.rule_high52, tech_rules.rule_high52(close))]
    return {
        "universe": {"live": list(universe.WIKI), "baskets": {k: len(v) for k, v in universe.FALLBACK.items() if k not in universe.WIKI},
                     "benchmark": universe.BENCHMARK, "index_levels": len(universe.INDEXES),
                     "russell": {"source": "iShares IWM holdings", "min_equities": universe.MIN_RUSSELL}},
        "funnel": {"min_bars": tech_rules.MIN_BARS, "stale_days": tech_rules.STALE_DAYS,
                   "min_dollar_vol": tech_rules.MIN_DOLLAR_VOL, "top_n": tech_rules.TOP_N,
                   "min_coverage_pct": round(pipeline.MIN_COVERAGE * 100), "mp_top": pipeline.TOP_N, "mp_low": pipeline.TOP_N // 2},
        "mispricing": {"weights_pct": {k: round(v * 100) for k, v in valuation.WEIGHTS.items()},
                       "value": [m for m, _ in valuation.VALUE_METRICS], "quality": [m for m, _ in valuation.QUALITY_METRICS],
                       "call_at": BULL_AT},
        "technical": {"bull_at": tech_rules.BULL, "bear_at": tech_rules.BEAR, "min_short": tech_rules.MIN_SHORT,
                      "min_swing": tech_rules.MIN_SWING,
                      "short_weights_pct": {n_: round(x * 100) for n_, x in w(short)},
                      "swing_weights_pct": {n_: round(x * 100) for n_, x in w(swing)}},
        "grading": {"windows": list(tracker.HORIZONS.values()), "min_days": tracker.MIN_DAYS},
        "longterm": {"rules": [lab for _, lab, _ in longterm.RULES]},
    }


def build_summary(latest: dict) -> dict:
    """Everything the home page needs, without the heavy per-ticker lookup (site/data/summary.json)."""
    out = {k: v for k, v in latest.items() if k not in ("lookup", "spy_spark")}
    out["lookup_n"] = len(latest.get("lookup", {}))
    return out


def export(scan: dict, site_dir, sample=False):
    latest, tr = build_latest(scan, sample), build_track(scan, sample)
    from scanner import charts as charts_mod
    store = {} if sample else charts_mod.load()  # 3 year candles for called tickers, written by the scan
    called = {r["ticker"] for r in scan.get("ledger") or []}
    for t, row in latest["lookup"].items():
        if t in store and t in called:
            row["ch"] = 1  # lookup reserves the chart box up front (no layout shift)
    d = Path(site_dir) / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "latest.json").write_text(json.dumps(latest, separators=(",", ":"), sort_keys=True))
    (d / "summary.json").write_text(json.dumps(build_summary(latest), separators=(",", ":"), sort_keys=True))
    (d / "track.json").write_text(json.dumps(tr, indent=1, sort_keys=True))
    (d / "method.json").write_text(json.dumps(build_method(), indent=1, sort_keys=True))
    from scripts import export_v5; export_v5.export(scan, latest, site_dir, store)  # v5 data: stock pages, changes, report card
    return latest, tr


def make_sample(tmp: Path) -> dict:
    """Run the real engine on synthetic data, then back-date the calls so the track record has rows."""
    from unittest import mock

    from scanner import data, pipeline, universe
    from tests.fixtures import synthetic as syn

    with mock.patch.object(tracker, "LEDGER", tmp / "picks.csv"), mock.patch.object(pipeline, "LATEST", tmp / "latest_scan.json"), \
            mock.patch.object(pipeline, "ROOT", tmp), mock.patch.object(data, "prices", syn.fake_prices), \
            mock.patch.object(data, "fundamentals", syn.fake_fund), mock.patch.object(data, "news", syn.fake_news), \
            mock.patch.object(data, "earnings_dates", lambda t: []), \
            mock.patch.object(universe, "russell_constituents", lambda live=True: ["AAPL", "MSFT"] + [f"RUT{i:03d}" for i in range(400)]), \
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
