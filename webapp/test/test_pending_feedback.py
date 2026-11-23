"""Instant feedback for side and Mass (no target): what the page shows right after a press.

    python test/test_pending_feedback.py
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
from test_round5 import Cmd, Jobs, RC, Sup  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def make(rc):
    tmp = tempfile.mkdtemp(prefix="afo_pend_")
    ctx = types.SimpleNamespace(app_dir=tmp, cfg={"paths": {"log_dir": tmp}, "session": {"target_writes_enabled": True},
                                                  "target": {"model": "AFO_r1"}},
                                runctl=RC(rc), jobs=Jobs(), live=Sup({"live_seen": True, "age_s": 0.05}),
                                training=Sup({"packets_ok": 0, "age_s": None}), commands=Cmd())
    ctx.session = S.SessionSetup(ctx)
    ctx.session.set_sid("S97")
    return ctx


def main():
    # not connected
    s = make({"connected": False}).session
    s.confirm_side("LEFT", "S97")
    check("not connected: chip at once", s.side_chip() == {"text": "Left · pending, sent when connected", "state": "pending"},
          s.side_chip())
    m = s.enter_value("weight", 83)
    check("not connected: Mass pending, sent when connected", s.status["weight"]["state"] == "pending"
          and "when connected" in s.status["weight"]["msg"] and "when connected" in m, (m, s.status.get("weight")))
    # Connect to an app that is ALREADY RUNNING: pending side + mass go out at once (no Start needed)
    import time as _t
    from pages.runctl import RunControl
    _t.sleep(0.6)                                          # bif_mass follows the body mass (sent after)
    ctx = s.ctx
    rcl = RunControl(ctx)
    ctx.matlab = types.SimpleNamespace(call=lambda *a, **k: json.dumps(
        {"ok": True, "connected": True, "loaded": True, "running": True, "app": "AFO_r1"}))
    ctx.runctl = rcl
    n0 = len(ctx.jobs.started)
    job = types.SimpleNamespace(lines=[], add=lambda line: None, meta={})
    rcl.call(job, "connect")
    t_end = _t.time() + 5
    want = {("session", "set side"), ("session", "set weight"), ("session", "set bif_mass")}
    while _t.time() < t_end and not want <= set(ctx.jobs.started[n0:]):
        _t.sleep(0.05)
    check("Connect to a running app: pending side, mass, BIF mass sent at once", want <= set(ctx.jobs.started[n0:]),
          ctx.jobs.started[n0:])
    check("... then read back (state sending -> setparam + getparam)", s.status["side"]["state"] == "sending"
          and s.status["weight"]["state"] == "sending", {k: s.status[k]["state"] for k in ("side", "weight")})
    n1 = len(ctx.jobs.started)
    rcl.call(job, "status")
    _t.sleep(0.4)
    check("a later status sends nothing twice", len(ctx.jobs.started) == n1, ctx.jobs.started[n1:])
    # Connect to a STOPPED app: still held, now 'sent after Start'
    s2 = make({"connected": False}).session
    s2.confirm_side("LEFT", "S97")
    ctx2 = s2.ctx
    rc2 = RunControl(ctx2)
    ctx2.matlab = types.SimpleNamespace(call=lambda *a, **k: json.dumps(
        {"ok": True, "connected": True, "loaded": True, "running": False, "app": "AFO_r1"}))
    ctx2.runctl = rc2
    n0 = len(ctx2.jobs.started)
    rc2.call(job, "connect")
    s2.after_connect_or_start("connect")
    check("Connect to a stopped app: nothing sent, chip 'sent after Start'", not ctx2.jobs.started[n0:]
          and s2.side_chip()["text"] == "Left · pending, sent after Start", (ctx2.jobs.started[n0:], s2.side_chip()))
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    css = open(os.path.join(APP, "assets", "afo-ui.css"), encoding="utf-8").read()
    check("page: pending fields amber (send-pending), errors red (send-error), separate",
          "classList.toggle('send-pending', stt === 'pending'" in js and "classList.toggle('send-error', stt === 'error')" in js
          and ".input.send-pending { border-color: var(--caution)" in css, None)
    # connected, app stopped (Stop unloads it)
    s = make({"connected": True, "loaded": False, "running": False, "app": "AFO_r1"}).session
    s.confirm_side("LEFT", "S97")
    check("app stopped: chip 'sent after Start' at once",
          s.side_chip() == {"text": "Left · pending, sent after Start", "state": "pending"}, s.side_chip())
    m = s.enter_value("weight", 83)
    check("app stopped: Mass pending after Start", s.status["weight"]["state"] == "pending"
          and "after Start" in s.status["weight"]["msg"] and "after Start" in m, (m, s.status.get("weight")))
    check("app stopped: Motor still locked", s.guard("motor") is not None)
    # (re)connect to an app started elsewhere: the target has the built values side -1, BIF mass 0
    from status import top_status
    ctx = make({"connected": True, "loaded": True, "running": True, "app": "AFO_r1"})
    ctx.live = Sup({"live_seen": True, "age_s": 0.05})
    ctx.training = Sup({"packets_ok": 100, "age_s": 0.05})
    s = ctx.session
    s._put("side", -1.0, "echo")
    s._put("bif_mass", 0.0, "getparam")
    st = top_status(ctx)
    keys = [i["key"] for i in st["issues"]]
    check("reconnect, side -1: status 'Confirm foot side'", st["text"] == "Confirm foot side" and "confirm-side" in keys,
          (st["text"], keys))
    check("reconnect, BIF mass 0: 'Set mass' listed", "bif-mass" in keys and
          any(i["text"] == "Set mass" for i in st["issues"]), keys)
    check("every open item says what to do", all(i.get("todo") for i in st["issues"]), st["issues"])
    n0 = len(ctx.jobs.started)
    m = s.confirm_side("LEFT", "S97")
    check("Left while connected + running: sent at once", ("session", "set side") in ctx.jobs.started[n0:]
          and s.status["side"]["state"] == "sending", (m, ctx.jobs.started[n0:], s.status.get("side")))
    # drive fault on AFO_r1 while running: red, first
    ctx.live = types.SimpleNamespace(get_status=lambda: {"live_seen": True, "age_s": 0.05}, last_hb=__import__("time").monotonic(),
                                     readback=lambda: {"statusword": 0x0628})
    st = top_status(ctx)
    check("drive fault: red 'Drive fault (STO)' on top", st["text"] == "Drive fault (STO)" and st["level"] == "red",
          (st["text"], st["level"]))
    # 15-float console packet (Andy's choice): IMU not ready -> Calibrating n/30 s -> Ready
    def ctx15(ready, valid, prog):
        cx = make({"connected": True, "loaded": True, "running": True, "app": "AFO_r1"})
        echo = {"side": 0.0, "weight_kg": 83.0, "assist_mode": 3.0, "fixed_k_pct": 5.0, "cmd_motor": 1.0,
                "cmd_assist": 1.0, "cmd_k": 1.0, "bif_valid": valid, "bif_cal_progress": prog, "bif_bias_ready": ready}
        cx.live = Sup({"live_seen": True, "age_s": 0.05})
        cx.training = Sup({"packets_ok": 100, "age_s": 0.05}, echo)
        ss = cx.session
        ss.values.update(side=0, weight=83.0, bif_mass=83.0, mode=3, k_percent=5)
        ss.side_confirmed = {"sid": "S97", "side": 0, "at": 0}
        ss.refresh_readback()
        ss._put("bif_mass", 83.0, "getparam")
        return cx
    cx = ctx15(0.0, 0.0, 0.0)
    st = top_status(cx)
    check("15 floats, bias 0: button 'IMU not ready' (amber)", st["text"] == "IMU not ready" and st["level"] == "amber",
          (st["text"], [i["key"] for i in st["issues"]]))
    chk = cx.session.checklist()
    check("15 floats, bias 0: popover IMU ready not done", [i["done"] for i in chk["items"]][2] is False, chk["items"])
    cx = ctx15(1.0, 0.0, 0.4)
    st = top_status(cx)
    check("15 floats, walking: button 'Calibrating 12/30 s'", st["text"] == "Calibrating 12/30 s", (st["text"], st["issues"]))
    chk = cx.session.checklist()
    check("15 floats, walking: popover IMU ready done, walk 40 %",
          chk["items"][2]["done"] is True and chk["items"][3]["detail"] == "40 %", chk["items"])
    cx = ctx15(1.0, 1.0, 1.0)
    st = top_status(cx)
    check("15 floats, valid: button 'Ready' (green), no note", st["text"] == "Ready" and st["level"] == "green"
          and not st.get("notes"), (st["text"], st["issues"], st.get("notes")))
    check("15 floats, valid: checklist all done", cx.session.checklist()["all_done"] is True)
    # IMU fault (red): console imu_ok = 0, or imu_bad_count rising in the last 10 s
    cx = ctx15(1.0, 1.0, 1.0)
    cx.training._latest.update(imu_ok=1.0, imu_bad_count=93.0)
    st = top_status(cx); top_status(cx)
    check("IMU fine, constant bad count: no IMU fault", not any(i["key"] == "imu-fault" for i in st["issues"]),
          [i["key"] for i in st["issues"]])
    cx.training._latest.update(imu_bad_count=97.0)
    st = top_status(cx)
    check("imu_bad_count rose: red 'IMU fault'", st["text"] == "IMU fault" and st["level"] == "red", (st["text"], st["issues"]))
    cx = ctx15(1.0, 1.0, 1.0)
    cx.training._latest.update(imu_ok=0.0, imu_bad_count=0.0)
    st = top_status(cx)
    fault = next((i for i in st["issues"] if i["key"] == "imu-fault"), {})
    check("imu_ok = 0: red 'IMU fault' with what to do", st["text"] == "IMU fault" and "replug" in fault.get("todo", ""),
          (st["text"], fault))

    # fresh readbacks: Connect / Start / Disconnect clear them; a failed getparam drops the value
    import json as _json
    cx = make({"connected": True, "loaded": True, "running": True, "app": "AFO_r1"})
    ss = cx.session
    ss._put("side", 0.0, "getparam"); ss._put("weight", 70.0, "getparam")
    ss.after_connect_or_start("connect")
    check("Connect clears the readback", not ss.readback and not ss.readback_src, ss.readback)
    ss._put("side", 0.0, "getparam")
    ss.after_connect_or_start("start")
    check("Start clears the readback", "side" not in ss.readback, ss.readback)
    ss._put("side", 0.0, "getparam")
    ss.clear_readback()       # what run control calls after Disconnect
    check("Disconnect clears the readback", not ss.readback, ss.readback)

    class SyncJobs:
        def __init__(self):
            self.started = []

        def running(self, kind):
            return None

        def start(self, kind, title, fn):
            self.started.append((kind, title))
            fn(types.SimpleNamespace(add=lambda line: None))

    class FakeML:
        def call(self, func, action, *args, timeout=0):
            if action == "read":
                vals = [{"path": p_, "value": 0.0, "err": ""} if "Left 0" in p_ else
                        {"path": p_, "value": [], "err": "Unable to get parameter: No application is loaded on target computer 'TargetPC1'."}
                        for p_ in args[0]]
                return _json.dumps({"ok": True, "values": vals})
            return _json.dumps({"ok": False, "err": "Unable to set 'Value' parameter value on target computer 'TargetPC1': "
                                                     "No application is loaded on target computer."})

        def snapshot(self, *a, **k):
            return None
    cx = make({"connected": True, "loaded": True, "running": True, "app": "AFO_r1"})
    cx.jobs, cx.matlab = SyncJobs(), FakeML()
    cx.live = Sup({"live_seen": True, "age_s": 0.05})
    cx.training = Sup({"packets_ok": 100, "age_s": 0.05})
    ss = cx.session
    ss._put("weight", 70.0, "getparam")
    ss.refresh_readback()
    check("failed getparam drops the old value", "weight" not in ss.readback and ss.readback.get("side") == 0.0,
          (ss.readback, ss.readback_src))
    st = top_status(cx)
    check("app started elsewhere: amber on the status button", st["text"] == ss.ELSEWHERE_MSG and st["level"] == "amber",
          (st["text"], [i["key"] for i in st["issues"]]))
    check("app started elsewhere: in the popover with what to do",
          any(i["key"] == "app-elsewhere" and i.get("todo") for i in st["issues"]))
    ss.side_confirmed = None
    m = ss.confirm_side("LEFT", "S97")
    check("setparam with no app loaded: status error with the message",
          ss.status["side"]["state"] == "error" and ss.status["side"]["msg"] == ss.ELSEWHERE_MSG, (m, ss.status.get("side")))
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: Mass state tag + toast on commit", 'id="sMassState"' in js and "after Start" in js
          and "toast(r.needs_confirm" in js)
    check("page: Start not locked by side", "s.disabled = !!T.running;" in js)
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
