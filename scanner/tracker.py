"""Pick ledger + scorecard: were the calls right?

Every Bullish/Bearish call (from the mispricing score or the short-term and swing
technical rules, called a "lens") is logged with the signal date. Grading rules:

* Entry is the close of the NEXT trading day after the signal date (no trading at
  the signal's own close). The benchmark (SPY) uses the same entry day.
* Windows are 5, 20 and 60 trading days counted from that entry close.
* A Bullish call wins by beating SPY over the window, a Bearish call by lagging it.
* Under 21 trading days of history the whole record is "still noise".
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
        "source", "lens", "score", "entry_rule"]
HORIZONS = {"5d": 5, "20d": 20, "60d": 60}
LENSES = ("mispricing", "short_term", "swing")
MIN_DAYS = 21
NEXT_CLOSE = "next_close"


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


def log_picks(picks: list[dict], bench_price: float, today=None) -> pd.DataFrame:
    """Append calls. One row per (date, ticker, lens); re-running a day replaces that day's rows."""
    today = pd.Timestamp(today or date.today()).normalize()
    led = load()
    rows = []
    for p in picks:
        call = normalize(p["call"])
        if call not in (BULLISH, BEARISH):
            continue
        rows.append({"date": today, "ticker": p["ticker"], "index": p.get("index"), "call": call,
                     "confidence": p.get("confidence"), "entry": p.get("price"), "bench_entry": bench_price,
                     "mispricing": p.get("mispricing"), "thesis": (p.get("thesis") or "")[:500],
                     "source": p.get("source"), "lens": p.get("lens", "mispricing"), "score": p.get("score"),
                     "entry_rule": NEXT_CLOSE})
    new = pd.DataFrame(rows, columns=COLS)
    # Append-only: old rows are kept as raw text so their hashes never change. Only today's own rows
    # (a same-day re-run) can be replaced, and nothing dated earlier than the newest logged date.
    old_rows = calllog.read_raw(LEDGER, COLS) if LEDGER.exists() else []
    day = today.strftime("%Y-%m-%d")
    if old_rows and day < max(r[0] for r in old_rows):
        raise ValueError(f"cannot log calls for {day}: the log already holds later dates (it is append-only)")
    new_rows = calllog.read_raw(new.to_csv(index=False), COLS) if not new.empty else []
    key = {(r[1], r[10]) for r in new_rows}
    kept = [r for r in old_rows if not (r[0] == day and (r[1], r[10] or "mispricing") in key)]
    calllog.write_sealed(LEDGER, kept + new_rows, COLS)
    return load()


def _naive(s: pd.Series) -> pd.Series:
    s = s.dropna()
    if getattr(s.index, "tz", None) is not None:
        s = s.copy()
        s.index = s.index.tz_localize(None)
    return s


def _after(s: pd.Series, d) -> pd.Series:
    return s[s.index > d]


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
            a, b = s[s.index >= r["date"]], bench[bench.index >= r["date"]]
            e, be, off = r["entry"], r["bench_entry"], 0
        else:
            a, b = _after(s, r["date"]), _after(bench, r["date"])
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
    """Trading days of calls so far: benchmark bars on or after the first logged call."""
    if led.empty:
        return 0
    b = _naive(bench)
    return int((b.index >= led["date"].min()).sum())


def scorecard(ev: pd.DataFrame, days: int | None = None) -> dict:
    out = {"total_picks": int(len(ev))}
    if days is not None:
        out["trading_days"] = int(days)
        out["status"] = "still noise" if days < MIN_DAYS else "enough days to read"
        out["note"] = (f"Only {days} trading days of calls so far (need {MIN_DAYS}). Treat results as noise."
                       if days < MIN_DAYS else f"{days} trading days of calls.")
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
