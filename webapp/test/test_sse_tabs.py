"""SSE with 4 tabs (localhost only: app 127.0.0.1:18050, bus :15432, console :15433).

Four headless Chrome tabs (Live, Live/Training, Trials, Signals) each keep ONE
/events connection: after the initial connects, /events requests per minute
must be ~0, no 503, the server's open-slot count is 4, every tab keeps
receiving snapshots and the Live tab keeps drawing. Closing a tab frees its
slot within a few seconds. Exit 1 on failure.
"""
import json
import os
import re
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
import replay_senders  # noqa: E402
from test_ui_v18 import BASE, Browser, Listener  # noqa: E402

DRAW_HOOK = r"""
(function hook(){
  window._draws = window._draws || 0;
  var P = window.Plotly;
  if (!P || !P.react) { setTimeout(hook, 200); return; }
  if (P._drawHooked) return; P._drawHooked = true;
  var r = P.react; P.react = function(){ window._draws++; return r.apply(this, arguments); };
  var e = P.extendTraces; P.extendTraces = function(){ window._draws++; return e.apply(this, arguments); };
})();
"""
SAMPLE = "JSON.stringify({sse: window._afoSse || null, draws: window._draws || 0, page: location.pathname})"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return json.loads(r.read())


def events_lines(log_path):
    txt = open(log_path, encoding="utf-8", errors="replace").read()
    txt = re.sub(r"\x1b\[[0-9;]*m", "", txt)
    ok = len(re.findall(r'"GET /events HTTP/1\.1" 200', txt))
    bad = len(re.findall(r'"GET /events HTTP/1\.1" 503', txt))
    return ok, bad


def main():
    tmp = tempfile.mkdtemp(prefix="afo_sse_")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15432, "send_host": "127.0.0.1",
                  "send_port": 15990, "param_port": 15991}
    cfg["dash"] = {"host": "127.0.0.1", "port": 18050}
    cfg["paths"]["log_dir"] = os.path.join(tmp, "logs")
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    lay["port"] = 15433
    json.dump(lay, open(os.path.join(tmp, "lay.json"), "w"))
    cfg["training"] = {"enabled": True, "listen_host": "127.0.0.1", "layout": os.path.join(tmp, "lay.json")}
    cfgp = os.path.join(tmp, "sse.yaml")
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    prof = os.path.join(APP, "data", "session_profiles.json")
    backup = None
    if os.path.exists(prof):
        backup = prof + ".sse.bak"
        shutil.copy2(prof, backup)
        os.remove(prof)
    ctl, prm = Listener(15990), Listener(15991)
    ctl.start(); prm.start()
    log_path = os.path.join(tmp, "server.log")
    log = open(log_path, "w")
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=log, stderr=subprocess.STDOUT,
                           env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    senders = replay_senders.start(15432, 15433, side=0.0)
    res, fail, tabs = {}, [], []
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(3)
        for i, path in enumerate(["/live", "/live", "/trials", "/signals"]):
            b = Browser(19341 + i, 1280, 800)
            b.c.call("Page.addScriptToEvaluateOnNewDocument", source=DRAW_HOOK)
            b.c.call("Page.navigate", url=BASE + path)
            tabs.append(b)
        for b in tabs:
            b.c.pump(3)
        tabs[1].c.js("(function(){var x=document.getElementById('pgTraining'); if(x){x.click();} return 1;})()")
        time.sleep(10)
        ok0, bad0 = events_lines(log_path)
        s0 = [json.loads(b.c.js(SAMPLE)) for b in tabs]
        res["initial_connects"], res["initial_503"] = ok0, bad0
        time.sleep(60)
        ok1, bad1 = events_lines(log_path)
        s1 = [json.loads(b.c.js(SAMPLE)) for b in tabs]
        res["events_connects_per_min"] = ok1 - ok0
        res["events_503_total"] = bad1
        res["sse_clients"] = get("/api/sse/clients")
        res["tabs"] = [{"page": a["page"], "msgs_per_min": (b["sse"] or {}).get("messages", 0) - (a["sse"] or {}).get("messages", 0),
                        "opens": (b["sse"] or {}).get("opens"), "errors": (b["sse"] or {}).get("errors"),
                        "draws_per_min": b["draws"] - a["draws"]} for a, b in zip(s0, s1)]
        if res["events_connects_per_min"] > 1:
            fail.append("reconnect churn")
        if bad1:
            fail.append("503")
        if res["sse_clients"]["clients"] != 4:
            fail.append("slot count")
        if any(t["msgs_per_min"] < 300 for t in res["tabs"]):
            fail.append("a tab stopped receiving")
        if res["tabs"][0]["draws_per_min"] < 600:      # ~30 fps x 2 graphs, capped by the 20 Hz messages
            fail.append("live tab not drawing")
        # closing a tab frees its slot
        tabs[3].close()
        t0 = time.time()
        freed = None
        while time.time() - t0 < 10:
            if get("/api/sse/clients")["clients"] == 3:
                freed = round(time.time() - t0, 2)
                break
            time.sleep(0.2)
        res["slot_freed_after_close_s"] = freed
        if freed is None:
            fail.append("slot not freed")
        res["udp_sent"] = len(ctl.pkts) + len(prm.pkts)
        if res["udp_sent"]:
            fail.append("udp sent")
        res["console_errors"] = [e for b in tabs[:3] for e in b.c.console][:6]
        if res["console_errors"]:
            fail.append("console errors")
    finally:
        for b in tabs:
            try:
                b.close()
            except Exception:
                pass
        senders.set()
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()
        if os.path.exists(prof):
            os.remove(prof)
        if backup:
            shutil.move(backup, prof)
    res["FAILS"] = fail
    os.makedirs(os.path.join(HERE, "e2e"), exist_ok=True)
    json.dump(res, open(os.path.join(HERE, "e2e", "sse_tabs_results.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
