"""Run 15 (Advanced over UDP): the page matches round1\\console_udp_layout.json ('<31f') and
round1\\settings_adv_udp_layout.json (5435) EXACTLY. Seconds, no browser, no app server,
no target, a few packets on test ports only.

- 5433 '<31f': cols 0-17 = run 14 unchanged; 18-28 = the 11 Advanced values in use in the
  order of settings_adv_udp_layout.json; 29 adv_seq; 30 spring_stiffness (ignored);
- config/ copies = round1; the receiver parses 31, 18, 15 and 12 floats;
- 31 floats: the Advanced values come from the echo (no getparam, nothing setparam'd), the
  page adopts them, spring stiffness never shows; nothing is sent on connect / refresh;
- 18 floats: getparam for Advanced as on run 14.

    python test/test_run15_layout.py
"""
import json
import os
import queue as Q
import socket
import struct
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
from test_run14_layout import Dev, make_session  # noqa: E402

ROUND1 = os.path.join(os.path.dirname(APP), "round1") if os.path.isdir(os.path.join(os.path.dirname(APP), "round1")) \
    else r"C:\Users\Andy\Desktop\AFO\round1"
FIX = os.path.join(HERE, "fixtures")
FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def names_of(lay):
    return [c["name"] for c in sorted(lay["columns"], key=lambda c: c["column"])]


def layouts():
    con = json.load(open(os.path.join(ROUND1, "console_udp_layout.json"), encoding="utf-8"))
    adv = json.load(open(os.path.join(ROUND1, "settings_adv_udp_layout.json"), encoding="utf-8"))
    r14 = json.load(open(os.path.join(FIX, "run14_console_udp_layout.json"), encoding="utf-8"))
    n = names_of(con)
    check("round1 console layout: '<31f', 31 columns, port 5433", con["format"] == "<31f" and len(n) == 31 and con["port"] == 5433,
          con["format"])
    check("cols 0-17 = run 14 unchanged", n[:18] == names_of(r14), n[:18])
    af = [f["name"] for f in sorted(adv["fields"], key=lambda f: f["index"])]
    check("5435 layout: '<16f', 64 B, port 5435", adv["format"] == "<16f" and adv["bytes"] == 64 and adv["port"] == 5435, adv)
    check("5435 layout: magic 4135, version 1, seq, ..., reserved_spring, reserved",
          af[:3] == ["magic", "version", "seq"] and af[14:] == ["reserved_spring", "reserved"]
          and "4135" in adv["fields"][0]["rule"], af)
    check("cols 18-28 = the 11 Advanced values in the 5435 field order", n[18:29] == af[3:14], (n[18:29], af[3:14]))
    check("col 29 adv_seq, col 30 spring_stiffness", n[29:] == ["adv_seq", "spring_stiffness"], n[29:])
    import training_worker as TW
    check("receiver: RUN15_TAIL = cols 18-30", TW.RUN15_TAIL == n[18:], TW.RUN15_TAIL)
    import session as S
    check("session: Advanced key -> echo column covers cols 18-28 exactly (spring not among them)",
          sorted(S.SessionSetup.ADV_ECHO_COL.values()) == sorted(n[18:29]) and "spring_stiffness" not in S.SessionSetup.ADV_ECHO_COL.values()
          and set(S.SessionSetup.ADV_ECHO_COL) == {sp["key"] for sp in S.SPECS if sp.get("adv")}, S.SessionSetup.ADV_ECHO_COL)
    for f in ("console_udp_layout.json", "settings_adv_udp_layout.json", "settings_udp_layout.json"):
        a = json.load(open(os.path.join(APP, "config", f), encoding="utf-8"))
        b = json.load(open(os.path.join(ROUND1, f), encoding="utf-8"))
        check(f"config/{f} = round1 copy", a == b)


def receiver():
    import training_worker as TW
    from fake_run14 import FakeRun14
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    tmp = tempfile.mkdtemp(prefix="afo_r15_")
    lp = os.path.join(tmp, "lay.json")
    json.dump(dict(lay, port=15438), open(lp, "w"))
    out_q, stop = Q.Queue(), threading.Event()
    threading.Thread(target=TW.worker_main, args=(lp, "127.0.0.1", out_q, Q.Queue(), Q.Queue(), stop, tmp), daemon=True).start()
    time.sleep(0.5)

    def last_hb():
        last = None
        while True:
            try:
                kind, pl = out_q.get_nowait()
            except Q.Empty:
                return last
            if kind == "hb":
                last = pl
    # the fake run-15 device (31 floats) on test ports, for 0.3 s only
    dev = FakeRun14(settings_port=15439, console_port=15438, n_floats=31, side=0.0, mass=70.0)
    dev.adv["torque_p_gain"], dev.adv_seq = 0.75, 4.0
    time.sleep(0.3)
    dev.close()
    time.sleep(0.15)
    hb = last_hb() or {}
    lt = hb.get("latest", {})
    check("receiver: 31 floats from the fake run-15 device accepted (no bad_length)",
          hb.get("columns") == 31 and hb.get("bad_length") == 0 and hb.get("packets_ok", 0) > 5, {k: hb.get(k) for k in ("columns", "bad_length", "packets_ok")})
    check("receiver: cols 0-17 keep their meaning (side 0, weight 70, settings_seq, bif_mass_kg)",
          (lt.get("side"), lt.get("weight_kg"), lt.get("bif_mass_kg"), lt.get("settings_seq")) == (0.0, 70.0, 70.0, 0.0), lt)
    check("receiver: Advanced cols 18-28 + adv_seq", lt.get("sv_target_min") == struct.unpack("<f", struct.pack("<f", 0.8))[0]
          and lt.get("torque_p_gain") == struct.unpack("<f", struct.pack("<f", 0.75))[0] and lt.get("standing_still_cutoff") == 200.0
          and lt.get("adv_seq") == 4.0, lt)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    got = {}
    for n in (18, 15, 12):
        for k in range(12):
            row = [900.0 + 10 * n + k * 0.01, 1.0, 70.0, 3.0, 5.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0,
                   1.0, 0.5, 1.0, 7.0, 12.0, 70.0][:n]
            s.sendto(struct.pack(f"<{n}f", *row), ("127.0.0.1", 15438))
            time.sleep(0.01)
        time.sleep(0.12)
        hb = last_hb() or {}
        got[n] = (hb.get("columns"), hb.get("bad_length"))
    stop.set()
    check("receiver: 18, 15 and 12 floats still accepted with the 31-float layout",
          [got[n] for n in (18, 15, 12)] == [(18, 0), (15, 0), (12, 0)], got)


class Dev31(Dev):
    """In-process run-15 device: Dev (5434 rules) + the 31-float echo."""
    def __init__(self, cols=31):
        super().__init__(18)
        self.cols31 = cols
        from fake_run14 import ADV_FIELDS, ADV_DEFAULTS
        self.adv = dict(zip(ADV_FIELDS, ADV_DEFAULTS))
        self.adv_seq, self.spring = 3.0, 1.25

    def status(self):
        st = super().status()
        if self.on and self.cols31 == 31:
            st["latest"].update(self.adv, adv_seq=self.adv_seq, spring_stiffness=self.spring)
            st["columns"] = 31
        return st


def session_31():
    dev, calls = Dev31(), []
    dev.v.update(side=0.0, weight_kg=80.0, bif_mass_kg=80.0, settings_seq=3.0)
    dev.adv["torque_p_gain"] = 0.7
    ctx, s = make_session(dev, calls)
    s.values["p_gain"] = 0.6                         # what an older (run-14) session had entered
    s.status["i_gain"] = {"state": "pending", "msg": "pending: sent after Start", "at": time.time()}
    dev.on = True
    time.sleep(0.3)
    calls.clear()
    s.refresh_echo()
    check("31 floats: adv_echo on", s.adv_echo(), s.echo())
    check("31 floats: Advanced readbacks from the echo (P gain 0.7, cutoff 200), source echo",
          s.readback.get("p_gain") == 0.7 and s.readback.get("threshold_pressure") == 200.0
          and all(s.readback_src.get(k) == "echo" for k in s.ADV_ECHO_COL), (s.readback, s.readback_src))
    check("31 floats: the page adopts them (values = echo), nothing sent",
          s.values.get("p_gain") == 0.7 and s.src.get("p_gain") == "adopted31" and not [c for c in calls if c[0] == "matlab"], (s.values, calls))
    check("31 floats: a value held for 'after Start' is dropped (never setparam'd)", "i_gain" not in s.status, s.status.get("i_gain"))
    check("31 floats: spring stiffness never shows", not any("spring" in k for k in list(s.readback) + list(s.values)), s.readback)
    check("31 floats: no getparam keys at all", s.getparam_keys() == [], s.getparam_keys())
    calls.clear()
    s.refresh_readback()
    s.after_connect_or_start("connect")
    time.sleep(0.5)
    check("31 floats: refresh / connect send and read nothing over MATLAB",
          not [c for c in calls if c[0] == "matlab"], calls)
    calls.clear()
    msg = s.enter_value("p_gain", 0.9)
    check("31 floats, no 5435 sender: an Advanced edit is refused read-only, never setparam'd",
          "read-only" in msg and not [c for c in calls if c[0] == "matlab"] and (s.status.get("p_gain") or {}).get("state") == "error",
          (msg, calls, s.status.get("p_gain")))
    from pages import console_api as CA
    v = CA._adv_view(ctx)
    check("page state: adv udp on, send off (read-only, no hint)", v["udp"] is True and v["send"] is False, v)
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: Advanced from the echo on 31 floats, disabled while there is no sender",
          "var ro = !av.send || !!av.frozen;" in js and "inp.disabled = ro;" in js and "v = sending ? v : (sv.readback || {})[k];" in js)

    # 18 floats: run 14 behaviour (getparam for Advanced)
    dev18, calls18 = Dev(18), []
    dev18.v.update(side=0.0, weight_kg=80.0, bif_mass_kg=80.0, settings_seq=3.0)
    ctx18, s18 = make_session(dev18, calls18)
    dev18.on = True
    time.sleep(0.3)
    check("18 floats: adv_echo off, getparam for the 11 Advanced", not s18.adv_echo() and sorted(s18.getparam_keys())
          == sorted(s18.ADV_ECHO_COL), s18.getparam_keys())


if __name__ == "__main__":
    layouts()
    receiver()
    session_31()
    print("FAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
