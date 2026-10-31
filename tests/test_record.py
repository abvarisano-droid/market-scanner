import json
from datetime import date

import pandas as pd

from scanner import record, tracker
from scripts import export_site, snapshot_record
from scanner import calllog


def fixture(hits_5d, n_5d, hits_20d=0, n_20d=0):
    """Ledger with outcome columns: n_5d graded 5-day calls with hits_5d wins, n_20d graded 20-day calls."""
    rows = []
    for i in range(max(n_5d, n_20d)):
        r = {"hit_5d": None, "alpha_5d": None, "hit_20d": None, "alpha_20d": None, "hit_60d": None, "alpha_60d": None}
        if i < n_5d:
            r["hit_5d"], r["alpha_5d"] = i < hits_5d, 0.02 if i < hits_5d else -0.01
        if i < n_20d:
            r["hit_20d"], r["alpha_20d"] = i < hits_20d, 0.05 if i < hits_20d else -0.05
        rows.append(r)
    return pd.DataFrame(rows)


def test_hit_rate_math_on_fixture():
    ev = fixture(hits_5d=6, n_5d=10, hits_20d=1, n_20d=4)
    w = {x["window"]: x for x in record.window_stats(ev, days=30)}
    assert (w[5]["n"], w[5]["hits"], w[5]["hit_rate_pct"]) == (10, 6, 60.0)
    assert w[5]["avg_excess_pct"] == round(100 * (6 * 0.02 - 4 * 0.01) / 10, 2) == 0.8
    assert (w[20]["n"], w[20]["hit_rate_pct"], w[20]["avg_excess_pct"]) == (4, 25.0, -2.5)
    assert (w[60]["n"], w[60]["hit_rate_pct"], w[60]["ci_low_pct"]) == (0, None, None)
    assert w[60]["label"] == "not graded yet"


def test_wilson_interval_known_values():
    lo, hi = record.wilson(6, 10)  # 95% Wilson for 6/10, worked by hand: 0.3127 to 0.8318
    assert abs(lo - 0.3127) < 5e-4 and abs(hi - 0.8318) < 5e-4
    lo, hi = record.wilson(0, 5)
    assert lo == 0.0 and 0.43 < hi < 0.44
    assert record.wilson(0, 0) is None
    assert record.wilson(50, 100)[0] < 0.5 < record.wilson(50, 100)[1]


def test_still_noise_until_21_trading_days_then_small_sample_flag():
    ev = fixture(6, 10)
    assert record.window_stats(ev, days=20)[0]["label"] == "still noise"
    assert record.window_stats(ev, days=21)[0]["label"] == "readable, small sample"
    big = fixture(30, 40)
    assert record.window_stats(big, days=21)[0]["label"] == "readable"
    assert record.window_stats(big, days=21)[0]["small_sample"] is False
    assert record.window_stats(pd.DataFrame(), days=0)[0]["n"] == 0


def test_hit_rate_stated_even_when_bad():
    w = record.window_stats(fixture(1, 10), days=40)[0]
    assert w["hit_rate_pct"] == 10.0 and w["ci_high_pct"] > w["hit_rate_pct"]


def test_scorecard_threshold_unchanged():
    ev = fixture(6, 10)
    ev["lens"] = "mispricing"
    assert tracker.scorecard(ev, 20)["status"] == "still noise"
    assert tracker.scorecard(ev, 21)["status"] == "enough days to read"


def test_committed_track_json_has_record_and_log():
    root = export_site.ROOT
    tr = json.loads((root / "site/data/track.json").read_text())
    assert tr["record"]["first_logged"] and len(tr["record"]["windows"]) == 3
    assert tr["log"]["raw_url"] == "data/picks.csv" and tr["log"]["verified"] is True
    assert (root / "site/data/picks.csv").read_text() == (root / "data/picks.csv").read_text()


def test_snapshot_written_once_per_week(tmp_path):
    text = (export_site.ROOT / "data/picks.csv").read_text()
    track = {"asof": "2026-10-30", "trading_days": 1, "status": "still noise", "record": {"first_logged": "2026-10-30", "windows": []}}
    p = snapshot_record.snapshot(track, text, date(2026, 10, 30), tmp_path)
    assert p.name == "2026-W44.json"
    body = json.loads(p.read_text())
    assert body["rows"] == calllog.verify(text, tracker.COLS)["n"] and body["head"] == calllog.verify(text, tracker.COLS)["head"]
    assert snapshot_record.snapshot(track, text, date(2026, 11, 2), tmp_path) is not None  # new ISO week
    assert snapshot_record.snapshot(track, text, date(2026, 10, 31), tmp_path) is None     # same week, not overwritten
