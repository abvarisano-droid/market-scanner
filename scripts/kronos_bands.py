"""Kronos model range for stock pages: prepare the model input, then turn the model's paths into site data.

A model range, not a prediction. Not investment advice.
  prepare  (trusted) picks the stock-page tickers for tonight (the watchlist file first, then the pages whose Kronos
           range is oldest or missing) and writes their last 64 daily candles from data/charts.json, which ends at the
           scan's last completed close: no later candle exists in the file.
  (model)  kronos/run_model.py samples the paths with the network blocked. Its output is data.
  ingest   (trusted, no model code) checks the output, writes site/data/kronos/<T>.json for every refreshed page,
           appends tonight's next-day bands to data/kronos_log.csv (append-only), and recomputes the walk-forward
           "held its p10 to p90 range" count for every page that has a Kronos file.

Usage:
  python scripts/kronos_bands.py prepare --out IN.json
  python scripts/kronos_bands.py ingest --input IN.json --raw RAW.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scanner import kronos_band as kb  # noqa: E402

CHARTS = ROOT / "data" / "charts.json"
WATCHLIST = ROOT / "data" / "kronos_watchlist.json"
OUT_DIR = ROOT / "site" / "data" / "kronos"
LOG = ROOT / "data" / "kronos_log.csv"
MAX_TICKERS = 36
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9./@\-]{1,80}$")


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def watchlist(path: Path = WATCHLIST) -> list[str]:
    raw = load_json(path, {})
    items = raw.get("tickers", []) if isinstance(raw, dict) else []
    return [t for t in (str(x).strip().upper() for x in items) if TICKER_RE.match(t)]


def order(charts: dict, wl: list[str], out_dir: Path = OUT_DIR, cap: int = MAX_TICKERS) -> list[str]:
    """Watchlist pages first, then pages whose Kronos range is missing or oldest, then A to Z; capped."""
    pages = sorted(t for t in charts if TICKER_RE.match(t))
    age = {t: (load_json(out_dir / f"{t}.json", {}) or {}).get("asof") or "" for t in pages}
    first = [t for t in wl if t in charts]
    rest = sorted((t for t in pages if t not in first), key=lambda t: (age[t], t))
    return (first + rest)[:cap]


def build_input(charts: dict, tickers: list[str], now: datetime) -> dict:
    series, dropped = [], []
    for t in tickers:
        rows = kb.model_input(charts[t])
        if rows is None:
            dropped.append({"ticker": t, "why": "fewer than 64 daily candles ending at the as-of close"})
            continue
        series.append({"ticker": t, "asof": rows[-1][0], "x_dates": [r[0] for r in rows], "y_dates": kb.future_dates(rows[-1][0]),
                       "ohlcv": [list(r[1:6]) for r in rows]})
    return {"note": kb.NOTE, "built_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "date": max((s["asof"] for s in series), default=None),
            "paths": kb.N_PATHS, "lookback": kb.LOOKBACK, "series": series, "dropped": dropped}


def check_series(s: dict, charts: dict) -> bool:
    """The series must be exactly what prepare writes from the committed chart file."""
    try:
        t = s["ticker"]
        if not TICKER_RE.match(t) or t not in charts:
            return False
        rows = kb.model_input(charts[t])
        return (rows is not None and s["x_dates"] == [r[0] for r in rows] and s["ohlcv"] == [list(r[1:6]) for r in rows]
                and s["y_dates"] == kb.future_dates(rows[-1][0]) and s["asof"] == rows[-1][0])
    except (KeyError, TypeError):
        return False


def page(t: str, s: dict, b: dict, base: float, model: str, h: dict, cur) -> dict:
    hist = [[d, v[3]] for d, v in zip(s["x_dates"][-30:], s["ohlcv"][-30:])]  # the last 30 closes the model saw, for context
    return {"t": t, "asof": s["asof"], "base": base, "cur": cur, "model": model, "paths_n": b["n"], "horizon": len(s["y_dates"]),
            "dates": s["y_dates"], "p10": b["p10"], "p50": b["p50"], "p90": b["p90"], "up": b["up"], "down": b["down"],
            "paths": b["paths"], "hist": hist, "held": h, "held_text": kb.held_text(h), "note": kb.NOTE,
            "method": f"{b['n']} paths from the open-source Kronos-small model on the last {kb.LOOKBACK} daily candles; "
                      f"bands are the 10th, 50th and 90th percentile of the paths at each step."}


def ingest(inp: dict, raw: dict, charts: dict, out_dir: Path = OUT_DIR, log_path: Path = LOG, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = {"written": [], "rejected": [], "rescored": 0}
    model = str(raw.get("model") or "") if isinstance(raw, dict) else ""
    model = model if MODEL_RE.match(model) else "Kronos-small"
    n = raw.get("paths") if isinstance(raw, dict) else None
    series = {s["ticker"]: s for s in (inp.get("series") or [])[:60] if isinstance(s, dict) and check_series(s, charts)}
    ok_raw = isinstance(raw, dict) and raw.get("status") == "ok" and isinstance(n, int) and not isinstance(n, bool) and 10 <= n <= 400
    try:
        made = datetime.fromisoformat(str(raw.get("made_at")).replace("Z", "+00:00")) if ok_raw else None
        built = datetime.fromisoformat(str(inp.get("built_at")).replace("Z", "+00:00"))
        ok_raw = ok_raw and made is not None and built <= made <= now + timedelta(minutes=2)
    except ValueError:
        ok_raw = False
    log_rows, seen = [], set()
    if ok_raw:
        for res in (raw.get("results") if isinstance(raw.get("results"), list) else [])[:60]:
            t = str(res.get("ticker", "")) if isinstance(res, dict) else ""
            if t not in series or t in seen:
                rep["rejected"].append({"ticker": t if TICKER_RE.match(t) else "?", "why": "not a prepared ticker, or a repeat"})
                continue
            s = series[t]
            bad = kb.check_result(res, n, len(s["y_dates"]))
            if bad:
                rep["rejected"].append({"ticker": t, "why": bad})
                continue
            seen.add(t)
            base = s["ohlcv"][-1][3]
            b = kb.band(res["close"], base)
            log_rows.append({"made_date": s["asof"], "ticker": t, "base_date": s["asof"], "next_p10": f"{b['next']['p10']:.6f}",
                             "next_p50": f"{b['next']['p50']:.6f}", "next_p90": f"{b['next']['p90']:.6f}", "paths": n, "model": model})
            rows = kb.daily_rows(charts[t])
            pg = page(t, s, b, base, model, {"held": 0, "scored": 0, "window": kb.WINDOW}, charts[t].get("cur"))
            (out_dir / f"{t}.json").write_text(json.dumps(pg, separators=(",", ":")), encoding="utf-8")
            rep["written"].append(t)
    kb.append_log(log_path, log_rows)
    log = kb.read_log(log_path)
    index = {}
    for f in sorted(out_dir.glob("*.json")):
        if f.name == "index.json":
            continue
        pg = load_json(f, None)
        t = f.stem
        if not isinstance(pg, dict) or t not in charts:
            continue
        h = kb.held(log, t, kb.daily_rows(charts[t]))
        pg.update(held=h, held_text=kb.held_text(h))
        f.write_text(json.dumps(pg, separators=(",", ":")), encoding="utf-8")
        index[t] = pg.get("asof")
        rep["rescored"] += 1
    (out_dir / "index.json").write_text(json.dumps({"note": kb.NOTE, "model": model, "pages": index}, separators=(",", ":"), sort_keys=True),
                                        encoding="utf-8")
    results = raw.get("results") if ok_raw and isinstance(raw.get("results"), list) else []
    secs = [r.get("seconds") for r in results if isinstance(r, dict) and not isinstance(r.get("seconds"), bool)
            and isinstance(r.get("seconds"), (int, float)) and math.isfinite(r["seconds"]) and 0 <= r["seconds"] <= 3600]
    rep["seconds_per_ticker"] = round(sum(secs) / len(secs), 1) if secs else None
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("prepare")
    p1.add_argument("--out", required=True)
    p2 = sub.add_parser("ingest")
    p2.add_argument("--input", required=True)
    p2.add_argument("--raw", required=True)
    a = ap.parse_args(argv)
    charts = load_json(CHARTS, {})
    if a.cmd == "prepare":
        inp = build_input(charts, order(charts, watchlist()), datetime.now(timezone.utc))
        Path(a.out).write_text(json.dumps(inp, separators=(",", ":")), encoding="utf-8")
        print(f"kronos input: {len(inp['series'])} series, {len(inp['dropped'])} dropped, as of {inp['date']}")
        return 0
    inp = load_json(Path(a.input), {})
    raw = load_json(Path(a.raw), {"status": "error"})
    rep = ingest(inp if isinstance(inp, dict) else {}, raw if isinstance(raw, dict) else {"status": "error"}, charts)
    print(f"kronos bands: {len(rep['written'])} written, {len(rep['rejected'])} rejected, {rep['rescored']} rescored, "
          f"{rep['seconds_per_ticker']} s per ticker")
    return 0


if __name__ == "__main__":
    sys.exit(main())
