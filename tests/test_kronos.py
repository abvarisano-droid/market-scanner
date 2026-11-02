"""Kronos model range: band math, the walk-forward held count, no look-ahead, output checks, pins and honest copy.

No network and no torch: chart files and model paths are fixtures.
"""
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from scanner import kronos_band as kb
from scripts import kronos_bands as kbs

ROOT = Path(__file__).resolve().parents[1]
KDIR = ROOT / "kronos"
NOW = datetime(2026, 10, 31, 2, 0, tzinfo=timezone.utc)


def chart(n=80, end="2026-10-30", px=100.0):
    days, d = [], date.fromisoformat(end)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    d0 = days[0]
    c = [px + i * 0.1 for i in range(n)]
    return {"t": "AAA", "asof": end, "d0": d0.isoformat(), "x": [(x - d0).days for x in days], "daily_from": 0,
            "o": c, "h": [v + 1 for v in c], "l": [v - 1 for v in c], "c": c, "v": [1000] * n, "cur": "USD"}


def paths(n, h, moves, base):
    cl = [[base * (1 + moves[i % len(moves)] * (k + 1) / h) for k in range(h)] for i in range(n)]
    return {"close": cl, "high": [[v * 1.001 for v in p] for p in cl], "low": [[v * 0.999 for v in p] for p in cl]}


def test_band_math():
    b = kb.band(paths(10, 20, [0.1, -0.1], 100.0)["close"], 100.0)
    assert b["up"] == 5 and b["down"] == 5 and b["n"] == 10 and len(b["p10"]) == 20
    assert b["p10"][-1] == pytest.approx(90.0) and b["p90"][-1] == pytest.approx(110.0) and b["p50"][-1] == pytest.approx(100.0)
    assert b["next"]["p10"] == pytest.approx(-0.005) and len(b["paths"]) == 10
    assert kb.quantile([1, 2, 3, 4], 0.5) == 2.5


def test_model_input_ends_at_the_asof_close():
    p = chart()
    rows = kb.model_input(p)
    assert len(rows) == kb.LOOKBACK and rows[-1][0] == "2026-10-30" == p["asof"]
    assert kb.future_dates("2026-10-30", 3) == ["2026-11-02", "2026-11-03", "2026-11-04"]
    p2 = dict(p, asof="2026-11-02")  # the file claims a later close than its last candle: refused
    assert kb.model_input(p2) is None
    assert kb.model_input(chart(n=30)) is None


def test_held_count_is_walk_forward_and_capped_at_20():
    p = chart(n=80)
    rows = kb.daily_rows(p)
    dates = [r[0] for r in rows]
    log = []
    for i in range(50, 79):  # bands logged on each base day; next close is +0.1 on ~105: about +0.095%
        log.append({"ticker": "AAA", "base_date": dates[i], "next_p10": "0.0", "next_p90": "0.002" if i % 2 else "0.0005"})
    h = kb.held(log, "AAA", rows)
    assert h["scored"] == 20 and h["window"] == 20 and h["held"] == 10
    assert kb.held_text(h) == "Kronos held its p10 to p90 range on 10 of the last 20 days."
    few = kb.held(log[-3:], "AAA", rows)
    assert few["scored"] == 3 and "fewer than 20" in kb.held_text(few)
    assert "No days scored yet" in kb.held_text(kb.held([], "AAA", rows))
    # the newest band (base = the last close) has no next close yet, so it is never scored
    assert kb.held([{"ticker": "AAA", "base_date": dates[-1], "next_p10": "-1", "next_p90": "1"}], "AAA", rows)["scored"] == 0


def test_append_log_is_append_only(tmp_path):
    p = tmp_path / "log.csv"
    row = {"made_date": "2026-10-30", "ticker": "AAA", "base_date": "2026-10-30", "next_p10": "-0.01", "next_p50": "0", "next_p90": "0.01",
           "paths": 100, "model": "m"}
    assert kb.append_log(p, [row]) == 1
    before = p.read_bytes()
    assert kb.append_log(p, [dict(row, next_p10="-0.5")]) == 0 and p.read_bytes() == before
    assert kb.append_log(p, [dict(row, made_date="2026-11-02")]) == 1 and p.read_bytes().startswith(before)


def test_ingest_writes_pages_and_rejects_bad_output(tmp_path):
    charts = {"AAA": chart(), "BBB": dict(chart(px=50.0), t="BBB")}
    inp = kbs.build_input(charts, ["AAA", "BBB"], NOW)
    raw = {"status": "ok", "model": "NeoQuasar/Kronos-small@901c26c13326", "paths": 20, "made_at": "2026-10-31T02:10:00Z",
           "results": [{"ticker": "AAA", "seconds": 25.0, **paths(20, 20, [0.05], 107.9)},
                       {"ticker": "BBB", "seconds": 25.0, **paths(20, 20, [0.05], 57.9)}]}
    raw["results"][1]["close"][0][0] = float("nan")
    rep = kbs.ingest(inp, raw, charts, out_dir=tmp_path / "k", log_path=tmp_path / "log.csv", now=NOW + timedelta(minutes=20))
    assert rep["written"] == ["AAA"] and rep["rejected"][0]["ticker"] == "BBB" and rep["seconds_per_ticker"] == 25.0
    pg = json.loads((tmp_path / "k" / "AAA.json").read_text())
    assert pg["note"] == kb.NOTE and pg["horizon"] == 20 and pg["dates"][0] == "2026-11-02" and len(pg["hist"]) == 30
    assert pg["held"]["scored"] == 0 and "No days scored yet" in pg["held_text"]
    idx = json.loads((tmp_path / "k" / "index.json").read_text())
    assert idx["pages"] == {"AAA": "2026-10-30"}
    txt = (tmp_path / "k" / "AAA.json").read_text()
    assert "\u2014" not in txt and "\u2013" not in txt


def test_ingest_drops_tampered_series_and_bad_timestamps(tmp_path):
    charts = {"AAA": chart()}
    inp = kbs.build_input(charts, ["AAA"], NOW)
    good = {"status": "ok", "model": "m", "paths": 20, "made_at": "2026-10-31T02:10:00Z", "results": [{"ticker": "AAA", **paths(20, 20, [0.05], 107.9)}]}
    bad = json.loads(json.dumps(inp))
    bad["series"][0]["ohlcv"][-1][3] = 999.0  # candles that differ from the committed chart file
    assert kbs.ingest(bad, good, charts, out_dir=tmp_path / "a", log_path=tmp_path / "a.csv", now=NOW + timedelta(minutes=20))["written"] == []
    early = dict(good, made_at="2026-10-31T01:00:00Z")  # before the input was built
    assert kbs.ingest(inp, early, charts, out_dir=tmp_path / "b", log_path=tmp_path / "b.csv", now=NOW + timedelta(minutes=20))["written"] == []
    assert kbs.ingest(inp, good, charts, out_dir=tmp_path / "c", log_path=tmp_path / "c.csv", now=NOW + timedelta(minutes=20))["written"] == ["AAA"]


def test_order_puts_watchlist_then_oldest_first(tmp_path):
    charts = {t: chart() for t in ("AAA", "BBB", "CCC", "DDD")}
    (tmp_path / "BBB.json").write_text(json.dumps({"asof": "2026-10-29"}))
    (tmp_path / "CCC.json").write_text(json.dumps({"asof": "2026-10-30"}))
    assert kbs.order(charts, ["DDD", "ZZZ"], out_dir=tmp_path) == ["DDD", "AAA", "BBB", "CCC"]
    assert len(kbs.order({f"T{i}": chart() for i in range(50)}, [], out_dir=tmp_path)) == kbs.MAX_TICKERS


def test_pins_and_vendored_code():
    man = json.loads((KDIR / "MANIFEST.json").read_text())
    assert len(man["code"]["commit"]) == 40 and len(man["weights"]["model"]["revision"]) == 40
    for rel in ("vendor/kronos/module.py", "vendor/kronos/LICENSE"):
        assert hashlib.sha256((KDIR / rel).read_bytes()).hexdigest() == man["code"]["files"][rel]["upstream_sha256"]
    code = (KDIR / "kronos_paths.py").read_text().split('"""', 2)[2]
    assert "load_file(" in code and "torch.load(" not in code and "import pickle" not in code
    req = (KDIR / "requirements.txt").read_text()
    pins = [ln for ln in req.splitlines() if ln and not ln.startswith((" ", "#"))]
    assert pins and all("==" in ln for ln in pins) and req.count("--hash=sha256:") >= len(pins)


def test_site_copy_is_honest():
    js = (ROOT / "site" / "kronos.js").read_text()
    assert "A model range, not a prediction. Not investment advice." in js
    assert not re.search(r"\b(buy|sell|target)\b", js, re.I)
    assert "\u2014" not in js and "\u2013" not in js
    assert 'kronos.js?v=' in (ROOT / "site" / "index.html").read_text()
    assert "KRONOS.mount" in (ROOT / "site" / "v5.js").read_text()
