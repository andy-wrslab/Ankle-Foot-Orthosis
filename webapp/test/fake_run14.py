"""Fake run-14 target for the UDP settings (test ports only, never 192.168.7.5).

Listens on 127.0.0.1:<settings_port> (test: 15434) for '<8f' packets
    magic 4134, version 1, seq, side, body_mass_kg, assist_mode, fixed_k_pct, gyro_cal_request
and behaves like the model: a wrong magic / version is ignored; per field an invalid value
keeps the last value; values are held. start() (= Start) resets side -1 and mass 0 until
the next valid packet. Echo at 100 Hz to 127.0.0.1:<console_port> (test: 15433), '<18f':
the 12 base console columns + bif_valid, bif_cal_progress, bif_bias_ready +
gyro_cal_request, last accepted seq, bif_mass_kg. stall(s) stops the echo for s seconds;
n_floats=15 sends the run-13 packet instead (no settings columns, 5434 ignored).
n_floats=44 is run 16: + col 31 slack_flag, 32 jam_flag, 33 slack_count, 34 slack_last_stride,
35-42 the guard settings in use, 43 guard_seq (guard_port: the 5436 receiver).
n_floats=31 is run 15: + cols 18-28 the 11 Advanced values in use (order of
round1/settings_adv_udp_layout.json), 29 adv_seq, 30 spring_stiffness (self.adv / adv_seq / spring).
"""
import socket
import struct
import threading
import time

BASE = ["t_model", "side", "weight_kg", "assist_mode", "fixed_k_pct", "cmd_motor", "cmd_assist", "cmd_k",
        "cmd_calibrate_pressure", "cmd_reset_sv", "imu_ok", "imu_bad_count",
        "bif_valid", "bif_cal_progress", "bif_bias_ready", "gyro_cal_request", "settings_seq", "bif_mass_kg"]
ADV_FIELDS = ["sv_target_min", "sv_target_max", "target_step_up", "target_step_down", "step_up_window",
              "step_down_window", "high_assist_level", "high_assist_strides", "torque_p_gain", "torque_i_gain",
              "standing_still_cutoff"]
ADV_DEFAULTS = [0.8, 1.5, 0.04, 0.08, 20.0, 10.0, 9.0, 10.0, 0.45, 0.55, 200.0]     # P 0.45 / I 0.55 (Andy Nov 24)
# run 16: torque guard (5436) settings in use, cols 35-42, defaults per settings_guard_udp_layout.json
GUARD_FIELDS = ["slack_floor_on", "slack_thr_nm", "slack_ms", "slack_floor_nm", "jam_cut_on", "jam_apnm", "jam_ms",
                "fb_filter"]
GUARD_DEFAULTS = [1.0, -0.5, 20.0, 0.5, 1.0, 7.5, 150.0, 0.0]     # jam on, 7.5 A/(N·m), 150 ms (Andy Nov 24)
GUARD_RULES = {"slack_floor_on": (0, 1, True), "slack_thr_nm": (-5, -0.05, False), "slack_ms": (1, 500, True),
               "slack_floor_nm": (0, 3, False), "jam_cut_on": (0, 1, True), "jam_apnm": (1, 50, False),
               "jam_ms": (10, 2000, True), "fb_filter": (0, 1, True)}


class FakeRun14:
    def __init__(self, settings_port=15434, console_port=15433, n_floats=18, side=-1.0, mass=0.0, mode=3.0, k=5.0,
                 gyro=0.0, motor=0.0, assist=0.0, kk=1.0, seq=0.0, adv_port=None, guard_port=None):
        self.addr = ("127.0.0.1", int(settings_port))
        self.console = ("127.0.0.1", int(console_port))
        self.n = n_floats
        self.v = {"side": side, "mass": mass, "mode": mode, "k": k, "gyro": gyro, "seq": seq,
                  "motor": motor, "assist": assist, "kk": kk}
        self.adv = dict(zip(ADV_FIELDS, ADV_DEFAULTS))     # run 15: Advanced values in use
        self.adv_seq = 0.0
        self.spring = 1.25                                 # read-only, echoed as col 30
        self.guard = dict(zip(GUARD_FIELDS, GUARD_DEFAULTS))    # run 16
        self.guard_seq = 0.0
        self.flags = {"slack_flag": 0.0, "jam_flag": 0.0, "slack_count": 0.0, "slack_last_stride": 0.0}
        self.guard_received = []
        self.received = []        # (time, tuple) of every packet that arrived
        self.accepted = 0
        self.ignored = 0
        self.gyro_changes = 0
        self._stall_until = 0.0
        self._stop = threading.Event()
        self.lock = threading.Lock()
        self.rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx.bind(self.addr)
        self.rx.settimeout(0.1)
        self.tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.t0 = time.time()
        threading.Thread(target=self._rx_loop, daemon=True).start()
        threading.Thread(target=self._tx_loop, daemon=True).start()
        self.adv_received = []
        self.adv_rx = None
        self.guard_rx = None
        if guard_port is not None:                     # run 16: torque guard over 5436 ('<12f')
            self.guard_rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.guard_rx.bind(("127.0.0.1", int(guard_port)))
            self.guard_rx.settimeout(0.1)
            threading.Thread(target=self._guard_loop, daemon=True).start()
        if adv_port is not None:                       # run 15: Advanced over 5435 ('<16f')
            self.adv_rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.adv_rx.bind(("127.0.0.1", int(adv_port)))
            self.adv_rx.settimeout(0.1)
            threading.Thread(target=self._adv_loop, daemon=True).start()

    def apply_adv(self, p):
        """The model's 5435 rules: magic 4135 / version 1, each field kept unless valid, SV
        min < max else both kept, [14] / [15] ignored."""
        if len(p) != 16 or p[0] != 4135.0 or p[1] != 1.0:
            return False
        rules = {"sv_target_min": (0.2, 2.0, False), "sv_target_max": (0.2, 2.0, False),
                 "target_step_up": (0, 0.5, False), "target_step_down": (0, 0.5, False),
                 "step_up_window": (1, 60, True), "step_down_window": (1, 60, True),
                 "high_assist_level": (0, 10, False), "high_assist_strides": (0, 200, True),
                 "torque_p_gain": (0.05, 3, False), "torque_i_gain": (0, 5, False),
                 "standing_still_cutoff": (0, 5000, False)}      # 0 allowed (Andy 16:31)
        new = dict(self.adv)
        for i, f in enumerate(ADV_FIELDS):
            v, (lo, hi, whole) = p[3 + i], rules[f]
            if v == v and lo <= v <= hi and (not whole or v == int(v)):
                new[f] = v
        if not new["sv_target_min"] < new["sv_target_max"]:
            new["sv_target_min"], new["sv_target_max"] = self.adv["sv_target_min"], self.adv["sv_target_max"]
        self.adv, self.adv_seq = new, p[2]
        return True

    def apply_guard(self, p):
        """The model's 5436 rules: magic 4136 / version 1, each field kept unless valid, [11] ignored."""
        if len(p) != 12 or p[0] != 4136.0 or p[1] != 1.0:
            return False
        for i, f in enumerate(GUARD_FIELDS):
            v, (lo, hi, whole) = p[3 + i], GUARD_RULES[f]
            if v == v and lo <= v <= hi and (not whole or v == int(v)):
                self.guard[f] = v
        self.guard_seq = p[2]
        return True

    def _guard_loop(self):
        while not self._stop.is_set():
            try:
                data, _ = self.guard_rx.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(data) != 48:
                continue
            p = struct.unpack("<12f", data)
            with self.lock:
                self.guard_received.append((time.time(), p))
                self.apply_guard(p)

    def _adv_loop(self):
        while not self._stop.is_set():
            try:
                data, _ = self.adv_rx.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(data) != 64:
                continue
            p = struct.unpack("<16f", data)
            with self.lock:
                self.adv_received.append((time.time(), p))
                self.apply_adv(p)

    def _rx_loop(self):
        while not self._stop.is_set():
            try:
                data, _ = self.rx.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(data) != 32:
                self.ignored += 1
                continue
            p = struct.unpack("<8f", data)
            with self.lock:
                self.received.append((time.time(), p))
                if p[0] != 4134.0 or p[1] != 1.0:
                    self.ignored += 1
                    continue
                self.accepted += 1
                self.v["seq"] = p[2]
                if p[3] in (0.0, 1.0):                  # -1 or anything else: keep
                    self.v["side"] = p[3]
                if 20.0 <= p[4] <= 200.0:               # sets weight AND BIF_mass_kg; else keep
                    self.v["mass"] = p[4]
                if p[5] in (1.0, 3.0):
                    self.v["mode"] = p[5]
                if 0.0 <= p[6] <= 10.0:
                    self.v["k"] = p[6]
                if p[7] == p[7] and abs(p[7]) != float("inf"):
                    if p[7] != self.v["gyro"]:
                        self.gyro_changes += 1          # a change re-runs the 5 s gyro bias
                    self.v["gyro"] = p[7]

    def _row(self):
        v = self.v
        t = 20.0 + (time.time() - self.t0)
        row = [t, v["side"], v["mass"], v["mode"], v["k"], v["motor"], v["assist"], v["kk"], 0.0, 0.0, 1.0, 0.0,
               1.0, 1.0, 1.0, v["gyro"], v["seq"], v["mass"]]
        row += [self.adv[f] for f in ADV_FIELDS] + [self.adv_seq, self.spring]
        row += [self.flags[k] for k in ("slack_flag", "jam_flag", "slack_count", "slack_last_stride")]
        row += [self.guard[f] for f in GUARD_FIELDS] + [self.guard_seq]
        return row[:self.n]

    def _tx_loop(self):
        k = 0
        t_start = time.perf_counter()
        while not self._stop.is_set():
            k += 1
            while time.perf_counter() - t_start < k * 0.01:
                time.sleep(0.001)
            if time.time() < self._stall_until:
                continue
            with self.lock:
                row = self._row()
            try:
                self.tx.sendto(struct.pack(f"<{len(row)}f", *row), self.console)
            except OSError:
                pass

    def start(self):
        """Start reloads the app: side -1, mass 0 until the next valid packet."""
        with self.lock:
            self.v["side"], self.v["mass"], self.v["gyro"], self.v["seq"] = -1.0, 0.0, 0.0, 0.0
            self.adv, self.adv_seq = dict(zip(ADV_FIELDS, ADV_DEFAULTS)), 0.0     # build values again

    def stall(self, seconds):
        self._stall_until = time.time() + seconds

    def close(self):
        self._stop.set()
        for sk in (self.rx, self.adv_rx, self.guard_rx):
            try:
                if sk is not None:
                    sk.close()
            except OSError:
                pass
