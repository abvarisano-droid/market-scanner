"""Log published calls and grade them against SPY (excess return, daily)."""
import argparse, json
from pathlib import Path
import pandas as pd
from prices import load_prices

HORIZON_DAYS = {"short_term": 10, "swing": 63}
MIN_DAYS = 21
CALL_COLS = ["date", "ticker", "horizon", "label", "score", "close"]


def log_calls(scan: dict, calls_path) -> int:
    """Append the published picks of a scan; idempotent per (date, ticker, horizon)."""
    p = Path(calls_path)
    old = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=CALL_COLS)
    seen = set(zip(old["date"], old["ticker"], old["horizon"]))
    new = []
    for hz, h in scan["horizons"].items():
        for r in h["top_bull"] + h["top_bear"]:
            if (scan["asof"], r["ticker"], hz) not in seen:
                new.append({"date": scan["asof"], "ticker": r["ticker"], "horizon": hz,
                            "label": r["label"], "score": r["score"], "close": r["close"]})
    if new:
        p.parent.mkdir(parents=True, exist_ok=True)
        pd.concat([old, pd.DataFrame(new)], ignore_index=True)[CALL_COLS].to_csv(p, index=False)
    return len(new)


def grade_call(call, stock: pd.DataFrame, spy: pd.DataFrame) -> dict | None:
    """Excess return vs SPY since the call date. Bullish wins by beating SPY, Bearish by lagging it.
    Neutral calls are not graded. Window ends at the horizon length or the latest bar."""
    if call["label"] == "Neutral":
        return None
    sd, pd_ = stock.set_index("date")["close"], spy.set_index("date")["close"]
    dates = [d for d in pd_.index if d >= call["date"] and d in sd.index]
    if not dates or dates[0] != call["date"] or len(dates) < 2:
        return None
    h = HORIZON_DAYS[call["horizon"]]
    end = dates[min(h, len(dates) - 1)]
    rs = sd[end] / sd[call["date"]] - 1
    rm = pd_[end] / pd_[call["date"]] - 1
    sign = 1 if call["label"] == "Bullish" else -1
    return {"days": min(h, len(dates) - 1), "closed": len(dates) - 1 >= h,
            "stock_return": rs, "spy_return": rm, "excess": sign * (rs - rm)}


def summarize(graded: list, trading_days: int) -> dict:
    by = {}
    for hz in HORIZON_DAYS:
        g = [x for x in graded if x["horizon"] == hz]
        by[hz] = {"graded": len(g),
                  "avg_excess_pct": round(100 * sum(x["excess"] for x in g) / len(g), 2) if g else None,
                  "hit_rate_pct": round(100 * sum(x["excess"] > 0 for x in g) / len(g), 1) if g else None}
    status = "still noise" if trading_days < MIN_DAYS else "enough days to read"
    note = (f"Only {trading_days} trading days of calls so far (need {MIN_DAYS}). Treat results as noise."
            if trading_days < MIN_DAYS else f"{trading_days} trading days of calls.")
    return {"status": status, "trading_days": trading_days, "note": note, "by_horizon": by}


def run_track(scan: dict, data_dir, out_dir) -> dict:
    calls_path = Path(data_dir) / "calls.csv"
    log_calls(scan, calls_path)
    calls = pd.read_csv(calls_path)
    spy = load_prices(data_dir, "SPY")
    cache, graded = {}, []
    for c in calls.to_dict("records"):
        if c["ticker"] not in cache:
            cache[c["ticker"]] = load_prices(data_dir, c["ticker"])
        st = cache[c["ticker"]]
        g = grade_call(c, st, spy) if st is not None else None
        if g:
            graded.append({**c, **g})
    first = calls["date"].min()
    days = int((spy["date"] >= first).sum()) if len(calls) else 0
    res = summarize(graded, days)
    res.update({"asof": scan["asof"], "calls_logged": len(calls), "disclaimer": "Not investment advice.",
                "graded": [{**x, "excess": round(x["excess"], 4), "stock_return": round(x["stock_return"], 4),
                            "spy_return": round(x["spy_return"], 4)} for x in graded]})
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "track.json").write_text(json.dumps(res, indent=2, sort_keys=True))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    a = ap.parse_args()
    scan = json.loads((Path(a.out_dir) / "latest.json").read_text())
    r = run_track(scan, a.data_dir, a.out_dir)
    print(r["status"], "-", r["note"])
    for hz, v in r["by_horizon"].items():
        print(hz, v)
