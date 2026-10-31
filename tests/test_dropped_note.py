"""The site shows the dropped-basket note only when the flag is set. Headless browser at 390 and 1280 px."""
import functools
import http.server
import json
import shutil
import threading
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
SITE = Path(__file__).resolve().parent.parent / "site"


def _serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    h.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _site(tmp_path, flag):
    root = tmp_path / ("flag" if flag else "plain")
    shutil.copytree(SITE, root)
    p = root / "data" / "summary.json"
    d = json.loads(p.read_text())
    d["dropped_baskets"] = [{"name": "Russell 2000", "date": d["asof"]}] if flag else []
    p.write_text(json.dumps(d))
    return root, d["asof"]


@pytest.mark.parametrize("flag", [False, True])
def test_note_only_when_dropped(tmp_path, flag):
    root, asof = _site(tmp_path, flag)
    srv = _serve(root)
    try:
        with pw.sync_playwright() as p:
            try:
                br = p.chromium.launch()
            except Exception as exc:
                pytest.skip(f"no browser: {exc}")
            for w in (390, 1280):
                pg = br.new_page(viewport={"width": w, "height": 900})
                errs = []
                pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
                pg.on("pageerror", lambda e: errs.append(str(e)))
                for hash_ in ("#/", "#/how"):
                    pg.goto(f"http://127.0.0.1:{srv.server_port}/index.html{hash_}")
                    pg.wait_for_selector("#app:not(.boot) h1, #app h1", timeout=15000)
                    pg.wait_for_timeout(500)
                    n = pg.locator(".dropnote").count()
                    assert n == (1 if flag else 0), (w, hash_)
                    if flag:
                        assert pg.locator(".dropnote").inner_text() == f"Russell 2000 list unavailable on {asof}, this scan ran without it."
                    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), (w, hash_)
                assert errs == [], errs
            br.close()
    finally:
        srv.shutdown()
