"""Forecast Lab command line.

  python -m forecast_lab weights                 # download the pinned Kronos weights once (sha256 checked)
  python -m forecast_lab backtest                # walk-forward contest, default 30 large caps, 52 weeks, weekly
  python -m forecast_lab backtest --models random_walk,gbm,bootstrap --tickers AAPL,MSFT --weeks 26

Private paper-trading experiment. Not investment advice. No broker, no orders.
Your own holdings stay out of this repo: pass them with --extra-file pointing at a local text file.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from . import report, walkforward
from .baselines import BASELINES
from .models import MODELS, fetch_kronos_weights
from .options_move import OptionsMove

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "forecast_lab"
OUT = ROOT / "reports" / "forecast_lab"
# 30 liquid US large caps across sectors. Public names only; personal holdings come from --extra-file.
DEFAULT_TICKERS = ("AAPL MSFT NVDA AMZN GOOGL META TSLA JPM V UNH XOM JNJ PG HD COST LLY AVGO MA KO PEP "
                   "WMT BAC CVX MRK ABBV ORCL CRM AMD NFLX CAT").split()
ALL = {**BASELINES, **MODELS, OptionsMove.name: OptionsMove}


def load_prices(tickers: list[str], refresh: bool) -> dict[str, pd.DataFrame]:
    """3 years of daily adjusted OHLCV per ticker, cached as CSV so a rerun works offline."""
    CACHE.mkdir(parents=True, exist_ok=True)
    out, need = {}, []
    for t in tickers:
        f = CACHE / f"{t}.csv"
        if f.exists() and not refresh:
            out[t] = pd.read_csv(f, index_col=0, parse_dates=True)
        else:
            need.append(t)
    if need:
        from scanner.data import prices
        got = prices(need, period="3y")
        for t, d in got.items():
            d = walkforward.normalize(d)
            d.to_csv(CACHE / f"{t}.csv")
            out[t] = d
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="forecast_lab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("weights", help="download the pinned Kronos weights")
    w.add_argument("--dest", default=str(ROOT / ".weights" / "kronos"))
    b = sub.add_parser("backtest", help="walk-forward contest")
    b.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    b.add_argument("--extra-file", help="local text file of extra tickers, one per line (kept out of git)")
    b.add_argument("--models", default=",".join(ALL), help=f"comma list from: {', '.join(ALL)}")
    b.add_argument("--weeks", type=int, default=52)
    b.add_argument("--step", type=int, default=5, help="trading days between test dates")
    b.add_argument("--refresh", action="store_true", help="download prices again instead of using the cache")
    b.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    if a.cmd == "weights":
        print(f"Kronos weights ready in {fetch_kronos_weights(Path(a.dest))}")
        return 0

    tickers = [t.strip().upper() for t in a.tickers.split(",") if t.strip()]
    if a.extra_file:
        tickers += [ln.strip().upper() for ln in Path(a.extra_file).read_text().splitlines() if ln.strip()]
    tickers = list(dict.fromkeys(tickers))
    unknown = [m for m in a.models.split(",") if m and m not in ALL]
    if unknown:
        ap.error(f"unknown models: {', '.join(unknown)}")
    contestants = {m: ALL[m]() for m in a.models.split(",") if m}
    prices = load_prices(tickers, a.refresh)
    if not prices:
        print("no price data", file=sys.stderr)
        return 1
    result = walkforward.run(prices, contestants, weeks=a.weeks, step=a.step)
    md, js = report.write(result, Path(a.out))
    print(md.read_text(encoding="utf-8"))
    print(f"wrote {md} and {js}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
