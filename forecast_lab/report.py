"""Turn graded forecasts into the contest table (Markdown and JSON)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .scoring import summarize

HEADER = "> Private paper-trading experiment. A model range, not a prediction. Not investment advice."


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def markdown(result: dict, rows: list[dict]) -> str:
    d = result["dates"]
    lines = ["# Forecast Lab: walk-forward contest", "", HEADER, "",
             f"{len(result['tickers'])} tickers, {len(d)} test dates ({d[0] if d else 'n/a'} to {d[-1] if d else 'n/a'}), "
             f"{result['horizon']} trading days ahead. Every forecast used only closes up to its date.", "",
             "| Rank | Model | Forecasts | 10 to 90 range held (aim 80%) | Brier (coin = 0.25) | CRPS | Skill vs random walk | Up or down right | Seconds each |",
             "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        lo, hi = r["held80_range"]
        skill = "n/a" if r["skill"] is None else f"{100 * r['skill']:+.1f}%"
        hit = "n/a" if r["hit_rate"] is None else f"{_pct(r['hit_rate'])} ({_pct(r['hit_range'][0])} to {_pct(r['hit_range'][1])})"
        lines.append(f"| {i} | {r['model']} | {r['n']} | {_pct(r['held80'])} ({_pct(lo)} to {_pct(hi)}) | {r['brier']:.3f} | "
                     f"{r['crps']:.4f} | {skill} | {hit} | {r['seconds']:.2f} |")
    if result["skipped"]:
        lines += ["", "Not in this run:"] + [f"- {m}: {why}" for m, why in sorted(result["skipped"].items())]
    lines += ["", "How to read it: skill above 0% means a smaller error than a random walk on the same tickers and dates. "
              "'+cal' rows are the same model with its ranges stretched by its own past misses (no look-ahead)."]
    return "\n".join(lines) + "\n"


def write(result: dict, out_dir: Path) -> tuple[Path, Path]:
    rows = summarize(result["graded"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    md = out_dir / f"contest-{stamp}.md"
    js = out_dir / f"contest-{stamp}.json"
    md.write_text(markdown(result, rows), encoding="utf-8")
    js.write_text(json.dumps({"made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "summary": rows,
                              "dates": result["dates"], "tickers": result["tickers"], "skipped": result["skipped"],
                              "horizon": result["horizon"]}, indent=1, default=float), encoding="utf-8")
    return md, js
