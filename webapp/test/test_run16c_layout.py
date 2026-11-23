"""Run 16c (standing-still torque fade): the page matches the round1 run-16c layouts EXACTLY.
Seconds, no browser, no app server, no target; test ports only.

- 5435 Advanced '<16f': [15] standstill_fade_ms 0..1000 (default 200, 0 = hard cut), [14]
  reserved_spring ignored (sent 0); the rest as run 15 / 16b;
- 5433 '<45f': col 44 standstill_fade_ms in use; the receiver parses 45 and 44 (run 16b) and
  every older length;
- the page: 'Fade' (ms) next to the standing-still cutoff, from the echo, confirmed over 5435
  like the cutoff (device value, no 'differs'); on a 44-float build the fade is unknown (not
  shown) and a packet carries NaN (= keep) in [15].

    python test/test_run16c_layout.py
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

ROUND1 = os.path.join(os.path.dirname(APP), "round1") if os.path.isdir(os.path.join(os.path.dirname(APP), "round1")) \
    else r"C:\Users\Andy\Desktop\AFO\round1"
FIX = os.path.join(HERE, "fixtures")
FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def names_of(lay):
    return [c["name"] for c in sorted(lay["columns"], key=lambda c: c["column"])]


def layouts():
    con = json.load(open(os.path.join(ROUND1, "console_udp_layout.json"), encoding="utf-8"))
    adv = json.load(open(os.path.join(ROUND1, "settings_adv_udp_layout.json"), encoding="utf-8"))
    r16b = json.load(open(os.path.join(FIX, "run16b_console_udp_layout.json"), encoding="utf-8"))
    n = names_of(con)
    check("round1 console layout: '<45f', 45 columns", con["format"] == "<45f" and len(n) == 45, con["format"])
    check("cols 0-43 = run 16b unchanged", n[:44] == names_of(r16b), n[:44])
    check("col 44 = standstill_fade_ms", n[44] == "standstill_fade_ms", n[44:])
    import training_worker as TW
    check("receiver: RUN16C_TAIL = col 44", TW.RUN16C_TAIL == n[44:], TW.RUN16C_TAIL)
    f = {x["index"]: x for x in adv["fields"]}
    check("5435: '<16f' 64 B, [14] reserved_spring, [15] standstill_fade_ms", adv["format"] == "<16f" and adv["bytes"] == 64
          and f[14]["name"] == "reserved_spring" and f[15]["name"] == "standstill_fade_ms", (f.get(14), f.get(15)))
    check("5435 [15] rule: 0..1000, default 200, 0 = hard cut", "0..1000" in f[15]["rule"] and "200" in f[15]["rule"],
          f[15]["rule"])
    for name in ("console_udp_layout.json", "settings_adv_udp_layout.json", "settings_guard_udp_layout.json",
                 "settings_udp_layout.json"):
        a = json.load(open(os.path.join(APP, "config", name), encoding="utf-8"))
        b = json.load(open(os.path.join(ROUND1, name), encoding="utf-8"))
        check(f"config/{name} = round1 copy (exact)", a == b)
    import udp_settings as U
    fields, rules, _ = U.load_adv_layout(os.path.join(ROUND1, "settings_adv_udp_layout.json"))
    check("5435 rules: fade 0..1000", rules.get("standstill_fade_ms", {}).get("min") == 0.0
          and rules["standstill_fade_ms"]["max"] == 1000.0, rules.get("standstill_fade_ms"))


def receiver():
    import training_worker as TW
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    tmp = tempfile.mkdtemp(prefix="afo_r16c_")
    lp = os.path.join(tmp, "lay.json")
    json.dump(dict(lay, port=15458), open(lp, "w"))
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
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    got = {}
    for n in (45, 44, 31, 18, 15, 12):
        for k in range(12):
            row = ([700.0 + 10 * n + k * 0.01, 1.0, 70.0, 3.0, 5.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0] + [0.5] * 32 + [150.0])[:n]
            s.sendto(struct.pack(f"<{n}f", *row), ("127.0.0.1", 15458))
            time.sleep(0.01)
        time.sleep(0.12)
        hb = last_hb() or {}
        got[n] = (hb.get("columns"), hb.get("bad_length"), (hb.get("latest") or {}).get("standstill_fade_ms"))
    stop.set()
    check("receiver: 45 floats -> fade 150 in use", got[45] == (45, 0, 150.0), got[45])
    check("receiver: 44 (run 16b) and older still accepted, fade unknown", [got[n][:2] for n in (44, 31, 18, 15, 12)]
          == [(44, 0), (31, 0), (18, 0), (15, 0), (12, 0)] and got[44][2] is None, got)


def adv_link():
    import udp_settings as U
    from fake_run14 import ADV_FIELDS, ADV_DEFAULTS
    row = dict(zip(ADV_FIELDS, ADV_DEFAULTS), adv_seq=3.0, standstill_fade_ms=200.0)
    echo = {"row": row, "cols": 45}
    sent = []
    lk = U.AdvLink({"udp": {"send_host": "127.0.0.1", "adv_port": 15435}}, lambda: (dict(echo["row"]), 0.01, echo["cols"]),
                   sender=lambda data, addr: sent.append(data), start_thread=False)
    lk.tick()
    r = lk.press("standstill_fade_ms", 0)
    p = struct.unpack("<16f", sent[-1])
    check("fade 0 (hard cut): one 64-byte packet, seq = adv_seq + 1, [15] = 0, [14] = 0, others in use",
          r["ok"] and len(sent[-1]) == 64 and p[2] == 4.0 and p[15] == 0.0 and p[14] == 0.0
          and list(p[3:14]) == [f32(v) for v in ADV_DEFAULTS], p)
    row.update(standstill_fade_ms=0.0, adv_seq=4.0)
    lk.tick()
    check("fade confirmed from the echo (col 44 + adv_seq)", lk.result["standstill_fade_ms"]["state"] == "confirmed", lk.result)
    sent.clear()
    for bad in (-1, 1001, float("nan")):
        r = lk.press("standstill_fade_ms", bad)
        check(f"fade {bad}: refused before sending", not r["ok"] and not sent, r)
    # a cutoff press carries the fade in use; on a 44-float (16b) echo the fade is unknown -> NaN (keep)
    r = lk.press("standing_still_cutoff", 0)
    p = struct.unpack("<16f", sent[-1])
    check("cutoff 0 press carries the fade in use (0)", r["ok"] and p[13] == 0.0 and p[15] == 0.0, p)
    lk.pending.clear()
    echo["cols"] = 44
    row.pop("standstill_fade_ms")
    lk.state = None
    lk.tick()
    r = lk.press("standing_still_cutoff", 300)
    p = struct.unpack("<16f", sent[-1])
    check("44-float build: fade unknown -> [15] NaN (keep), the cutoff still sent", r["ok"] and p[15] != p[15] and p[13] == 300.0, p)


def session_page():
    import udp_settings as U
    from test_run14_layout import make_session
    from test_run15_layout import Dev31
    from pages import console_api as CA

    class Dev45(Dev31):
        def __init__(self, fade=True):
            super().__init__()
            self.fade = 200.0 if fade else None

        def recv(self, data, addr):
            if len(data) == 64:
                p = struct.unpack("<16f", data)
                if p[15] == p[15] and 0 <= p[15] <= 1000 and self.fade is not None:
                    self.fade = p[15]
            super().recv(data, addr)

        def status(self):
            st = super().status()
            if self.on and self.fade is not None:
                st["latest"]["standstill_fade_ms"] = self.fade
                st["columns"] = 45
            return st
    for fade in (True, False):
        dev, calls = Dev45(fade), []
        dev.v.update(side=0.0, weight_kg=80.0, bif_mass_kg=80.0, settings_seq=3.0)
        ctx, s = make_session(dev, calls)
        ctx.adv_link = U.AdvLink({"udp": {"send_host": "127.0.0.1", "adv_port": 15435}}, s.echo_for_link,
                                 on_status=s.adv_link_status, on_adopt=s.adv_link_adopted, sender=dev.recv)
        dev.on = True
        time.sleep(0.4)
        s.refresh_echo()
        if fade:
            check("45 floats: Fade readback from the echo (200), source echo, Advanced profile on",
                  s.readback.get("fade_ms") == 200.0 and s.readback_src.get("fade_ms") == "echo" and s.adv_profile(), s.readback)
            msg = s.enter_value("fade_ms", 50)
            t0 = time.time()
            while time.time() - t0 < 1.0 and (s.status.get("fade_ms") or {}).get("state") != "confirmed":
                time.sleep(0.02)
            s.refresh_echo()
            check("Fade 50: sent over 5435, confirmed, device value shown", "sending" in msg
                  and (s.status.get("fade_ms") or {}).get("state") == "confirmed" and s.values.get("fade_ms") == 50.0
                  and not [c for c in calls if c[0] == "matlab"], (msg, s.status.get("fade_ms"), s.values.get("fade_ms")))
            rows = CA.settings_rows(ctx)["rows"]
            check("popover: no 'differs' state", all(r["state"] != "differs" for r in rows), rows)
        else:
            check("44 floats (run 16b): Advanced profile still on, fade unknown (no readback)",
                  s.adv_profile() and s.readback.get("fade_ms") is None, (s.echo_cols(), s.readback.get("fade_ms")))
            adv = next(r for r in CA.settings_rows(ctx)["rows"] if r["key"] == "adv")
            check("44 floats: Advanced row counts the 11 values (fade not expected)", adv["label"] == "Advanced (11)", adv)
        ctx.adv_link.stop()
        ctx.settings_link.stop()
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: 'Fade' (ms) right after the standing-still cutoff, shown only when echoed, whole ms",
          "['threshold_pressure', 'Standing-still cutoff'" in js and js.index("['threshold_pressure'") < js.index("['fade_ms', 'Fade', 'ms'")
          and "has = advUdp && (sv.readback || {}).fade_ms != null" in js and "fade_ms: 0}" in js)


if __name__ == "__main__":
    layouts()
    receiver()
    adv_link()
    session_page()
    print("FAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
