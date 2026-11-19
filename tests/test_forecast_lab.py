"""Forecast Lab: contest math, no look-ahead, calibration, options math. No network, no model weights."""
import math

import numpy as np
import pandas as pd
import pytest

from forecast_lab import calibrate, core, options_move, report, scoring, walkforward
from forecast_lab.baselines import GBM, Bootstrap, RandomWalk
from forecast_lab.core import LEVELS, ContestantUnavailable, Forecast


def series(n=420, seed=1, vol=0.02, start="2024-01-02"):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, vol, n)))
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6}, index=idx)


def test_forecast_shape_sorting_and_prices():
    q = np.tile(np.linspace(-0.05, 0.05, 9), (5, 1))[:, ::-1]  # crossed on purpose
    f = Forecast("m", "T", "2026-01-02", 50.0, q)
    assert (np.diff(f.q, axis=1) >= 0).all()
    assert f.prices()[4] == pytest.approx(50.0)
    assert f.p_up() == pytest.approx(0.5, abs=1e-9)
    with pytest.raises(ValueError):
        Forecast("m", "T", "d", 1.0, np.zeros((5, 3)))


def test_cdf_interpolates_and_clamps():
    qs = np.linspace(-0.04, 0.04, 9)
    assert core.cdf(qs, 0.0) == pytest.approx(0.5)
    assert core.cdf(qs, -0.04) == pytest.approx(0.1)
    assert core.cdf(qs, -1.0) == 0.005 and core.cdf(qs, 1.0) == 0.995


@pytest.mark.parametrize("model", [RandomWalk(), GBM(), Bootstrap()])
def test_baselines_are_monotone_widening_and_seeded(model):
    d = series()
    q = model.forecast_q(d, "T", "2025-06-02", 5)
    assert q.shape == (5, 9)
    assert (np.diff(q, axis=1) >= 0).all()
    width = q[:, -1] - q[:, 0]
    assert width[-1] > width[0]  # further out, wider range
    assert np.array_equal(q, model.forecast_q(d, "T", "2025-06-02", 5))


def test_random_walk_matches_normal_quantiles():
    d = series(vol=0.01)
    sd = np.std(np.diff(np.log(d["close"].to_numpy()))[-60:], ddof=1)
    q = RandomWalk().forecast_q(d, "T", "x", 5)
    assert q[4, 8] == pytest.approx(sd * math.sqrt(5) * 1.2815516, rel=1e-6)


def test_pinball_crps_and_inside():
    qs = np.zeros(9)
    assert scoring.pinball(qs, LEVELS, 0.0) == 0.0
    assert scoring.pinball(qs, LEVELS, 1.0) == pytest.approx(np.mean(LEVELS))
    assert scoring.crps(qs, LEVELS, 1.0) == pytest.approx(2 * np.mean(LEVELS))
    qs = np.linspace(-0.1, 0.1, 9)
    assert scoring.inside(qs, LEVELS, 0.05) and not scoring.inside(qs, LEVELS, 0.2)


def test_brier_and_wilson():
    assert scoring.brier(0.5, 0.01) == 0.25
    assert scoring.brier(1.0, -0.01) == 1.0
    lo, hi = scoring.wilson(80, 160)
    assert lo == pytest.approx(0.423, abs=0.002) and hi == pytest.approx(0.577, abs=0.002)
    assert scoring.wilson(0, 0) == (0.0, 1.0)


def test_skill_is_paired_and_ranked():
    def g(model, t, crps):
        return {"model": model, "ticker": t, "asof": "d", "crps": crps, "brier": 0.25, "in80": True, "in40": False,
                "dir_hit": True, "seconds": 0.0}
    graded = [g("random_walk", "A", 1.0), g("random_walk", "B", 1.0), g("good", "A", 0.5), g("bad", "A", 2.0),
              g("bad", "C", 0.0)]  # bad's easy C has no random-walk pair, so it cannot help bad
    rows = scoring.summarize(graded)
    assert [r["model"] for r in rows][:1] == ["good"]
    bad = next(r for r in rows if r["model"] == "bad")
    assert bad["skill"] == pytest.approx(-1.0) and bad["paired"] == 1


def test_calibration_widens_an_overconfident_model():
    rng = np.random.default_rng(3)
    narrow = np.linspace(-0.01, 0.01, 9)  # claims +-1%, truth has sd 2%
    hist = [(narrow, float(rng.normal(0, 0.02))) for _ in range(200)]
    f = calibrate.fit_factor(hist)
    assert f > 2.0
    held = np.mean([scoring.inside(calibrate.stretch(q, f), LEVELS, y) for q, y in hist])
    assert held >= 0.8
    assert calibrate.fit_factor(hist[:5]) == 1.0  # too little history: unchanged


class Spy:
    """A contestant that records how much history it was shown."""
    name = "spy"

    def __init__(self):
        self.seen = []

    def forecast_q(self, df, ticker, asof, horizon=5):
        self.seen.append((asof, df.index[-1].date().isoformat(), len(df)))
        return RandomWalk().forecast_q(df, ticker, asof, horizon)


def test_walkforward_never_shows_the_future():
    prices = {"A": series(seed=1), "B": series(seed=2)}
    spy = Spy()
    res = walkforward.run(prices, {"spy": spy}, weeks=12, step=5, log=lambda *a: None)
    assert spy.seen and all(asof == last for asof, last, _ in spy.seen)
    for r in res["graded"]:
        assert r["outcome_date"] > r["asof"]
        d = walkforward.normalize(prices[r["ticker"]])
        i = d.index.get_loc(pd.Timestamp(r["asof"]))
        assert r["realized"] == pytest.approx(math.log(d["close"].iloc[i + 5] / d["close"].iloc[i]))


def test_walkforward_calibration_uses_only_known_outcomes():
    prices = {"A": series(seed=4)}
    res = walkforward.run(prices, {"random_walk": RandomWalk()}, weeks=40, step=1, log=lambda *a: None)
    cal = [r for r in res["graded"] if r["model"] == "random_walk+cal"]
    assert cal[0]["stretch"] == 1.0  # nothing known yet on the first date
    assert len(cal) == len([r for r in res["graded"] if r["model"] == "random_walk"])


def test_unavailable_model_is_skipped_not_fatal():
    class Missing:
        name = "missing"

        def forecast_q(self, *a, **k):
            raise ContestantUnavailable("not installed")

    class Live:
        name = "live"
        live_only = True

        def forecast_q(self, *a, **k):
            raise AssertionError("must not be called in a backtest")

    res = walkforward.run({"A": series()}, {"missing": Missing(), "live": Live(), "random_walk": RandomWalk()},
                          weeks=8, log=lambda *a: None)
    assert set(res["skipped"]) == {"missing", "live"}
    assert any(r["model"] == "random_walk" for r in res["graded"])


def test_report_markdown(tmp_path):
    res = walkforward.run({"A": series(), "B": series(seed=9)}, {"random_walk": RandomWalk(), "gbm": GBM()},
                          weeks=10, log=lambda *a: None)
    md, js = report.write(res, tmp_path)
    text = md.read_text()
    assert "Not investment advice" in text and "random_walk" in text and "gbm" in text
    assert "\u2014" not in text  # no em dashes, ever
    assert js.exists()


def test_options_math():
    sig = options_move.sigma_from_straddle(straddle=4.0, spot=100.0)
    assert sig == pytest.approx(0.04 * math.sqrt(math.pi / 2))
    q = options_move.quantiles_from_sigma(sig, days_to_expiry=5, horizon=5)
    assert q.shape == (5, 9)
    assert (q[4, 8] - q[4, 0]) / 2 == pytest.approx(1.2815516 * sig, rel=1e-6)
    from datetime import date
    assert options_move.pick_expiry(["2026-11-20", "2026-11-27"], date(2026, 11, 19)) == "2026-11-27"
    with pytest.raises(ContestantUnavailable):
        options_move.pick_expiry(["2026-11-20"], date(2026, 11, 19))


def test_atm_straddle_refuses_one_sided_quotes():
    calls = pd.DataFrame({"strike": [95, 100, 105], "bid": [6, 2, 0.5], "ask": [6.2, 2.2, 0.6]})
    puts = pd.DataFrame({"strike": [95, 100, 105], "bid": [0.4, 1.9, 5.8], "ask": [0.5, 2.1, 6.0]})
    assert options_move.atm_straddle(calls, puts, 101) == pytest.approx(2.1 + 2.0)
    puts.loc[1, "bid"] = 0
    with pytest.raises(ContestantUnavailable):
        options_move.atm_straddle(calls, puts, 100)


def test_model_adapters_fail_soft_without_packages(monkeypatch):
    from forecast_lab import models
    import builtins
    real = builtins.__import__

    def no_ml(name, *a, **k):
        if name.split(".")[0] in {"timesfm", "chronos", "uni2ts", "gluonts", "torch"}:
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_ml)
    d = series()
    for cls in (models.TimesFM, models.Chronos, models.Moirai, models.Kronos):
        with pytest.raises(ContestantUnavailable):
            cls().forecast_q(d, "T", "2025-06-02", 5)
