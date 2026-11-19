"""Session setup + command guard, in process (no target, no UDP to the target).

Checks: Motor/Assist presses are blocked until the S-ID is set, the side is
confirmed, and the side read back (training UDP echo) matches; -1 = 'not set';
a mismatch shows the side warning; K is never blocked; nothing is sent while
target writes are disabled; export naming.
"""
import json
import os
import sys
import tempfile
import types

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
os.chdir(APP)

from commands import CommandState  # noqa: E402
from session import SessionSetup  # noqa: E402


def main():
    tmp = tempfile.mkdtemp(prefix="afo_sess_")
    echo = {}
    sent = []
    ctx = types.SimpleNamespace()
    ctx.app_dir = tmp
    ctx.cfg = {"paths": {"log_dir": tmp, "afo_root": tmp}, "session": {"target_writes_enabled": False}}
    ctx.runctl = types.SimpleNamespace(status={"connected": False, "app": "AFO_r1"})
    ctx.training = types.SimpleNamespace(latest=lambda max_age_s=1.0: dict(echo))
    ctx.jobs = types.SimpleNamespace(running=lambda k: None)
    ctx.commands = CommandState({}, os.path.join(tmp, "last.json"), lambda *a, **k: sent.append(a),
                                lambda *a, **k: None, lambda: dict(echo))
    ctx.commands.toggles.update({"motor": 0, "assist": 0, "k": 0})
    s = SessionSetup(ctx)
    ctx.commands.guard = s.guard
    r = {}
    r["1_no_sid"] = ctx.commands.press_toggle("motor")
    r["1_k_not_blocked"] = ctx.commands.press_toggle("k")
    r["2_set_sid_bad"] = s.set_sid("Caleb")
    r["2_set_sid"] = s.set_sid("s47")
    r["2_side_not_confirmed"] = ctx.commands.press_toggle("motor")
    r["3_confirm_wrong_sid"] = s.confirm_side("RIGHT", "S46")
    r["3_confirm"] = s.confirm_side("RIGHT", "S47")
    r["3_no_readback_yet"] = ctx.commands.press_toggle("motor")
    echo.update({"side": -1.0})
    s.refresh_readback()
    r["4_unset_chip"] = s.side_chip()
    r["4_unset_press"] = ctx.commands.press_toggle("assist")
    echo.update({"side": 0.0})
    s.refresh_readback()
    r["5_mismatch_chip"] = s.side_chip()
    r["5_mismatch_press"] = ctx.commands.press_toggle("motor")
    echo.update({"side": 1.0, "weight_kg": 55.0, "assist_mode": 3.0, "fixed_k_pct": 5.0})
    s.refresh_readback()
    r["6_match_chip"] = s.side_chip()
    n0 = len(sent)
    r["6_match_press"] = ctx.commands.press_toggle("motor")
    r["6_packets_sent"] = len(sent) - n0
    r["7_weight_entry_writes_disabled"] = s.enter_value("weight", 72.5)
    r["7_k_out_of_range"] = s.enter_value("k_percent", 12)
    r["7_mode_ilc_refused"] = s.enter_value("mode", 2)
    ctx.commands.toggles["motor"] = 1
    echo.pop("cmd_motor", None)
    r["8_mode_change_motor_on_needs_confirm"] = s.check_change("mode", 1)
    r["8_k_change_small_ok"] = s.check_change("k_percent", 6)
    s.values["k_percent"] = 5.0
    r["8_k_change_big_confirm"] = s.check_change("k_percent", 8)
    r["9_readback_sources"] = s.view()["rows"]
    print(json.dumps(r, indent=1, default=str))
    json.dump(r, open(os.path.join(APP, "test", "e2e", "session_guard_results.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
