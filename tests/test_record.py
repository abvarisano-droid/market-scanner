import json
from datetime import date

import pandas as pd

from scanner import calllog, record, tracker
from scripts import export_site, snapshot_record


def test_wilson_interval_known_values():
    lo, hi = record.wilson(6, 10)  # 95% Wilson for 6/10, worked by hand: 0.3127 to 0.8318
    assert abs(lo - 0.3127) < 5e-4 and abs(hi - 0.8318) < 5e-4
    lo, hi = record.wilson(0, 5)
    assert lo == 0.0 and 0.43 < hi < 0.44
    assert record.wilson(0, 0) is None
    assert record.wilson(50, 100)[0] < 0.5 < record.wilson(50, 100)[1]


def test_interval_pct_from_rate_and_n():
    assert record.interval_pct(0.6, 10) == {"hits": 6, "ci_low_pct": 31.3, "ci_high_pct": 83.2}
    assert record.interval_pct(None, 0) == {"hits": 0, "ci_low_pct": None, "ci_high_pct": None}
    bad = record.interval_pct(0.1, 10)  # a bad rate is shown as it is, with its range
    assert bad["hits"] == 1 and bad["ci_high_pct"] > 10


def test_still_noise_until_60_trading_days():
    ev = pd.DataFrame({"hit_5d": [True], "alpha_5d": [0.01], "lens": ["mispricing"]})
    assert tracker.MIN_DAYS == 60
    assert tracker.scorecard(ev, 59)["status"] == "still noise"
    assert tracker.scorecard(ev, 60)["status"] == "enough days to read"
    assert "need 60" in tracker.scorecard(ev, 12)["note"]


def test_track_export_folds_n_and_interval_into_lens_windows():
    sc = {"trading_days": 12, "status": "still noise", "note": "",
          "by_lens": {"mispricing": {"calls": 10, "hit_rate_5d": 0.6, "avg_alpha_5d": 0.01, "n_5d": 10}}}
    tr = export_site.build_track({"date": "2026-10-30", "scorecard": sc, "ledger": []}, sample=True)
    w = tr["by_lens"]["mispricing"]["windows"]
    assert (w["5"]["graded"], w["5"]["hits"], w["5"]["ci_low_pct"], w["5"]["ci_high_pct"]) == (10, 6, 31.3, 83.2)
    assert w["60"]["graded"] == 0 and w["60"]["ci_low_pct"] is None
    assert tr["min_days"] == 60 and tr["interval"] == "95% Wilson interval"


def test_committed_track_json_has_intervals():
    tr = json.loads((export_site.ROOT / "site/data/track.json").read_text())
    for lens in tr["by_lens"].values():
        for w in lens["windows"].values():
            assert "ci_low_pct" in w and "hits" in w
    assert tr["min_days"] == 60 and tr["log"]["verified"] is True


def test_snapshot_written_once_per_week(tmp_path):
    base = (export_site.ROOT / "data/picks.csv").read_text()
    rows = calllog.read_raw(base, tracker.COLS)
    earlier = [["2026-10-29"] + r[1:] for r in rows[:3]]
    text = calllog.render(earlier + rows, tracker.COLS)  # an earlier day exists, so some rows are settled
    track = {"asof": "2026-10-30", "trading_days": 1, "min_days": 60, "status": "still noise", "first_logged": "2026-10-29", "by_lens": {}}
    p = snapshot_record.snapshot(track, text, date(2026, 10, 30), tmp_path)
    assert p.name == "2026-W44.json"
    body = json.loads(p.read_text())
    n = calllog.settled_count(calllog.read_raw(text, tracker.COLS))
    assert body["rows"] == n and body["head"] == calllog.read_chain(text)[n - 1] and "Not investment advice" in body["note"]
    assert snapshot_record.snapshot(track, text, date(2026, 11, 2), tmp_path) is not None  # new ISO week
    assert snapshot_record.snapshot(track, text, date(2026, 10, 31), tmp_path) is None     # same week, not overwritten
