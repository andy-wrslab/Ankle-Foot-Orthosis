"""AFO_r1 model profile test (no MATLAB, no target; localhost UDP test port 15433).

Replays console packets (5433 layout) with AFO_r1 values through the real
receiver process: side -1 then 0, 12-float and 15-float packets (cols 12-14 =
bif_valid, bif_cal_progress, bif_bias_ready). BIF_mass_kg has no 5433 column:
its getparam readback is faked (0 then 75). The Bi-LSTM state falls back to a
fake Signals stream when the packet has only 12 floats. Also checks the model
profile (paths, escaping, AFO vs AFO_r1 settings, mass validation).

    python test/test_r1_profile.py        exit 1 on any failure
"""
import json
import os
import socket
import struct
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
os.chdir(APP)

import model_profile as mp  # noqa: E402
import session as S  # noqa: E402
from status import top_status  # noqa: E402
from training_worker import load_layout  # noqa: E402
from workers import TrainingSupervisor  # noqa: E402
from test_round5 import Cmd, Jobs, RC, Sup  # noqa: E402

PORT = 15433
FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"))
    if not cond:
        FAILS.append(name)


class FakeMatlab:
    """Stands in for the MATLAB worker's Signals buffer ("latest" snapshot)."""
    def __init__(self):
        self.values = {}

    def snapshot(self, kind, *args, timeout=1.0):
        if kind != "latest":
            return None
        return {"values": {k: v for k, v in self.values.items() if k in args[0]}, "age_s": {}}


def make_ctx(training, rc_status, model_cfg="auto"):
    tmp = tempfile.mkdtemp(prefix="afo_r1_")
    ctx = type("Ctx", (), {})()
    ctx.app_dir = tmp
    ctx.cfg = {"paths": {"log_dir": tmp, "afo_root": tmp}, "session": {}, "target": {"model": model_cfg}}
    ctx.runctl = RC(rc_status)
    ctx.jobs = Jobs()
    ctx.live = Sup({"live_seen": True, "age_s": 0.05})
    ctx.training = training
    ctx.commands = Cmd()
    ctx.matlab = FakeMatlab()
    ctx.session = S.SessionSetup(ctx)
    return ctx


def profile_checks():
    m = S.DEFAULT_MODELS
    check("r1 side path escaped", m["AFO_r1"]["side"] == "AFO_r1/Left 0//Right 1|Value", m["AFO_r1"]["side"])
    check("r1 spring stiffness not an Advanced setting any more (Andy 15:03)", "spring" not in m["AFO_r1"])
    check("r1 torque P gain path", m["AFO_r1"]["p_gain"] == "AFO_r1/P|Value", m["AFO_r1"].get("p_gain"))
    check("r1 weight is Constant Value", m["AFO_r1"]["weight"] == "AFO_r1/weight|Value")
    check("r1 BIF mass path", m["AFO_r1"]["bif_mass"] == "AFO_r1/BIF_mass_kg|Value")
    check("AFO weight is Gain", m["AFO"]["weight"] == "AFO/weight|Gain")
    check("AFO has no BIF mass", "bif_mass" not in m["AFO"])
    sup = Sup({"packets_ok": 0, "age_s": None})
    # config decides while not connected; the loaded app wins when known
    check("cfg auto -> AFO", make_ctx(sup, {"connected": False}).session.model() == "AFO")
    check("cfg AFO_r1 while not connected", make_ctx(sup, {"connected": False}, "AFO_r1").session.model() == "AFO_r1")
    check("loaded AFO beats cfg AFO_r1",
          make_ctx(sup, {"connected": True, "app": "AFO"}, "AFO_r1").session.model() == "AFO")
    c = make_ctx(sup, {"connected": False}, "AFO_r1")
    c.session.set_sid("S91")
    check("BIF mass 20 rejected", "more than 20" in c.session.enter_value("bif_mass", 20), c.session.enter_value("bif_mass", 20))
    check("BIF mass 20.5 accepted", "saved" in c.session.enter_value("bif_mass", 20.5))
    c2 = make_ctx(sup, {"connected": False}, "AFO")
    c2.session.set_sid("S91")
    check("BIF mass refused in AFO", "not in model AFO" in c2.session.enter_value("bif_mass", 75))
    check("AFO profile has no checklist", c2.session.checklist() is None and c2.session.bif_view() is None)
    keys = [sp["key"] for sp in c.session.specs()]
    check("r1 settings include both masses", "weight" in keys and "bif_mass" in keys, keys)
    check("r1: body mass 20 rejected", "more than 20" in c.session.enter_value("weight", 20))
    msg = c.session.enter_value("weight", 72)
    check("r1: body mass sets the Bi-LSTM mass too", c.session.values.get("weight") == 72
          and c.session.values.get("bif_mass") == 72, (msg, c.session.values))
    check("AFO: body mass does not touch bif_mass", "bif_mass" not in c2.session.values
          and "saved" in c2.session.enter_value("weight", 72), c2.session.values)


def replay_checks():
    lay, names = load_layout(os.path.join(APP, "config", "console_udp_layout.json"))
    check("layout is 12 floats", lay["format"] == "<12f" and len(names) == 12, lay["format"])
    lay["port"] = PORT
    tmpd = tempfile.mkdtemp(prefix="afo_r1_console_")
    lp = os.path.join(tmpd, "layout.json")
    json.dump(lay, open(lp, "w"))
    sup = TrainingSupervisor({"training": {"enabled": True, "listen_host": "127.0.0.1", "layout": lp}}, APP, tmpd)
    sup.start()
    time.sleep(3)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    f12, f15 = struct.Struct("<12f"), struct.Struct("<15f")
    t = [200.0]

    # A background sender keeps the current row going at 100 Hz between bursts, so the
    # console echo stays fresh (< 0.5 s) while the checks run (the old version stopped
    # sending and slept 0.6 s, which made the echo checks flaky).
    import threading
    cur = {"kw": None, "tail": None}
    lock = threading.Lock()
    halt = threading.Event()

    def keep():
        while not halt.is_set():
            with lock:
                kw, tail = cur["kw"], cur["tail"]
                if kw is not None:
                    t[0] = round(t[0] + 0.01, 4)
                    r = dict(t_model=t[0], side=-1.0, weight_kg=55.0, assist_mode=3.0, fixed_k_pct=5.0, cmd_motor=0.0,
                             cmd_assist=0.0, cmd_k=0.0, cmd_calibrate_pressure=0.0, cmd_reset_sv=0.0, imu_ok=1.0,
                             imu_bad_count=0.0)
                    r.update(kw)
                    vals = [r[nm] for nm in names]
                    s.sendto(f15.pack(*vals, *tail) if tail else f12.pack(*vals), ("127.0.0.1", PORT))
            time.sleep(0.01)
    threading.Thread(target=keep, daemon=True).start()

    def burst(n=60, tail=None, **kw):
        with lock:
            cur["kw"], cur["tail"] = dict(kw), tail
        time.sleep(n * 0.01 + 0.6)       # n packets of the new row, then a heartbeat

    run = {"connected": True, "running": True, "app": "AFO_r1"}
    ctx = make_ctx(sup, run)
    sess = ctx.session
    sess.set_sid("S92")
    sess.values.update(side=0, weight=72.5, bif_mass=75, mode=3, k_percent=5)
    sess.side_confirmed = {"sid": "S92", "side": 0, "at": time.time()}

    # 1) after Start: side -1 (built), 12-float packets, BIF mass reads back 0
    burst(side=-1.0)
    sess.refresh_readback()
    sess._put("bif_mass", 0.0, "getparam")
    chip = sess.side_chip()
    check("side -1 -> unset chip", chip == {"text": "Foot side unset, motor locked until set", "state": "unset"}, chip)
    check("side -1 blocks Motor", "motor locked" in (sess.guard("motor") or ""), sess.guard("motor"))
    st = top_status(ctx)
    check("status: confirm foot side + set mass", {"confirm-side", "bif-mass"} <= {i["key"] for i in st["issues"]},
          [i["key"] for i in st["issues"]])
    check("console stream required for AFO_r1", st["streams"]["console_required"] is True)
    bif = sess.bif_view()
    check("12 floats, no Signals -> unknown", bif["phase"] == "unknown" and bif["source"] is None, bif)
    chk = sess.checklist()
    check("checklist: nothing done", [i["done"] for i in chk["items"]] == [False, False, None, None], chk["items"])
    stw = sup.get_status()
    check("12-float packets counted", stw.get("columns") == 12 and stw.get("bad_length") == 0, stw)

    # 2) Signals fallback (still 12 floats): bias not ready, then the walk at 40 %
    ctx.matlab.values = {"bif_bias_ready": 0.0, "bif_valid": 0.0, "bif_dbg(1)": 0.0, "bif_dbg(8)": 0.0}
    bif = sess.bif_view()
    check("signals: hold still (IMU not ready)", bif["text"] == "Bi-LSTM: hold still 5 s… (IMU not ready yet)"
          and bif["source"] == "signals", bif)
    ctx.matlab.values = {"bif_bias_ready": 1.0, "bif_valid": 0.0, "bif_dbg(1)": 1.0, "bif_dbg(8)": 0.4}
    bif = sess.bif_view()
    check("signals: calibration walk 40 %", bif["text"] == "Bi-LSTM: IMU ready · calibration walk 40 %" and
          bif["state_text"] == "calibrating", bif)

    # 3) side set to 0 (echo), BIF mass reads back 75
    burst(side=0.0)
    sess.refresh_readback()
    sess._put("bif_mass", 75.0, "getparam")
    check("side 0 -> ok chip", sess.side_chip()["state"] == "ok", sess.side_chip())
    check("side readback from echo", sess.readback_src.get("side") == "echo" and sess.readback.get("side") == 0.0)
    st = top_status(ctx)
    keys = {i["key"] for i in st["issues"]}
    check("status: no side / mass issue", not ({"confirm-side", "bif-mass", "differs-bif_mass"} & keys), keys)
    chk = sess.checklist()
    check("checklist: side + mass done, walk 40 %",
          [i["done"] for i in chk["items"]] == [True, True, True, False] and chk["items"][3]["detail"] == "40 %",
          chk["items"])
    tbl = {r["name"]: r for r in sess.target_table()}
    check("table: weight from echo, BIF mass from getparam",
          tbl["weight"]["source"] == "echo" and tbl["bif_mass"]["source"] == "getparam" and tbl["bif_mass"]["match"] is True,
          {k: (tbl[k]["source"], tbl[k]["match"]) for k in ("weight", "bif_mass")})

    # 4) 15-float packets: console columns win over Signals
    ctx.matlab.values = {"bif_bias_ready": 0.0, "bif_valid": 0.0}
    burst(side=0.0, tail=(0.0, 0.0, 0.0))
    bif = sess.bif_view()
    check("15 floats: hold still (console)", bif["phase"] == "bias" and bif["source"] == "console", bif)
    burst(side=0.0, tail=(0.0, 0.65, 1.0))
    bif = sess.bif_view()
    check("15 floats: calibration walk 65 %", bif["text"] == "Bi-LSTM: IMU ready · calibration walk 65 %", bif)
    burst(side=0.0, tail=(1.0, 1.0, 1.0))
    bif = sess.bif_view()
    check("15 floats: valid", bif["text"] == "Bi-LSTM: valid", bif)
    check("checklist all done", sess.checklist()["all_done"] is True, sess.checklist())
    stw = sup.get_status()
    check("15-float packets counted", stw.get("columns") == 15 and stw.get("packets_ext", 0) >= 180
          and stw.get("bad_length") == 0, {k: stw.get(k) for k in ("columns", "packets_ext", "bad_length")})
    check("history keeps the tail", "bif_cal_progress" in (sup.data(["bif_cal_progress"], 5.0) or {}).get("series", {}))

    # 5) back to 12 floats: tail gone from latest, Signals fallback again
    ctx.matlab.values = {"bif_bias_ready": 1.0, "bif_valid": 1.0}
    burst(side=0.0)
    lat = sup.latest(max_age_s=1.0)
    check("12 floats again: no tail in latest", "bif_valid" not in lat, sorted(lat))
    check("12 floats again: Signals source", sess.bif_view()["source"] == "signals")
    # 6) wrong length still rejected
    s.sendto(b"\x00" * 52, ("127.0.0.1", PORT))
    time.sleep(0.8)
    check("52-byte packet rejected", sup.get_status().get("bad_length") == 1, sup.get_status().get("bad_length"))
    halt.set()
    time.sleep(0.05)
    sup.shutdown()


def main():
    profile_checks()
    replay_checks()
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
