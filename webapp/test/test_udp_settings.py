"""Run-14 UDP settings (5434 out, 18-float 5433 echo) against the fake run-14 target.
Test ports only (settings 15434, console 15433 on 127.0.0.1), light: no browser, no app
server, no MATLAB. Covers:
- the 5433 parser accepts 12 / 15 / 18 floats (training_worker, in-process);
- packet layout (magic 4134, version 1, seq, side, mass, mode, K, gyro);
- adopt on start: the device state shown (Right / 70 kg / Motor ON), seq continues from
  the echoed last seq + 1, NOTHING sent (page start / restart);
- a press: exactly one field changed, confirmed by the echo within ~0.1-0.2 s;
- bad magic / wrong value: no confirm, 3 retries within 1 s, "Not confirmed: no echo from model";
- link stall 3 s: frozen, zero packets, presses refused; back: re-adopt, unfreeze, device unchanged;
- resend once after Start (the device resets side / mass);
- run-13 fallback: a 15-float echo leaves the link inactive and the session uses setparam;
- session: no MATLAB calls for side / mass / mode / K / IMU with the link on;
- view-only: nothing sent.

    python test/test_udp_settings.py
"""
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
try:
    import _lowprio  # noqa: F401
except Exception:
    pass
import udp_settings as U  # noqa: E402
from fake_run14 import BASE, FakeRun14  # noqa: E402

FAILS = []
CFG = {"udp": {"send_host": "127.0.0.1", "session_port": 15434}}


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


class Echo:
    """Minimal 5433 receiver: latest row as {name: value}, its age and the column count."""
    def __init__(self, port=15433):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.bind(("127.0.0.1", port))
        self.s.settimeout(0.1)
        self.latest, self.at, self.cols = {}, None, None
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                d, _ = self.s.recvfrom(256)
            except (socket.timeout, OSError):
                continue
            n = len(d) // 4
            row = struct.unpack(f"<{n}f", d)
            self.latest, self.at, self.cols = {BASE[i]: row[i] for i in range(n)}, time.time(), n

    def __call__(self):
        return dict(self.latest), (time.time() - self.at) if self.at else None, self.cols

    def close(self):
        self._stop.set()
        self.s.close()


def wait(cond, t=2.0):
    t0 = time.time()
    while time.time() - t0 < t:
        if cond():
            return True
        time.sleep(0.01)
    return False


def parser_units():
    """training_worker accepts 12 / 15 / 18 floats on the real layout."""
    import multiprocessing
    import queue as Q
    import training_worker as TW
    out_q, req_q, resp_q = Q.Queue(), Q.Queue(), Q.Queue()
    stop = threading.Event()
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    lay["port"] = 15436
    tmp = tempfile.mkdtemp(prefix="afo_tw_")
    lp = os.path.join(tmp, "lay.json")
    json.dump(lay, open(lp, "w"))
    th = threading.Thread(target=TW.worker_main, args=(lp, "127.0.0.1", out_q, req_q, resp_q, stop, tmp), daemon=True)
    th.start()
    time.sleep(0.6)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seen = {}
    for n in (12, 15, 18):
        for k in range(30):
            row = [100.0 * n + k * 0.01, 0.0, 70.0, 3.0, 5.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0,
                   1.0, 1.0, 1.0, 2.0, 7.0, 70.0][:n]
            s.sendto(struct.pack(f"<{n}f", *row), ("127.0.0.1", 15436))
            time.sleep(0.01)
        time.sleep(0.15)
        st = None
        while True:
            try:
                kind, p = out_q.get_nowait()
            except Q.Empty:
                break
            if kind == "hb":
                st = p
        seen[n] = (st or {}).get("columns"), sorted((st or {}).get("latest", {}))
    stop.set()
    check("5433 parser: 12, 15 and 18 floats accepted", [seen[n][0] for n in (12, 15, 18)] == [12, 15, 18], seen)
    check("5433 parser: 18 floats carry gyro_cal_request, settings_seq, bif_mass_kg",
          {"gyro_cal_request", "settings_seq", "bif_mass_kg"} <= set(seen[18][1]), seen[18][1])
    check("5433 heartbeat at 20 Hz (confirm within ~0.1 s)", "time.sleep(0.05)" in open(TW.__file__, encoding="utf-8").read())


def main():
    parser_units()
    echo = Echo()
    dev = FakeRun14(side=1.0, mass=70.0, mode=3.0, k=5.0, gyro=4.0, motor=1.0, seq=41.0)   # Right / 70 kg / Motor ON
    statuses, adopts = [], []
    try:
        # ---- page (re)start: adopt, send nothing
        lk = U.SettingsLink(CFG, echo, on_status=lambda f, s, m: statuses.append((f, s, m)), on_adopt=adopts.append)
        check("adopt: device state taken from the echo", wait(lambda: lk.state is not None)
              and lk.state == {"side": 1.0, "mass": 70.0, "mode": 3.0, "k": 5.0, "gyro": 4.0}, lk.state)
        check("adopt: Right / 70 kg shown to the page (on_adopt)", wait(lambda: bool(adopts), 1.0)
              and adopts[0]["side"] == 1.0 and adopts[0]["mass"] == 70.0, adopts)
        check("adopt: Motor ON on the device is in the echo (cmd_motor 1)", echo()[0].get("cmd_motor") == 1.0)
        time.sleep(0.5)
        check("page start / restart sends NOTHING", not lk.sent and not dev.received, (lk.sent, dev.received))
        check("seq continues from the echoed last seq (41)", lk.seq == 41, lk.seq)
        # ---- a press: one field changed, confirmed fast
        t0 = time.time()
        r = lk.press("mass", 72.5)
        ok = wait(lambda: lk.result.get("mass", {}).get("state") == "confirmed", 1.0)
        dt = time.time() - t0
        p = dev.received[0][1] if dev.received else None
        check("press: packet layout magic 4134, version 1, seq 42", p and p[:3] == (4134.0, 1.0, 42.0), p)
        check("press: exactly one field changed (mass 70 -> 72.5; side, mode, K, gyro = device)",
              p and p[3:] == (1.0, 72.5, 3.0, 5.0, 4.0), p)
        check(f"press: confirmed by the echo in {dt * 1000:.0f} ms (< 300)", r["ok"] and ok and dt < 0.3, (r, dt))
        check("press: one packet only (no retry needed)", len(dev.received) == 1, len(dev.received))
        # ---- wrong value (model keeps the last): no confirm, 3 retries, message
        n0 = len(dev.received)
        lk.state["k"] = 5.0
        lk.pending.clear()
        U.valid_orig = U.valid
        U.valid = lambda f, v: True                 # let the page send what the model will refuse
        lk.press("mode", 2.0)                       # 2 = ILC: the model keeps 3
        U.valid = U.valid_orig
        ok = wait(lambda: lk.result.get("mode", {}).get("state") == "error", 1.5)
        n_sent = len(dev.received) - n0
        check("wrong value: not confirmed -> 'Not confirmed: no echo from model'", ok
              and lk.result["mode"]["msg"] == U.NOT_CONFIRMED_MSG, lk.result.get("mode"))
        check("wrong value: 1 send + 3 retries within 1 s, then stop", n_sent == 4, n_sent)
        check("wrong value: device kept mode 3", dev.v["mode"] == 3.0, dev.v)
        # ---- bad magic: ignored by the model
        n0 = len(dev.received)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(struct.pack("<8f", 1234.0, 1.0, 99.0, 0.0, 10.0, 1.0, 1.0, 9.0), ("127.0.0.1", 15434))
        time.sleep(0.2)
        check("bad magic: device ignores it (side stays Right, mass 72.5)", dev.v["side"] == 1.0 and dev.v["mass"] == 72.5
              and dev.ignored >= 1, dev.v)
        # ---- link stall 3 s: frozen, nothing sent, re-adopt after
        n0 = len(dev.received)
        dev.stall(3.0)
        check("stall: frozen within ~1 s", wait(lambda: lk.frozen, 1.5), lk.view())
        r = lk.press("side", 0.0)
        check("stall: a press is refused with the message", not r["ok"] and r["msg"] == U.FROZEN_MSG, r)
        time.sleep(2.2)
        check("stall: zero packets sent during the stall", len(dev.received) == n0, len(dev.received) - n0)
        check("back: re-adopted and unfrozen", wait(lambda: not lk.frozen, 2.0) and lk.state["side"] == 1.0
              and lk.state["mass"] == 72.5, lk.view())
        check("back: device values unchanged (Right / 72.5 / mode 3)", (dev.v["side"], dev.v["mass"], dev.v["mode"]) == (1.0, 72.5, 3.0), dev.v)
        # ---- Start: the device resets side / mass; the page resends once
        n0 = len(dev.received)
        dev.start()
        pkt = lk.after_start()
        ok = wait(lambda: dev.v["side"] == 1.0 and dev.v["mass"] == 72.5, 1.0)
        check("after Start: one packet restores side Right / 72.5 kg", ok and len(dev.received) - n0 == 1 and pkt[3:5] == (1.0, 72.5),
              (pkt, dev.v, len(dev.received) - n0))
        # ---- IMU: counter + 1
        r = lk.press("gyro", lk.state["gyro"] + 1)
        check("Calibrate IMU: gyro_cal_request counter + 1 confirmed", wait(lambda: lk.result.get("gyro", {}).get("state") == "confirmed", 1.0)
              and dev.v["gyro"] == 5.0, dev.v)
        # ---- view-only: never sends
        vo = U.SettingsLink(CFG, echo, view_only=True, start_thread=False)
        vo.tick()
        n0 = len(dev.received)
        r = vo.press("side", 0.0)
        vo.after_start()
        time.sleep(0.2)
        check("view-only: nothing sent (press refused, no after-Start packet)", not r["ok"] and len(dev.received) == n0, r)
        lk.stop()
    finally:
        dev.close()
        time.sleep(0.15)
    # ---- run-13 fallback: 15-float echo -> link inactive, setparam path
    dev13 = FakeRun14(n_floats=15, side=0.0, mass=60.0)
    try:
        lk13 = U.SettingsLink(CFG, echo, start_thread=False)
        time.sleep(0.2)
        lk13.tick()
        check("run 13 (15 floats): link inactive, nothing adopted, nothing sent", not lk13.active() and lk13.state is None
              and not lk13.sent, lk13.view())
        session_checks(echo, dev13)
    finally:
        dev13.close()
        echo.close()
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


def session_checks(echo, dev13):
    """Session routes side / mass over the link only when the link is active."""
    import session as S
    from test_round5 import Cmd
    tmp = tempfile.mkdtemp(prefix="afo_udpsess_")
    calls = []

    class Jobs:
        def running(self, kind):
            return None

        def start(self, kind, title, fn):
            calls.append(("job", title))
            fn(types.SimpleNamespace(add=lambda l: None, meta={}))
            return types.SimpleNamespace(id=1)
    ml = types.SimpleNamespace(call=lambda fn, action, *a, **k: calls.append(("matlab", fn, action)) or json.dumps({"ok": True, "readback": a[-1] if a else 0}))
    ctx = types.SimpleNamespace(app_dir=tmp, cfg={"paths": {"log_dir": tmp}, "target": {"model": "AFO_r1"},
                                                  "session": {"target_writes_enabled": True}},
                                runctl=types.SimpleNamespace(status={"connected": True, "running": True, "app": "AFO_r1"}),
                                jobs=Jobs(), commands=Cmd(), matlab=ml,
                                training=types.SimpleNamespace(get_status=lambda: {"latest": echo()[0], "age_s": echo()[1], "columns": echo()[2]},
                                                               latest=lambda max_age_s=1.0: echo()[0], last_hb=time.monotonic()))
    ctx.session = S.SessionSetup(ctx)
    ctx.session.set_sid("S94")
    # run 13 now (15 floats): setparam path
    ctx.settings_link = U.SettingsLink(CFG, ctx.session.echo_for_link, start_thread=False)
    ctx.session.confirm_side("LEFT", "S94")
    check("run 13: side goes by setparam (MATLAB)", any(c[0] == "matlab" and c[2] == "set" for c in calls), calls)
    dev13.close()                       # frees 15434 for the run-14 fake
    time.sleep(0.3)
    dev = FakeRun14(side=0.0, mass=60.0, gyro=2.0, seq=5.0)
    try:
        time.sleep(0.2)
        lk = U.SettingsLink(CFG, ctx.session.echo_for_link, on_status=ctx.session.link_status,
                            on_adopt=ctx.session.link_adopted)
        ctx.settings_link = lk
        wait(lambda: lk.state is not None, 1.0)
        calls.clear()
        ctx.session.confirm_side("RIGHT", "S94")
        ctx.session.enter_value("weight", 66.0)
        ok = wait(lambda: dev.v["side"] == 1.0 and dev.v["mass"] == 66.0, 1.5)
        check("run 14: side + mass over 5434, no MATLAB call", ok and not [c for c in calls if c[0] == "matlab"],
              (dev.v, calls))
        check("run 14: session shows 'confirmed' from the echo", wait(lambda: (ctx.session.status.get("side") or {}).get("state") == "confirmed"
                                                                         and (ctx.session.status.get("weight") or {}).get("state") == "confirmed", 1.0),
              {k: ctx.session.status.get(k) for k in ("side", "weight")})
        ctx.session.refresh_readback()
        check("run 14: no getparam (refresh_readback makes no MATLAB call)", not [c for c in calls if c[0] == "matlab"], calls)
        lk.stop()
    finally:
        dev.close()


if __name__ == "__main__":
    main()
