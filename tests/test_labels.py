import pandas as pd

from scanner import news_ai, tracker
from scanner.labels import BEARISH, BULLISH, NEUTRAL, normalize


def test_normalize_new_and_legacy():
    assert [normalize(x) for x in ("BUY", "sell", "Watch", "Bullish", "bearish", "Neutral", None, "?")] == \
        [BULLISH, BEARISH, NEUTRAL, BULLISH, BEARISH, NEUTRAL, NEUTRAL, NEUTRAL]


def test_rule_calls_use_new_labels():
    assert news_ai.rule_based_call({"mispricing": 80, "coverage": 1}, 0)["call"] == BULLISH
    assert news_ai.rule_based_call({"mispricing": -80, "coverage": 1}, 0)["call"] == BEARISH
    assert news_ai.rule_based_call({"mispricing": 0, "coverage": 1}, 0)["call"] == NEUTRAL


def test_legacy_ledger_loads_with_new_labels(tmp_path, monkeypatch):
    monkeypatch.setattr(tracker, "LEDGER", tmp_path / "picks.csv")
    pd.DataFrame([{"date": "2026-06-01", "ticker": "AAA", "index": "S&P 500", "call": "BUY", "confidence": 70,
                   "entry": 100.0, "bench_entry": 400.0, "mispricing": 50, "thesis": "x", "source": "rules"},
                  {"date": "2026-06-01", "ticker": "BBB", "index": "S&P 500", "call": "SELL", "confidence": 70,
                   "entry": 100.0, "bench_entry": 400.0, "mispricing": -50, "thesis": "x", "source": "rules"}]
                 ).to_csv(tracker.LEDGER, index=False)
    led = tracker.load()
    assert list(led["call"]) == [BULLISH, BEARISH] and set(led["lens"]) == {"mispricing"}
    assert list(led["entry_rule"]) == ["", ""]  # old rows keep the old same-day entry rule


def test_no_buy_sell_in_user_facing_source():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    for f in ["app.py", "scanner/pipeline.py"]:
        txt = (root / f).read_text()
        assert not re.search(r"\b(BUY|SELL|WATCH)\b", txt), f
