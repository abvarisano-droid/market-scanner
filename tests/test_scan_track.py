import json, pandas as pd
import scan, track
from tests.fixtures.synthetic import write_all, make_prices, trending
from prices import parse_chart
from universe import parse_universe


def build(tmp_path, n=40):
    write_all(tmp_path, n)
    uni = pd.read_csv(tmp_path / "universe.csv")
    frames = {t: pd.read_csv(tmp_path / "prices" / f"{t}.csv") for t in uni["ticker"]}
    spy = pd.read_csv(tmp_path / "prices" / "SPY.csv")
    return uni, frames, spy


def test_funnel_counts(tmp_path):
    uni, frames, spy = build(tmp_path)
    frames["SYN000"] = frames["SYN000"].tail(50)          # short history
    frames["SYN001"] = frames["SYN001"].iloc[:-3]          # stale
    del frames["SYN002"]                                   # no data
    res = scan.run_scan(uni, frames, spy)
    f = res["funnel"]["swing"]
    assert f["universe"] == 40 and f["with_data"] == 39 and f["passed_checks"] == 37
    assert f["scored"] == 37
    assert res["dropped"]["short history"] == 1 and res["dropped"]["stale"] == 1 and res["dropped"]["no data"] == 1
    for hz in res["horizons"].values():
        assert len(hz["top_bull"]) <= 15 and len(hz["top_bear"]) <= 15
        assert sum(hz["counts"].values()) == 37
        sc = [r["score"] for r in hz["top_bull"]]
        assert sc == sorted(sc, reverse=True)


def test_scan_reproducible(tmp_path):
    uni, frames, spy = build(tmp_path)
    a = scan.run_scan(uni, frames, spy); b = scan.run_scan(uni, frames, spy)
    assert a == b
    frames["SYN005"] = frames["SYN005"].copy(); frames["SYN005"].loc[frames["SYN005"].index[-1], "close"] *= 1.01
    assert scan.run_scan(uni, frames, spy)["inputs_hash"] != a["inputs_hash"]


def test_full_scan_end_to_end(tmp_path, monkeypatch):
    data, out = tmp_path / "d", tmp_path / "o"
    write_all(data, 80)
    monkeypatch.setattr("sys.argv", ["scan", "--data-dir", str(data), "--out-dir", str(out)])
    scan.main()
    latest = json.loads((out / "latest.json").read_text())
    assert (out / f"scan-{latest['asof']}.json").exists()
    assert latest["funnel"]["short_term"]["scored"] == 80
    assert latest["horizons"]["swing"]["top_bull"][0]["reasons"]
    r = track.run_track(latest, data, out)
    assert r["status"] == "still noise" and (out / "track.json").exists()
    assert (data / "calls.csv").exists()


def test_log_calls_idempotent(tmp_path):
    uni, frames, spy = build(tmp_path)
    res = scan.run_scan(uni, frames, spy)
    p = tmp_path / "calls.csv"
    n1 = track.log_calls(res, p); n2 = track.log_calls(res, p)
    assert n1 > 0 and n2 == 0
    df = pd.read_csv(p)
    assert list(df.columns) == track.CALL_COLS and len(df) == n1


def _frames(stock_slope, spy_slope=0.0, n=30):
    return trending(n, stock_slope), trending(n, spy_slope)


def test_grade_bullish_and_bearish():
    st, spy = _frames(0.01)
    d0 = st["date"].iloc[-12]
    g = track.grade_call({"date": d0, "label": "Bullish", "horizon": "short_term"}, st, spy)
    assert g["days"] == 10 and g["closed"] and g["excess"] > 0
    g2 = track.grade_call({"date": d0, "label": "Bearish", "horizon": "short_term"}, st, spy)
    assert g2["excess"] < 0 and abs(g2["excess"] + g["excess"]) < 1e-12


def test_grade_open_and_skips():
    st, spy = _frames(0.01)
    d = st["date"].iloc[-5]
    g = track.grade_call({"date": d, "label": "Bullish", "horizon": "swing"}, st, spy)
    assert g["days"] == 3 and not g["closed"]
    assert track.grade_call({"date": d, "label": "Neutral", "horizon": "swing"}, st, spy) is None
    assert track.grade_call({"date": st["date"].iloc[-1], "label": "Bullish", "horizon": "swing"}, st, spy) is None
    # next bar exists but nothing after the entry bar yet: still pending
    assert track.grade_call({"date": st["date"].iloc[-2], "label": "Bullish", "horizon": "swing"}, st, spy) is None


def test_entry_is_next_close():
    st, spy = _frames(0.01)
    d0 = st["date"].iloc[-12]
    g = track.grade_call({"date": d0, "label": "Bullish", "horizon": "short_term"}, st, spy)
    assert g["entry_date"] == st["date"].iloc[-11]
    exp = st["close"].iloc[-1] / st["close"].iloc[-11] - 1
    assert abs(g["stock_return"] - exp) < 1e-12


def test_summary_noise_threshold():
    g = [{"horizon": "swing", "excess": 0.02}, {"horizon": "swing", "excess": -0.01}]
    s20 = track.summarize(g, 20); s21 = track.summarize(g, 21)
    assert s20["status"] == "still noise" and s21["status"] != "still noise"
    assert s20["by_horizon"]["swing"]["hit_rate_pct"] == 50.0
    assert s20["by_horizon"]["short_term"]["graded"] == 0


def test_parse_chart():
    payload = {"chart": {"result": [{"timestamp": [1700000000, 1700086400],
        "indicators": {"quote": [{"open": [1, 2], "high": [2, 3], "low": [1, 1], "close": [1.5, None], "volume": [10, 20]}],
                       "adjclose": [{"adjclose": [1.4, None]}]}}]}}
    df = parse_chart(payload)
    assert len(df) == 1 and df["close"].iloc[0] == 1.4


def test_parse_universe():
    page = '<table id="constituents"><tr><th>Symbol</th></tr><tr><td><a>BRK.B</a></td><td>Berkshire</td><td>Financials</td></tr><tr><td><a>AAPL</a></td><td>Apple</td><td>Tech</td></tr></table>'
    df = parse_universe(page)
    assert list(df["ticker"]) == ["AAPL", "BRK-B"]
