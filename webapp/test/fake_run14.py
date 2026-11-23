"""Fake run-14 target for the UDP settings (test ports only, never 192.168.7.5).

Listens on 127.0.0.1:<settings_port> (test: 15434) for '<8f' packets
    magic 4134, version 1, seq, side, body_mass_kg, assist_mode, fixed_k_pct, gyro_cal_request
and behaves like the model: a wrong magic / version is ignored; per field an invalid value
keeps the last value; values are held. start() (= Start) resets side -1 and mass 0 until
the next valid packet. Echo at 100 Hz to 127.0.0.1:<console_port> (test: 15433), '<18f':
the 12 base console columns + bif_valid, bif_cal_progress, bif_bias_ready +
gyro_cal_request, last accepted seq, bif_mass_kg. stall(s) stops the echo for s seconds;
n_floats=15 sends the run-13 packet instead (no settings columns, 5434 ignored).
"""
import socket
import struct
import threading
import time

BASE = ["t_model", "side", "weight_kg", "assist_mode", "fixed_k_pct", "cmd_motor", "cmd_assist", "cmd_k",
        "cmd_calibrate_pressure", "cmd_reset_sv", "imu_ok", "imu_bad_count",
        "bif_valid", "bif_cal_progress", "bif_bias_ready", "gyro_cal_request", "settings_seq", "bif_mass_kg"]


class FakeRun14:
    def __init__(self, settings_port=15434, console_port=15433, n_floats=18, side=-1.0, mass=0.0, mode=3.0, k=5.0,
                 gyro=0.0, motor=0.0, assist=0.0, kk=1.0, seq=0.0):
        self.addr = ("127.0.0.1", int(settings_port))
        self.console = ("127.0.0.1", int(console_port))
        self.n = n_floats
        self.v = {"side": side, "mass": mass, "mode": mode, "k": k, "gyro": gyro, "seq": seq,
                  "motor": motor, "assist": assist, "kk": kk}
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

    def stall(self, seconds):
        self._stall_until = time.time() + seconds

    def close(self):
        self._stop.set()
        try:
            self.rx.close()
        except OSError:
            pass
