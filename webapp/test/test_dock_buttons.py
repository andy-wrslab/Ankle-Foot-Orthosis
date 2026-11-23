"""Dock one-shot buttons (Andy 15:05-15:06), seconds, no browser, no target:
- Zero / Calibrate FSR are latched toggles: one 5430 packet per press, field = 1 then (next
  press) 0, motor / assist / k unchanged, and every later packet carries the latched field
  (hold-last-command). Zero ON refused with Assist on, OFF always allowed. Calibrate FSR's lit
  state is adopted from the 5433 echo (cmd_calibrate_pressure) without sending anything.
- Reset SV stays a ~200 ms 1 -> 0 pulse (level-triggered in the model), with one INFO line:
  send times of the 1 and the 0, echo samples seen, max col 8 / col 9.
- Calibrate IMU = the 5434 gyro counter + 1.
- Page: the JScript harness runs assets/afo_dock_actions.js (disabled cleared after a press,
  fixed labels, lit / greyed / pressed); no countdown, busy text or success toast remains.

    python test/test_dock_buttons.py
"""
import logging
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def make_cs(rb):
    from commands import CommandState
    sent = []
    tmp = tempfile.mkdtemp(prefix="afo_dock_")
    path = os.path.join(tmp, "last.json")
    cs = CommandState({"udp": {}}, path, lambda cfg, *v, force=False: sent.append((time.time(), v)),
                      lambda *a, **k: None, lambda: dict(rb))
    return cs, sent, path


def toggles():
    rb = {"cmd_motor": 1.0, "cmd_assist": 0.0, "cmd_k": 1.0}
    cs, sent, path = make_cs(rb)
    r = cs.pulse("zero")
    time.sleep(0.4)
    check("Zero ON: accepted, state 1, no success text", r["ok"] and r.get("state") == 1 and r["msg"] == "", r)
    check("Zero ON: exactly one packet, field 0 = 1, motor / assist / k = 1, 0, 1",
          len(sent) == 1 and sent[0][1] == (1.0, 1.0, 0.0, 1.0, 0.0, 0.0), sent)
    sent.clear()
    r = cs.press_toggle("k")
    check("hold-last-command: a K press carries Zero = 1", r["ok"] and len(sent) == 1 and sent[0][1][0] == 1.0
          and sent[0][1][3] == 0.0, sent)
    rb["cmd_k"] = 0.0
    rb["cmd_assist"] = 1.0
    sent.clear()
    r = cs.pulse("zero")
    check("Zero OFF with Assist on: allowed, one packet field 0 = 0", r["ok"] and r.get("state") == 0 and len(sent) == 1
          and sent[0][1][0] == 0.0, (r, sent))
    sent.clear()
    r = cs.pulse("zero")
    check("Zero ON with Assist on: refused, nothing sent", not r["ok"] and "Assist off" in r["msg"] and not sent, (r, sent))
    rb["cmd_assist"] = 0.0

    # Calibrate FSR toggle
    sent.clear()
    r = cs.pulse("calibrate")
    check("Calibrate FSR ON: one packet, field 4 = 1, no lock / countdown text",
          r["ok"] and r.get("state") == 1 and r["msg"] == "" and len(sent) == 1 and sent[0][1][4] == 1.0, (r, sent))
    check("Calibrate FSR: no 30 s lock in the view", cs.view()["calibrate_busy_s"] == 0.0, cs.view()["calibrate_busy_s"])
    rb["cmd_calibrate_pressure"] = 0.0          # echo not caught up yet: the just-sent state wins
    check("Calibrate FSR: lit right after the press although the echo still says 0",
          cs.view()["latched"]["calibrate"] == 1, cs.view()["latched"])
    rb["cmd_calibrate_pressure"] = 1.0
    sent.clear()
    r = cs.pulse("calibrate")
    check("Calibrate FSR OFF: second press sends field 4 = 0 (press again = off)",
          r["ok"] and r.get("state") == 0 and len(sent) == 1 and sent[0][1][4] == 0.0, (r, sent))

    # adopt from the echo: nothing sent, the next packet carries the device's state
    cs2, sent2, _ = make_cs({"cmd_motor": 0.0, "cmd_assist": 0.0, "cmd_k": 0.0, "cmd_calibrate_pressure": 1.0})
    v = cs2.view()
    check("adopt: Calibrate FSR lit from the echo (col 8 = 1) on a fresh console, nothing sent",
          v["latched"]["calibrate"] == 1 and not sent2, (v["latched"], sent2))
    cs2.press_toggle("motor")
    check("adopt: the next packet (Motor) carries calibrate = 1", len(sent2) == 1 and sent2[0][1][4] == 1.0, sent2)

    # restart: the latched Zero comes back from last_command.json, nothing sent
    from commands import CommandState
    sent3 = []
    cs3 = CommandState({"udp": {}}, path, lambda cfg, *v, force=False: sent3.append(v), lambda *a, **k: None,
                       lambda: {"cmd_motor": 1.0, "cmd_assist": 0.0, "cmd_k": 0.0})
    cs3.toggles.update(motor=1, assist=0, k=0)
    check("restart: Zero state from the last sent command (no echo for Zero), nothing sent",
          cs3.view()["latched"]["zero"] == 0 and not sent3, (cs3.view()["latched"], sent3))


class _Cap(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, rec):
        self.lines.append(rec.getMessage())


def reset_pulse():
    rb = {"cmd_motor": 1.0, "cmd_assist": 0.0, "cmd_k": 1.0, "cmd_reset_sv": 0.0, "cmd_calibrate_pressure": 0.0,
          "t_model": 10.0}
    cs, sent, _ = make_cs(rb)
    cap = _Cap()
    logging.getLogger("afo.commands").addHandler(cap)
    logging.getLogger("afo.commands").setLevel(logging.INFO)

    def fake_echo():
        t_end = time.time() + 0.5
        while time.time() < t_end:
            rb["t_model"] = round(rb["t_model"] + 0.05, 2)
            rb["cmd_reset_sv"] = 1.0 if sent and sent[-1][1][5] == 1.0 else 0.0
            time.sleep(0.05)
    import threading
    r = cs.pulse("reset")
    threading.Thread(target=fake_echo, daemon=True).start()
    time.sleep(0.6)
    check("Reset SV: accepted, no success text", r["ok"] and r["msg"] == "", r)
    check("Reset SV: still exactly two packets, field 5 = 1 then 0", len(sent) == 2 and sent[0][1][5] == 1.0
          and sent[1][1][5] == 0.0, sent)
    check("Reset SV: ~200 ms pulse", len(sent) == 2 and 0.15 <= sent[1][0] - sent[0][0] <= 0.35,
          [round(x[0] - sent[0][0], 3) for x in sent])
    check("Reset SV: motor / assist / k unchanged in both packets", all(p[1][1:4] == (1.0, 0.0, 1.0) for p in sent), sent)
    ln = [x for x in cap.lines if x.startswith("user pulsed reset")]
    check("Reset SV: one INFO line with send times, echo samples, max col 8 / col 9",
          len(ln) == 1 and "1 sent" in ln[0] and "0 sent" in ln[0] and "echo samples" in ln[0]
          and "max cmd_calibrate_pressure 0.0" in ln[0] and "max cmd_reset_sv 1.0" in ln[0] and "saw it: True" in ln[0], ln)


def imu_plus_one():
    from imu_cal import ImuCal
    pressed = []

    class Lk:
        def view(self):
            return {"adopted": {"gyro": 4.0}}

        def press(self, field, value):
            pressed.append((field, value))
            return {"ok": True}

    class Sess:
        def link(self):
            return Lk()

        def bif_view(self):
            return {"bias_ready": 1.0}

        def audit(self, *a):
            pass

    class Ctx:
        session = Sess()
    ic = ImuCal(Ctx())
    ic.block_reason = lambda: None
    r = ic.press()
    check("Calibrate IMU: 5434 gyro_cal_request = echoed counter + 1 (4 -> 5)", r["ok"] and pressed == [("gyro", 5.0)], (r, pressed))


def page():
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    da = open(os.path.join(APP, "assets", "afo_dock_actions.js"), encoding="utf-8").read()
    gone = [t for t in ("Zeroing", "Resetting", "Reset sent", "Calibrating… 30 s", "Calibrate IMU: sending",
                        "toast('Zeroed'", "calibrate_busy_s", "ic.text") if t in js or t in da]
    check("page: no busy text, countdown or success toast on the dock buttons", not gone, gone)
    import re
    users = re.findall(r"busyNow\(\$\('(\w+)'\)", js)
    check("page: busyNow only on Connect / Start / Stop (their render clears disabled)",
          set(users) <= {"tConnect", "tStart", "tStop"}, users)
    check("page: renderTarget re-enables Connect / Start / Stop", "c.disabled = false;" in js
          and "s.disabled = !!T.running;" in js and "p.disabled = !T.running;" in js)
    check("page: dock render goes through AFODockActions.render", "AFODockActions.render({zero: $('bZero')" in js)
    css = open(os.path.join(APP, "assets", "afo-ui.css"), encoding="utf-8").read()
    check("css: lit and pressed styles for the dock buttons", ".btn.act.lit" in css and ".btn.act.pressed" in css)
    check("Calibrate IMU / Reset SV momentary: dark only while held (:active), no pressed tint, never lit",
          'class="btn act momentary" id="bImuCal"' in js and 'class="btn act momentary" id="bResetSV"' in js
          and ".btn.act.momentary:active" in css and "!b.classList.contains('momentary')" in js
          and "lit: false, locked: !ic.enabled" in da and "ic.state === 'busy'" not in da)
    if os.name != "nt":
        print("skip: JScript harness needs Windows (cscript)")
        return
    p = subprocess.run(["cscript", "//nologo", "//E:jscript", os.path.join(HERE, "js", "dock_actions_harness.js"),
                        os.path.join(APP, "assets", "afo_dock_actions.js")], capture_output=True, text=True,
                       timeout=60, creationflags=0x08000000)
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    for l in lines:
        if l.startswith("ok") or l.startswith("FAIL"):
            check("js: " + l[5:], l.startswith("ok"), l)
    check("js: harness ran to the end", lines and lines[-1] == "done", (p.stdout[-400:], p.stderr[-400:]))


if __name__ == "__main__":
    toggles()
    reset_pulse()
    imu_plus_one()
    page()
    print("FAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
