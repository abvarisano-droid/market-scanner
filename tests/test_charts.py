import gzip
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scanner import charts
from scripts import export_v5 as v5

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def ohlc(close, start="2023-11-01"):
    idx = pd.bdate_range(start=start, periods=len(close))
    c = np.asarray(close, dtype=float)
    return pd.DataFrame({"Open": c * 0.995, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=idx)


def test_fan_is_centered_on_no_change_even_for_a_steady_riser():
    # 20% a year, every day the same: zero volatility, and the range must not carry the past trend forward
    c = 100 * np.exp(np.log(1.2) / 252 * np.arange(600))
    f = charts.fan(pd.Series(c))
    assert f["sigma"] == pytest.approx(0, abs=1e-6) and f["drift"] == 0
    assert f["up_pct"] == f["flat_pct"] == f["down_pct"] == 0
    assert f["flat"] == pytest.approx(c[-1], rel=1e-4)


def test_fan_matches_hand_math_on_random_walk():
    rng = np.random.default_rng(3)
    lr = rng.normal(0.0003, 0.02, 760)
    c = pd.Series(50 * np.exp(np.cumsum(lr)))
    f = charts.fan(c)
    sigma = np.log(c).diff().dropna().std(ddof=1) * math.sqrt(252)
    assert f["sigma"] == pytest.approx(sigma, abs=1e-4)
    assert f["flat_pct"] == 0
    assert f["up_pct"] == pytest.approx(100 * (math.exp(sigma) - 1), abs=0.06)
    assert f["down_pct"] == pytest.approx(100 * (math.exp(-sigma) - 1), abs=0.06)
    assert f["down_pct"] < 0 < f["up_pct"]
    assert f["up"] == pytest.approx(c.iloc[-1] * (1 + f["up_pct"] / 100), rel=1e-3)
    p = charts.path(100, sigma, 1)
    assert p[0] == 100 and p[-1] == pytest.approx(100 * math.exp(sigma))


def test_refan_recomputes_from_stored_sigma():
    store = {"AAA": {"last": 200.0, "fan": {"sigma": 0.3, "median_log": 0.39, "base_pct": 47.9, "years": 3}}}
    f = charts.refan(store)["AAA"]["fan"]
    assert "base_pct" not in f and "median_log" not in f and f["flat"] == 200.0
    assert f["up_pct"] == pytest.approx(100 * (math.exp(0.3) - 1), abs=0.06)


def test_fan_needs_a_year_of_history():
    assert charts.fan(pd.Series(np.linspace(10, 20, 200))) is None


def test_build_weekly_then_daily_and_index_map():
    rng = np.random.default_rng(5)
    df = ohlc(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 756))))
    p = charts.build(df, "AAA", "USD", {"label": "Earnings", "date": "2030-01-01"})
    n = len(p["c"])
    assert n - p["daily_from"] == charts.DAILY_BARS
    assert p["daily_from"] < 140  # about 2.5 years of weekly candles
    assert len(p["dc"]) == 756 and len(p["ix"]) == n and p["ix"][-1] == 755
    assert all(p["dc"][i] == pytest.approx(p["c"][k], rel=1e-4) for k, i in enumerate(p["ix"]))
    assert all(lo <= min(o, c) and hi >= max(o, c) for o, hi, lo, c in zip(p["o"], p["h"], p["l"], p["c"]))
    assert p["x"] == sorted(p["x"]) and p["last"] == round(df["Close"].iloc[-1], 2)
    assert p["lo52"] <= p["last"] <= p["hi52"]


def test_next_earnings_only_future_dates():
    from datetime import date
    d = [date(2026, 10, 28), date(2026, 11, 18)]
    assert charts.next_earnings("X", date(2026, 10, 30), lambda t: d) == {"label": "Earnings", "date": "2026-11-18"}
    assert charts.next_earnings("X", date(2026, 12, 1), lambda t: d) is None
    assert charts.next_earnings("X", date(2026, 10, 1), lambda t: 1 / 0) is None


def test_committed_chart_files():
    d = json.loads((SITE / "data/v5.json").read_text())
    files = {f.stem: f for f in (SITE / "data/charts").glob("*.json")}
    charted = {t for t, s in d["stocks"].items() if s.get("chart")}
    assert charted == set(files) and len(files) >= 0.9 * len(d["stocks"])
    for t, f in files.items():
        raw = f.read_bytes()
        assert len(gzip.compress(raw)) < 40_000, t
        p = json.loads(raw)
        assert p["t"] == t and len(p["dc"]) >= 60 and p["dc"][-1] == pytest.approx(p["last"], rel=1e-3)
        txt = raw.decode()
        assert not v5.BANNED.search(txt) and "target" not in txt.lower()


def test_fundamentals_gap_and_bad_pe():
    f = v5.fundamentals({"price": 100, "targetMeanPrice": 120, "numberOfAnalystOpinions": 9, "forwardPE": -3,
                         "trailingPE": 25.04, "enterpriseToEbitda": float("nan"), "sector": "Tech", "marketCap": 5e9})
    assert f["consensus_gap"] == 0.2 and f["analysts"] == 9
    assert f["fwd_pe"] is None and f["ttm_pe"] == 25.0 and f["ev_ebitda"] is None
    assert v5.fundamentals({"price": 100, "targetMeanPrice": 120, "numberOfAnalystOpinions": 0})["consensus_gap"] is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_indicators_match_pandas():
    rng = np.random.default_rng(9)
    c = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.015, 400))))
    js = f"""
      const I = require({json.dumps(str(SITE / 'indicators.js'))});
      const c = {json.dumps(c.round(6).tolist())};
      const bb = I.bollinger(c, 20, 2), m = I.macd(c, 12, 26, 9);
      console.log(JSON.stringify({{sma: I.sma(c, 50), rsi: I.rsi(c, 14), up: bb.up, lo: bb.lo, macd: m.macd, sig: m.signal, hist: m.hist}}));
    """
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    c = c.round(6)
    ref_sma = c.rolling(50).mean()
    mid, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    d = c.diff()
    g = d.clip(lower=0).fillna(0).iloc[1:].ewm(alpha=1 / 14, adjust=False).mean()
    l_ = (-d.clip(upper=0)).fillna(0).iloc[1:].ewm(alpha=1 / 14, adjust=False).mean()
    ref_rsi = 100 - 100 / (1 + g / l_)
    e12, e26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    line = e12 - e26
    sig = line.ewm(span=9, adjust=False).mean()

    def same(js_vals, ref, start):
        for i in range(start, len(c)):
            assert js_vals[i] == pytest.approx(ref.iloc[i] if hasattr(ref, "iloc") else ref[i], rel=1e-7, abs=1e-9), i
        assert all(v is None for v in js_vals[:start - 1]) if start > 1 else True

    same(out["sma"], ref_sma, 49)
    same(out["up"], mid + 2 * sd, 19)
    same(out["lo"], mid - 2 * sd, 19)
    for i in range(14, len(c)):
        assert out["rsi"][i] == pytest.approx(ref_rsi.loc[i], rel=1e-7)
    for i in range(33, len(c)):
        assert out["macd"][i] == pytest.approx(line.iloc[i], rel=1e-7, abs=1e-9)
        assert out["sig"][i] == pytest.approx(sig.iloc[i], rel=1e-7, abs=1e-9)
        assert out["hist"][i] == pytest.approx(line.iloc[i] - sig.iloc[i], rel=1e-6, abs=1e-9)
    assert out["macd"][32] is None and 0 <= min(v for v in out["rsi"] if v is not None)


def test_earnings_dates_times_out(monkeypatch):
    import time
    import types
    import sys
    from scanner import data
    slow = types.SimpleNamespace(Ticker=lambda t: types.SimpleNamespace(calendar=time.sleep(0.5) or {"Earnings Date": ["x"]}))
    monkeypatch.setitem(sys.modules, "yfinance", slow)
    assert data.earnings_dates("AAA", timeout=0.05) == []
    fast = types.SimpleNamespace(Ticker=lambda t: types.SimpleNamespace(calendar={"Earnings Date": ["2026-11-12"]}))
    monkeypatch.setitem(sys.modules, "yfinance", fast)
    assert data.earnings_dates("AAA") == ["2026-11-12"]


def test_earnings_dates_timeout_does_not_hold_exit():
    import subprocess
    import sys
    import time
    code = (
        "import sys, time, types\n"
        "sys.modules['yfinance'] = types.SimpleNamespace(Ticker=lambda t: (time.sleep(30), None)[1])\n"
        "from scanner import data\n"
        "assert data.earnings_dates('AAA', timeout=0.1) == []\n"
    )
    t0 = time.monotonic()
    subprocess.run([sys.executable, "-c", code], check=True, cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]), timeout=20)
    assert time.monotonic() - t0 < 10
