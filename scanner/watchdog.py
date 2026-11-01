"""Nightly scan watchdog: which weekdays have no scan by the next day at 12:00 UTC?

Pure logic plus a tiny CLI. No network and no secrets: the CLI reads the repo's own
git log (scan commits are titled "Daily scan YYYY-MM-DD", where the date is the scan's US
market as-of date, not the day the job happened to run) and writes site/data/watchdog.json.

`python -m scanner.watchdog --need-scan` prints need=true|false (also to $GITHUB_OUTPUT): true when
the newest US session that has closed has no scan commit yet. The daily scan workflow uses it as a
gate, so a backup cron or a catch-up dispatch never runs a second scan for the same market date.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
LOOKBACK_DAYS = 10
DEADLINE_HOUR_UTC = 12
NY = ZoneInfo("America/New_York")
CLOSE_NY = (16, 0)  # NYSE regular close, New York time (early closes are treated as full days, a few hours of slack)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _easter(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(y, month, day)


def _nth_weekday(y: int, m: int, wd: int, n: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(wd - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_monday(y: int, m: int) -> date:
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=d.weekday())


def _observed(d: date) -> date | None:
    """NYSE rule: a Saturday holiday is observed the Friday before, a Sunday holiday the Monday after (New Year on a Saturday is the exception, handled by the caller)."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def us_market_holidays(year: int) -> set[date]:
    out = {
        _nth_weekday(year, 1, 0, 3),            # MLK Day
        _nth_weekday(year, 2, 0, 3),            # Presidents Day
        _easter(year) - timedelta(days=2),      # Good Friday
        _last_monday(year, 5),                  # Memorial Day
        _nth_weekday(year, 9, 0, 1),            # Labor Day
        _nth_weekday(year, 11, 3, 4),           # Thanksgiving
    }
    for d in (date(year, 6, 19), date(year, 7, 4), date(year, 12, 25)):
        out.add(_observed(d))
    ny = date(year, 1, 1)
    if ny.weekday() != 5:  # a Saturday New Year is not observed on Friday Dec 31
        out.add(_observed(ny))
    # Jan 1 of next year falling on Sunday is observed Monday Jan 2 (handled by that year's call)
    return out


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in us_market_holidays(d.year)


def market_date(now: datetime) -> date:
    """The newest US trading day whose 16:00 New York close has passed at `now` (DST handled by the zone)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ny = now.astimezone(NY)
    d = ny.date()
    if (ny.hour, ny.minute) < CLOSE_NY:
        d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def need_scan(scan_dates, now: datetime) -> bool:
    return market_date(now) not in set(scan_dates)


def missed_weekdays(scan_dates, now: datetime, lookback_days: int = LOOKBACK_DAYS, since: date | None = None) -> list[date]:
    """Trading weekdays in the last `lookback_days` whose scan is overdue.

    A weekday D is due at 12:00 UTC on D+1 (inclusive). It is missed if due and D is not in scan_dates.
    Weekends and US market holidays are never flagged. Days before `since` (default: the earliest
    scan date) are ignored so a young repo is not blamed for history it never had.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    have = {d for d in scan_dates}
    start = since or (min(have) if have else None)
    if start is None:
        return []
    out = []
    for back in range(lookback_days, -1, -1):
        d = now.date() - timedelta(days=back)
        if d < start or not is_trading_day(d):
            continue
        due = datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=DEADLINE_HOUR_UTC)
        if now >= due and d not in have:
            out.append(d)
    return out


def scan_dates_from_git(repo: Path = ROOT) -> list[date]:
    log = subprocess.run(["git", "log", "--format=%s"], cwd=repo, capture_output=True, text=True, check=True).stdout
    return sorted({date.fromisoformat(m) for m in re.findall(r"^Daily scan (\d{4}-\d{2}-\d{2})", log, re.M)})


def build_report(scan_dates, now: datetime) -> dict:
    """{checked_at, missed, status, market_date, last_scan, catch_up}. The site reads `missed`; the Brain can read
    `status` and `last_scan`. catch_up is true when the newest closed session has no scan, so the workflow asks
    for one (the scan's own gate makes a duplicate request a no-op)."""
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    missed = missed_weekdays(scan_dates, now)
    have = sorted(set(scan_dates))
    return {"checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "missed": [d.isoformat() for d in missed],
            "status": "missed" if missed else "ok", "market_date": market_date(now).isoformat(),
            "last_scan": have[-1].isoformat() if have else None, "catch_up": bool(have) and need_scan(have, now)}


def _gh_output(line: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(line + "\n")


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    now = _now()
    dates = scan_dates_from_git()
    if "--need-scan" in args:
        need = need_scan(dates, now)
        line = f"need={'true' if need else 'false'}"
        print(f"{line} (market date {market_date(now).isoformat()}, last scan "
              f"{dates[-1].isoformat() if dates else 'none'})")
        _gh_output(line)
        return 0
    rep = build_report(dates, now)
    _gh_output(f"catch_up={'true' if rep['catch_up'] else 'false'}")
    out = ROOT / "site" / "data" / "watchdog.json"
    out.write_text(json.dumps(rep, indent=1) + "\n")
    if rep["missed"]:
        print("Scan missed on " + ", ".join(rep["missed"]) + ". The nightly scan did not commit by 12:00 UTC the next day.", file=sys.stderr)
        return 1
    print("Watchdog ok: no missed scans in the last %d days." % LOOKBACK_DAYS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
