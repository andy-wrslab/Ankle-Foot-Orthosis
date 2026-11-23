"""Failed Connect -> amber "Speedgoat offline" until Disconnect or a successful connect.

Units (no MATLAB, no target: the afo_rc call is a stub): a Connect that raises (ping
timeout) or answers connected=false makes the status button "Speedgoat offline"
(amber) with the reason and what to do in the popover; a later status refresh that is
still not connected keeps it; Disconnect or a successful connect clears it.
Browser (app on 127.0.0.1:18050, test ports): the page renders that state (fetch of
/api/console/state stubbed in the page with the status computed above): amber button,
popover item with the reason and the todo. Nothing reaches MATLAB or the target.

    python test/test_connect_offline.py
"""
import json
import os
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
from pages.runctl import RunControl  # noqa: E402
from status import top_status  # noqa: E402
from test_round5 import make_ctx  # noqa: E402
from workers import JobManager  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


class StubML:
    """Stands in for the MATLAB engine: answers afo_rc from a script, never connects."""
    def __init__(self):
        self.next = {}
        self.calls = []

    def call(self, fn, action, *a, **k):
        self.calls.append((fn, action))
        r = self.next.get(action)
        if isinstance(r, Exception):
            raise r
        return json.dumps(r if r is not None else {"ok": True, "connected": False})


def run(ctx, action):
    job = ctx.runctl.run_action(action)
    t0 = time.time()
    while ctx.jobs.running("rc") and time.time() - t0 < 5:
        time.sleep(0.02)
    return job


def units():
    ctx = make_ctx({}, live_age=None, tr_age=None)
    ctx.jobs = JobManager()
    ctx.matlab = StubML()
    ctx.runctl = RunControl(ctx)
    st = top_status(ctx)
    check("start: 'Not connected' (grey)", st["text"] == "Not connected" and st["level"] == "grey", st["text"])
    # 1) ping timeout: afo_rc raises
    ctx.matlab.next["connect"] = TimeoutError("Unable to connect to target computer 'TargetPC1': ping timeout")
    run(ctx, "connect")
    st = top_status(ctx)
    check("connect raised (ping timeout): 'Speedgoat offline' amber", st["text"] == "Speedgoat offline"
          and st["level"] == "amber", (st["text"], st["level"]))
    it = next((i for i in st["issues"] if i["key"] == "speedgoat-offline"), {})
    check("popover: why (the error, with the time)", "ping timeout" in it.get("detail", "")
          and "Connect failed at" in it.get("detail", ""), it)
    check("popover: what to do", "switched on" in it.get("todo", "") and "Connect again" in it.get("todo", ""), it)
    # status refresh, still not connected: stays offline
    ctx.matlab.next["status"] = {"ok": True, "connected": False}
    job = type("J", (), {"add": lambda self, l: None, "meta": {}})()
    ctx.runctl.call(job, "status")
    check("status refresh, still not connected: stays 'Speedgoat offline'", top_status(ctx)["text"] == "Speedgoat offline")
    # Disconnect clears it
    ctx.matlab.next["disconnect"] = {"ok": True, "connected": False}
    run(ctx, "disconnect")
    check("Disconnect: back to 'Not connected'", top_status(ctx)["text"] == "Not connected", top_status(ctx)["text"])
    # 2) connect answers connected=false (no response)
    ctx.matlab.next["connect"] = {"ok": False, "connected": False, "err": "no response from 192.168.7.5"}
    run(ctx, "connect")
    st = top_status(ctx)
    check("connect answered not connected: 'Speedgoat offline'", st["text"] == "Speedgoat offline", st["text"])
    check("... reason shown", "no response" in st["issues"][0].get("detail", ""), st["issues"][:1])
    offline_status = st
    # 3) a successful connect clears it
    ctx.matlab.next["connect"] = {"ok": True, "connected": True, "loaded": True, "running": False, "app": "AFO_r1"}
    ctx.matlab.next["status"] = {"ok": True, "connected": True, "loaded": True, "running": False, "app": "AFO_r1"}
    run(ctx, "connect")
    st = top_status(ctx)
    check("successful connect: not offline any more", st["text"] != "Speedgoat offline"
          and ctx.runctl.offline is None, (st["text"], ctx.runctl.offline))
    check("only the afo_rc stub was called", all(f == "afo_rc" for f, _ in ctx.matlab.calls), ctx.matlab.calls)
    return offline_status


STUB = r"""
(function () {
  var f0 = window.fetch.bind(window);
  window.fetch = function (url, opt) {
    var u = String(url), p = f0(url, opt);
    if (u.indexOf('/api/console/state') >= 0) {
      return p.then(function (r) { return r.json().then(function (j) {
        j.status = %s; j.target = Object.assign({}, j.target || {}, {connected: false, running: false});
        return new Response(JSON.stringify(j), {headers: {'Content-Type': 'application/json'}}); }); });
    }
    return p;
  };
})();
"""


def e2e(status):
    from test_ui_v18 import BASE, Browser
    tmp = tempfile.mkdtemp(prefix="afo_off_")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15432, "send_host": "127.0.0.1",
                  "send_port": 15990, "param_port": 15991}
    cfg["dash"] = {"host": "127.0.0.1", "port": 18050}
    cfg["paths"]["log_dir"] = os.path.join(tmp, "logs")
    cfg["training"] = {"enabled": False}
    cp = os.path.join(tmp, "off.yaml")
    yaml.safe_dump(cfg, open(cp, "w"), sort_keys=False)
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=open(os.path.join(tmp, "s.log"), "w"),
                           stderr=subprocess.STDOUT, env=dict(os.environ, AFO_GUI_CONFIG=cp))
    b = None
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        b = Browser(19475, 1600, 1000)
        c = b.c
        c.call("Page.addScriptToEvaluateOnNewDocument", source=STUB % json.dumps(json.loads(json.dumps(status, default=str))))
        c.call("Page.navigate", url=BASE + "/live")
        c.pump(4)
        v = json.loads(c.js("JSON.stringify({cls: document.getElementById('statusBtn').className, "
                            "txt: document.getElementById('statusTxt').textContent})"))
        check("page: status button 'Speedgoat offline'", v["txt"] == "Speedgoat offline", v)
        check("page: amber (not grey / red)", "caution" in v["cls"] or "amber" in v["cls"], v)
        c.js("document.getElementById('statusBtn').click(); 1")
        c.pump(0.6)
        pop = c.js("document.getElementById('openItems') ? document.getElementById('openItems').textContent : ''")
        check("popover: item, reason and what to do", "Speedgoat offline" in pop and "no response" in pop
              and "switched on" in pop, pop[:300])
        check("no browser errors", not c.console, c.console[:4])
    finally:
        if b:
            b.close()
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()


if __name__ == "__main__":
    st = units()
    if "--units-only" not in sys.argv:
        e2e(st)
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
