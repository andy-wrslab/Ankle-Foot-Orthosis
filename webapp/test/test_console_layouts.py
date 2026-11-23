"""Console packet (UDP 5433) parser with both layout files x both packet sizes
(localhost test port 15433 only; no target).

Layout 12: test/fixtures/run12_console_udp_layout.json (pinned; config/ is now 31 floats) ('<12f'). Layout 15: the same plus
bif_valid (12), bif_cal_progress (13), bif_bias_ready (14) as written by the
Simulink make step ('<15f'). With either layout a 48-byte (12-float) packet and a
60-byte (15-float) packet must both parse; the Bi-LSTM values appear in "latest"
only from 15-float packets; any other length is rejected.

    python test/test_console_layouts.py
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
import _lowprio  # noqa: E402,F401
from workers import TrainingSupervisor  # noqa: E402
from training_worker import load_layout  # noqa: E402

PORT = 15433
FAILS = []
TAIL = ["bif_valid", "bif_cal_progress", "bif_bias_ready"]


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def run(label, lay):
    tmpd = tempfile.mkdtemp(prefix="afo_layouts_")
    lp = os.path.join(tmpd, "layout.json")
    lay = dict(lay, port=PORT)
    json.dump(lay, open(lp, "w"))
    sup = TrainingSupervisor({"training": {"enabled": True, "listen_host": "127.0.0.1", "layout": lp}}, APP, tmpd)
    sup.start()
    time.sleep(3)
    base = json.load(open(os.path.join(APP, "test", "fixtures", "run12_console_udp_layout.json"), encoding="utf-8"))
    names = [c.get("name", c.get("n")) for c in sorted(base["columns"], key=lambda c: c.get("column", c.get("i")))]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    t = [10.0]

    def send(n, tail=None, k=40):
        for _ in range(k):
            t[0] = round(t[0] + 0.01, 4)
            r = dict(t_model=t[0], side=0.0, weight_kg=80.0, assist_mode=3.0, fixed_k_pct=5.0, cmd_motor=0.0,
                     cmd_assist=0.0, cmd_k=0.0, cmd_calibrate_pressure=0.0, cmd_reset_sv=0.0, imu_ok=1.0,
                     imu_bad_count=0.0)
            vals = [r[nm] for nm in names]
            if n == 15:
                vals += list(tail)
            s.sendto(struct.pack(f"<{n}f", *vals), ("127.0.0.1", PORT))
            time.sleep(0.01)
        time.sleep(0.4)

    send(12)
    st = sup.get_status()
    lat = sup.latest(max_age_s=1.0)
    check(f"{label}: 12-float packets parse", st.get("columns") == 12 and st.get("bad_length") == 0
          and lat.get("weight_kg") == 80.0, {k: st.get(k) for k in ("columns", "bad_length", "packets_ok")})
    check(f"{label}: no Bi-LSTM values from 12 floats", not any(k in lat for k in TAIL), sorted(lat))
    send(15, (1.0, 0.5, 1.0))
    st = sup.get_status()
    lat = sup.latest(max_age_s=1.0)
    check(f"{label}: 15-float packets parse", st.get("columns") == 15 and st.get("bad_length") == 0,
          {k: st.get(k) for k in ("columns", "bad_length", "packets_ext")})
    check(f"{label}: Bi-LSTM values from 15 floats", lat.get("bif_valid") == 1.0 and lat.get("bif_cal_progress") == 0.5
          and lat.get("bif_bias_ready") == 1.0, {k: lat.get(k) for k in TAIL})
    s.sendto(b"\x00" * 52, ("127.0.0.1", PORT))
    time.sleep(0.8)
    check(f"{label}: 52-byte packet rejected", sup.get_status().get("bad_length") == 1, sup.get_status().get("bad_length"))
    sup.shutdown()
    time.sleep(1.0)


def main():
    lay12, names = load_layout(os.path.join(APP, "test", "fixtures", "run12_console_udp_layout.json"))
    check("layout 12 file is '<12f'", lay12["format"] == "<12f" and len(names) == 12, lay12["format"])
    lay15 = json.loads(json.dumps(lay12))
    lay15["format"] = "<15f"
    lay15["columns"] = lay15["columns"] + [{"name": n, "column": 12 + i, "unit": "", "description": "Bi-LSTM"}
                                           for i, n in enumerate(TAIL)]
    run("layout 12", lay12)
    run("layout 15", lay15)
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
