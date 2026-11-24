"""Calibrate IMU with a fake target (no MATLAB, no target).

Checks: the button is disabled with "needs the next r1 build" when the loaded app has
no Gyro_Cal_Request block; with the block it reads the value and writes value + 1
(readback checked); blocked while Assist AND Motor are on; "Hold still N s…" then
"IMU ready" when bif_bias_ready (console echo) is 1 again, or "IMU ready (assumed)" without it;
AFO (GPR) profile: hidden.

    python test/test_imu_cal.py
"""
import json
import os
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

import session as S  # noqa: E402
from imu_cal import ImuCal  # noqa: E402
from test_round5 import RC, Sup  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


class SyncJobs:
    """Runs job functions at once (so the test sees their effect)."""
    def __init__(self):
        self.started = []

    def running(self, kind):
        return None

    def start(self, kind, title, fn):
        self.started.append((kind, title))
        job = types.SimpleNamespace(add=lambda line: None, title=title)
        try:
            fn(job)
        except Exception:
            pass
        return job


class FakeTarget:
    """afo_session('read', [path|param]) / ('set', blk, prm, val) against a dict of params."""
    def __init__(self, params):
        self.params = dict(params)
        self.sets = []
        self.stream = {}

    def call(self, func, action, *args, timeout=0):
        assert func == "afo_session"
        if action == "read":
            vals = []
            for p in args[0]:
                if p in self.params:
                    vals.append({"path": p, "value": self.params[p], "err": ""})
                else:
                    vals.append({"path": p, "value": [], "err": "Unable to find block"})
            return json.dumps({"ok": True, "values": vals})
        if action == "set":
            blk, prm, val = args
            key = f"{blk}|{prm}"
            if key not in self.params:
                return json.dumps({"ok": False, "err": "Unable to find block"})
            self.params[key] = val
            self.sets.append((key, val))
            return json.dumps({"ok": True, "readback": val, "requested": val})
        raise AssertionError(action)

    def snapshot(self, kind, names, max_age, timeout=0.3):
        return {"values": {k: v for k, v in self.stream.items() if k in names}}


class Cmd:
    def __init__(self, motor=0, assist=0):
        self.t = {"motor": {"value": motor}, "assist": {"value": assist}, "k": {"value": 1}}

    def view(self):
        return {"toggles": self.t}


def make(params, app="AFO_r1", motor=0, assist=0):
    tmp = tempfile.mkdtemp(prefix="afo_imucal_")
    ctx = types.SimpleNamespace()
    ctx.app_dir = tmp
    ctx.cfg = {"paths": {"log_dir": tmp}, "session": {"target_writes_enabled": True}, "target": {"model": "auto"}}
    ctx.runctl = RC({"connected": True, "running": True, "app": app})
    ctx.jobs = SyncJobs()
    ctx.live = Sup({"live_seen": True, "age_s": 0.05})
    ctx.training = Sup({"packets_ok": 0, "age_s": None})
    ctx.commands = Cmd(motor, assist)
    ctx.matlab = FakeTarget(params)
    ctx.session = S.SessionSetup(ctx)
    ctx.imu_cal = ImuCal(ctx, hold_s=0.6, ready_timeout_s=1.0, hold_no_signal_s=0.9)
    return ctx


def main():
    path = "AFO_r1/Gyro_Cal_Request|Value"
    # 1) current r1 build: no block -> disabled with the reason
    ctx = make({})
    ic = ctx.imu_cal
    ic.probe(force=True)
    v = ic.view()
    check("no block: visible but disabled", v["visible"] and not v["enabled"], v)
    check("no block: says it needs the next r1 build", "next r1 build" in v["reason"], v["reason"])
    check("no block: press refused, nothing set", not ic.press()["ok"] and not ctx.matlab.sets)

    # 2) block present, Assist and Motor ON -> blocked
    ctx = make({path: 3.0}, motor=1, assist=1)
    ctx.imu_cal.probe(force=True)
    v = ctx.imu_cal.view()
    check("block: available", v["available"] is True and v["value"] == 3.0, v)
    check("Assist+Motor on: blocked", not v["enabled"] and "Assist or Motor" in v["reason"], v)

    # 3) Motor OFF: press -> value + 1 with readback, hold, then IMU ready from Signals
    ctx = make({path: 3.0}, motor=0, assist=1)
    ic = ctx.imu_cal
    ic.probe(force=True)
    check("Motor off: enabled", ic.view()["enabled"], ic.view())
    ctx.training = Sup({"packets_ok": 100, "age_s": 0.05}, {"bif_bias_ready": 1.0, "bif_valid": 0.0})   # a bias signal exists at the press
    r = ic.press()
    check("press: ok", r["ok"], r)
    check("press: setparam value + 1", ctx.matlab.sets == [(path, 4.0)], ctx.matlab.sets)
    v = ic.view()
    check("after press: Hold still N s…", v["state"] == "busy" and v["text"].startswith("Hold still"), v)
    check("after press: button disabled while holding", not v["enabled"], v)
    ctx.training = Sup({"packets_ok": 100, "age_s": 0.05}, {"bif_bias_ready": 0.0, "bif_valid": 0.0})
    time.sleep(0.7)
    v = ic.view()
    check("bias not ready yet: waiting", v["text"] == "Hold still… waiting for IMU ready", v)
    ctx.training = Sup({"packets_ok": 100, "age_s": 0.05}, {"bif_bias_ready": 1.0, "bif_valid": 0.0})
    v = ic.view()
    check("bias ready: IMU ready", v["text"] == "IMU ready" and v["state"] == "done", v)
    check("enabled again after", ic.view()["enabled"], ic.view())
    r = ic.press()
    check("second press: value + 1 again", r["ok"] and ctx.matlab.sets[-1] == (path, 5.0), ctx.matlab.sets)

    # 4) no Signals stream: IMU ready (assumed) after the hold
    ctx = make({path: 0.0})
    ic = ctx.imu_cal
    ic.probe(force=True)
    ic.press()
    time.sleep(0.7)
    v = ic.view()
    check("no Signals: still holding (longer countdown)", v["text"].startswith("Hold still"), v)
    time.sleep(0.3)
    v = ic.view()
    check("no Signals: IMU ready (assumed)", v["text"] == "IMU ready (assumed)", v)

    # 4b) the countdown length is fixed at the confirmation and counted from it (no bias signal: 0.9 s here,
    #     6 s live): still holding just before, done just after, even if a bias signal appears meanwhile
    ctx = make({path: 0.0})
    ic = ctx.imu_cal
    ic.probe(force=True)
    ic.press()
    t_conf = ic.pressed_at
    check("hold length fixed at confirmation (no bias signal)", ic.hold_len == 0.9, ic.hold_len)
    ctx.training = Sup({"packets_ok": 100, "age_s": 0.05}, {"bif_bias_ready": 1.0})        # a signal appearing later must not shorten it
    time.sleep(max(0.0, t_conf + 0.75 - time.time()))
    check("still holding at 0.75 s", ic.view()["text"].startswith("Hold still"), ic.view())
    time.sleep(max(0.0, t_conf + 0.95 - time.time()))
    check("done after 0.9 s", not ic.view()["text"].startswith("Hold still"), ic.view())

    # 5) bias never comes back -> not ready message
    ctx = make({path: 0.0})
    ic = ctx.imu_cal
    ic.probe(force=True)
    ic.press()
    ctx.training = Sup({"packets_ok": 100, "age_s": 0.05}, {"bif_bias_ready": 0.0})
    time.sleep(1.8)
    v = ic.view()
    check("bias stays 0: IMU not ready", v["state"] == "error" and "not ready" in v["text"], v)

    # 6) AFO (GPR): hidden
    ctx = make({path: 0.0}, app="AFO")
    v = ctx.imu_cal.view()
    check("AFO profile: hidden", not v["visible"], v)

    # 7) not connected (model known from config target.model AFO_r1)
    ctx = make({path: 0.0})
    ctx.runctl.status = {"connected": False}
    ctx.session.configured_model = "AFO_r1"
    check("not connected: Connect first", ctx.imu_cal.view()["reason"] == "Connect first", ctx.imu_cal.view())

    # 8) page wiring
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: IMU next to FSR in the Calibration section", "id=\"bImuCal\"" in js and ">FSR</button>" in js
          and "/api/console/imucal" in js)
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
