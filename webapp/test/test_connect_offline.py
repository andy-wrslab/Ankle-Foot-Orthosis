"""Failed Connect -> amber "Speedgoat offline" / "Speedgoat busy" / "Connect failed", until
Disconnect or a successful connect (no answer / another MATLAB session / any other error).

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


def lt(st):
    """The MATLAB link result (Trials row), '' when none."""
    return st["rc_issues"][0]["text"] if st.get("rc_issues") else ""


def units():
    ctx = make_ctx({}, live_age=None, tr_age=None)
    ctx.jobs = JobManager()
    ctx.matlab = StubML()
    ctx.runctl = RunControl(ctx)
    st = top_status(ctx)
    # Andy 16:11: the MATLAB link result is NOT on the status button (it says 'No data' here: no
    # stream); it is in rc_issues, shown on the Trials 'MATLAB link' row
    check("start: button 'No data' (grey), no link issue", st["text"] == "No data" and st["level"] == "grey"
          and not st["rc_issues"], st["text"])
    # 1) ping timeout: afo_rc raises
    ctx.matlab.next["connect"] = TimeoutError("Unable to connect to target computer 'TargetPC1': ping timeout")
    run(ctx, "connect")
    st = top_status(ctx)
    check("connect raised (ping timeout): 'Speedgoat offline' amber", lt(st) == "Speedgoat offline"
          and st["rc_issues"][0]["level"] == "amber" and st["text"] == "No data", (lt(st), st["level"]))
    it = next((i for i in st["rc_issues"] if i["key"] == "speedgoat-offline"), {})
    check("popover: why (the error, with the time)", "ping timeout" in it.get("detail", "")
          and "Connect failed at" in it.get("detail", ""), it)
    check("popover: what to do", "switched on" in it.get("todo", "") and "Connect again" in it.get("todo", ""), it)
    # status refresh, still not connected: stays offline
    ctx.matlab.next["status"] = {"ok": True, "connected": False}
    job = type("J", (), {"add": lambda self, l: None, "meta": {}})()
    ctx.runctl.call(job, "status")
    check("status refresh, still not connected: stays 'Speedgoat offline'", lt(top_status(ctx)) == "Speedgoat offline")
    # Disconnect clears it
    ctx.matlab.next["disconnect"] = {"ok": True, "connected": False}
    run(ctx, "disconnect")
    check("Disconnect: no link issue any more", lt(top_status(ctx)) == "", lt(top_status(ctx)))
    # 2) connect answers connected=false (no response)
    ctx.matlab.next["connect"] = {"ok": False, "connected": False, "err": "no response from 192.168.7.5"}
    run(ctx, "connect")
    st = top_status(ctx)
    check("connect answered not connected: 'Speedgoat offline'", lt(st) == "Speedgoat offline", lt(st))
    check("... reason shown", "no response" in st["rc_issues"][0].get("detail", ""), st["rc_issues"][:1])
    offline_status = st
    # 3) a successful connect clears it
    ctx.matlab.next["connect"] = {"ok": True, "connected": True, "loaded": True, "running": False, "app": "AFO_r1"}
    ctx.matlab.next["status"] = {"ok": True, "connected": True, "loaded": True, "running": False, "app": "AFO_r1"}
    run(ctx, "connect")
    st = top_status(ctx)
    check("successful connect: not offline any more", lt(st) != "Speedgoat offline"
          and ctx.runctl.offline is None, (lt(st), ctx.runctl.offline))
    # 4) "another MATLAB session" (13:50:43 live): busy, not offline
    ctx.matlab.next["status"] = {"ok": True, "connected": False}     # target gone again
    ctx.matlab.next["disconnect"] = {"ok": True, "connected": False}
    run(ctx, "disconnect")
    ctx.matlab.next["connect"] = RuntimeError("Unable to connect to target computer 'TargetPC1': The target computer "
                                              "may be connected to another MATLAB session.")
    run(ctx, "connect")
    st = top_status(ctx)
    it = next((i for i in st["rc_issues"] if i["key"] == "speedgoat-busy"), {})
    check("another MATLAB session: amber 'Speedgoat busy' (not offline)", lt(st) == "Speedgoat busy"
          and st["rc_issues"][0]["level"] == "amber" and not any(i["key"] == "speedgoat-offline" for i in st["rc_issues"]), lt(st))
    check("busy: what to do", it.get("todo", "").startswith("Another MATLAB session is connected to the Speedgoat")
          and "press Connect again" in it.get("todo", ""), it)
    check("busy: the real error in the detail", "another MATLAB session" in it.get("detail", ""), it)
    # 5) any other error: "Connect failed" with the real error
    run(ctx, "disconnect")
    ctx.matlab.next["connect"] = RuntimeError("slrealtime: license checkout failed (error -5)")
    run(ctx, "connect")
    st = top_status(ctx)
    it = next((i for i in st["rc_issues"] if i["key"] == "connect-failed"), {})
    check("other error: 'Connect failed' with the real error", lt(st) == "Connect failed"
          and "license checkout failed" in it.get("detail", ""), (lt(st), it))
    # 6) 'Request timed out' is offline
    run(ctx, "disconnect")
    ctx.matlab.next["connect"] = {"ok": False, "connected": False, "err": "Request timed out."}
    run(ctx, "connect")
    check("'Request timed out': offline", lt(top_status(ctx)) == "Speedgoat offline", lt(top_status(ctx)))
    from pages.runctl import connect_failure_kind as k
    check("classifier", [k("ping timeout"), k("The target computer may be connected to another MATLAB session."),
                         k("no response from 192.168.7.5"), k("Access is denied")] == ["offline", "busy", "offline", "failed"])
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: Connect shows the stage and a live m:ss counter while it runs",
          "var acting = {connect: c, disconnect: c, start: s, stop: p}[busy.action]" in js
          and "acting.textContent = (busy.stage || busy.verb) + el" in js and "mmss(Date.now() / 1000 - busy.started)" in js)
    check("page: Connect enabled again after a failed connect (retry)", "c.disabled = false;" in js)
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
        check("page: the status button does NOT show the MATLAB link result", v["txt"] != "Speedgoat offline", v)
        c.js("document.getElementById('statusBtn').click(); 1")
        c.pump(0.6)
        pop = c.js("document.getElementById('openItems') ? document.getElementById('openItems').textContent : ''")
        check("popover: no link item (Trials row only)", "Speedgoat offline" not in pop, pop[:300])
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
