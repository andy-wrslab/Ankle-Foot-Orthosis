"""Continuous fake training stream (layout v1) for developing/testing the Training tab.

    python training_replay_sender.py [port=15433] [seconds=0 (forever)] [--faults]

Sends 100 Hz packets built from config/training_udp_layout.json to 127.0.0.1:<port>
(never to the Speedgoat): plausible walking signals (sv around the target band,
assistance adapting stride by stride, Uc toggling, torque profile per stride),
side/weight/mode/K% and the command echo. --faults adds a bad-length packet, a
wrong-version packet, a NaN and a counter gap every 10 s.
Point the app at it with training.layout set to a copy whose "port" is <port>.
"""
import json
import math
import os
import socket
import struct
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 15433
    dur = float(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].replace(".", "").isdigit() else 0.0
    faults = "--faults" in sys.argv
    lay = json.load(open(os.path.join(APP, "config", "training_udp_layout.json")))
    names = [c["n"] for c in lay["columns"]]
    fmt = struct.Struct(lay["format"])
    idx = {n: i for i, n in enumerate(names)}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    t0 = time.perf_counter()
    k = 0
    counter = 0
    level = 4.0
    stride = 0
    while dur <= 0 or time.perf_counter() - t0 < dur:
        while time.perf_counter() - t0 < k / 100.0:
            time.sleep(0.001)
        t = k / 100.0
        r = [0.0] * len(names)
        phase = (t % 1.1) / 1.1                    # ~1.1 s strides
        if phase < 0.01 and k:
            stride += 1
            level = min(10.0, max(0.0, level + (0.5 if (stride // 7) % 2 else -0.4)))
        sv = 1.15 + 0.12 * math.sin(t / 9.0) + 0.02 * math.sin(t * 3.1)
        r[idx["t_model"]] = t
        r[idx["layout_version"]] = lay["layout_version"]
        r[idx["packet_counter"]] = counter
        r[idx["sv_target"]] = 1.1
        r[idx["sv_target_adaptive"]] = 1.1 + 0.05 * math.sin(t / 30.0)
        r[idx["sv"]] = sv
        r[idx["sv_mean"]] = 1.15
        r[idx["sv_median"]] = 1.14
        r[idx["sv_error"]] = sv - 1.1
        r[idx["stride_length"]] = 1.3
        r[idx["stride_idx"]] = stride
        r[idx["p_sum"]] = 800 * max(0.0, math.sin(phase * math.pi * 1.6))
        r[idx["uc"]] = 1.0 if (stride // 5) % 2 else 0.0
        r[idx["uc_all_one"]] = r[idx["uc"]]
        r[idx["uc_non_one"]] = 1 - r[idx["uc"]]
        r[idx["rl_assistance"]] = level + 0.3 * math.sin(t / 4.0)
        r[idx["assistance_level"]] = level
        prof = max(0.0, math.sin((phase - 0.35) / 0.3 * math.pi)) if 0.35 < phase < 0.65 else 0.0
        r[idx["desired_torque"]] = 0.75 * level * prof
        r[idx["torque_command"]] = r[idx["desired_torque"]]
        r[idx["torque_actual"]] = 0.95 * r[idx["desired_torque"]]
        r[idx["statusword"]] = 0x0637
        r[idx["drive_enabled"]] = 1
        r[idx["is_alive"]] = 1
        r[idx["imu_ok"]] = 1
        r[idx["side"]] = 1
        r[idx["weight_kg"]] = 72.5
        r[idx["assist_mode"]] = 1
        r[idx["fixed_k_pct"]] = 5
        r[idx["cmd_motor"]] = 1
        r[idx["cmd_assist"]] = 1
        r[idx["cmd_k"]] = 1
        for p, v in (("param_epsilon_up", 0.05), ("param_epsilon_down", 0.05), ("param_step_up", 0.05),
                     ("param_step_down", 0.05), ("param_v_min", 0.5)):
            r[idx[p]] = v
        if faults and k % 1000 == 500:
            s.sendto(b"\x00" * 77, ("127.0.0.1", port))
            bad = list(r); bad[1] = 99.0
            s.sendto(fmt.pack(*bad), ("127.0.0.1", port))
            r[idx["sv"]] = float("nan")
            counter += 3
        s.sendto(fmt.pack(*r), ("127.0.0.1", port))
        counter = (counter + 1) % (1 << 24)
        k += 1


if __name__ == "__main__":
    main()
