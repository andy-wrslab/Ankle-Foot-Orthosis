"""Hover box never changes width and its values never move (Andy Nov 24 16:11 "the value
still jumps in UI"). Offline: a throw-away headless Chrome opens a local file that loads the
page's own assets/afo-ui.css and assets/live_uplot.js (no app, no network), renders the hover
of every Live plot (live_spec: Gait, Sensors, Training) with values like 0.01 / -0.00 / 12.34
/ -12.34 and checks the box width and every value's right edge are identical, and that
"-0.00" never shows.

    python test/test_hover_width.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import _lowprio  # noqa: E402,F401  (below normal priority)
from cdp_capture import _CDP, CHROME  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def main():
    from pages.live import live_spec
    spec = live_spec()
    tmp = tempfile.mkdtemp(prefix="afo_hover_")
    page = os.path.join(tmp, "h.html")
    css = pathlib.Path(APP, "assets", "afo-ui.css").as_uri()
    js = pathlib.Path(APP, "assets", "live_uplot.js").as_uri()
    open(page, "w", encoding="utf-8").write(
        f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{css}"></head><body>'
        f'<div id="liveSpec" hidden data-spec=\'{json.dumps(spec)}\'></div>'
        f'<div class="uplot-host" style="width:900px;height:300px"><div id="tip" class="u-tip"></div></div>'
        f'<script>window.uPlot = function () {{}};</script><script src="{js}"></script></body></html>')
    port = 19235
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={tempfile.mkdtemp(prefix='afo_cdp_')}",
                             "--no-first-run", "--allow-file-access-from-files", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                t = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2))
                if any(x.get("type") == "page" for x in t):
                    break
            except Exception:
                pass
            time.sleep(0.25)
        c = _CDP(next(x for x in t if x.get("type") == "page")["webSocketDebuggerUrl"])
        c.call("Runtime.enable"); c.call("Page.enable")
        c.call("Page.navigate", url=pathlib.Path(page).as_uri())
        c.pump(2)
        check("live_uplot.js loaded with the hover hooks", c.js("!!(window._afoPlots && window._afoPlots.tipHTML)"), c.console[:3])
        values = [0.01, -0.004, 0.0, -0.0, 12.34, -12.34, 3.5, -3.5, 1.0, -9.99, 0.004]
        for pid, ps in spec["plots"].items():
            res = c.js("""(function (ps, values) {
                var E = window._afoPlots, tip = document.getElementById('tip'), out = [];
                for (var j = 0; j < values.length; j++) {
                    var vals = []; for (var k = 0; k < ps.series.length; k++) { vals.push(values[(j + k) %% values.length] * (ps.y[1] > 100 ? 40 : 1)); }
                    var shown = ps.series.map(function () { return true; });
                    tip.innerHTML = E.tipHTML(ps, 4794.62 + j, vals, shown);
                    var bs = [].slice.call(tip.querySelectorAll('.u-tip-g b'));
                    out.push({w: tip.getBoundingClientRect().width, right: bs.map(function (b) { return Math.round(b.getBoundingClientRect().right * 100) / 100; }),
                              txt: bs.map(function (b) { return b.textContent; })});
                }
                return out;
            })(%s, %s)""" % (json.dumps(ps), json.dumps(values)))
            widths = sorted({round(r["w"], 2) for r in res})
            rights = {x for r in res for x in r["right"]}
            texts = [x for r in res for x in r["txt"]]
            check(f"{pid}: hover box width identical for every value set", len(widths) == 1, widths)
            check(f"{pid}: every value's right edge identical", len(rights) == 1, sorted(rights))
            check(f"{pid}: never '-0', '-0.0' or '-0.00'", not any(x.strip().startswith("-") and float(x) == 0 for x in texts),
                  [x for x in texts if x.strip().startswith("-0")])
        c.ws.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


main()
print("\nFAILS:", FAILS)
sys.exit(1 if FAILS else 0)
