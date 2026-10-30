"""End-to-end scan: universe -> data -> signals -> valuation -> news/AI -> picks -> report."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, news_ai, signals, tracker, universe, valuation

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / "data" / "latest_scan.json"


def build_table(price_map: dict[str, pd.DataFrame], fundamentals: pd.DataFrame, uni: dict[str, str]) -> pd.DataFrame:
    rows = []
    for t, df in price_map.items():
        tech = signals.technicals(df)
        tech["flags"] = signals.flags(tech)
        rows.append({"ticker": t, "index": uni.get(t), **tech})
    table = pd.DataFrame(rows).set_index("ticker")
    table = table.join(fundamentals, how="left")
    return valuation.score(table)


def index_snapshot(price_map: dict[str, pd.DataFrame]) -> list[dict]:
    out = []
    for name, sym in universe.INDEXES.items():
        df = price_map.get(sym)
        if df is None:
            continue
        t = signals.technicals(df)
        out.append({"name": name, "symbol": sym, "level": t["price"], "chg_1d": t["chg_1d"],
                    "chg_1m": t["chg_1m"], "chg_3m": t["chg_3m"], "rsi": t["rsi"],
                    "pct_from_high": t["pct_from_high"]})
    return out


def run(indexes: list[str] | None = None, top_n: int = 12, live_constituents: bool = True,
        max_tickers: int | None = None) -> dict:
    uni = universe.full_universe(indexes, live=live_constituents)
    tickers = list(uni)[:max_tickers] if max_tickers else list(uni)
    log.info("scanning %d stocks", len(tickers))

    price_map = data.prices(tickers + list(universe.INDEXES.values()) + [universe.BENCHMARK])
    stock_prices = {t: price_map[t] for t in tickers if t in price_map}
    fund = data.fundamentals(list(stock_prices))
    table = build_table(stock_prices, fund, uni)

    # rank the most mispriced in both directions, only where we have real data
    eligible = table[table["coverage"] >= 0.4]
    cands = pd.concat([eligible.nlargest(top_n, "mispricing"), eligible.nsmallest(top_n // 2, "mispricing")])

    picks = []
    for t, r in cands.iterrows():
        row = {"ticker": t, **r.to_dict()}
        res = news_ai.analyze(row, data.news(t))
        picks.append({**_clean(row), **res})

    bench = price_map[universe.BENCHMARK]["Close"]
    led = tracker.log_picks(picks, float(bench.iloc[-1]))
    hist = {t: df["Close"] for t, df in price_map.items()}
    missing = [t for t in led["ticker"].unique() if t not in hist]
    if missing:
        hist.update({t: d["Close"] for t, d in data.prices(missing).items()})
    ev = tracker.evaluate(led, hist, bench)

    result = {
        "date": date.today().isoformat(),
        "indexes": index_snapshot(price_map),
        "picks": picks,
        "movers": _movers(table),
        "sectors": signals.sector_rotation(table).reset_index().to_dict("records"),
        "table": _clean_records(table.reset_index()),
        "scorecard": tracker.scorecard(ev),
        "ledger": _clean_records(ev),
    }
    LATEST.parent.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(result, default=str))
    write_report(result)
    return result


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


def _pct(x):
    return "n/a" if x is None else f"{x:+.1%}"


def write_report(res: dict) -> Path:
    L = [f"# Market Scan, {res['date']}", "", "## Global indexes", "",
         "| Index | Level | 1D | 1M | 3M | From 52w high |", "|---|---|---|---|---|---|"]
    for i in res["indexes"]:
        L.append(f"| {i['name']} | {i['level']:,.0f} | {_pct(i['chg_1d'])} | {_pct(i['chg_1m'])} | "
                 f"{_pct(i['chg_3m'])} | {_pct(i['pct_from_high'])} |")
    L += ["", "## Top calls", ""]
    for p in sorted(res["picks"], key=lambda p: -(p.get("mispricing") or 0)):
        L += [f"### {p['ticker']} ({p.get('shortName') or ''}): **{p['call']}** "
              f"(confidence {p.get('confidence')}, mispricing {p.get('mispricing'):+.0f})",
              f"*{p.get('index')}, {p.get('sector') or 'n/a'}, price {p.get('price'):,.2f}*", "",
              p.get("thesis", "")]
        if p.get("catalysts"):
            L.append(f"\n**Catalysts:** {p['catalysts']}  \n**Risks:** {p.get('risks', '')}")
        for h in (p.get("headlines") or [])[:3]:
            L.append(f"- [{h['title']}]({h['link']})")
        L.append("")
    L += ["## Unusual movers", ""]
    for m in res["movers"][:15]:
        L.append(f"- **{m['ticker']}** {_pct(m['chg_1d'])}: {', '.join(m['flags'])}")
    sc = res["scorecard"]
    L += ["", "## Track record", "", "```", json.dumps(sc, indent=2), "```", ""]
    out = ROOT / "reports" / f"{res['date']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L))
    (ROOT / "reports" / "latest.md").write_text("\n".join(L))
    return out
