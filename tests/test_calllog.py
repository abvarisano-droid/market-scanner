import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from scanner import calllog, tracker
from scripts import check_call_log

ROOT = Path(__file__).resolve().parent.parent
COLS = tracker.COLS


def picks(*tickers, lens="mispricing"):
    return [{"ticker": t, "call": "Bullish", "price": 10.0, "lens": lens, "thesis": "cheap, vs peers"} for t in tickers]


def build(tmp_path, monkeypatch, days=("2026-10-26", "2026-10-27", "2026-10-28")):
    monkeypatch.setattr(tracker, "LEDGER", tmp_path / "picks.csv")
    for d in days:
        tracker.log_picks(picks("AAA", "BBB"), 400.0, today=d)
    return tracker.LEDGER


def test_log_is_chained_and_verifies(tmp_path, monkeypatch):
    p = build(tmp_path, monkeypatch)
    v = calllog.verify(p.read_text(), COLS)
    assert v["ok"] and v["n"] == 6 and len(v["head"]) == 64


def test_editing_a_past_row_fails_the_check(tmp_path, monkeypatch):
    p = build(tmp_path, monkeypatch)
    good = p.read_text()
    bad = good.replace("2026-10-26,AAA", "2026-10-26,ZZZ", 1)
    assert bad != good
    v = calllog.verify(bad, COLS)
    assert not v["ok"] and v["first_bad"] == 1
    assert check_call_log.run(bad, snap_dir=tmp_path / "none")  # non-empty problem list


def test_deleting_or_reordering_rows_fails(tmp_path, monkeypatch):
    p = build(tmp_path, monkeypatch)
    lines = p.read_text().splitlines()
    dropped = "\n".join(lines[:2] + lines[3:]) + "\n"
    assert not calllog.verify(dropped, COLS)["ok"]
    swapped = "\n".join([lines[0], lines[2], lines[1]] + lines[3:]) + "\n"
    assert not calllog.verify(swapped, COLS)["ok"]


def test_recomputed_chain_still_caught_against_base(tmp_path, monkeypatch):
    p = build(tmp_path, monkeypatch)
    base = p.read_text()
    rows = calllog.read_raw(base, COLS)
    rows[0][4] = "99.0"  # edit confidence of the first row, then recompute a valid chain
    forged = calllog.render(rows, COLS)
    assert calllog.verify(forged, COLS)["ok"]
    problems = check_call_log.run(forged, base_text=base, snap_dir=tmp_path / "none")
    assert any("frozen row 1" in x for x in problems)


def test_append_and_same_day_rerun_are_allowed(tmp_path, monkeypatch):
    p = build(tmp_path, monkeypatch)
    base = p.read_text()
    tracker.log_picks(picks("AAA", "CCC"), 401.0, today="2026-10-28")  # same-day rerun replaces that day
    tracker.log_picks(picks("DDD"), 402.0, today="2026-10-29")          # new day appends
    head = p.read_text()
    assert check_call_log.run(head, base_text=base, snap_dir=tmp_path / "none") == []
    assert calllog.read_raw(head, COLS)[:4] == calllog.read_raw(base, COLS)[:4]  # older days untouched


def test_logging_an_earlier_date_is_refused(tmp_path, monkeypatch):
    build(tmp_path, monkeypatch)
    try:
        tracker.log_picks(picks("EEE"), 400.0, today="2026-10-20")
    except ValueError as e:
        assert "append-only" in str(e)
    else:
        raise AssertionError("backdated call was accepted")


def test_backdated_row_caught_against_base(tmp_path, monkeypatch):
    p = build(tmp_path, monkeypatch)
    base = p.read_text()
    rows = calllog.read_raw(base, COLS) + [["2026-10-20", "ZZZ"] + [""] * (len(COLS) - 2)]
    problems = calllog.compare_to_base(base, calllog.render(rows, COLS), COLS)
    assert any("dated before" in x for x in problems)


def test_snapshot_anchor_detects_rewrite(tmp_path, monkeypatch):
    p = build(tmp_path, monkeypatch)
    text = p.read_text()
    snaps = tmp_path / "snaps"
    snaps.mkdir()
    n = calllog.settled_count(calllog.read_raw(text, COLS))
    (snaps / "2026-W44.json").write_text(json.dumps({"rows": n, "head": calllog.read_chain(text)[n - 1]}))
    assert check_call_log.run(text, snap_dir=snaps) == []
    rows = calllog.read_raw(text, COLS)
    rows[2][1] = "XXX"
    forged = calllog.render(rows, COLS)  # internally valid chain, but the snapshot head no longer matches
    assert any("snapshot" in x for x in check_call_log.run(forged, snap_dir=snaps))


def test_same_day_rerun_after_snapshot_still_passes(tmp_path, monkeypatch):
    from datetime import date
    from scripts import snapshot_record
    build(tmp_path, monkeypatch)
    snaps = tmp_path / "snaps"
    track = {"asof": "2026-10-28", "record": {}}
    p = snapshot_record.snapshot(track, tracker.LEDGER.read_text(), date(2026, 10, 28), snaps)
    assert json.loads(p.read_text())["rows"] == 4  # only the two earlier days
    assert check_call_log.run(tracker.LEDGER.read_text(), snap_dir=snaps) == []
    tracker.log_picks(picks("AAA", "CCC"), 400.0, today="2026-10-28")  # same-day rerun replaces the newest rows
    assert check_call_log.run(tracker.LEDGER.read_text(), snap_dir=snaps) == []


def test_snapshot_skipped_when_only_one_day_logged(tmp_path, monkeypatch):
    from datetime import date
    from scripts import snapshot_record
    build(tmp_path, monkeypatch, days=("2026-10-28",))
    assert snapshot_record.snapshot({"record": {}}, tracker.LEDGER.read_text(), date(2026, 10, 28), tmp_path / "s") is None


def test_snapshot_then_new_day_then_old_row_edit_detected(tmp_path, monkeypatch):
    from datetime import date
    from scripts import snapshot_record
    build(tmp_path, monkeypatch)
    snaps = tmp_path / "snaps"
    snapshot_record.snapshot({"record": {}}, tracker.LEDGER.read_text(), date(2026, 10, 28), snaps)
    tracker.log_picks(picks("AAA", "BBB"), 400.0, today="2026-10-29")
    assert check_call_log.run(tracker.LEDGER.read_text(), snap_dir=snaps) == []
    rows = calllog.read_raw(tracker.LEDGER.read_text(), COLS)
    rows[1][1] = "XXX"
    assert any("snapshot" in x for x in check_call_log.run(calllog.render(rows, COLS), snap_dir=snaps))


def test_committed_log_is_valid_and_script_exits_clean():
    assert calllog.verify((ROOT / "data" / "picks.csv").read_text(), COLS)["ok"]
    r = subprocess.run([sys.executable, "scripts/check_call_log.py"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_load_ignores_chain_column(tmp_path, monkeypatch):
    build(tmp_path, monkeypatch)
    assert list(tracker.load().columns) == COLS and isinstance(tracker.load()["date"].iloc[0], pd.Timestamp)


def test_newest_date_row_change_passes_nightly_but_fails_strict(tmp_path, monkeypatch):
    p = build(tmp_path, monkeypatch)
    base = p.read_text()
    rows = calllog.read_raw(base, COLS)
    assert rows[-1][0] == "2026-10-28"  # newest date
    rows[-1][4] = "99.0"  # change a newest-date row, then recompute a valid chain
    forged = calllog.render(rows, COLS)
    assert check_call_log.run(forged, base_text=base, snap_dir=tmp_path / "none") == []  # nightly (daily scan)
    problems = check_call_log.run(forged, base_text=base, snap_dir=tmp_path / "none", strict=True)  # CI
    assert any("frozen row" in x for x in problems)
    dropped = calllog.render(rows[:-1], COLS)
    assert check_call_log.run(dropped, base_text=base, snap_dir=tmp_path / "none", strict=True)
    appended = calllog.render(calllog.read_raw(base, COLS) + [["2026-10-29"] + rows[0][1:]], COLS)
    assert check_call_log.run(appended, base_text=base, snap_dir=tmp_path / "none", strict=True) == []


def test_ci_uses_strict_and_daily_scan_uses_nightly():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    daily = (ROOT / ".github/workflows/daily-scan.yml").read_text()
    assert "check_call_log.py --base origin/main --strict" in ci
    assert "check_call_log.py --base HEAD" in daily and "--strict" not in daily
