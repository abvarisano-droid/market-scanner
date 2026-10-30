"""Funnel scan: universe -> data checks -> scored -> top picks per horizon."""
import argparse, hashlib, json
from pathlib import Path
import pandas as pd
import signals
from prices import load_prices

TOP_N = 15
MIN_BARS = 252
MIN_DOLLAR_VOL = 1_000_000


def data_check(df, spy_last):
    """Return (ok, reason)."""
    if df is None or df.empty:
        return False, "no data"
    if len(df) < MIN_BARS:
        return False, "short history"
    if df["date"].iloc[-1] != spy_last:
        return False, "stale"
    if (df["close"] <= 0).any() or df[["close", "volume"]].isna().any().any():
        return False, "bad values"
    if (df["close"].tail(20) * df["volume"].tail(20)).mean() < MIN_DOLLAR_VOL:
        return False, "illiquid"
    return True, ""


def inputs_hash(frames: dict) -> str:
    h = hashlib.sha256()
    for t in sorted(frames):
        h.update(t.encode())
        h.update(frames[t].tail(260).to_csv(index=False).encode())
    return h.hexdigest()


def pick_lists(rows, n=TOP_N):
    bull = sorted((r for r in rows if r["score"] > 50), key=lambda r: (-r["score"], r["ticker"]))[:n]
    bear = sorted((r for r in rows if r["score"] < 50), key=lambda r: (r["score"], r["ticker"]))[:n]
    return bull, bear


def run_scan(universe: pd.DataFrame, frames: dict, spy: pd.DataFrame) -> dict:
    spy_last = spy["date"].iloc[-1]
    names = dict(zip(universe["ticker"], universe["name"]))
    sectors = dict(zip(universe["ticker"], universe.get("sector", pd.Series(dtype=str))))
    reasons = {"no data": 0, "short history": 0, "stale": 0, "bad values": 0, "illiquid": 0}
    have, passed = 0, {}
    for t in universe["ticker"]:
        df = frames.get(t)
        if df is not None:
            have += 1
        ok, why = data_check(df, spy_last)
        if ok:
            passed[t] = df
        else:
            reasons[why] += 1
    rows = {"short_term": [], "swing": []}
    for t, df in passed.items():
        base = {"ticker": t, "name": names.get(t, t), "sector": sectors.get(t, ""),
                "close": round(float(df["close"].iloc[-1]), 2)}
        spy_a = spy[spy["date"].isin(df["date"])]
        for hz, res in (("short_term", signals.short_term(df)), ("swing", signals.swing(df, spy_a))):
            if res:
                rows[hz].append({**base, **res})
    horizons, funnel = {}, {}
    for hz, rs in rows.items():
        bull, bear = pick_lists(rs)
        counts = {k: sum(1 for r in rs if r["label"] == k) for k in ("Bullish", "Neutral", "Bearish")}
        horizons[hz] = {"counts": counts, "top_bull": bull, "top_bear": bear}
        funnel[hz] = {"universe": len(universe), "with_data": have, "passed_checks": len(passed),
                      "scored": len(rs), "bullish": counts["Bullish"], "bearish": counts["Bearish"],
                      "picks": len(bull) + len(bear)}
    return {"asof": spy_last, "inputs_hash": inputs_hash({**passed, "SPY": spy}),
            "dropped": reasons, "funnel": funnel, "horizons": horizons,
            "disclaimer": "Not investment advice."}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    a = ap.parse_args()
    uni = pd.read_csv(f"{a.data_dir}/universe.csv")
    spy = load_prices(a.data_dir, "SPY")
    if spy is None:
        raise SystemExit("SPY prices missing; run prices.py first")
    frames = {t: load_prices(a.data_dir, t) for t in uni["ticker"]}
    frames = {t: f for t, f in frames.items() if f is not None}
    res = run_scan(uni, frames, spy)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(res, indent=2, sort_keys=True)
    (out / f"scan-{res['asof']}.json").write_text(text)
    (out / "latest.json").write_text(text)
    for hz, f in res["funnel"].items():
        print(hz, f)
    print("asof", res["asof"], "hash", res["inputs_hash"][:12])


if __name__ == "__main__":
    main()
