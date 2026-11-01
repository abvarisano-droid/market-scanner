"""End-to-end scan: universe -> data -> signals -> valuation -> news/AI -> picks -> report."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import charts, data, news_ai, signals, technical, tracker, universe, valuation, watchdog

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / "data" / "latest_scan.json"
AI_USAGE = "data/ai_usage.json"  # relative to ROOT: per-run AI token and cost log the Brain reads (no key values)
MIN_COVERAGE = 0.4  # share of value and quality metrics a stock needs before its Mispricing score is ranked
TOP_N = 12  # Mispricing picks on the high side; half as many on the low side


_RUN_ID = os.getenv("GITHUB_RUN_ID") or uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive_index(idx) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(idx)
    return idx.tz_localize(None) if idx.tz is not None else idx


def _asof(price_map: dict[str, pd.DataFrame], now: datetime | None = None) -> pd.Timestamp:
    """The scan's US market date: SPY's last bar, capped at the newest New York session that has closed.

    The run time never sets the date. A cron that starts hours late (after midnight UTC, when Asian markets
    already show a partial next-day bar) or a hand-run during market hours still gets the session that closed.
    Every series is then cut at this date (_cut), so no call is scored on a bar after it and the next-close
    entry rule can never use a close that was known when the call was made."""
    bench = price_map[universe.BENCHMARK]["Close"].dropna()
    last = _naive_index(bench.index)[-1].normalize()
    closed = pd.Timestamp(watchdog.market_date(now or _now()))
    return min(last, closed)


def _cut(price_map: dict[str, pd.DataFrame], asof: pd.Timestamp) -> dict[str, pd.DataFrame]:
    out = {}
    for t, df in price_map.items():
        keep = df[_naive_index(df.index).normalize() <= asof]
        if len(keep):
            out[t] = keep
    return out


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
    asof = _asof(price_map)
    price_map = _cut(price_map, asof)
    stock_prices = {t: price_map[t] for t in tickers if t in price_map}

    # technical rules (short-term and swing) on the same price data, SPY as the market reference.
    # The history, freshness and liquidity checks run first so illiquid names never cost a fundamentals call.
    bench_df = price_map[universe.BENCHMARK]
    bench = bench_df["Close"].dropna()
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
    news_ai.start_run()
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
        other = prior[(prior["date"] == asof) & (prior["run_id"].astype(str) != str(_RUN_ID))] if not prior.empty else prior
        if len(other):  # idempotent: a late, backup or catch-up run never adds to a date another run already logged
            log.info("as-of %s is already logged by an earlier run (%d rows): not logging again", asof.date(), len(other))
            led = prior
        else:
            led = tracker.log_picks(picks + tech_calls, bench_at, today=asof, run_id=_RUN_ID)
        hist = {t: df["Close"] for t, df in price_map.items()}
        missing = [t for t in led["ticker"].unique() if t not in hist]
        if missing:
            hist.update({t: d["Close"] for t, d in _cut(data.prices(missing), asof).items()})
        ev = tracker.evaluate(led, hist, bench)
        scorecard = tracker.scorecard(ev, tracker.trading_days(led, bench))
        ledger_rows = _clean_records(ev)
    except Exception as exc:  # the track record must not take the scan down; the ledger file is already safe
        log.exception("tracker stage failed (%s); scan continues without a scorecard", exc)
        scorecard = {"total_picks": 0, "trading_days": 0, "status": "still noise",
                     "note": "Track record unavailable for this run."}
        ledger_rows = []

    try:  # 3 year candles for every called ticker: one extra batched download of about 70 names
        called = sorted(set(led["ticker"])) if ledger_rows else []
        cur = {t: table.loc[t, "currency"] for t in called if t in table.index and "currency" in table}
        got = charts.collect(called, currencies={k: v for k, v in cur.items() if isinstance(v, str)}) if called else {}
        if got:  # an empty download keeps the previous file instead of wiping every chart
            charts.save(got, ROOT / "data" / "charts.json")
    except Exception as exc:  # charts are optional; the scan and ledger never depend on them
        log.warning("charts step failed (%s); keeping the previous data/charts.json", exc)

    try:
        news_ai.save_usage(ROOT / AI_USAGE, asof.date().isoformat(), _RUN_ID)
    except Exception as exc:  # cost logging is optional and must never fail the scan
        log.warning("AI usage log not written (%s)", exc)
    funnel = _funnel(tags, tickers, stock_prices, tech, len(eligible), len(picks))
    listed = indexes or universe.DEFAULT_INDEXES
    # a --max test run cuts the universe on purpose: only judge baskets that still have stocks in it
    judged = [n for n in listed if not max_tickers or n in universe.DROPPED or funnel["by_index_stages"]["universe"].get(n)]
    dropped = dropped_baskets(judged, universe.DROPPED, funnel["by_index_stages"])
    funnel["baskets"] = {"listed": len(listed), "scanned": funnel_scanned(funnel),
                         "index_levels": len(universe.INDEXES)}
    result = {
        "date": asof.date().isoformat(),
        "dropped_baskets": dropped,
        "funnel": funnel,
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


def dropped_baskets(names, load_failures: dict[str, str], stages: dict) -> list[dict]:
    """Every basket with no stock that passed the data checks, with the reason, so the site flag fires whenever
    a basket is effectively missing: its list failed to load, its prices did not download (for example the download
    budget ran out before its batches), or none of its stocks passed the checks."""
    out = []
    for n in names:
        if n in load_failures:
            out.append({"name": n, "reason": load_failures[n]})
        elif not stages["universe"].get(n):
            out.append({"name": n, "reason": "no constituents listed"})
        elif not stages["with_data"].get(n):
            out.append({"name": n, "reason": f"no price data for any of its {stages['universe'][n]} stocks"})
        elif not stages["passed_checks"].get(n):
            out.append({"name": n, "reason": "no stock passed the data checks"})
    return out


def funnel_scanned(funnel: dict) -> int:
    return sum(1 for v in funnel["by_index_stages"]["passed_checks"].values() if v)


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
