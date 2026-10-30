"""Pick ledger + scorecard: were the calls right?

Every BUY/SELL is logged with its entry price and the benchmark level. Later
runs mark each pick to market and judge it on absolute and benchmark-relative
return at 5, 20 and 60 trading days.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

LEDGER = Path(__file__).resolve().parent.parent / "data" / "picks.csv"
COLS = ["date", "ticker", "index", "call", "confidence", "entry", "bench_entry", "mispricing", "thesis", "source"]
HORIZONS = {"5d": 5, "20d": 20, "60d": 60}


def load() -> pd.DataFrame:
    if LEDGER.exists():
        return pd.read_csv(LEDGER, parse_dates=["date"])
    return pd.DataFrame(columns=COLS)


def log_picks(picks: list[dict], bench_price: float, today: date | None = None) -> pd.DataFrame:
    today = pd.Timestamp(today or date.today())
    led = load()
    new = pd.DataFrame([{
        "date": today, "ticker": p["ticker"], "index": p.get("index"), "call": p["call"],
        "confidence": p.get("confidence"), "entry": p["price"], "bench_entry": bench_price,
        "mispricing": p.get("mispricing"), "thesis": p.get("thesis", "")[:500], "source": p.get("source"),
    } for p in picks if p["call"] in ("BUY", "SELL")], columns=COLS)
    if not led.empty:  # one entry per ticker per day
        led = led[~((led["date"] == today) & led["ticker"].isin(new["ticker"]))]
    led = pd.concat([led, new], ignore_index=True) if not led.empty else new
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    led.to_csv(LEDGER, index=False)
    return led


def evaluate(led: pd.DataFrame, history: dict[str, pd.Series], bench: pd.Series) -> pd.DataFrame:
    """history: {ticker: close series indexed by date}. Returns ledger with outcome columns."""
    if led.empty:
        return led
    led = led.copy()
    for col, n in HORIZONS.items():
        rets, rels, hits = [], [], []
        for _, r in led.iterrows():
            s = history.get(r["ticker"])
            if s is None:
                rets.append(None); rels.append(None); hits.append(None); continue
            after = s[s.index.tz_localize(None) >= r["date"]] if s.index.tz is not None else s[s.index >= r["date"]]
            b_after = bench[bench.index.tz_localize(None) >= r["date"]] if bench.index.tz is not None else bench[bench.index >= r["date"]]
            if len(after) <= n or len(b_after) <= n:
                rets.append(None); rels.append(None); hits.append(None); continue
            ret = after.iloc[n] / r["entry"] - 1
            bret = b_after.iloc[n] / r["bench_entry"] - 1
            sign = 1 if r["call"] == "BUY" else -1
            rel = sign * (ret - bret)
            rets.append(ret); rels.append(rel); hits.append(rel > 0)
        led[f"ret_{col}"], led[f"alpha_{col}"], led[f"hit_{col}"] = rets, rels, hits
    # live mark-to-market
    led["ret_now"] = [
        (history[t].iloc[-1] / e - 1) if t in history else None for t, e in zip(led["ticker"], led["entry"])
    ]
    led["alpha_now"] = [
        (1 if c == "BUY" else -1) * (r - (bench.iloc[-1] / b - 1)) if r is not None else None
        for c, r, b in zip(led["call"], led["ret_now"], led["bench_entry"])
    ]
    return led


def scorecard(ev: pd.DataFrame) -> dict:
    out = {"total_picks": int(len(ev))}
    for col in HORIZONS:
        h = ev.get(f"hit_{col}")
        if h is None:
            continue
        done = h.dropna()
        if len(done):
            out[f"hit_rate_{col}"] = round(float(done.astype(bool).mean()), 3)
            out[f"avg_alpha_{col}"] = round(float(ev[f"alpha_{col}"].dropna().mean()), 4)
            out[f"n_{col}"] = int(len(done))
    if "alpha_now" in ev:
        a = ev["alpha_now"].dropna()
        if len(a):
            out["open_win_rate"] = round(float((a > 0).mean()), 3)
            out["open_avg_alpha"] = round(float(a.mean()), 4)
    return out
