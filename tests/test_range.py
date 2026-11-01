"""Play the range: site/range.js checked against an independent Python version on real chart files."""
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
TICKERS = ["ABBV", "AJG", "0700.HK"]
M32 = 0xFFFFFFFF


def fnv(s):
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & M32
    return h


def mulberry(seed):
    a = seed & M32

    def nxt():
        nonlocal a
        a = (a + 0x6D2B79F5) & M32
        t = a
        t = ((t ^ (t >> 15)) * (t | 1)) & M32
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & M32)) & M32
        return ((t ^ (t >> 14)) & M32) / 4294967296

    return nxt


def simulate(dc, k, h, seed, n=1000):
    r = np.diff(np.log(np.asarray(dc[: k + 1], dtype=float)))
    r = r - r.mean()
    nxt = mulberry(fnv(seed))
    idx = np.array([[math.floor(nxt() * len(r)) for _ in range(h)] for _ in range(n)])
    ends = r[idx].sum(axis=1)
    start = dc[k]
    return {"p10": start * math.exp(np.percentile(ends, 10)), "p50": start * math.exp(np.percentile(ends, 50)),
            "p90": start * math.exp(np.percentile(ends, 90)), "up": round((ends > 0).sum() / n * 100)}


def regime(dc, k):
    a = np.asarray(dc, dtype=float)
    slope = a[k - 49:k + 1].mean() / a[k - 69:k - 19].mean() - 1
    path = np.abs(np.diff(a[k - 20:k + 1])).sum()
    eff = abs(a[k] - a[k - 20]) / path if path else 0
    return "TRENDING" if abs(slope) >= 0.03 and eff >= 0.3 else "CHOPPY"


def py_summary(dc, t):
    last = len(dc) - 1
    days = [last - 20 - 15 * j for j in range(4, -1, -1)]
    rounds, hits = [], 0
    for j, k in enumerate(days):
        s = simulate(dc, k, 20, f"{t}|{j}")
        real = dc[k + 20]
        s["hit"] = s["p10"] <= real <= s["p90"]
        s["regime"] = regime(dc, k)
        hits += s["hit"]
        rounds.append(s)
    return rounds, hits


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("t", TICKERS)
def test_range_js_matches_python(t):
    p = json.loads((SITE / "data/charts" / f"{t}.json").read_text())
    js = f"const R=require({json.dumps(str(SITE / 'range.js'))});const p=require({json.dumps(str(SITE / 'data/charts' / (t + '.json')))});" \
         f"console.log(JSON.stringify(R.summary(p.dc,{json.dumps(t)})))"
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    rounds, hits = py_summary(p["dc"], t)
    assert out["hits"] == hits and len(out["rounds"]) == 5
    for a, b in zip(out["rounds"], rounds):
        for q in ("p10", "p50", "p90"):
            assert a[q] == pytest.approx(b[q], rel=1e-9)
        assert a["hit"] == b["hit"] and a["upPct"] == b["up"] and a["regime"] == b["regime"]
    assert out["today"]["p10"] < p["dc"][-1] < out["today"]["p90"]


def test_range_copy_is_honest():
    js = (SITE / "v5.js").read_text()
    block = js[js.index("/* ---------- play the range"):js.index("/* ---------- fundamentals card")]
    text = " ".join(re.findall(r'"([^"]*)"', block)).lower()
    for w in ("buy", "sell", "target", "predict"):
        assert not re.search(r"\b" + w, text), w
    assert "Replay on past data. A range of typical moves, not a forecast. Not investment advice." in js
    for f in ("range.js", "v5.js", "style.css"):
        assert "—" not in (SITE / f).read_text() and "–" not in (SITE / f).read_text()
