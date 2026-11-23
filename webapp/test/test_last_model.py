"""Offline model profile = the app of the last successful connect (no target, no MATLAB).

target.model auto: before any connect the page uses AFO (GPR); a connect that reads
AFO_r1 is remembered in data/last_model.json, and a new app session that is not
connected keeps the AFO_r1 controls (Calibrate IMU visible but disabled with the
reason in its title, quiet side chip, no "? CONFIRM FOOT"). Only a successful connect
that reads a different app switches the profile; an explicit target.model wins.

    python test/test_last_model.py
"""
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

import session as S  # noqa: E402
from imu_cal import ImuCal  # noqa: E402
from pages.console_api import side_view  # noqa: E402
from pages.runctl import RunControl  # noqa: E402
from test_round5 import Cmd, Jobs, Sup  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def make(app_dir, model="auto"):
    ctx = types.SimpleNamespace(app_dir=app_dir, cfg={"paths": {"log_dir": app_dir}, "target": {"model": model},
                                                      "session": {"target_writes_enabled": True}},
                                jobs=Jobs(), live=Sup({"live_seen": False, "age_s": None}),
                                training=Sup({"packets_ok": 0, "age_s": None}), commands=Cmd())
    ctx.runctl = RunControl(ctx)
    ctx.session = S.SessionSetup(ctx)
    ctx.imu_cal = ImuCal(ctx)
    return ctx


def connect(ctx, app):
    ctx.matlab = types.SimpleNamespace(call=lambda *a, **k: json.dumps(
        {"ok": True, "connected": True, "loaded": True, "running": False, "app": app}))
    job = types.SimpleNamespace(lines=[], add=lambda line: None, meta={})
    ctx.runctl.call(job, "connect")


def disconnect(ctx):
    ctx.runctl.status = {"connected": False}


def main():
    d = tempfile.mkdtemp(prefix="afo_lastmodel_")
    ctx = make(d)
    check("fresh install, offline: AFO (GPR)", ctx.session.model() == "AFO", ctx.session.model())
    connect(ctx, "AFO_r1")
    check("connect reads AFO_r1: profile AFO_r1", ctx.session.model() == "AFO_r1")
    lm = os.path.join(d, "data", "last_model.json")
    check("remembered in data/last_model.json", os.path.exists(lm) and json.load(open(lm))["app"] == "AFO_r1",
          open(lm).read() if os.path.exists(lm) else None)
    disconnect(ctx)
    check("same session, disconnected: still AFO_r1", ctx.session.model() == "AFO_r1")

    # app restart with the target off
    ctx = make(d)
    s = ctx.session
    check("restart, target off: AFO_r1 (last connected)", s.model() == "AFO_r1", s.model())
    iv = ctx.imu_cal.view()
    check("offline: Calibrate IMU visible", iv["visible"] is True, iv)
    check("offline: Calibrate IMU disabled with a reason", iv["enabled"] is False and iv["reason"] == "Connect first", iv)
    s.set_sid("S5")
    s.values["side"] = 0                    # entered earlier (not confirmed in this app session)
    sv = side_view(ctx)
    check("offline: no '? CONFIRM FOOT', quiet 'Left foot · not confirmed'",
          sv["chip"] == "Left foot · not confirmed" and not sv["connected"], sv)
    s.values.pop("side")
    check("offline, no side: 'Foot side · not set'", side_view(ctx)["chip"] == "Foot side · not set", side_view(ctx)["chip"])
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: amber CONFIRM FOOT only when connected", "sd.state === 'confirm' && onLive && sd.connected ? ' unset'" in js)
    check("page: Rig status says 'last connected'", "'last connect'" in js and "· last connected" in js)
    ctx.live = Sup({"live_seen": True, "age_s": 0.05})      # MATLAB not connected, but live data
    check("not connected but live data (app runs): '? CONFIRM FOOT'", side_view(ctx)["chip"] == "? CONFIRM FOOT",
          side_view(ctx)["chip"])
    ctx.live = Sup({"live_seen": False, "age_s": None})
    ctx.runctl.status = {"connected": True, "app": "AFO_r1"}
    check("connected, side not confirmed: '? CONFIRM FOOT' as before", side_view(ctx)["chip"] == "? CONFIRM FOOT",
          side_view(ctx)["chip"])

    # a failed connect / status without an app keeps it; a different app switches
    ctx.runctl.status = {"connected": False}
    s.remember_app(None)
    check("no app read: profile kept", s.model() == "AFO_r1")
    connect(ctx, "AFO")
    disconnect(ctx)
    check("connect reads AFO: switches to AFO (GPR) and stays offline", s.model() == "AFO" and make(d).session.model() == "AFO")
    connect(ctx, "AFO_r1")
    disconnect(ctx)
    # explicit target.model wins over the last connect
    check("explicit target.model AFO wins offline", make(d, model="AFO").session.model() == "AFO")
    check("unknown app read: profile kept", (connect(ctx, "SomeOtherApp") or True) and
          (disconnect(ctx) or True) and make(d).session.model() == "AFO_r1")
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
