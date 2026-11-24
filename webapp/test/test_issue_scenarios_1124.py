"""Today's issues replayed offline (Andy Nov 24: "make sure it works ... under the cases of
issues we said"). In-process fake device only; nothing is sent to the Speedgoat.

1. 14:29 "why mass showed not set": page restarted (80 kg left in the box, not entered this
   page session), device reloaded by a Stop -> Start (mass 0): the page does not send the
   leftover 80 and shows "Mass not set".
2. 14:33 "i literally entered and clicked enter": Enter on the unchanged 80 now commits
   (browser rule) and the server sends it: device mass 80, confirmed by the echo.
3. The next Stop -> Start (device reloads mass 0 / side -1): the page re-sends the mass entered
   in 2 and the side confirmed this session, in one packet.
4. 14:34 Advanced: an edit is not sent on Enter; Confirm sends it (static + see
   test_adv_confirm_e2e for the device round trip).
5. 14:50 the blanket test run that stopped / started the real target: the live run-control
   test now skips without AFO_LIVE_TARGET_OK=1.

    python test/test_issue_scenarios_1124.py
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import _lowprio  # noqa: E402,F401  (below normal priority)

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def wait(cond, t=2.0):
    t0 = time.time()
    while time.time() - t0 < t and not cond():
        time.sleep(0.02)
    return cond()


def mass_and_side():
    import session as S
    import udp_settings as U
    from test_run14_layout import Dev, fresh_session
    dev, calls = Dev(18), []
    ctx, s = fresh_session(dev, calls)
    s.set_sid("S5")
    s.values["weight"] = 80.0                  # the leftover box value after a page restart (not entered)
    dev.v.update(side=0.0)                      # device: Left, mass 0 (a reload)
    dev.on = True
    time.sleep(0.4)
    s.confirm_side("LEFT", "S5")                # Andy confirmed Left this page session (14:27:51)
    wait(lambda: dev.v["side"] == 0.0)
    # (1) Stop -> Start: device reloads (side -1, mass 0); the leftover 80 is not sent
    dev.v.update(side=-1.0, weight_kg=0.0, bif_mass_kg=0.0)
    n0 = len(dev.packets)
    s.after_connect_or_start("start")
    time.sleep(0.8)
    pk = dev.packets[n0] if len(dev.packets) > n0 else None
    check("1. Start after a page restart: leftover 80 kg NOT sent (packet mass 0 = keep)", pk is not None and pk[4] == 0.0, dev.packets[n0:])
    check("1. ... side Left re-sent (confirmed this session)", pk is not None and pk[3] == 0.0 and dev.v["side"] == 0.0, pk)
    check("1. ... page shows 'Mass not set' (the amber tag Andy saw)", (s.status.get("weight") or {}).get("msg") == S.MASS_NOT_SET,
          s.status.get("weight"))
    # (2) Enter on the unchanged 80: the browser now posts it; the server sends it
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("2. browser: Enter commits even when the number is unchanged",
          "if (e.key === 'Enter') { el._enter = true; el.blur(); }" in js and "var send = el._enter || el._typed || el.value !== start;" in js)
    n0 = len(dev.packets)
    s.enter_value("weight", "80")
    check("2. server: unchanged 80 -> one 5434 packet with mass 80", wait(lambda: len(dev.packets) > n0) and dev.packets[n0][4] == 80.0,
          dev.packets[n0:])
    check("2. device mass 80 (weight and Bi-LSTM mass)", wait(lambda: dev.v["bif_mass_kg"] == 80.0) and dev.v["weight_kg"] == 80.0, dev.v)
    check("2. confirmed by the echo (tag clears)", wait(lambda: (s.status.get("weight") or {}).get("state") == "confirmed"),
          s.status.get("weight"))
    # (3) the next Stop -> Start: mass (entered) and side (confirmed) re-sent together
    dev.v.update(side=-1.0, weight_kg=0.0, bif_mass_kg=0.0)
    n0 = len(dev.packets)
    s.after_connect_or_start("start")
    time.sleep(0.8)
    pk = dev.packets[n0] if len(dev.packets) > n0 else None
    check("3. next Start: ONE packet with mass 80 and side Left", pk is not None and pk[4] == 80.0 and pk[3] == 0.0, dev.packets[n0:])
    check("3. device back to mass 80 / Left", dev.v["bif_mass_kg"] == 80.0 and dev.v["side"] == 0.0, dev.v)
    check("3. no 'Mass not set' after that Start", (s.status.get("weight") or {}).get("msg") != S.MASS_NOT_SET, s.status.get("weight"))
    ctx.settings_link.stop()


def advanced_static():
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    seg = js.split("document.querySelectorAll('.guard-in').forEach(function (inp) {\n            var f = inp.getAttribute('data-g');\n            onCommit(")[1]
    seg = seg.split("$('advOk').addEventListener")[0]
    check("4. Advanced Enter: staged only, no POST", "post(" not in seg and seg.count("stageAdv(inp, '") == 2)
    check("4. Confirm: the one POST to /api/console/advanced",
          js.split("$('advOk').addEventListener('click', function () {")[1].split("$('advCancel')")[0].count("post(") == 1)


def live_test_guard():
    env = {k: v for k, v in os.environ.items() if k != "AFO_LIVE_TARGET_OK"}
    p = subprocess.run([sys.executable, os.path.join(HERE, "test_runcontrol_live.py")], env=env, capture_output=True,
                       text=True, timeout=60)
    check("5. live run-control test skips without AFO_LIVE_TARGET_OK=1 (never touches the target)",
          p.returncode == 0 and p.stdout.startswith("SKIP:") and "afo_rc" not in p.stdout, (p.returncode, p.stdout[:200], p.stderr[:200]))


mass_and_side()
advanced_static()
live_test_guard()
print("\nFAILS:", FAILS)
sys.exit(1 if FAILS else 0)
