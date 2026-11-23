"""MATLAB only for logging (Andy 16:11 "the MATLAB based tools are ONLY used for logging
data ... other than that it's just plug and play"), the status button live-only, the device
as the only truth for the dock (Andy 16:15), Zero / Calibrate FSR momentary again.
Seconds, no browser, no target, no MATLAB.

- Start / Stop / Export / Load / the run list connect on demand and disconnect right after;
  an explicit Connect keeps the link; idle: no MATLAB call (no polling, no getparam);
- the status button never shows Connecting / Starting / a MATLAB link result;
- a 31-column device with MATLAB disconnected (every MATLAB call raises): side (5434), mass,
  mode, K, Advanced (5435), Motor / Assist / K / Zero / Calibrate FSR / Reset SV (5431) and
  Calibrate IMU (5434) all work over UDP only;
- Motor / Assist / K show the device echo, never last_command.json; no echo -> unknown; no
  'differs'; Zero / Calibrate FSR: one 1 -> 0 pulse per press, no latch.

    python test/test_matlab_on_demand.py
"""
import json
import os
import struct
import sys
import tempfile
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


def on_demand():
    from pages.runctl import RunControl
    from test_round5 import make_ctx
    from workers import JobManager
    ctx = make_ctx({}, live_age=0.05, tr_age=0.05)
    ctx.jobs = JobManager()
    seq = []
    tmp_root = tempfile.mkdtemp(prefix="afo_od_")
    ctx.cfg["paths"]["afo_root"] = tmp_root

    class ML:
        def call(self, fn, action, *a, **k):
            seq.append(action)
            conn = action not in ("disconnect",)
            return json.dumps({"ok": True, "connected": conn, "app": "AFO_r1", "running": action in ("start", "status"),
                               "values": [], **({"file": os.path.join(tmp_root, "x.mat")} if action == "save" else {})})
    ctx.matlab = ML()
    ctx.runctl = rc = RunControl(ctx)

    def run(action, *args):
        rc.run_action(action, *args)
        t0 = time.time()
        while ctx.jobs.running("rc") and time.time() - t0 < 10:
            time.sleep(0.02)
    for action in ("start", "stop", "load"):
        seq.clear()
        run(action, "x.mldatx") if action == "load" else run(action)
        check(f"{action}: connects on demand, then disconnects right after", seq[:2] == ["connect", action]
              and seq[-1] == "disconnect" and not rc.status.get("connected"), seq)
    seq.clear()
    open(os.path.join(tmp_root, "x.mat"), "wb").write(b"m")
    run("save", os.path.join(tmp_root, "x.mat"))
    check("export: connects on demand, then disconnects", seq[0] == "connect" and "save" in seq and seq[-1] == "disconnect", seq)
    # the run list (Trials Refresh) is on demand too
    from filelog import FileLogRuns
    ctx.filelog = fl = FileLogRuns(ctx)
    seq.clear()
    job, msg = fl.refresh()
    t0 = time.time()
    while ctx.jobs.running("rc") and time.time() - t0 < 10:
        time.sleep(0.02)
    check("run list: on demand (no 'connect first'), disconnects after", job is not None and seq[0] == "connect"
          and seq[-1] == "disconnect", (msg, seq))
    # explicit Connect keeps the link (manual)
    seq.clear()
    run("connect")
    run("stop")
    check("explicit Connect: the link stays open after Stop", rc.status.get("connected") and "disconnect" not in seq, seq)
    run("disconnect")
    # idle: no MATLAB at all
    seq.clear()
    ctx.session.refresh_readback()
    time.sleep(0.3)
    check("idle (not connected): no MATLAB call, no getparam polling", seq == [], seq)
    # the status button: run-control jobs never show
    from status import top_status
    before = top_status(ctx)["text"]

    class Hold:
        def __init__(self):
            import threading
            self.ev = threading.Event()

        def __call__(self, job):
            job.meta["stage"] = "Connecting…"
            self.ev.wait(2)
            return {"ok": True}
    h = Hold()
    ctx.jobs.start("rc", "run control: connect", h)
    time.sleep(0.1)
    st = top_status(ctx)
    check("a connect job running: status button text unchanged (never 'Connecting…')", st["text"] == before
          and "Connecting" not in st["text"], (before, st["text"]))
    h.ev.set()
    rc.offline = {"at": time.time(), "err": "ping timeout", "kind": "offline"}
    rc.status = {"connected": False}
    st = top_status(ctx)
    check("a failed connect: not on the status button (Trials row only, rc_issues)",
          "Speedgoat offline" not in st["text"] and any(i["key"] == "speedgoat-offline" for i in st["rc_issues"]), (st["text"], st["rc_issues"]))
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("Trials row: 'Not connected (connects for Start/Stop/Export)' as the normal state",
          "'Not connected (connects for Start/Stop/Export)'" in js and "(st.status || {}).rc_issues" in js)


def udp_only():
    """31-column device, MATLAB fully disconnected and every MATLAB call raising."""
    import udp_settings as U
    from commands import CommandState
    from imu_cal import ImuCal
    from test_run14_layout import make_session
    from test_run15_layout import Dev31
    dev, calls = Dev31(), []
    dev.v.update(side=0.0, weight_kg=80.0, bif_mass_kg=80.0, settings_seq=3.0, cmd_motor=0.0, cmd_assist=0.0, cmd_k=1.0,
                 bif_bias_ready=1.0)
    ctx, s = make_session(dev, calls)
    ctx.runctl.status = {"connected": False, "running": False}

    def boom(*a, **k):
        raise RuntimeError("MATLAB must not be used")
    ctx.matlab = types.SimpleNamespace(call=boom)
    ctx.adv_link = U.AdvLink({"udp": {"send_host": "127.0.0.1", "adv_port": 15435}}, s.echo_for_link,
                             on_status=s.adv_link_status, on_adopt=s.adv_link_adopted, sender=dev.recv)
    sent5431 = []
    cs = CommandState({"udp": {}}, os.path.join(tempfile.mkdtemp(), "last.json"),
                      lambda cfg, *v, force=False: sent5431.append(v), lambda *a, **k: None,
                      lambda: {k: dev.v[k] for k in ("cmd_motor", "cmd_assist", "cmd_k")})
    cs.frozen = s.link_frozen
    cs.echo_expected = lambda: True
    ctx.commands = cs
    dev.on = True
    time.sleep(0.4)
    s.refresh_echo()
    n = len(dev.packets)
    m = s.confirm_side("RIGHT", "S1")
    check("foot side (two-step confirm) -> one 5434 packet, no MATLAB", len(dev.packets) == n + 1 and dev.packets[-1][3] == 1.0
          and "sending" in m, (m, dev.packets[n:]))
    time.sleep(0.2)
    for key, val, slot in (("weight", 77.0, 4), ("mode", 1, 5), ("k_percent", 4.0, 6)):
        n = len(dev.packets)
        m = s.enter_value(key, val)
        check(f"{key} -> one 5434 packet, no MATLAB", len(dev.packets) == n + 1 and abs(dev.packets[-1][slot] - val) < 1e-3, (m, dev.packets[n:]))
        time.sleep(0.15)
    n = len(getattr(dev, "adv_packets", []))
    m = s.enter_value("i_gain", 1.2)
    check("Advanced -> one 5435 packet, no MATLAB", len(dev.adv_packets) == n + 1, (m, len(getattr(dev, "adv_packets", []))))
    for t in ("motor", "assist", "k"):
        sent5431.clear()
        r = cs.press_toggle(t)
        check(f"{t} -> one 5431 packet, no MATLAB", r["ok"] and len(sent5431) == 1, (r, sent5431))
    dev.v["cmd_assist"] = 0.0
    for name, field in (("zero", 0), ("calibrate", 4), ("reset", 5)):
        sent5431.clear()
        r = cs.pulse(name)
        time.sleep(0.45)
        check(f"{name} -> one 1 -> 0 pulse on 5431 field {field} (two packets, no latch), no MATLAB",
              r["ok"] and len(sent5431) == 2 and sent5431[0][field] == 1.0 and sent5431[1][field] == 0.0
              and not cs.view().get("latched"), (r, sent5431))
    ic = ImuCal(ctx)
    n = len(dev.packets)
    g0 = dev.v["gyro_cal_request"]
    r = ic.press()
    check("Calibrate IMU -> one 5434 packet with the echoed counter + 1, no MATLAB", r["ok"] and len(dev.packets) == n + 1
          and dev.packets[-1][7] == g0 + 1, (r, g0, dev.packets[n:]))
    check("no MATLAB call at all", not [c for c in calls if c[0] == "matlab"], calls)
    ctx.adv_link.stop()
    ctx.settings_link.stop()


def device_only():
    from commands import CommandState
    rb = {"cmd_motor": 0.0, "cmd_assist": 0.0, "cmd_k": 1.0}
    path = os.path.join(tempfile.mkdtemp(), "last.json")
    json.dump({"toggles": {"motor": 1, "assist": 1, "k": 0}}, open(path, "w"))     # 15:41 leftovers
    cs = CommandState({"udp": {}}, path, lambda *a, **k: None, lambda *a, **k: None, lambda: dict(rb))
    cs.echo_expected = lambda: True
    v = cs.view()
    check("Motor / Assist / K show the device echo, not last_command.json", [v["toggles"][t]["value"] for t in ("motor", "assist", "k")]
          == [0, 0, 1], v["toggles"])
    check("no 'differs' / mismatch for Motor / Assist / K", v["mismatch"] == [], v["mismatch"])
    rb.clear()
    v = cs.view()
    check("no echo: unknown (never the remembered values)", all(v["toggles"][t]["value"] is None for t in ("motor", "assist", "k")),
          v["toggles"])
    import status
    src = open(status.__file__, encoding="utf-8").read()
    check("status: no 'X differs' issues any more", 'f"{label} differs"' not in src)


if __name__ == "__main__":
    on_demand()
    udp_only()
    device_only()
    print("FAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
