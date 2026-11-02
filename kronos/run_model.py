"""Kronos model step: sample price paths for each prepared series, with the network blocked.

Private paper-trading experiment. Not investment advice. Paper only: no broker, no orders, no real money.
Reads the input written by the trusted prepare step (candles that end at the last completed close, never later),
checks the pinned weights (sha256, safetensors only), blocks the network, then samples N paths per series until the
time budget runs out. Writes only numbers: every path's high, low and close per step, plus the runtime per ticker.
The decision (majority, stop and target race, EV) is made later by trusted code that treats this file as data.

Usage: python -I kronos/run_model.py --input IN.json --weights DIR --out RAW.json [--budget SECONDS]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script folder off sys.path
import kronos_paths as kp  # noqa: E402

MAX_SERIES = 60
MAX_PATHS = 400


def sig(x: float) -> float:
    return float(f"{x:.6g}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=float, default=780.0, help="stop starting new tickers after this many seconds")
    a = ap.parse_args(argv)
    t0 = time.time()
    inp = json.loads(Path(a.input).read_text(encoding="utf-8"))
    man = kp.manifest()
    n = int(inp.get("paths", 100))
    if not 10 <= n <= MAX_PATHS:
        raise SystemExit("paths out of range")
    import torch
    torch.set_num_threads(max(1, os.cpu_count() or 1))
    tok, mod = kp.load_models(Path(a.weights), man)
    kp.block_network()
    s = man["sampling"]
    out = {"status": "ok", "model": f"{man['weights']['model']['repo']}@{man['weights']['model']['revision'][:12]}",
           "tokenizer": f"{man['weights']['tokenizer']['repo']}@{man['weights']['tokenizer']['revision'][:12]}",
           "code_commit": man["code"]["commit"], "paths": n, "date": inp.get("date"), "results": [], "skipped": [],
           "load_seconds": round(time.time() - t0, 1)}
    for ser in inp.get("series", [])[:MAX_SERIES]:
        t = str(ser.get("ticker"))
        if time.time() - t0 > a.budget:
            out["skipped"].append({"ticker": t, "why": "time budget used"})
            continue
        t1 = time.time()
        try:
            seed = zlib.crc32(f"{t}|{inp.get('date')}".encode()) & 0x7FFFFFFF
            p = kp.sample_paths(tok, mod, [{"ohlcv": ser["ohlcv"], "x_dates": ser["x_dates"], "y_dates": ser["y_dates"]}],
                                len(ser["y_dates"]), n, T=s["T"], top_k=s["top_k"], top_p=s["top_p"], seed=seed,
                                max_context=s["max_context"], clip=s["clip"])[0]
        except Exception as e:  # one bad series never stops the rest
            out["skipped"].append({"ticker": t, "why": f"model error ({type(e).__name__})"})
            continue
        ohlc = p[:, :, :4]
        out["results"].append({
            "ticker": t, "seconds": round(time.time() - t1, 2),
            "high": [[sig(v) for v in row] for row in ohlc.max(axis=2)],
            "low": [[sig(v) for v in row] for row in ohlc.min(axis=2)],
            "close": [[sig(v) for v in row] for row in p[:, :, 3]],
        })
        print(f"{t}: {out['results'][-1]['seconds']}s", flush=True)
    secs = [r["seconds"] for r in out["results"]]
    out["seconds_total"] = round(time.time() - t0, 1)
    out["seconds_per_ticker"] = round(sum(secs) / len(secs), 2) if secs else None
    out["made_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    Path(a.out).write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"kronos: {len(secs)} tickers, {len(out['skipped'])} skipped, {out['seconds_per_ticker']}s per ticker, {out['seconds_total']}s total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
