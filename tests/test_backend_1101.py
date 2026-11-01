"""Back-end fixes, 2026-11-01: late cron starts, idempotent re-runs, catch-up, dropped baskets,
5-day grading and the AI thesis call. Every test here failed (or could not run) on main before the fix."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from scanner import pipeline, tracker, universe, watchdog
from tests.fixtures.synthetic import END, fake_prices, patch_engine

ROOT = Path(__file__).resolve().parent.parent


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


# ---- item 2: late starts use the market date, not the run time ---------------------------------
def test_market_date_follows_the_new_york_close():
    # Fri 2026-10-30 close is 16:00 EDT = 20:00 UTC
    assert watchdog.market_date(utc(2026, 10, 30, 19, 0)) == date(2026, 10, 29)  # Friday, before the close
    assert watchdog.market_date(utc(2026, 10, 30, 21, 30)) == date(2026, 10, 30)
    assert watchdog.market_date(utc(2026, 10, 31, 0, 58)) == date(2026, 10, 30)  # the real late cron start (Sat UTC)
    assert watchdog.market_date(utc(2026, 11, 2, 13, 7)) == date(2026, 10, 30)  # Monday morning: still Friday
    # after the clocks go back (EST): Monday 2026-11-02 close is 21:00 UTC
    assert watchdog.market_date(utc(2026, 11, 2, 20, 59)) == date(2026, 10, 30)
    assert watchdog.market_date(utc(2026, 11, 2, 21, 0)) == date(2026, 11, 2)
    assert watchdog.market_date(utc(2026, 11, 27, 2, 0)) == date(2026, 11, 25)  # Thanksgiving skipped


def _with_asia_next_day_bar(tickers, period="1y", n=300):
    """A late run (after midnight UTC): an Asian market already has a partial bar dated the next day."""
    out = fake_prices(tickers, period, n)
    for t in out:
        if t.endswith(".KS") or t.endswith(".T"):
            extra = out[t].iloc[[-1]].copy()
            extra.index = extra.index + pd.offsets.BDay(1)
            out[t] = pd.concat([out[t], extra])
    return out


def test_late_run_is_labelled_with_the_us_market_date(tmp_path, monkeypatch):
    from scanner import data
    patch_engine(monkeypatch, tmp_path)
    monkeypatch.setattr(data, "prices", _with_asia_next_day_bar)
    monkeypatch.setattr(pipeline, "_now", lambda: utc(2026, 10, 31, 1, 15))  # Friday 10-30 scan starting 01:15 UTC Saturday
    res = pipeline.run(live_constituents=False)
    assert res["date"] == END  # SPY's date, never the Asian next-day bar or the run date
    assert set(tracker.load()["date"].dt.strftime("%Y-%m-%d")) == {END}
    # no stock is scored on a bar after the as-of date
    assert all(r.get("price") is not None for r in res["table"])


def test_mid_session_run_drops_todays_partial_bar(tmp_path, monkeypatch):
    from scanner import data
    patch_engine(monkeypatch, tmp_path)

    def with_partial_today(tickers, period="1y", n=300):
        out = fake_prices(tickers, period, n)
        for t, df in out.items():
            extra = df.iloc[[-1]].copy()
            extra.index = extra.index + pd.offsets.BDay(1)  # Mon 2026-11-02, session still open
            out[t] = pd.concat([df, extra])
        return out

    monkeypatch.setattr(data, "prices", with_partial_today)
    monkeypatch.setattr(pipeline, "_now", lambda: utc(2026, 11, 2, 17, 0))  # 12:00 EST Monday
    res = pipeline.run(live_constituents=False)
    assert res["date"] == END


def _revised(tickers, period="1y", n=300):
    """Yahoo revises late prints between two runs on the same day, so the ranking changes."""
    out = fake_prices(tickers, period, n)
    for i, (t, df) in enumerate(out.items()):
        if t != "SPY" and i % 3 == 0:
            df = df.copy()
            df.iloc[-5:, :4] *= 1.15
            out[t] = df
    return out


def test_same_day_rerun_by_another_run_is_idempotent(tmp_path, monkeypatch):
    patch_engine(monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, "_now", lambda: utc(2026, 10, 30, 21, 40))  # as-of == run day
    monkeypatch.setattr(pipeline, "_RUN_ID", "run-1")
    pipeline.run(live_constituents=False)
    first = tracker.LEDGER.read_text()
    monkeypatch.setattr(pipeline, "_RUN_ID", "run-2")
    from scanner import data
    monkeypatch.setattr(data, "prices", _revised)  # same day, revised data: a different ranking must not append rows
    pipeline.run(live_constituents=False)
    assert tracker.LEDGER.read_text() == first


def test_daily_scan_commit_title_uses_the_scan_as_of_date():
    wf = (ROOT / ".github" / "workflows" / "daily-scan.yml").read_text()
    assert 'Daily scan $(date +%F)' not in wf
    assert "scan_asof" in wf or "latest_scan.json" in wf.split("git commit")[0].split("Commit reports")[-1]


def test_daily_scan_has_backup_cron_and_gate():
    wf = (ROOT / ".github" / "workflows" / "daily-scan.yml").read_text()
    assert wf.count("- cron:") >= 2  # a backup start when the first one is very late or dropped
    assert "\n  gate:" in wf and "needs: gate" in wf and "--need-scan" in wf


def test_need_scan_cli(tmp_path, monkeypatch, capsys):
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(watchdog, "scan_dates_from_git", lambda repo=watchdog.ROOT: [date(2026, 10, 29)])
    monkeypatch.setattr(watchdog, "_now", lambda: utc(2026, 10, 30, 21, 30))
    assert watchdog.main(["--need-scan"]) == 0
    assert "need=true" in out.read_text()
    monkeypatch.setattr(watchdog, "scan_dates_from_git", lambda repo=watchdog.ROOT: [date(2026, 10, 30)])
    assert watchdog.main(["--need-scan"]) == 0
    assert out.read_text().strip().endswith("need=false")


# ---- item 1: the watchdog writes a status the site and the Brain can read, and asks for a catch-up ----
def test_watchdog_report_has_status_and_catch_up():
    scans = [date(2026, 10, d) for d in (26, 27, 28, 29)]
    rep = watchdog.build_report(scans, utc(2026, 11, 2, 13, 7))
    assert rep["missed"] == ["2026-10-30"] and rep["status"] == "missed"
    assert rep["market_date"] == "2026-10-30" and rep["last_scan"] == "2026-10-29"
    assert rep["catch_up"] is True  # the newest market day has no scan: dispatch one (gated, so never a double run)
    ok = watchdog.build_report(scans + [date(2026, 10, 30)], utc(2026, 11, 2, 13, 7))
    assert ok["status"] == "ok" and ok["missed"] == [] and ok["catch_up"] is False


def test_watchdog_workflow_dispatches_catch_up():
    wf = (ROOT / ".github" / "workflows" / "scan-watchdog.yml").read_text()
    assert "actions: write" in wf
    assert "gh workflow run daily-scan.yml" in wf and "--ref main" in wf


# ---- item 3: counts from data, and the dropped flag fires whenever a basket has no scanned stocks ----
def test_basket_with_no_price_data_is_flagged(tmp_path, monkeypatch):
    from scanner import data
    patch_engine(monkeypatch, tmp_path)
    rows = [{"ticker": f"RUT{i:03d}", "name": "", "sector": "", "weight": ""} for i in range(30)]
    universe.write_russell_cache("2026-10-29", rows, tmp_path / "russell2000.csv")

    def no_russell(tickers, period="1y", n=300):  # e.g. the download budget ran out before the Russell batches
        return fake_prices([t for t in tickers if not t.startswith("RUT")], period, n)

    monkeypatch.setattr(data, "prices", no_russell)
    res = pipeline.run(live_constituents=False)
    assert [d["name"] for d in res["dropped_baskets"]] == ["Russell 2000"]
    assert "price data" in res["dropped_baskets"][0]["reason"]
    assert res["funnel"]["baskets"]["scanned"] == len(universe.DEFAULT_INDEXES) - 1
    assert res["funnel"]["baskets"]["index_levels"] == len(res["indexes"])


def test_basket_counts_match_when_everything_scans(tmp_path, monkeypatch):
    patch_engine(monkeypatch, tmp_path)
    rows = [{"ticker": f"RUT{i:03d}", "name": "", "sector": "", "weight": ""} for i in range(30)]
    universe.write_russell_cache("2026-10-29", rows, tmp_path / "russell2000.csv")
    res = pipeline.run(live_constituents=False)
    assert res["dropped_baskets"] == []
    assert res["funnel"]["baskets"] == {"listed": 16, "scanned": 16, "index_levels": 16}


# ---- item 4: 5-day grading produces rows (entry Mon 11-02, five trading days later is Mon 11-09) ----
def test_first_5d_grades_appear_on_2026_11_09():
    led = pd.DataFrame([{"date": pd.Timestamp("2026-10-30"), "ticker": "AAA", "index": "x", "call": "Bullish",
                         "confidence": 50, "entry": 1.0, "bench_entry": 1.0, "mispricing": 50, "thesis": "",
                         "source": "rules", "lens": "mispricing", "score": None, "entry_rule": "next_close",
                         "run_id": None}])

    def ev_on(last_day):
        idx = pd.bdate_range("2026-06-01", last_day)
        stock = pd.Series(range(1, len(idx) + 1), index=idx, dtype=float)
        bench = pd.Series(100.0, index=idx)
        return tracker.evaluate(led, {"AAA": stock}, bench).iloc[0]

    assert pd.isna(ev_on("2026-11-06")["hit_5d"])  # Friday 11-06: only four bars after the entry close
    r = ev_on("2026-11-09")
    assert bool(r["hit_5d"]) is True and r["ret_5d"] > 0 and pd.isna(r["hit_20d"])


def test_track_json_shows_graded_rows_after_5_days(tmp_path, monkeypatch):
    """End to end on synthetic dates: log on day 0, scan again 6 trading days later, export has graded rows."""
    from scripts import export_site
    patch_engine(monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, "_now", lambda: utc(2026, 10, 30, 21, 40))
    pipeline.run(live_constituents=False)
    n0 = len(tracker.load())
    led = tracker.load()
    led["date"] = pd.Timestamp("2026-10-22")  # pretend the calls were logged six trading days before END
    led.to_csv(tracker.LEDGER, index=False)
    hist = {t: d["Close"] for t, d in fake_prices(list(led.ticker) + ["SPY"]).items()}
    ev = tracker.evaluate(tracker.load(), hist, hist["SPY"])
    scan = {"date": END, "scorecard": tracker.scorecard(ev, 6), "ledger": pipeline._clean_records(ev)}
    tr = export_site.build_track(json.loads(json.dumps(scan, default=str)), sample=False)
    assert tr["calls_logged"] == n0 and len(tr["graded"]) == n0 and tr["pending"] == 0
    assert all(g["window"] == 5 for g in tr["graded"])


# ---- item 5: the AI thesis call --------------------------------------------------------------
class _FakeMessages:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, []

    def create(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return self.resp


class _FakeClient:
    def __init__(self, resp=None, exc=None):
        self.beta = type("B", (), {})()
        self.beta.messages = _FakeMessages(resp, exc)
        self.messages = self.beta.messages


def _msg(text, stop="end_turn", usage=(700, 260, 0, 0), model="claude-sonnet-5-5"):
    from anthropic.types import Message, TextBlock, ThinkingBlock, Usage
    return Message(id="msg_1", type="message", role="assistant", model=model, stop_reason=stop,
                   stop_sequence=None, content=[ThinkingBlock(type="thinking", thinking="", signature="sig"),
                                                TextBlock(type="text", text=text)],
                   usage=Usage(input_tokens=usage[0], output_tokens=usage[1],
                               cache_read_input_tokens=usage[2], cache_creation_input_tokens=usage[3]))


ROW = {"ticker": "AAA", "shortName": "Aaa Corp", "price": 10.0, "mispricing": 60, "valuation_reasons": ["cheap"]}
GOOD = json.dumps({"call": "Bullish", "confidence": 61, "thesis": "Cheap vs peers.", "catalysts": "earnings",
                   "risks": "margins"})


def test_ai_call_reads_the_text_block_after_a_thinking_block(monkeypatch):
    from scanner import news_ai
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    news_ai.start_run()
    fake = _FakeClient(_msg(GOOD))
    out = news_ai.ai_call(ROW, [], client=fake)
    assert out and out["call"] == "Bullish" and out["source"] == "ai"
    kw = fake.beta.messages.calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["max_tokens"] >= 1500
    assert kw["output_config"]["format"]["type"] == "json_schema" and kw["output_config"]["effort"] == "low"
    u = news_ai.USAGE
    assert u["ok"] == 1 and u["input_tokens"] == 700 and u["output_tokens"] == 260
    assert abs(u["cost_usd"] - (700 * 2 + 260 * 10) / 1e6) < 1e-9


def test_ai_errors_are_counted_and_auth_errors_stop_the_run(monkeypatch):
    import anthropic
    import httpx
    from scanner import news_ai
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    news_ai.start_run()
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=req), body=None)
    fake = _FakeClient(exc=err)
    assert news_ai.ai_call(ROW, [], client=fake) is None
    assert news_ai.ai_call(ROW, [], client=fake) is None
    assert len(fake.beta.messages.calls) == 1  # circuit open after an auth error: no more paid attempts
    assert news_ai.USAGE["errors"] == {"auth": 1} and news_ai.USAGE["skipped"] == 1


def test_ai_truncated_or_refused_output_falls_back_and_is_counted(monkeypatch):
    from scanner import news_ai
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    news_ai.start_run()
    assert news_ai.ai_call(ROW, [], client=_FakeClient(_msg('{"call": "Bull', stop="max_tokens"))) is None
    assert news_ai.ai_call(ROW, [], client=_FakeClient(_msg("", stop="refusal"))) is None
    assert news_ai.USAGE["errors"] == {"max_tokens": 1, "refusal": 1}
    assert news_ai.USAGE["cost_usd"] > 0  # truncated calls still cost money and are counted


def test_ai_cost_cap_is_off_by_default_and_enforced_when_set(monkeypatch):
    from scanner import news_ai
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    monkeypatch.delenv("AI_RUN_COST_CAP_USD", raising=False)
    news_ai.start_run()
    assert news_ai.USAGE["cap_usd"] is None
    monkeypatch.setenv("AI_RUN_COST_CAP_USD", "0.004")
    news_ai.start_run()
    fake = _FakeClient(_msg(GOOD))
    assert news_ai.ai_call(ROW, [], client=fake)  # 0.004 spent
    assert news_ai.ai_call(ROW, [], client=fake) is None  # cap reached: rules model instead
    assert len(fake.beta.messages.calls) == 1 and news_ai.USAGE["skipped"] == 1


def test_usage_file_written_without_secrets(tmp_path, monkeypatch):
    from scanner import news_ai
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value-123")
    news_ai.start_run()
    news_ai.ai_call(ROW, [], client=_FakeClient(_msg(GOOD)))
    p = tmp_path / "ai_usage.json"
    for i in range(3):
        news_ai.save_usage(p, f"2026-10-{28 + i}", f"run{i}")
    text = p.read_text()
    assert "sk-ant" not in text and "secret" not in text
    d = json.loads(text)
    assert [r["date"] for r in d["runs"]] == ["2026-10-28", "2026-10-29", "2026-10-30"]
    assert d["runs"][-1]["calls"] == 1 and d["model"] == "claude-sonnet-5-5"
    assert d["proposed_cap_usd_per_run"] > 0 and d["cap_enabled"] is False


def test_pipeline_writes_usage_even_without_a_key(tmp_path, monkeypatch):
    patch_engine(monkeypatch, tmp_path)
    pipeline.run(live_constituents=False)
    d = json.loads((tmp_path / "data" / "ai_usage.json").read_text())
    assert d["runs"][-1]["key_present"] is False and d["runs"][-1]["calls"] == 0


def test_fallback_answer_is_priced_at_its_own_model(monkeypatch):
    from scanner import news_ai
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    news_ai.start_run()
    assert news_ai.ai_call(ROW, [], client=_FakeClient(_msg(GOOD, model="claude-opus-5-5")))
    assert abs(news_ai.USAGE["cost_usd"] - (700 * 4 + 260 * 20) / 1e6) < 1e-9


def test_banned_words_cover_ratings_and_targets():
    from scripts import export_site
    for w in ("rating", "Ratings", "target", "targets", "price target"):
        assert export_site.BANNED.search(f"the {w} is"), w
    assert not export_site.BANNED.search("cheap vs peers, consensus sits +20% from the last close")


def test_workflow_hardening():
    wf = (ROOT / ".github" / "workflows" / "daily-scan.yml").read_text()
    wd = (ROOT / ".github" / "workflows" / "scan-watchdog.yml").read_text()
    assert "${{ inputs.force }}\" ]" not in wf and '"$FORCE"' in wf and '"$EVENT"' in wf
    assert "permissions: { contents: read }" in wf
    assert '"$GITHUB_REPOSITORY"' in wd and "permissions: {}" in wd
    assert wd.index("Request a catch-up scan") < wd.index("Commit watchdog.json") and "always() &&" in wd
    for text in (wf, wd):
        assert "@v4\n" not in text and "@v5\n" not in text  # actions pinned to full SHAs
