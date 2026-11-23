"""Foot side / mass with run 13 live (Nov 23 13:53, Andy: "foot side sending takes way too
long, and it still showed ? confirm foot after a while"). No target, no MATLAB.

- a refused setparam ("No application is loaded" while running: app started by another
  MATLAB) shows at once on the chip: "Left · target refused" with "Target refused: app
  started by another MATLAB, press Stop → Start" (no silent wait for a readback);
- the 5433 console echo confirms the side as soon as it matches (one console packet, no
  getparam);
- a confirmed side is not reverted when the echo goes stale or a getparam fails; only a
  different echoed value (mismatch) or Start clears it.

    python test/test_side_echo.py
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
from pages.console_api import side_view  # noqa: E402
from test_round5 import Cmd  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


class SyncJobs:
    """Runs each job at once (the real JobManager runs it in a thread)."""
    def __init__(self):
        self.started = []

    def running(self, kind):
        return None

    def start(self, kind, title, fn):
        self.started.append((kind, title))
        job = types.SimpleNamespace(add=lambda line: None, meta={}, id=len(self.started))
        fn(job)
        return job


class Console:
    """Fake 5433 stream: latest() returns the echo while fresh."""
    def __init__(self):
        self.echo, self.at = {}, 0.0

    def get_status(self):
        return {"packets_ok": 1, "age_s": 0.01}

    def latest(self, max_age_s=1.0):
        return dict(self.echo) if self.echo and time.time() - self.at <= max_age_s else {}

    def send(self, **v):
        self.echo, self.at = dict(v), time.time()


def make(setparam_answer):
    tmp = tempfile.mkdtemp(prefix="afo_side_")
    calls = []

    def ml_call(fn, action, *a, **k):
        calls.append((fn, action, a))
        return json.dumps(setparam_answer(action, a))
    ctx = types.SimpleNamespace(app_dir=tmp, cfg={"paths": {"log_dir": tmp}, "target": {"model": "AFO_r1"},
                                                  "session": {"target_writes_enabled": True}},
                                runctl=types.SimpleNamespace(status={"connected": True, "running": True, "app": "AFO_r1"}),
                                jobs=SyncJobs(), live=types.SimpleNamespace(get_status=lambda: {"live_seen": True, "age_s": 0.02},
                                                                            last_hb=time.monotonic()),
                                training=Console(), commands=Cmd(), matlab=types.SimpleNamespace(call=ml_call))
    ctx.session = S.SessionSetup(ctx)
    ctx.session.set_sid("S95")
    return ctx, calls


def main():
    # 1) refused: app started by another MATLAB (session_setup.csv 13:51:23, 13:52:38)
    err = ("Unable to set 'Value' parameter value on target computer 'TargetPC1': "
           "No application is loaded on target computer.")
    ctx, calls = make(lambda action, a: {"ok": False, "err": err})
    s = ctx.session
    t0 = time.time()
    s.confirm_side("LEFT", "S95")
    chip = s.side_chip()
    check("refused: chip says so at once", chip["state"] == "refused" and chip["text"] == "Left · target refused"
          and time.time() - t0 < 0.5, chip)
    check("refused: exact message (app elsewhere)", chip.get("msg") == "Target refused: app started by another MATLAB, press Stop → Start",
          chip)
    sv = side_view(ctx)
    check("page state: side 'refused' with the message (dock + toast)", sv["state"] == "refused"
          and sv["msg"].startswith("Target refused: app started by another MATLAB") and sv["chip"] == "Left · target refused", sv)
    s.enter_value("weight", 70)
    check("mass refused: status error with the reason", (s.status.get("weight") or {}).get("state") == "error"
          and s.refusal_text("weight") == "Target refused: app started by another MATLAB, press Stop → Start", s.status.get("weight"))
    # other refusal: the real error
    ctx2, _ = make(lambda action, a: {"ok": False, "err": "Parameter 'Value' is not tunable"})
    ctx2.session.confirm_side("RIGHT", "S95")
    check("other refusal: the real error", ctx2.session.side_chip().get("msg") == "Target refused: Parameter 'Value' is not tunable",
          ctx2.session.side_chip())
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: refused side red + dock message once; mass 'refused' + dock message", "sd.state === 'refused'" in js
          and "dockMsg(sd.msg, true)" in js and "mt = 'refused'" in js and "S.massRefusedShown" in js)

    # 2) the 5433 echo confirms within one console packet (no getparam)
    ctx, calls = make(lambda action, a: {"ok": True, "readback": 0.0} if action == "set" else {"ok": True, "values": []})
    s = ctx.session
    s.confirm_side("LEFT", "S95")
    s.readback.pop("side", None)              # no getparam readback at all
    n_ml = len(calls)
    ctx.training.send(side=0.0, weight_kg=0.0)
    t0 = time.time()
    chip = s.side_chip()
    check("echo side 0 = LEFT: confirmed at once", chip == {"text": "Side: LEFT", "state": "ok"} and time.time() - t0 < 0.1, chip)
    check("... and Motor unlocked by the echo", s.guard("motor") is None, s.guard("motor"))
    check("... without any MATLAB call", len(calls) == n_ml, calls[n_ml:])

    # 3) not reverted by a timeout / stale echo / failed getparam
    ctx.training.echo = {}                    # link stalled: echo stale
    s.readback.pop("side", None)
    check("echo stale, no readback: still 'Side: LEFT' (no '? CONFIRM FOOT')", s.side_chip()["state"] == "ok"
          and side_view(ctx)["chip"] != "? CONFIRM FOOT", (s.side_chip(), side_view(ctx)["chip"]))
    check("echo stale: Motor still allowed (verified this session, nothing against it)", s.guard("motor") is None)
    ctx.training.send(side=1.0)               # the device now reports RIGHT
    check("a different echo: mismatch", s.side_chip()["state"] == "bad" and s.guard("motor") is not None, s.side_chip())
    ctx.training.send(side=0.0)
    s.side_chip()
    ctx.training.echo = {}
    refuse = {"ok": False, "err": "No application is loaded on target computer."}
    ctx.matlab.call = lambda fn, action, *a, **k: json.dumps(refuse if action == "set" else {"ok": True, "values": []})
    s.after_connect_or_start("start")         # Start reloads the build default; the re-send is refused here
    check("after Start: the old verification is not kept (re-send refused -> 'refused', not 'Side: LEFT')",
          s.side_verified is None and s.side_chip()["state"] == "refused", s.side_chip())
    # Motor locked by the side (13:56: "red with a greyed out shade ... still greyed out"): it says why
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("Motor locked: aria-disabled (title + hover / press reach it), not disabled",
          "mb.setAttribute('aria-disabled', locked ? 'true' : 'false');" in js and "mb.disabled = false;" in js)
    check("Motor locked: reason foot side not set on the target (+ app elsewhere: press Stop -> Start)",
          "'foot side not set on the target'" in js and "' (app started by another MATLAB: press Stop → Start)'" in js
          and "'Motor locked: ' + why" in js)
    check("Motor locked: press / hover says it once in the dock, sends nothing",
          "dockMsg(S.motorLockWhy || 'Motor locked', true);" in js and "S.motorLockShown !== S.motorLockWhy" in js)
    # cloud harness nits (85e7cd4): instant pending chip, one short toast, amber held Mass
    check("side pick: chip pending client-side at once", "chip.textContent = name + ' · sending…'; chip.className = 'side-chip pending';" in js)
    check("side pick: one short toast ('Left foot saved; sent when connected')",
          "name + ' foot saved; ' + (when || 'sent later')" in js and "' foot saved for ' + ((S.state" not in js)
    check("Mass held: amber send-pending, non-error toast (mass_pending.patch)",
          "mass.classList.toggle('send-pending', held);" in js and "!ok && !held" in js)
    ty = open(os.path.join(APP, "pages", "teensy.py"), encoding="utf-8").read()
    check("Teensy: Last flash only in Build and flash (not in the Firmware card)",
          '("Last flash", "ty-lastflash")' not in ty and 'Output("ty-lastflash"' not in ty)
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
