"""Fake Speedgoat for demos/testing: sends 124-byte UDP packets
(31 x float32 LE, gait-like waveforms + noise) at ~330 Hz to localhost.

Usage:  python fake_speedgoat.py [seconds] [port]     (defaults: 3600, 5432)
Stop with Ctrl+C or by closing the window.
"""
import math, random, socket, struct, sys, time

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 3600.0
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 5432
DST = ("127.0.0.1", PORT)

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
t0 = time.perf_counter()
P = 1.14                      # stride period [s]
tau = 2 * math.pi
seq = 0
bell = lambda x, c, w: math.exp(-((x - c) ** 2) / (2 * w * w))

print(f"sending 31ch x float32 to {DST[0]}:{DST[1]} for {SECONDS:.0f} s ... Ctrl+C to stop")
try:
    while time.perf_counter() - t0 < SECONDS:
        t = time.perf_counter() - t0
        p = (t / P) % 1.0
        v = [0.0] * 31
        ang = -11 * math.sin(tau * p) + 5.5 * math.sin(2 * tau * p + 0.6)
        v[0] = ang                                  # ankle_angle
        v[1] = ang * 1.015                          # pot_raw
        v[2] = 4.2 * math.sin(tau * p + 0.5)        # torque_cmd
        stance = 1.0 if p < 0.62 else 0.0
        for i in range(8):                          # insole p1..p8
            v[3 + i] = stance * 200 * bell(p, 0.06 + i * 0.068, 0.075)
        v[11] = (v[3] + v[4] + v[5]) / 3            # heel_agg
        v[12] = (v[8] + v[9] + v[10]) / 3           # toe_agg
        v[13] = 2.8 * math.sin(tau * p * 0.5)       # imu yaw/pitch/roll
        v[14] = 7.5 * math.sin(tau * p + 0.3)
        v[15] = 4.2 * math.sin(tau * p + 1.4)
        v[16] = 1.8 * math.sin(tau * p)             # imu accel
        v[17] = 1.1 * math.sin(tau * p + 1.1)
        v[18] = 9.81 + 1.4 * math.sin(2 * tau * p)
        v[19] = 44 * math.cos(tau * p)              # imu gyro
        v[20] = 26 * math.cos(tau * p + 0.8)
        v[21] = 15 * math.cos(tau * p + 2)
        v[22] = 0 if p < 0.14 else 1 if p < 0.4 else 2 if p < 0.62 else 3   # gait_phase
        v[23] = 1.24                                # stride_vel
        v[24] = 1.31                                # stride_len
        v[25] = max(0.0, 9.5 * bell(p, 0.5, 0.085)) # assist_Uc
        v[26] = 1.0 if int(t) % 2 == 0 else 0.0     # sync_led
        v[27] = v[2] * 0.42                         # motor_current
        v[28] = -11 * math.cos(tau * p)             # motor_vel
        v[29] = 1.0                                 # ctrl_loop_dt
        v[30] = float(seq % 100000)                 # spare_31 (packet counter)
        for i in range(22):                         # sensor noise on analog channels
            v[i] += (random.random() - 0.5) * 0.4
        s.sendto(struct.pack("<31f", *v), DST)
        seq += 1
        time.sleep(0.003)
except KeyboardInterrupt:
    pass
