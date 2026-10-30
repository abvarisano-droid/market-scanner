import numpy as np, pandas as pd, pytest
import signals as s
from tests.fixtures.synthetic import trending, make_prices


def test_label_thresholds():
    assert s.label(65) == "Bullish" and s.label(64.9) == "Neutral"
    assert s.label(35) == "Bearish" and s.label(35.1) == "Neutral"
    assert s.label(0) == "Bearish" and s.label(100) == "Bullish" and s.label(50) == "Neutral"


def test_rsi_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert s.rsi(up) == 100.0
    assert s.rsi(up[::-1].reset_index(drop=True)) < 1
    assert 40 < s.rsi(pd.Series([1.0, 2.0] * 30)) < 60


def test_ma20_rule():
    c = pd.Series([100.0] * 19 + [110.0])
    r = s.rule_ma20(c)
    assert r.score > 0.5 and "above" in r.text
    c2 = pd.Series([100.0] * 19 + [90.0])
    assert s.rule_ma20(c2).score < 0.5 and "below" in s.rule_ma20(c2).text
    assert s.rule_ma20(pd.Series([100.0] * 20)).score == 0.5


def test_momentum_rule():
    up = pd.Series(np.linspace(100, 120, 30))
    dn = pd.Series(np.linspace(120, 100, 30))
    assert s.rule_momentum(up).score > 0.9 and s.rule_momentum(dn).score < 0.1


def test_rsi_rule_notes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    r = s.rule_rsi(up)
    assert r.score == 1.0 and "stretched" in r.text
    assert "washed out" in s.rule_rsi(up[::-1].reset_index(drop=True)).text


def test_volume_rule_direction():
    base = pd.DataFrame({"close": [100.0] * 29 + [102.0], "volume": [1000] * 29 + [3000]})
    assert s.rule_volume(base).score > 0.5
    dn = base.copy(); dn.loc[29, "close"] = 98.0
    assert s.rule_volume(dn).score < 0.5
    quiet = base.copy(); quiet.loc[29, "volume"] = 1000
    assert s.rule_volume(quiet).score == 0.5


def test_ma50_ma200_slope_rules():
    up, dn = trending(300, 0.003)["close"], trending(300, -0.003)["close"]
    for f in (s.rule_ma50, s.rule_ma200, s.rule_slope):
        assert f(up).score > 0.5 and f(dn).score < 0.5
    assert "rising" in s.rule_slope(up).text and "falling" in s.rule_slope(dn).text


def test_relative_strength_rule():
    spy = trending(300, 0.001)["close"]
    assert s.rule_rs(trending(300, 0.004)["close"], spy).score > 0.5
    assert s.rule_rs(trending(300, -0.002)["close"], spy).score < 0.5
    assert "ahead of" in s.rule_rs(trending(300, 0.004)["close"], spy).text


def test_high52_rule():
    up = trending(300, 0.003)["close"]
    assert s.rule_high52(up).score == 1.0 and "52-week high" in s.rule_high52(up).text
    crashed = pd.Series(list(np.linspace(100, 200, 280)) + list(np.linspace(200, 120, 20)))
    r = s.rule_high52(crashed)
    assert r.score == pytest.approx(0.0) and "below" in r.text


def test_horizon_bull_and_bear():
    spy = trending(300, 0.001)
    bull = s.short_term(trending(300, 0.004)); bear = s.short_term(trending(300, -0.004))
    assert bull["label"] == "Bullish" or bull["score"] > 60
    assert bear["score"] < bull["score"] and bear["label"] in ("Bearish", "Neutral")
    sw_b = s.swing(trending(300, 0.004), spy); sw_r = s.swing(trending(300, -0.004), spy)
    assert sw_b["label"] == "Bullish" and sw_r["label"] == "Bearish"
    assert len(sw_b["reasons"]) == 3 and all(isinstance(x, str) for x in sw_b["reasons"])
    assert 0 <= sw_r["score"] <= 100


def test_insufficient_data():
    assert s.short_term(make_prices("X", 10)) is None
    assert s.swing(make_prices("X", 100), make_prices("SPY", 100)) is None
    assert s.short_term(None) is None


def test_deterministic():
    a = s.short_term(make_prices("AAA", 300)); b = s.short_term(make_prices("AAA", 300))
    assert a == b


def test_swing_rs_aligns_dates_with_spy():
    import numpy as np, pandas as pd
    from signals import swing
    dates = pd.bdate_range("2024-01-01", periods=300).strftime("%Y-%m-%d")
    stock = pd.DataFrame({"date": dates, "close": np.linspace(100, 130, 300), "volume": 1e6})
    spy_full = pd.DataFrame({"date": dates, "close": 100.0})
    # SPY missing 20 dates: misaligned positional RS would compare different days
    spy_gap = spy_full.drop(index=range(250, 270)).reset_index(drop=True)
    a = swing(stock, spy_gap)
    b = swing(stock.drop(index=range(250, 270)).reset_index(drop=True), spy_gap)
    rs_a = [r for r in a["reasons"] if "S&P" in r]
    assert a is not None and b is not None
    # with alignment, RS text matches the aligned computation
    from signals import rule_rs
    m = stock.merge(spy_gap, on="date", suffixes=("", "_spy"))
    exp = rule_rs(m["close"], m["close_spy"]).text
    assert all(r == exp for r in rs_a)
