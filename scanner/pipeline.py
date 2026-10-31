"""End-to-end scan: universe -> data -> signals -> valuation -> news/AI -> picks -> report."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, news_ai, signals, technical, tracker, universe, valuation

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / "data" / "latest_scan.json"
MIN_COVERAGE = 0.4  # share of value and quality metrics a stock needs before its Mispricing score is ranked
TOP_N = 12  # Mispricing picks on the high side; half as many on the low side


_RUN_ID = os.getenv("GITHUB_RUN_ID") or uuid.uuid4().hex[:12]


def _asof(price_map: dict[str, pd.DataFrame]) -> pd.Timestamp:
    """Latest bar date across everything fetched. Using the max (not just SPY's last bar) means a market that
    already has a later bar can never be graded from a day whose close was known at signal time."""
    last = []
    for df in price_map.values():
        idx = df["Close"].dropna().index
        if len(idx):
            t = pd.Timestamp(idx[-1])
            last.append(t.tz_localize(None) if t.tzinfo is not None else t)
    return max(last).normalize()


def build_table(price_map: dict[str, pd.DataFrame], fundamentals: pd.DataFrame, uni: dict[str, str],
                tags: dict[str, list[str]] | None = None) -> pd.DataFrame:
    rows = []
    for t, df in price_map.items():
        try:
            tech = signals.technicals(df)
            tech["flags"] = signals.flags(tech)
        except Exception as exc:  # one bad ticker must not kill the scan
            log.warning("skipping %s: signals failed (%s)", t, exc)
            continue
        rows.append({"ticker": t, "index": uni.get(t), "indexes": (tags or {}).get(t) or [uni.get(t)], **tech})
    table = pd.DataFrame(rows).set_index("ticker")
    table = table.join(fundamentals, how="left")
    return valuation.score(table)


def index_snapshot(price_map: dict[str, pd.DataFrame]) -> list[dict]:
    out = []
    for name, sym in universe.INDEXES.items():
        df = price_map.get(sym)
        if df is None:
            continue
        try:
            t = signals.technicals(df)
        except Exception as exc:
            log.warning("index %s skipped (%s)", name, exc)
            continue
        out.append({"name": name, "symbol": sym, "level": t["price"], "chg_1d": t["chg_1d"],
                    "chg_1m": t["chg_1m"], "chg_3m": t["chg_3m"], "rsi": t["rsi"],
                    "pct_from_high": t["pct_from_high"]})
    return out


def run(indexes: list[str] | None = None, top_n: int = TOP_N, live_constituents: bool = True,
        max_tickers: int | None = None) -> dict:
    tags = universe.universe_tags(indexes, live=live_constituents)
    uni = {t: v[0] for t, v in tags.items()}
    tickers = list(uni)[:max_tickers] if max_tickers else list(uni)
    log.info("scanning %d stocks", len(tickers))

    price_map = data.prices(tickers + list(universe.INDEXES.values()) + [universe.BENCHMARK], period="2y")
    stock_prices = {t: price_map[t] for t in tickers if t in price_map}

    # technical rules (short-term and swing) on the same price data, SPY as the market reference.
    # The history, freshness and liquidity checks run first so illiquid names never cost a fundamentals call.
    bench_df = price_map[universe.BENCHMARK]
    bench = bench_df["Close"].dropna()
    asof = _asof(price_map)
    tech = technical.scan_technical({t: technical.from_ohlcv(df) for t, df in stock_prices.items()},
                                    technical.from_ohlcv(bench_df))
    tech["dropped"]["no data"] += len(tickers) - len(stock_prices)
    passed = set(tech["spark"])

    checked = {t: df for t, df in stock_prices.items() if t in passed}
    try:
        fund = data.fundamentals(list(checked))
    except Exception as exc:
        log.warning("fundamentals failed (%s); scoring on prices only", exc)
        fund = pd.DataFrame(index=list(checked), columns=data.FUNDAMENTAL_FIELDS)
    table = build_table(checked, fund, uni, tags)

    # rank the most mispriced in both directions, only where we have real data
    eligible = table[(table["coverage"] >= MIN_COVERAGE) & table.index.isin(passed)]
    cands = pd.concat([eligible.nlargest(top_n, "mispricing"), eligible.nsmallest(top_n // 2, "mispricing")])

    picks = []
    for t, r in cands.iterrows():
        row = {"ticker": t, **r.to_dict()}
        try:
            res = news_ai.analyze(row, data.news(t))
        except Exception as exc:
            log.warning("news/AI step failed for %s (%s); using rules", t, exc)
            res = {**news_ai.rule_based_call(row, 0.0), "sentiment": 0.0, "headlines": []}
        picks.append({**_clean(row), **res, "lens": "mispricing"})

    tech_calls = []
    for hz, h in tech["horizons"].items():
        for r in h["top_bull"] + h["top_bear"]:
            if r["label"] in ("Bullish", "Bearish"):
                tech_calls.append({"ticker": r["ticker"], "index": uni.get(r["ticker"]), "call": r["label"],
                                   "price": _finite(table.loc[r["ticker"], "price"]) if r["ticker"] in table.index else None,
                                   "score": r["score"], "thesis": "; ".join(r["reasons"]), "source": "technical",
                                   "lens": hz})

    try:
        bench_n = tracker._naive(bench)
        bench_at = float(bench_n[bench_n.index <= asof].iloc[-1])  # benchmark close on or before the as-of date
        prior = tracker.load()
        if not prior.empty and asof in set(prior["date"]) and asof < pd.Timestamp(date.today()):
            log.info("as-of %s is already in the ledger and is before today (holiday or stale data): not logging again", asof.date())
            led = prior
        else:
            led = tracker.log_picks(picks + tech_calls, bench_at, today=asof, run_id=_RUN_ID)
        hist = {t: df["Close"] for t, df in price_map.items()}
        missing = [t for t in led["ticker"].unique() if t not in hist]
        if missing:
            hist.update({t: d["Close"] for t, d in data.prices(missing).items()})
        ev = tracker.evaluate(led, hist, bench)
        scorecard = tracker.scorecard(ev, tracker.trading_days(led, bench))
        ledger_rows = _clean_records(ev)
    except Exception as exc:  # the track record must not take the scan down; the ledger file is already safe
        log.exception("tracker stage failed (%s); scan continues without a scorecard", exc)
        scorecard = {"total_picks": 0, "trading_days": 0, "status": "still noise",
                     "note": "Track record unavailable for this run."}
        ledger_rows = []

    result = {
        "date": asof.date().isoformat(),
        "funnel": _funnel(tags, tickers, stock_prices, tech, len(eligible), len(picks)),
        "spy_spark": [round(float(x), 2) for x in bench.tail(60)],
        "technical": {k: tech[k] for k in ("asof", "dropped", "horizons", "scores", "spark")},
        "indexes": index_snapshot(price_map),
        "picks": picks,
        "movers": _movers(table),
        "sectors": signals.sector_rotation(table).reset_index().to_dict("records"),
        "table": _clean_records(table.reset_index()),
        "scorecard": scorecard,
        "ledger": ledger_rows,
    }
    LATEST.parent.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(result, default=str))
    try:
        write_report(result)
    except Exception as exc:
        log.exception("report failed (%s); latest_scan.json is saved", exc)
    return result


def _funnel(tags, tickers, stock_prices, tech, n_scored, n_picks) -> dict:
    base = {"universe": len(tickers), "with_data": len(stock_prices), "passed_checks": tech["passed_checks"]}
    # per index: a stock in two indexes counts once in each, so these can sum to more than the universe
    stages: dict[str, dict] = {"universe": {}, "with_data": {}, "passed_checks": {}}
    passed = set(tech["spark"])
    for t in tickers:
        for ix in tags.get(t) or [None]:
            stages["universe"][ix] = stages["universe"].get(ix, 0) + 1
            if t in stock_prices:
                stages["with_data"][ix] = stages["with_data"].get(ix, 0) + 1
            if t in passed:
                stages["passed_checks"][ix] = stages["passed_checks"].get(ix, 0) + 1
    f = {"mispricing": {**base, "scored": n_scored, "picks": n_picks},
         "by_index": stages["universe"], "by_index_stages": stages, "dropped": tech["dropped"]}
    for hz, h in tech["horizons"].items():
        f[hz] = {**base, "scored": h["scored"], "picks": len(h["top_bull"]) + len(h["top_bear"])}
    return f


def _movers(table: pd.DataFrame) -> list[dict]:
    flagged = table[table["flags"].map(len) > 0].copy()
    flagged["abs"] = flagged["chg_1d"].abs()
    cols = ["index", "shortName", "price", "chg_1d", "vol_ratio", "flags"]
    return _clean_records(flagged.nlargest(25, "abs")[cols].reset_index())


def _clean(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, (float, np.floating)) and not np.isfinite(v):
            v = None
        elif isinstance(v, np.generic):
            v = v.item()
        out[k] = v
    return out


def _clean_records(df: pd.DataFrame) -> list[dict]:
    return [_clean(r) for r in df.to_dict("records")]


def _finite(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _num(x, fmt: str) -> str:
    return "n/a" if _finite(x) is None else format(float(x), fmt)


def _pct(x):
    return "n/a" if _finite(x) is None else f"{x:+.1%}"


def write_report(res: dict) -> Path:
    L = [f"# Market Scan, {res['date']}", "", "## Global indexes", "",
         "| Index | Level | 1D | 1M | 3M | From 52w high |", "|---|---|---|---|---|---|"]
    for i in res["indexes"]:
        L.append(f"| {i['name']} | {_num(i['level'], ',.0f')} | {_pct(i['chg_1d'])} | {_pct(i['chg_1m'])} | "
                 f"{_pct(i['chg_3m'])} | {_pct(i['pct_from_high'])} |")
    L += ["", "## Top calls", ""]
    for p in sorted(res["picks"], key=lambda p: -(p.get("mispricing") or 0)):
        L += [f"### {p['ticker']} ({p.get('shortName') or ''}): **{p['call']}** "
              f"(confidence {p.get('confidence')}, mispricing {_num(p.get('mispricing'), '+.0f')})",
              f"*{p.get('index')}, {p.get('sector') or 'n/a'}, price {_num(p.get('price'), ',.2f')}*", "",
              p.get("thesis", "")]
        if p.get("catalysts"):
            L.append(f"\n**Catalysts:** {p['catalysts']}  \n**Risks:** {p.get('risks', '')}")
        for h in (p.get("headlines") or [])[:3]:
            L.append(f"- [{h['title']}]({h['link']})")
        L.append("")
    for hz, title in (("short_term", "Short-term"), ("swing", "Swing")):
        h = res["technical"]["horizons"][hz]
        L += [f"## {title} technical signals", ""]
        for side, rows in (("Bullish", h["top_bull"][:5]), ("Bearish", h["top_bear"][:5])):
            for r in rows:
                L.append(f"- **{r['ticker']}** {side} ({_num(r['score'], '.0f')}): {'; '.join(r['reasons'])}")
        L.append("")
    L += ["## Unusual movers", ""]
    for m in res["movers"][:15]:
        L.append(f"- **{m['ticker']}** {_pct(m['chg_1d'])}: {', '.join(m['flags'])}")
    sc = res["scorecard"]
    L += ["", "## Track record", "", "Not investment advice. Calls are graded from the next trading day's close.", "", "```", json.dumps(sc, indent=2), "```", ""]
    out = ROOT / "reports" / f"{res['date']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L))
    (ROOT / "reports" / "latest.md").write_text("\n".join(L))
    return out
