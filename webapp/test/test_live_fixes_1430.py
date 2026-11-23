"""Live fixes 14:26-14:35 (run 14), seconds, no browser, no target:
- echo only on 18 floats: the root constant BIF_mass_kg reads 0 by getparam while the echo
  says 80 -> the page shows 80 confirmed, no "Set mass" / "Mass (Bi-LSTM) differs" item;
- a press is confirmed within 300 ms of an echo that comes 20 ms after the packet; the page
  polls at 100 ms while something is sending and the toast turns to "... saved";
- Zero: a 1 -> 0 pulse on 5431 field 0 with motor / assist / k unchanged, refused with
  Assist on; dock button with the tooltip;
- Advanced: the UDP 5430 block hidden on AFO_r1; After Start checklist without marks;
- no "UDP only · N packets/s" text on the Live toolbar.

    python test/test_live_fixes_1430.py
"""
import json
import os
import sys
import tempfile
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import udp_settings as U  # noqa: E402
from test_run14_layout import Dev, make_session  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def echo_only():
    from status import top_status
    from test_round5 import Sup
    dev, calls = Dev(18), []
    dev.v.update(side=0.0, weight_kg=80.0, bif_mass_kg=80.0, settings_seq=3.0)
    ctx, s = make_session(dev, calls)
    dev.on = True
    time.sleep(0.3)
    s.values.update(weight=80.0, bif_mass=80.0, side=0)
    s.side_confirmed = {"sid": "S1", "side": 0, "at": time.time()}
    s._put("bif_mass", 0.0, "getparam")           # what getparam on the root constant returns on run 14
    s.refresh_echo()
    check("18 floats: BIF mass readback from the echo (col 17 = 80), not the getparam 0",
          s.readback.get("bif_mass") == 80.0 and s.readback_src.get("bif_mass") == "echo", (s.readback, s.readback_src))
    calls.clear()
    s.refresh_readback()
    reads = [c for c in calls if c[0] == "matlab"]
    check("18 floats: getparam only for the Advanced constants (never side / mass / BIF / mode / K / gyro)",
          (lambda reads: all(all(not any(x in pth for x in ("Left 0/Right 1", "Constant4", "Constant10", "weight", "BIF_mass", "Gyro_Cal"))
                                    for pth in (r[2][0] if len(r) > 2 and r[2] else [])) for r in reads))(reads), reads)
    ctx.live = Sup({"live_seen": True, "age_s": 0.05})
    dev_status = dev.status
    ctx.training.get_status = lambda: dict(dev_status(), packets_ok=100)
    st = top_status(ctx)
    keys = [i["key"] for i in st["issues"]]
    check("no 'Set mass' and no 'Mass (Bi-LSTM) differs' open item", "bif-mass" not in keys
          and not any(k.startswith("differs-bif_mass") or k.startswith("differs-weight") for k in keys), keys)
    ctx.settings_link.stop()


def confirm_speed():
    dev, calls = Dev(18), []
    dev.v.update(side=0.0, weight_kg=70.0, bif_mass_kg=70.0)
    ctx, s = make_session(dev, calls)
    real = dev.recv
    dev.recv = lambda data, addr: threading.Timer(0.02, real, args=(data, addr)).start()    # echo 20 ms later
    ctx.settings_link._sender = dev.recv
    dev.on = True
    time.sleep(0.3)
    t0 = time.time()
    s.enter_value("weight", 80.0)
    while time.time() - t0 < 1.5 and (s.status.get("weight") or {}).get("state") != "confirmed":
        time.sleep(0.005)
    dt = time.time() - t0
    check(f"mass confirmed {dt * 1000:.0f} ms after the press (echo after 20 ms; limit 300 ms)",
          (s.status.get("weight") or {}).get("state") == "confirmed" and dt < 0.3, (dt, s.status.get("weight")))
    check("float32 echo 80.0 matches the entered 80", dev.v["bif_mass_kg"] == 80.0)
    ctx.settings_link.stop()
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: polls every 100 ms while a value is sending; toast turns to '... saved'",
          "if (S.fastUntil && Date.now() < S.fastUntil) { poll(); } }, 100);" in js and "toast(e.label + ' saved', false)" in js
          and "expectConfirm(ck," in js and "expectConfirm('side'," in js)
    import pages.console_api as CA
    src = open(CA.__file__, encoding="utf-8").read()
    check("server: echo readbacks on every state poll (refresh_echo)", "ctx.session.refresh_echo()" in src)


def zero():
    from commands import CommandState
    sent = []
    rb = {"cmd_motor": 1.0, "cmd_assist": 0.0, "cmd_k": 1.0}
    tmp = tempfile.mkdtemp(prefix="afo_zero_")
    cs = CommandState({"udp": {}}, os.path.join(tmp, "last.json"),
                      lambda cfg, *v, force=False: sent.append((time.time(), v)), lambda *a, **k: None, lambda: dict(rb))
    r = cs.pulse("zero")
    time.sleep(0.4)
    # Andy 15:06 "they should all just be toggle": Zero is a latched toggle (test_dock_buttons.py)
    check("Zero: accepted with Assist off (toggle ON, no success text)", r["ok"] and r.get("state") == 1 and r["msg"] == "", r)
    check("Zero: one packet, field 0 = 1 (latched)", len(sent) == 1 and sent[0][1][0] == 1.0, sent)
    check("Zero: motor / assist / k unchanged (1, 0, 1)", all(p[1][1:4] == (1.0, 0.0, 1.0) for p in sent), sent)
    cs.pulse("zero")          # back off
    rb["cmd_assist"] = 1.0
    sent.clear()
    r = cs.pulse("zero")
    check("Zero: refused with Assist on, nothing sent", not r["ok"] and "Assist off" in r["msg"] and not sent, (r, sent))
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    da = open(os.path.join(APP, "assets", "afo_dock_actions.js"), encoding="utf-8").read()
    check("dock: Zero button with the tooltip, aria-disabled when Assist is on (afo_dock_actions.js)",
          'id="bZero" title="Zero: sets the current ankle angle and motor encoder position as zero (hold the ankle still in neutral, Assist off)"' in js
          and "var zLock = !zLit && assist !== 0;" in da and "b.setAttribute('aria-disabled', s.locked ? 'true' : 'false');" in da)


def page_static():
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("Advanced: UDP 5430 block hidden on AFO_r1", "nc.hidden = isBif;" in js and 'id="advNc"' in js)
    check("After Start checklist: no check marks (colour only)", "\\u2713" not in js and "\\u25CB" not in js and "✓" not in js)
    css = open(os.path.join(APP, "assets", "afo-ui.css"), encoding="utf-8").read()
    check("checklist: open items amber", "ul.pop-checklist li.todo { color: var(--caution);" in css)
    live = open(os.path.join(APP, "pages", "live.py"), encoding="utf-8").read()
    check("Live toolbar: no 'UDP only · packets/s' text", "liveSrc" not in live and "liveSrc" not in js)
    check("hover hold: no plot held on any page", "var HELD = [];" in open(os.path.join(APP, "assets", "hover_hold.js"), encoding="utf-8").read())


if __name__ == "__main__":
    try:
        import _lowprio  # noqa: F401
    except Exception:
        pass
    echo_only()
    confirm_speed()
    zero()
    page_static()
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
