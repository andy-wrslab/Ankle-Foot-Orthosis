"""Click -> visible feedback with REAL input events while 100 Hz data streams (test ports only).

App on 127.0.0.1:18050 (AFO_r1, target writes disabled), replay bus 1 kHz -> :15432 and
console 100 Hz -> :15433. The page's fetch is wrapped (in the page only): the state the
app returns is shown as connected + running, so Stop is enabled, and every POST to
/api/run/* is answered in the page after 2 s with {ok: true} and never reaches the app
(nothing is started, stopped or sent to MATLAB / the target).

Clicks are CDP Input.dispatchMouseEvent (queued like a user's click, unlike el.click()),
on Live > Sensors (heaviest view) and Live > Torque. Measured: wall time from the
mouse-up dispatch to the first text change of the button (MutationObserver), and the
long tasks (> 50 ms) on the main thread during streaming.

Checks (< 100 ms each): Stop -> "Confirm stop?", confirm -> "Stopping…" and it stays
"Stopping…" through later renders (1.5 s), Calibrate FSR -> "Calibrating…". Calibrate FSR
sends one pulse to the test listener on :15990 only.

    python test/test_click_latency.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import replay_senders  # noqa: E402  (also lowers this process's priority)
from test_ui_v18 import BASE, Browser, Listener, api  # noqa: E402

FAILS = []
LIMIT_MS = 100


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


STUB = r"""
(function () {
  var f0 = window.fetch.bind(window);
  window._runPosts = [];
  window.fetch = function (url, opt) {
    var u = String(url);
    if (u.indexOf('/api/run/') >= 0 && opt && opt.method === 'POST') {
      window._runPosts.push(u);
      return new Promise(function (res) { setTimeout(function () {
        res(new Response(JSON.stringify({ok: true, job: 0}), {headers: {'Content-Type': 'application/json'}})); }, 2000); });
    }
    var p = f0(url, opt);
    if (u.indexOf('/api/console/state') >= 0) {
      return p.then(function (r) { return r.json().then(function (j) {
        j.target = Object.assign({}, j.target || {}, {connected: true, running: true, loaded: true});
        return new Response(JSON.stringify(j), {headers: {'Content-Type': 'application/json'}}); }); });
    }
    return p;
  };
  window._long = [];
  try { new PerformanceObserver(function (l) { l.getEntries().forEach(function (e) { window._long.push(Math.round(e.duration)); }); })
        .observe({type: 'longtask', buffered: true}); } catch (e) {}
})();
"""

ARM = r"""
(function (sel) {
  var el = document.querySelector(sel); window._m = {t: null, text: null};
  var t0 = el.textContent;
  var mo = new MutationObserver(function () {
    if (window._m.t == null && el.textContent !== t0) {
      window._m = {t: performance.timeOrigin + performance.now(), text: el.textContent}; mo.disconnect(); } });
  mo.observe(el, {subtree: true, childList: true, characterData: true});
  var r = el.getBoundingClientRect();
  return JSON.stringify({x: r.left + r.width / 2, y: r.top + r.height / 2, dis: el.disabled, text: t0});
})('%s')
"""


def real_click(c, sel):
    info = json.loads(c.js(ARM % sel))
    x, y = info["x"], info["y"]
    c.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
    t_up = time.time()
    c.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
    c.pump(0.6)
    m = json.loads(c.js("JSON.stringify(window._m)"))
    ms = None if m["t"] is None else round(m["t"] - t_up * 1000.0)
    return ms, m["text"], info


def main():
    tmp = tempfile.mkdtemp(prefix="afo_clicklat_")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15432, "send_host": "127.0.0.1",
                  "send_port": 15990, "param_port": 15991}
    cfg["dash"] = {"host": "127.0.0.1", "port": 18050}
    cfg["paths"]["log_dir"] = os.path.join(tmp, "logs")
    cfg["target"] = {"model": "AFO_r1"}
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    lay["port"] = 15433
    json.dump(lay, open(os.path.join(tmp, "lay.json"), "w"))
    cfg["training"] = {"enabled": True, "listen_host": "127.0.0.1", "layout": os.path.join(tmp, "lay.json")}
    cfgp = os.path.join(tmp, "cl.yaml")
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    prof = os.path.join(APP, "data", "session_profiles.json")
    backup = None
    if os.path.exists(prof):
        backup = prof + ".cl.bak"
        shutil.copy2(prof, backup)
        os.remove(prof)
    ctl, prm = Listener(15990), Listener(15991)
    ctl.start(); prm.start()
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=open(os.path.join(tmp, "s.log"), "w"),
                           stderr=subprocess.STDOUT, env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    senders = replay_senders.start(15432, 15433, side=0.0)
    b = None
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(3)
        api("/api/console/sid", {"sid": "S97"})
        api("/api/console/side", {"side": "LEFT"})
        b = Browser(19451, 1920, 1080)
        c = b.c
        c.call("Page.addScriptToEvaluateOnNewDocument", source=STUB)
        for view in ("Sensors", "Torque"):
            c.call("Page.navigate", url=BASE + "/live")
            c.pump(5)
            if view == "Sensors":
                c.js("document.getElementById('pgSensors').click(); 1")
            c.pump(4)
            c.js("window._long = []; 1")
            c.pump(6)
            longs = json.loads(c.js("JSON.stringify(window._long)"))
            print(f"[{view}] long tasks in 6 s of streaming: n={len(longs)} max={max(longs) if longs else 0} ms")
            check(f"{view}: no main-thread task > {LIMIT_MS} ms while streaming", not longs or max(longs) <= LIMIT_MS, longs[:10])
            ms, txt, info = real_click(c, "#tStop")
            print(f"[{view}] Stop -> {txt!r} {ms} ms {info}")
            check(f"{view}: Stop -> 'Confirm stop?' < {LIMIT_MS} ms", txt == "Confirm stop?" and ms is not None and ms < LIMIT_MS, (txt, ms, info))
            ms, txt, info = real_click(c, "#tStop")
            print(f"[{view}] confirm -> {txt!r} {ms} ms")
            check(f"{view}: confirm -> 'Stopping…' < {LIMIT_MS} ms", txt is not None and txt.startswith("Stopping") and ms is not None
                  and ms < LIMIT_MS, (txt, ms))
            c.pump(1.0)
            held = c.js("document.getElementById('tStop').textContent")
            check(f"{view}: 'Stopping…' kept through renders (1.6 s)", str(held).startswith("Stopping"), held)
            posts = json.loads(c.js("JSON.stringify(window._runPosts)"))
            check(f"{view}: stop POST stayed in the page stub", posts and all(p.endswith("/api/run/stop") for p in posts), posts)
            c.pump(2.5)
            ms, txt, info = real_click(c, "#bCal")
            print(f"[{view}] Calibrate FSR -> {txt!r} {ms} ms")
            check(f"{view}: Calibrate FSR -> 'Calibrating…' < {LIMIT_MS} ms", txt is not None and txt.startswith("Calibrating")
                  and ms is not None and ms < LIMIT_MS, (txt, ms))
            c.pump(1.0)
            held = c.js("document.getElementById('bCal').textContent")
            check(f"{view}: Calibrating… kept (1.6 s)", str(held).startswith("Calibrating"), held)
            c.pump(30.5)          # let the 30 s calibration end before the next view
        check("UDP only to the test listener (FSR pulses), no param writes", not prm.pkts and len(ctl.pkts) <= 20,
              (len(ctl.pkts), len(prm.pkts)))
        check("no browser errors", not c.console, c.console[:4])
    finally:
        senders.set()
        if b:
            b.close()
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()
        if os.path.exists(prof):
            os.remove(prof)
        if backup:
            shutil.move(backup, prof)
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
