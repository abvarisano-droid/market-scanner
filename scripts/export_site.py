"""Copy the fields the website needs into site/data/latest.json and site/data/track.json.

Live:    python scripts/export_site.py --data-dir data --out-dir out
Sample:  python scripts/export_site.py --sample   (synthetic data, clearly labeled)
"""
import argparse, json, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pandas as pd
import scan, signals, track
from prices import load_prices

SPARK_N = 60
SAMPLE_NOTE = "Sample data, first live scan runs nightly after launch"
SAMPLE_BACK = 12  # trading days of synthetic call history


def build_lookup(data_dir, universe, spy):
    spy_last = spy["date"].iloc[-1]
    out = {}
    for _, u in universe.iterrows():
        df = load_prices(data_dir, u["ticker"])
        ok, _ = scan.data_check(df, spy_last)
        if not ok:
            continue
        spy_a = spy[spy["date"].isin(df["date"])]
        row = {"n": str(u["name"]), "s": str(u.get("sector", "")), "c": round(float(df["close"].iloc[-1]), 2),
               "spark": [round(float(x), 2) for x in df["close"].tail(SPARK_N)]}
        for key, res in (("st", signals.short_term(df)), ("sw", signals.swing(df, spy_a))):
            if res:
                row[key] = {"score": res["score"], "label": res["label"], "reasons": res["reasons"]}
        out[u["ticker"]] = row
    return out


def export(data_dir, out_dir, site_dir, sample=False):
    latest = json.loads((Path(out_dir) / "latest.json").read_text())
    tr = json.loads((Path(out_dir) / "track.json").read_text())
    uni = pd.read_csv(Path(data_dir) / "universe.csv")
    spy = load_prices(data_dir, "SPY")
    latest = {k: latest[k] for k in ("asof", "funnel", "dropped", "horizons", "disclaimer")}
    latest["lookup"] = build_lookup(data_dir, uni, spy)
    latest["spy_spark"] = [round(float(x), 2) for x in spy["close"].tail(SPARK_N)]
    latest["sample"] = sample
    latest["banner"] = SAMPLE_NOTE if sample else ""
    keep = ("ticker", "date", "entry_date", "horizon", "label", "score", "days", "closed",
            "stock_return", "spy_return", "excess")
    tr = {**{k: tr[k] for k in ("asof", "status", "trading_days", "note", "by_horizon", "calls_logged", "pending", "disclaimer")},
          "min_days": track.MIN_DAYS,
          "graded": [{k: g[k] for k in keep} for g in tr["graded"]][-300:],
          "sample": sample, "banner": SAMPLE_NOTE if sample else ""}
    d = Path(site_dir) / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "latest.json").write_text(json.dumps(latest, separators=(",", ":"), sort_keys=True))
    (d / "track.json").write_text(json.dumps(tr, indent=1, sort_keys=True))
    return latest, tr


def make_sample(tmp):
    """Synthetic universe, with SAMPLE_BACK days of past calls so the track record has graded rows."""
    from tests.fixtures.synthetic import write_all
    data, out = Path(tmp) / "d", Path(tmp) / "o"
    write_all(data, 150, n=330)
    uni = pd.read_csv(data / "universe.csv")
    full = {t: pd.read_csv(data / "prices" / f"{t}.csv") for t in list(uni["ticker"]) + ["SPY"]}
    for back in range(SAMPLE_BACK, 0, -1):
        cut = {t: f.iloc[:-back] for t, f in full.items()}
        res = scan.run_scan(uni, {t: f for t, f in cut.items() if t != "SPY"}, cut["SPY"])
        track.log_calls(res, data / "calls.csv")
    res = scan.run_scan(uni, {t: f for t, f in full.items() if t != "SPY"}, full["SPY"])
    out.mkdir(parents=True)
    (out / "latest.json").write_text(json.dumps(res))
    track.run_track(res, data, out)
    return data, out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--site-dir", default=str(ROOT / "site"))
    ap.add_argument("--sample", action="store_true")
    a = ap.parse_args()
    if a.sample:
        with tempfile.TemporaryDirectory() as t:
            data, out = make_sample(t)
            l, r = export(data, out, a.site_dir, True)
    else:
        l, r = export(a.data_dir, a.out_dir, a.site_dir)
    print("exported", l["asof"], len(l["lookup"]), "tickers;", r["status"], r["trading_days"], "days")
