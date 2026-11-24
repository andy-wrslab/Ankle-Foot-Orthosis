"""Fake Speedgoat streams for developing/testing the UI (localhost only).

    python test/replay_senders.py [bus_port=15432] [console_port=15433] [seconds=0] [--side N] [--stop-console-after S]

* Main bus (31 x float32, 1024 Hz) to 127.0.0.1:<bus_port>: walking-like data,
  ~1.1 s strides: torque profile (measured follows command), SV stepping once
  per stride around a 1.1 m/s target, Uc toggling every few strides, assistance
  level adapting, FSR heel->toe roll, IMU accel, statusword 0x0637.
* Console packet ('<12f', 100 Hz) to 127.0.0.1:<console_port>: side (default
  0 = LEFT), weight 55, mode 3 (fixed K), K 5 %, commands motor/assist/k = 0/0/1 (cmds= overrides).
Never sends to the Speedgoat or to any control port.
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _lowprio  # noqa: E402,F401  (below normal priority)
import json
import math
import os
import socket
import struct
import sys
import threading
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def arg(i, default):
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    try:
        return float(pos[i])
    except (IndexError, ValueError):
        return default


def opt(name, default):
    if name in sys.argv:
        return float(sys.argv[sys.argv.index(name) + 1])
    return default


def bus(port, dur, stop):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    t0, k = time.perf_counter(), 0
    stride, level, sv = 0, 4.0, 1.05
    while not stop.is_set() and (dur <= 0 or time.perf_counter() - t0 < dur):
        while time.perf_counter() - t0 < k / 1024.0:
            time.sleep(0.0005)
        t = 20.0 + k / 1024.0
        ph = (t % 1.1) / 1.1
        if k and (k % 1126) == 0:          # new stride
            stride += 1
            sv = 1.1 + 0.12 * math.sin(stride / 6.0) + 0.03 * math.sin(stride * 1.7)
            level = min(10.0, max(0.0, level + (0.5 if (stride // 7) % 2 else -0.4)))
        uc = 1.0 if (stride // 5) % 2 else 0.0
        prof = max(0.0, math.sin((ph - 0.35) / 0.3 * math.pi)) if 0.35 < ph < 0.65 else 0.0
        cmd = 1.2 * level * prof
        r = [0.0] * 31
        r[0] = t
        r[1] = sv
        r[2] = 12.0 * math.sin(2 * math.pi * ph)
        heel = max(0.0, math.sin(min(1.0, ph / 0.6) * math.pi)) if ph < 0.6 else 0.0
        for i in range(8):
            d = i / 7.0
            r[3 + i] = 900.0 * max(0.0, math.sin(min(1.0, max(0.0, (ph - 0.05 * i) / 0.55)) * math.pi)) * (0.5 + 0.5 * d) if ph < 0.65 else 3.0
        r[11] = 0.2 * math.sin(2 * math.pi * ph * 2)
        r[12] = 0.1 * math.cos(2 * math.pi * ph)
        r[13] = 1.0 + 0.3 * math.sin(2 * math.pi * ph)
        r[23] = 1.1
        r[24] = uc
        r[25] = 0.93 * cmd + 0.15 * math.sin(t * 40)
        r[26] = 1.0 if ph < 0.02 else 0.0
        r[27] = level
        r[28] = cmd
        r[29] = 0x0637
        r[30] = float(k % 1000)
        _ = heel
        s.sendto(struct.pack("<31f", *r), ("127.0.0.1", port))
        k += 1


# every column of the newest layout (run 16, '<44f') has a value: a device that is set up
# (Bi-LSTM ready, mass set, Advanced / guard at their build values, no slack / jam)
CONSOLE_DEFAULTS = dict(bif_valid=1.0, bif_cal_progress=1.0, bif_bias_ready=1.0, gyro_cal_request=0.0, settings_seq=1.0,
                        bif_mass_kg=55.0, sv_target_min=0.8, sv_target_max=1.5, target_step_up=0.04,
                        target_step_down=0.08, step_up_window=20.0, step_down_window=10.0, high_assist_level=9.0,
                        high_assist_strides=10.0, torque_p_gain=0.45, torque_i_gain=0.55, standing_still_cutoff=200.0,
                        adv_seq=1.0, spring_stiffness=1.25, slack_flag=0.0, jam_flag=0.0, slack_count=0.0,
                        slack_last_stride=0.0, slack_floor_on=1.0, slack_thr_nm=-0.5, slack_ms=20.0, slack_floor_nm=0.5,
                        jam_cut_on=1.0, jam_apnm=7.5, jam_ms=150.0, fb_filter=0.0, guard_seq=1.0)


def console(port, dur, stop, side, stop_after, cmds=None, layout=None):
    lay = json.load(open(layout or os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    names = [c.get("name", c.get("n")) for c in sorted(lay["columns"], key=lambda c: c.get("column", c.get("i")))]
    fmt = struct.Struct(lay["format"])
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    t0, k = time.perf_counter(), 0
    while not stop.is_set() and (dur <= 0 or time.perf_counter() - t0 < dur):
        if stop_after and time.perf_counter() - t0 > stop_after:
            time.sleep(0.1)
            continue
        while time.perf_counter() - t0 < k / 100.0:
            time.sleep(0.001)
        v = dict(t_model=20.0 + k / 100.0, side=side, weight_kg=55.0, assist_mode=3.0, fixed_k_pct=5.0,
                 cmd_motor=0.0, cmd_assist=0.0, cmd_k=1.0, cmd_calibrate_pressure=0.0, cmd_reset_sv=0.0,
                 imu_ok=1.0, imu_bad_count=0.0)
        v.update(cmds or {})
        s.sendto(fmt.pack(*[v.get(n, CONSOLE_DEFAULTS.get(n, 0.0)) for n in names]), ("127.0.0.1", port))
        k += 1


def start(bus_port=15432, console_port=15433, dur=0.0, side=0.0, stop_console_after=0.0, cmds=None, layout=None):
    stop = threading.Event()
    threading.Thread(target=bus, args=(int(bus_port), dur, stop), daemon=True).start()
    if console_port:
        threading.Thread(target=console, args=(int(console_port), dur, stop, side, stop_console_after, cmds, layout),
                         daemon=True).start()
    return stop


if __name__ == "__main__":
    st = start(arg(0, 15432), arg(1, 15433), arg(2, 0.0), opt("--side", 0.0), opt("--stop-console-after", 0.0))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        st.set()
