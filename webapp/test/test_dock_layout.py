"""Dock layout (Andy Nov 24 16:16-16:17), offline: the app on 127.0.0.1:18050 with TEST UDP ports
only (15432 / 15433 / 15990, nothing to the Speedgoat), a throw-away headless Chrome.

- [Window 2 s | 10 s] bottom-left, [Motor Assist K Mode] centred, [Calibration Encoder IMU
  FSR SV] bottom-right; the side sections mirror (distance from the edge, height) within 1 px,
  the group is centred within 1 px (>= 1360 px);
- nothing overlaps and nothing scrolls sideways at 360 ... 1920 px;
- the old Live toolbar has no window selector; the dock's 2 s / 10 s still sets the window;
- Encoder / FSR / SV / IMU send exactly the old requests (same endpoints, same bodies).
The app process tree is killed at the end (taskkill /T).

    python test/test_dock_layout.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import _lowprio  # noqa: E402,F401  (below normal priority)
from cdp_capture import _CDP, CHROME  # noqa: E402

PORT = 18050
BASE = f"http://127.0.0.1:{PORT}"
OUT = os.path.join(tempfile.gettempdir(), "afo_dock_layout")
FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


GEOM_JS = """(function () {
  function r(el) { if (!el) return null; var b = el.getBoundingClientRect(); return {l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height}; }
  var d = document.getElementById('dock');
  var parts = {dock: r(d), win: r(document.querySelector('#dock .win-sec')), ctl: r(document.querySelector('#dock .controls')),
               cal: r(document.querySelector('#dock .cal-sec'))};
  var boxes = [].slice.call(document.querySelectorAll('#dock .win-sec, #dock .controls, #dock .cal-sec, #dock #dockMsg')).map(r);
  var over = [];
  for (var i = 0; i < boxes.length; i++) for (var j = i + 1; j < boxes.length; j++) {
    var a = boxes[i], b = boxes[j]; if (!a || !b || !a.w || !b.w) continue;
    if (a.l < b.r - 0.5 && b.l < a.r - 0.5 && a.t < b.b - 0.5 && b.t < a.b - 0.5) over.push([i, j]);
  }
  parts.overlap = over;
  parts.hscroll = document.documentElement.scrollWidth > window.innerWidth + 0.5;
  parts.inside = [].slice.call(document.querySelectorAll('#dock button')).filter(function (b) { return b.offsetParent; })
    .every(function (b) { var x = b.getBoundingClientRect(); return x.left >= -0.5 && x.right <= window.innerWidth + 0.5; });
  parts.labels = ['bZero', 'bImuCal', 'bCal', 'bResetSV'].map(function (id) { var e = document.getElementById(id); return e ? e.textContent : null; });
  parts.toolbarWin = !!document.querySelector('#page-live > .toolbar #liveWin');
  return parts;
})()"""


class Browser:
    def __init__(self, port, w, h):
        self.proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}",
                                      f"--user-data-dir={tempfile.mkdtemp(prefix='afo_cdp_')}", "--no-first-run",
                                      "--hide-scrollbars", f"--window-size={w},{h}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                t = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2))
                if any(x.get("type") == "page" for x in t):
                    break
            except Exception:
                pass
            time.sleep(0.25)
        self.c = _CDP(next(x for x in t if x.get("type") == "page")["webSocketDebuggerUrl"])
        self.c.call("Runtime.enable"); self.c.call("Page.enable")
        self.c.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)

    def close(self):
        try:
            self.c.ws.close()
        except Exception:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="afo_dock_")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15432, "send_host": "127.0.0.1", "send_port": 15990}
    cfg["dash"] = {"host": "127.0.0.1", "port": PORT}
    cfg.setdefault("paths", {})["log_dir"] = os.path.join(tmp, "logs")
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    lay["port"] = 15433
    lp = os.path.join(tmp, "layout.json")
    json.dump(lay, open(lp, "w"))
    cfg["training"] = {"enabled": True, "listen_host": "127.0.0.1", "layout": lp}
    cfgp = os.path.join(tmp, "dock.yaml")
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    log = open(os.path.join(tmp, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=log, stderr=subprocess.STDOUT,
                           env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    print(f"test app pid {srv.pid} on :{PORT} (test UDP ports only)", flush=True)
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(2)
        for w, h in ((1920, 1080), (1600, 1000), (1440, 900), (1366, 768), (1280, 800), (1024, 768), (768, 1024), (390, 844), (360, 740)):
            b = Browser(19296, w, h)
            try:
                c = b.c
                c.call("Page.navigate", url=BASE + "/live")
                c.pump(5)
                g = c.js(GEOM_JS)
                shot = os.path.join(OUT, f"dock_{w}x{h}.png")
                c.shot(shot)
                check(f"{w}: no overlap in the dock, no sideways scroll, every button on screen",
                      not g["overlap"] and not g["hscroll"] and g["inside"], {k: g[k] for k in ("overlap", "hscroll", "inside")})
                if w >= 1360:
                    d, win, ctl, cal = g["dock"], g["win"], g["ctl"], g["cal"]
                    centre_off = (ctl["l"] + ctl["r"]) / 2 - (d["l"] + d["r"]) / 2
                    check(f"{w}: Motor / Assist / K / Mode centred (within 1 px)", abs(centre_off) <= 1, centre_off)
                    check(f"{w}: Window and Calibration mirror: same distance from the edge (within 1 px)",
                          abs((win["l"] - d["l"]) - (d["r"] - cal["r"])) <= 1, (win["l"] - d["l"], d["r"] - cal["r"]))
                    check(f"{w}: Window and Calibration: same height, same row (within 1 px)",
                          abs(win["h"] - cal["h"]) <= 1 and abs(win["t"] - cal["t"]) <= 1, (win, cal))
                if w == 1920:
                    check("labels: Encoder, IMU, FSR, SV", g["labels"] == ["Encoder", "IMU", "FSR", "SV"], g["labels"])
                    check("Live toolbar: no window selector any more (it is in the dock)", not g["toolbarWin"])
                    # the dock's window buttons still drive the plots' window
                    c.js("document.getElementById('w2').click(); 1"); c.pump(0.5)
                    w2 = c.js("[window._afoWinSec, document.getElementById('w2').getAttribute('aria-pressed')]")
                    c.js("document.getElementById('w10').click(); 1"); c.pump(0.5)
                    w10 = c.js("[window._afoWinSec, document.getElementById('w10').getAttribute('aria-pressed')]")
                    check("dock 2 s / 10 s set the window (2 then 10)", w2 == [2, "true"] and w10 == [10, "true"], (w2, w10))
                    # the four Calibration buttons send exactly the old requests (fetch recorded, not sent)
                    c.js("""window.__p = []; var _f = window.fetch; window.fetch = function (u, o) {
                        if (o && String(o.method).toUpperCase() === 'POST' && String(u).indexOf('/api/console/') === 0) {
                            window.__p.push([String(u), o.body]); return Promise.resolve(new Response('{"ok":true}', {status: 200})); }
                        return _f.apply(this, arguments); }; 1""")
                    for bid in ("bZero", "bCal", "bResetSV"):
                        c.js(f"(function(){{var b=document.getElementById('{bid}'); b.disabled=false; b.removeAttribute('aria-disabled'); b.click(); return 1;}})()")
                        c.pump(0.4)
                    c.js("(function(){var b=document.getElementById('bImuCal'); b.hidden=false; b.disabled=false; b.removeAttribute('aria-disabled'); b.click(); return 1;})()")
                    c.pump(0.4)
                    got = c.js("window.__p")
                    want = [["/api/console/pulse", '{"name":"zero"}'], ["/api/console/pulse", '{"name":"calibrate"}'],
                            ["/api/console/pulse", '{"name":"reset"}'], ["/api/console/imucal", "{}"]]
                    check("Encoder / FSR / SV / IMU: the old endpoints and bodies (zero, calibrate, reset, imucal)",
                          [g2 for g2 in got if g2 in want] == want, got)
                print(f"   screenshot {shot}", flush=True)
            finally:
                b.close()
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(srv.pid)], capture_output=True)
        time.sleep(1)


main()
print("\nFAILS:", FAILS)
sys.exit(1 if FAILS else 0)
