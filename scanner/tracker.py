"""Pick ledger + scorecard: were the calls right?

Every Bullish/Bearish call (from the mispricing score or the short-term and swing
technical rules, called a "lens") is logged with the signal date. Grading rules:

* Entry is the close of the NEXT trading day after the signal date (no trading at
  the signal's own close). The benchmark (SPY) uses the same entry day.
* Windows are 5, 20 and 60 trading days counted from that entry close.
* A Bullish call wins by beating SPY over the window, a Bearish call by lagging it.
* Under 60 trading days of history the whole record is "still noise".
* data/picks.csv is append-only and hash-chained (see calllog.py).
* Rows logged before this rule existed (entry_rule blank) keep the old same-day
  entry so history is not rewritten. Old BUY/SELL/WATCH values load as
  Bullish/Bearish/Neutral.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from . import calllog
from .labels import BEARISH, BULLISH, normalize, sign

LEDGER = Path(__file__).resolve().parent.parent / "data" / "picks.csv"
COLS = ["date", "ticker", "index", "call", "confidence", "entry", "bench_entry", "mispricing", "thesis",
        "source", "lens", "score", "entry_rule", "run_id"]
HORIZONS = {"5d": 5, "20d": 20, "60d": 60}
LENSES = ("mispricing", "short_term", "swing")
MIN_DAYS = 60  # "still noise" until the log covers 60 trading days (the longest grading window)
NEXT_CLOSE = "next_close"
DI, TI, LI, RI = (COLS.index(c) for c in ("date", "ticker", "lens", "run_id"))


def load() -> pd.DataFrame:
    if not LEDGER.exists():
        return pd.DataFrame(columns=COLS)
    led = pd.read_csv(LEDGER, parse_dates=["date"])
    for c in COLS:
        if c not in led:
            led[c] = None
    led["call"] = led["call"].map(normalize)
    led["lens"] = led["lens"].fillna("mispricing")
    led["entry_rule"] = led["entry_rule"].fillna("")
    return led[COLS]


def log_picks(picks: list[dict], bench_price: float, today=None, run_id: str | None = None) -> pd.DataFrame:
    """Append calls. One row per (date, ticker, lens).

    Rows are never replaced by a later run: only a rewrite inside the same run (same run_id) may replace its own rows.
    A call that an earlier run already logged for that date is kept as it was and the new copy is dropped."""
    today = pd.Timestamp(today or date.today()).normalize()
    rows = []
    for p in picks:
        call = normalize(p["call"])
        if call not in (BULLISH, BEARISH):
            continue
        rows.append({"date": today, "ticker": p["ticker"], "index": p.get("index"), "call": call,
                     "confidence": p.get("confidence"), "entry": p.get("price"), "bench_entry": bench_price,
                     "mispricing": p.get("mispricing"), "thesis": (p.get("thesis") or "")[:500],
                     "source": p.get("source"), "lens": p.get("lens", "mispricing"), "score": p.get("score"),
                     "entry_rule": NEXT_CLOSE, "run_id": run_id})
    new = pd.DataFrame(rows, columns=COLS)
    # Append-only and hash-chained (scanner/calllog.py): earlier rows are kept as their raw CSV text so their chain
    # values never change. Nothing may be logged for a date earlier than the newest logged date.
    old_rows = calllog.read_raw(LEDGER, COLS) if LEDGER.exists() else []
    day = today.strftime("%Y-%m-%d")
    if old_rows and day < max(r[DI] for r in old_rows):
        raise ValueError(f"cannot log calls for {day}: the log already holds later dates (it is append-only)")
    new_rows = calllog.read_raw(new.to_csv(index=False), COLS) if not new.empty else []
    key = {(r[TI], r[LI]) for r in new_rows}
    rid = str(run_id) if run_id else None
    # same-run rewrite only: a later run (or a row with no run_id) is never replaced
    old_rows = [r for r in old_rows
                if not (rid and r[DI] == day and (r[TI], r[LI] or "mispricing") in key and r[RI] == rid)]
    kept = {(r[TI], r[LI] or "mispricing") for r in old_rows if r[DI] == day}
    new_rows = [r for r in new_rows if (r[TI], r[LI]) not in kept]  # earlier runs win
    calllog.write_sealed(LEDGER, old_rows + new_rows, COLS)
    return load()


def _naive(s: pd.Series) -> pd.Series:
    s = s.dropna()
    if getattr(s.index, "tz", None) is not None:
        s = s.copy()
        s.index = s.index.tz_localize(None)
    return s


def _after(s: pd.Series, d) -> pd.Series:
    return s[s.index > d]


def _align(bench: pd.Series, index: pd.Index) -> pd.Series:
    """Benchmark closes on the stock's own dates (last known close carried forward), so position n means the same
    calendar day for both. Dates before the benchmark's first bar are dropped."""
    return bench.reindex(bench.index.union(index)).ffill().reindex(index).dropna()


def evaluate(led: pd.DataFrame, history: dict[str, pd.Series], bench: pd.Series) -> pd.DataFrame:
    """history: {ticker: close series indexed by date}. Returns ledger with outcome columns."""
    if led.empty:
        return led
    led = led.copy()
    hist = {t: _naive(s) for t, s in history.items()}
    bench = _naive(bench)
    out = {f"{k}_{h}": [] for h in HORIZONS for k in ("ret", "alpha", "hit")}
    out.update({"ret_now": [], "alpha_now": []})
    for _, r in led.iterrows():
        sg = sign(r["call"])
        s = hist.get(r["ticker"])
        legacy = r.get("entry_rule") != NEXT_CLOSE
        if s is None or len(s) == 0:
            for k in out: out[k].append(None)
            continue
        if legacy:  # old rule: same-day entry price as logged, windows counted from the signal date
            a = s[s.index >= r["date"]]
            b = _align(bench, a.index)
            e, be, off = r["entry"], r["bench_entry"], 0
        else:
            a = _after(s, r["date"])
            b = _align(bench, a.index)
            if len(a) == 0 or len(b) == 0:
                for k in out: out[k].append(None)
                continue
            e, be, off = a.iloc[0], b.iloc[0], 0
        for h, n in HORIZONS.items():
            if len(a) <= n + off or len(b) <= n + off:
                out[f"ret_{h}"].append(None); out[f"alpha_{h}"].append(None); out[f"hit_{h}"].append(None)
                continue
            ret, bret = a.iloc[n] / e - 1, b.iloc[n] / be - 1
            rel = sg * (ret - bret)
            out[f"ret_{h}"].append(ret); out[f"alpha_{h}"].append(rel); out[f"hit_{h}"].append(bool(rel > 0))
        if not legacy and len(a) < 2:  # entry bar only, nothing to mark yet
            out["ret_now"].append(None); out["alpha_now"].append(None)
        else:
            ret = a.iloc[-1] / e - 1
            out["ret_now"].append(ret); out["alpha_now"].append(sg * (ret - (b.iloc[-1] / be - 1)))
    for k, v in out.items():
        led[k] = v
    return led


def trading_days(led: pd.DataFrame, bench: pd.Series) -> int:
    """Trading days of calls so far: benchmark bars strictly after the first signal date (the signal day itself is not a day of results)."""
    if led.empty:
        return 0
    b = _naive(bench)
    return int((b.index > led["date"].min()).sum())


def scorecard(ev: pd.DataFrame, days: int | None = None) -> dict:
    out = {"total_picks": int(len(ev))}
    if days is not None:
        out["trading_days"] = int(days)
        out["status"] = "still noise" if days < MIN_DAYS else "enough days to read"
        unit = "trading day" if days == 1 else "trading days"
        out["note"] = (f"Only {days} {unit} of calls so far (need {MIN_DAYS}). Treat results as noise."
                       if days < MIN_DAYS else f"{days} {unit} of calls.")
    if ev.empty:
        return out

    def block(df):
        o = {}
        for col in HORIZONS:
            h = df.get(f"hit_{col}")
            if h is None:
                continue
            done = h.dropna()
            if len(done):
                o[f"hit_rate_{col}"] = round(float(done.astype(bool).mean()), 3)
                o[f"avg_alpha_{col}"] = round(float(df[f"alpha_{col}"].dropna().mean()), 4)
                o[f"n_{col}"] = int(len(done))
        if "alpha_now" in df:
            a = df["alpha_now"].dropna()
            if len(a):
                o["open_win_rate"] = round(float((a > 0).mean()), 3)
                o["open_avg_alpha"] = round(float(a.mean()), 4)
        return o

    out.update(block(ev))
    out["by_lens"] = {l: {"calls": int((ev["lens"] == l).sum()), **block(ev[ev["lens"] == l])} for l in LENSES}
    return out
