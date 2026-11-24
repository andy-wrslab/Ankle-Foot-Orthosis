"""Training x axis: never below 0, and (Andy 14:34) the same 2 s / 10 s window and shared clock as Gait.

Units: training_range / training_fig give [max(0, t - w), max(w, t)].
Browser (app on 127.0.0.1:18050, replay senders on test ports; the replay's model time
starts at 20 s): Training sub-tab with 30 s / 2 min / 5 min, both plots: start >= 0,
range = [max(0, t - w), max(w, t)] for the shown t (the plot refreshes once a second),
from 0 while t < w and scrolling once t > w (30 s window at t > 30 s).

    python test/test_training_axis.py
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
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import replay_senders  # noqa: E402  (also lowers this process's priority)
from pages.live import training_fig, training_range  # noqa: E402
from plot_style import TRAINING_PLOTS  # noqa: E402
from test_ui_v18 import BASE, Browser, Listener, api  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def units():
    check("t 50 s, 2 min: [0, 120] (was -70..50 / -60..40)", training_range(50, 120) == [0.0, 120.0], training_range(50, 120))
    check("t 50 s, 30 s: scrolling [20, 50]", training_range(50, 30) == [20.0, 50.0], training_range(50, 30))
    check("t 50 s, 5 min: [0, 300]", training_range(50, 300) == [0.0, 300.0], training_range(50, 300))
    check("t 200 s, 2 min: scrolling [80, 200]", training_range(200, 120) == [80.0, 200.0])
    check("t 0 s: [0, w]", training_range(0, 30) == [0.0, 30.0])
    p = TRAINING_PLOTS[0]
    f = training_fig(p, {}, 120, 50.0)
    check("training_fig uses it", list(f.layout.xaxis.range) == [0.0, 120.0], f.layout.xaxis.range)


RANGES = r"""
JSON.stringify((function(){
  var st = window._afoPlots ? window._afoPlots.state() : {plots: {}};
  var out = [];
  ['tr-assist', 'tr-uc'].forEach(function(id){ var p = st.plots[id]; if (p) { out.push([id, [p.xmin, p.xmax]]); } });
  return {r: out, t: st.shown != null ? st.shown : st.clock};
})())
"""


def e2e():
    tmp = tempfile.mkdtemp(prefix="afo_traxis_")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15432, "send_host": "127.0.0.1",
                  "send_port": 15990}
    cfg["dash"] = {"host": "127.0.0.1", "port": 18050}
    cfg["paths"]["log_dir"] = os.path.join(tmp, "logs")
    cfg["target"] = {"model": "AFO_r1"}
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    lay["port"] = 15433
    json.dump(lay, open(os.path.join(tmp, "lay.json"), "w"))
    cfg["training"] = {"enabled": True, "listen_host": "127.0.0.1", "layout": os.path.join(tmp, "lay.json")}
    cp = os.path.join(tmp, "tr.yaml")
    yaml.safe_dump(cfg, open(cp, "w"), sort_keys=False)
    prof = os.path.join(APP, "data", "session_profiles.json")
    backup = None
    if os.path.exists(prof):
        backup = prof + ".tr.bak"
        shutil.copy2(prof, backup)
        os.remove(prof)
    ctl, prm = Listener(15990), Listener(15991)
    ctl.start(); prm.start()
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=open(os.path.join(tmp, "s.log"), "w"),
                           stderr=subprocess.STDOUT, env=dict(os.environ, AFO_GUI_CONFIG=cp))
    b = None
    senders = None
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(2)
        senders = replay_senders.start(15432, 15433, side=0.0)      # model time starts at 20 s
        b = Browser(19474, 1600, 1000)
        c = b.c
        c.call("Page.navigate", url=BASE + "/live")
        c.pump(4)
        c.js("document.getElementById('pgTraining').click(); 1")
        c.pump(2.5)

        def look(w, label):
            # Andy 14:34: Training uses the same 2 s / 10 s buttons and shared clock as Gait / Sensors
            c.js("document.getElementById('%s').click(); 1" % ("w2" if w == 2 else "w10"))
            c.pump(1.0)
            v = json.loads(c.js(RANGES))
            t = v["t"]
            ok_all = len(v["r"]) == 2
            for gid, r in v["r"]:
                want = training_range(t, w)
                ok = r and r[0] >= 0 and abs(r[0] - want[0]) <= 0.2 and abs(r[1] - want[1]) <= 0.2
                ok_all = ok_all and ok
                check(f"{label}: {gid} range {[round(x, 1) for x in r]} ~ {[round(x, 1) for x in want]} (t {t:.1f})", ok, (r, want, t))
            return v, ok_all

        v, _ = look(10, "t~25 s, 10 s")
        check("10 s at t > 10 s: scrolling (start > 0)", all(r[0] > 0 for _, r in v["r"]), v)
        v, _ = look(2, "2 s")
        check("2 s window", all(abs((r[1] - r[0]) - 2) < 1e-6 for _, r in v["r"]), v)
        check("Training has no own window buttons any more", c.js("(function(){var w=document.getElementById('trWin');"
                                                                    "return !w || w.hidden || w.style.display==='none';})()"))
        check("no browser errors", not c.console, c.console[:4])
    finally:
        if senders:
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


if __name__ == "__main__":
    units()
    if "--units-only" not in sys.argv:
        e2e()
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
