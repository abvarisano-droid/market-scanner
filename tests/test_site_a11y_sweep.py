"""UX sweep 2026-11-02: route changes move focus instead of re-reading the page, and the replay counter reads in words."""
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"


def test_main_is_not_one_big_live_region():
    html = (SITE / "index.html").read_text()
    assert '<main id="app" class="boot" aria-busy="true">' in html
    assert 'aria-live="polite" aria-busy' not in html
    assert html.index('src="a11y.js') < html.index('src="app.js')


def test_route_change_focuses_the_view_and_names_the_tab():
    js = (SITE / "a11y.js").read_text()
    assert 'addEventListener("hashchange"' in js and "app.focus(" in js
    assert 'document.title = t && !/^Loading/.test(t) ? t + " | " + base : base;' in js
    assert "—" not in js and "–" not in js


def test_replay_counter_reads_in_words():
    v5 = (SITE / "v5.js").read_text()
    assert 'R.hits + " of " + R.done + (R.done === 1 ? " round" : " rounds")' in v5
    assert '"0/0"' not in v5 and ">0/0<" not in v5


def test_late_redraws_and_load_errors_are_spoken():
    html = (SITE / "index.html").read_text()
    assert '<p id="route-status" class="sr" role="status"></p>' in html
    js = (SITE / "a11y.js").read_text()
    assert "var ERROR = /unavailable|could not|hit a snag/i;" in js
    assert 'live.setAttribute("role", urgent ? "alert" : "status");' in js
    assert "if (focused && t && !/^Loading/.test(t))" in js and "focused = true;" in js
