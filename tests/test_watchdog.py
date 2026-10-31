import json
from datetime import date, datetime, timezone, timedelta

from scanner import watchdog as w


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


WEEK = [date(2026, 10, d) for d in (19, 20, 21, 22, 23, 26, 27, 28, 29, 30)]  # Mon..Fri x2


def test_normal_week_not_flagged():
    assert w.missed_weekdays(WEEK, utc(2026, 10, 31, 13, 7)) == []


def test_seeded_missed_day_flagged():
    scans = [d for d in WEEK if d != date(2026, 10, 28)]
    assert w.missed_weekdays(scans, utc(2026, 10, 31, 13, 7)) == [date(2026, 10, 28)]


def test_boundary_next_day_noon_utc():
    scans = [d for d in WEEK if d != date(2026, 10, 30)]
    assert w.missed_weekdays(scans, utc(2026, 10, 31, 11, 59)) == []
    assert w.missed_weekdays(scans, utc(2026, 10, 31, 12, 0)) == [date(2026, 10, 30)]


def test_weekends_not_flagged():
    # Friday scanned, nothing Sat/Sun; Monday 13:07 must not flag Sat or Sun
    assert w.missed_weekdays(WEEK, utc(2026, 11, 2, 13, 7)) == []
    # Friday's scan missing is due Saturday noon, flagged then
    scans = [d for d in WEEK if d != date(2026, 10, 30)]
    assert w.missed_weekdays(scans, utc(2026, 11, 2, 13, 7)) == [date(2026, 10, 30)]


def test_holidays_not_flagged():
    assert date(2026, 11, 26) in w.us_market_holidays(2026)  # Thanksgiving
    assert date(2026, 4, 3) in w.us_market_holidays(2026)  # Good Friday
    assert date(2026, 7, 3) in w.us_market_holidays(2026)  # July 4 observed
    scans = [date(2026, 11, d) for d in (23, 24, 25, 27)]
    assert w.missed_weekdays(scans, utc(2026, 11, 28, 13, 7)) == []
    assert w.missed_weekdays(scans + [], utc(2026, 11, 28, 13, 7), since=date(2026, 11, 23)) == []


def test_empty_history_and_pre_history_ignored():
    assert w.missed_weekdays([], utc(2026, 10, 31, 13)) == []
    assert w.missed_weekdays([date(2026, 10, 29), date(2026, 10, 30)], utc(2026, 10, 31, 13)) == []


def test_lookback_window():
    scans = [date(2026, 9, 1), date(2026, 10, 30)]
    old = w.missed_weekdays(scans, utc(2026, 10, 31, 13))
    assert old and min(old) >= date(2026, 10, 21)


def test_report_shape():
    rep = w.build_report([d for d in WEEK if d != date(2026, 10, 28)], utc(2026, 10, 31, 13, 7))
    assert rep == {"checked_at": "2026-10-31T13:07:00Z", "missed": ["2026-10-28"]}
    json.dumps(rep)


def test_git_subject_parser(tmp_path):
    import subprocess
    run = lambda *a: subprocess.run(a, cwd=tmp_path, check=True, capture_output=True)
    run("git", "init", "-q")
    for s in ("Daily scan 2026-10-29", "other", "Daily scan 2026-10-30"):
        run("git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "--allow-empty", "-qm", s)
    assert w.scan_dates_from_git(tmp_path) == [date(2026, 10, 29), date(2026, 10, 30)]
