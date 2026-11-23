"""Connect moved to Trials (Andy 14:48), Advanced params on run 14, Training legend. Seconds,
no browser, no target (run control and MATLAB are stubs).
- top bar has no Connect; Trials has a "MATLAB link" row with Connect and the state;
- Start / Stop / Export / Load while not connected connect first ("Connecting…" then their
  own stage) and stay connected; a failed auto-connect does not run the action;
- run 14 without MATLAB: the status is not a problem ("Ready" while UDP data flows); the Rig
  row explains "MATLAB: not connected (connects on Start/Stop/Export)";
- Advanced on run 14: the getparam read covers the 12 Advanced constants and none of side /
  mass / BIF mass / mode / K / Gyro_Cal; the IMU probe makes no MATLAB call;
- Training Assistance card: no single-trace legend.

    python test/test_connect_move.py
"""
import json
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def page_static():
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    a = js.index("function chromeHTML()")
    top = js[a:js.index("'</header>'", a)]
    check("top bar: no Connect button", 'id="tConnect"' not in top and 'id="tStart"' in top and 'id="tStop"' in top)
    tr = js[js.index("function trialsHTML()"):]
    tr = tr[:tr.index("}") + 1] if "}" in tr else tr
    check("Trials: 'MATLAB link' row with the state and Connect", "MATLAB link" in tr and 'id="mlState"' in tr and 'id="tConnect"' in tr)
    check("Start / Stop not locked by the connection", "s.disabled = !!T.running;" in js and "p.disabled = !T.running;" in js)
    live = open(os.path.join(APP, "pages", "live.py"), encoding="utf-8").read()
    check("Training: no 'Level in use' legend", "Level in use\", \"var(--s-meas)\"" not in live)
    # helper texts removed (Andy 14:51), essential hints kept as tooltips
    for gone in ("All runs in the Speedgoat file log, newest first", "Click a run to select it.",
                 '<span class="hint">Rarely changed', '<p class="sec-help">', "Start, Stop, Export and Load connect by themselves</span>"):
        check(f"helper text removed: {gone[:40]}", gone not in js)
    check("tooltips: Advanced head, export name, Trials Connect", 'title="Rarely changed · sent on Enter"' in js
          and 'id="expName" autocomplete="off" title="Participant ID' in js and 'title="Start, Stop, Export and Load connect by themselves"' in js)
    ty = open(os.path.join(APP, "pages", "teensy.py"), encoding="utf-8").read()
    check("DAQ: no helper sentence under the heading, no 'DAQ/ only' subtitle", 'html.Span("Debugging only.' not in ty
          and 'html.Span("DAQ/ only", className="hint")' not in ty)
    css = open(os.path.join(APP, "assets", "afo-ui.css"), encoding="utf-8").read()
    check("Live sub-tabs / window one step larger (30 px, 16 px, padding 14 px)",
          "#page-live > .toolbar .seg button { height: 30px; font-size: 16px; padding: 0 14px; }" in css)
    check("focus ring only for keyboard focus", "button:focus:not(:focus-visible)" in css and ":focus-visible { outline: 2px solid var(--accent)" in css)
    ps = open(os.path.join(APP, "plot_style.py"), encoding="utf-8").read()
    check("Sensors: 'Pressure' and 'Acceleration', no unit next to them (trace units kept for the cursor label)",
          '"id": "imu", "title": "Acceleration", "unit": "g", "card_unit": None' in ps
          and '"id": "press", "title": "Pressure", "unit": "counts", "card_unit": None' in ps
          and "Linear acceleration (gravity removed)" not in ps)
    # one 2 s / 10 s window shared by Gait / Sensors / Training, shown on every switch, kept across reloads
    sl = js[js.index("function setLiveSub(sub)"):]
    sl = sl[:sl.index("\n    }")]
    check("window: selector re-highlighted on every sub-tab switch", "showWin();" in sl)
    check("window: stored (localStorage, try/catch) and restored on load",
          "window.localStorage.setItem('afo.win'" in js and "window.localStorage.getItem('afo.win')" in js)
    check("window selector: same size / style as Gait | Sensors | Training (one rule for both)",
          "#page-live > .toolbar .seg button { height: 30px; font-size: 16px; padding: 0 14px; }" in css)
    uj = open(os.path.join(APP, "assets", "live_uplot.js"), encoding="utf-8").read()
    check("plots use the shared window on their first frame", "var win = window._afoWinSec || S.window_default;" in uj)
    tyc = open(os.path.join(APP, "assets", "teensy.css"), encoding="utf-8").read()
    check("DAQ column centred (max width kept)", ".teensy { max-width: 1120px; margin-inline: auto;" in tyc
          and ".page:not(.live) > .narrow { margin-inline: auto; }" in css)
    for gone in ("Debugging only.", "From the live UDP stream.", "(USB only when debugging)"):
        check(f"DAQ text removed: {gone}", gone not in ty)
    check("DAQ: the live-stream lock is not printed next to Flash (still blocks, reason in the title)",
          'msg = "" if (reason or "").startswith("Locked while the UDP stream is live")' in ty)
    order = [js.index('id="' + k + '"') for k in ("bZero", "bImuCal", "bCal", "bResetSV")]
    check("dock order: Zero, Calibrate IMU, Calibrate FSR, Reset SV (Andy 15:02)", order == sorted(order), order)
    ca = open(os.path.join(APP, "pages", "console_api.py"), encoding="utf-8").read()
    check("Rig status: 'MATLAB: not connected (connects on Start/Stop/Export)'",
          "MATLAB: not connected (connects on Start/Stop/Export)" in ca)


def auto_connect():
    from pages.runctl import RunControl
    from test_round5 import make_ctx
    from workers import JobManager
    ctx = make_ctx({}, live_age=0.05, tr_age=0.05)
    ctx.jobs = JobManager()
    seq, stages = [], []

    class ML:
        def __init__(self, connect_ok=True):
            self.ok = connect_ok

        def call(self, fn, action, *a, **k):
            seq.append(action)
            job = ctx.jobs.running("rc")
            if job is not None:
                stages.append(job.meta.get("stage"))
            if action == "connect":
                return json.dumps({"ok": self.ok, "connected": self.ok, "app": "AFO_r1", "running": False,
                                   **({} if self.ok else {"err": "ping timeout"})})
            if action == "start":
                return json.dumps({"ok": True, "connected": True, "app": "AFO_r1", "running": True})
            return json.dumps({"ok": True, "connected": True, "app": "AFO_r1", "running": action == "start",
                               **({"file": "x.mat"} if action == "save" else {})})
    ctx.matlab = ML()
    ctx.runctl = RunControl(ctx)

    def run(action):
        ctx.runctl.run_action(action)
        t0 = time.time()
        while ctx.jobs.running("rc") and time.time() - t0 < 5:
            time.sleep(0.02)
    run("start")
    check("Start while not connected: connect, then start", seq[:2] == ["connect", "start"], seq)
    check("stages: 'Connecting…' then 'Loading / starting…'", stages[:2] == ["Connecting…", "Loading / starting…"], stages)
    check("stays connected afterwards", (ctx.runctl.status or {}).get("connected") is True, ctx.runctl.status)
    seq.clear(); stages.clear()
    run("stop")
    check("Stop while connected: no extra connect", seq[:1] == ["stop"], seq)
    for action in ("save", "load"):
        ctx.runctl.status = {"connected": False}
        seq.clear()
        run(action)
        check(f"{action} while not connected: connect first", seq[:2] == ["connect", action], seq)
    ctx.runctl.status = {"connected": False}
    ctx.matlab = ML(connect_ok=False)
    seq.clear()
    run("start")
    check("auto-connect fails: Start is NOT called; offline recorded", seq == ["connect", "status"] or seq == ["connect"]
          and ctx.runctl.offline is not None, (seq, ctx.runctl.offline))


def status_run14():
    from status import top_status
    from test_round5 import ECHO, confirm, make_ctx
    ctx = make_ctx({"connected": False}, live_age=0.05, tr_age=0.05, echo=ECHO)
    confirm(ctx)
    ctx.session.refresh_readback()
    ctx.runctl.offline = None
    st = top_status(ctx)
    check("run 14 without MATLAB, UDP data flowing: not a problem ('Ready')", st["text"] == "Ready" and st["level"] == "green",
          (st["text"], st["level"], [i["key"] for i in st["issues"]]))
    check("no 'not connected' open item", not [i for i in st["issues"] if "connect" in i["key"]], st["issues"])


def advanced_run14():
    sys.path.insert(0, HERE)
    from test_run14_layout import Dev, make_session
    dev, calls = Dev(18), []
    dev.v.update(side=0.0, weight_kg=70.0, bif_mass_kg=70.0)
    ctx, s = make_session(dev, calls)
    dev.on = True
    time.sleep(0.3)
    keys = s.getparam_keys()
    adv = s.advanced_keys()
    check("run 14: getparam read = the 12 Advanced constants", sorted(keys) == sorted(adv) and len(adv) == 12, (keys, adv))
    check("run 14: no side / mass / BIF mass / mode / K in the getparam read",
          not set(keys) & {"side", "weight", "bif_mass", "mode", "k_percent"}, keys)
    paths = [s.target_path(k) for k in keys]
    check("run 14: no Gyro_Cal_Request path in the read", not any(p and "Gyro_Cal" in p[0] for p in paths), paths)
    from imu_cal import ImuCal
    ctx.imu_cal = ImuCal(ctx)
    n0 = len([c for c in calls if c[0] == "matlab"])
    ctx.imu_cal.probe(force=True)
    check("run 14: IMU probe makes no MATLAB call (counter from echo col 15)", len([c for c in calls if c[0] == "matlab"]) == n0
          and ctx.imu_cal.available is True, calls[n0:])
    s._put("p_gain", 0.5, "getparam")
    check("last Advanced value kept for the offline display", s.adv_last.get("p_gain", {}).get("value") == 0.5, s.adv_last)
    s.clear_readback()
    check("... and kept after a disconnect (readback cleared)", s.adv_last.get("p_gain", {}).get("value") == 0.5
          and "p_gain" not in s.readback)
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: offline Advanced = last read greyed / '–', title 'Connect on Trials to read'",
          "inp.title = 'Connect on Trials to read'" in js and "var lt = last == null ? '–' : String(+last);" in js)
    ctx.settings_link.stop()


if __name__ == "__main__":
    try:
        import _lowprio  # noqa: F401
    except Exception:
        pass
    page_static()
    auto_connect()
    status_run14()
    advanced_run14()
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
