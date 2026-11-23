"""Run 16 (torque guard over UDP 5436): the page matches round1\\console_udp_layout.json ('<44f')
and round1\\settings_guard_udp_layout.json (5436, '<12f') EXACTLY. Seconds, no browser, no
app server, no target; a few packets on test ports only.

- 5433 '<44f': cols 0-30 = run 15 unchanged; 31 slack_flag, 32 jam_flag (latched until Motor
  OFF -> ON), 33 slack_count, 34 slack_last_stride, 35-42 the guard settings in use, 43
  guard_seq; the receiver parses 44 / 31 / 18 / 15 / 12 floats;
- 5436: '<12f' 48 B, magic 4136, version 1, seq = guard_seq + 1, the 8 in-use values with one
  changed, [11] = 0; confirm from the echo, 3 retries in 1 s, frozen on a stall, the layout's
  ranges / whole numbers / 0-1 switches refused before sending; inactive below 44 floats;
- status button: red 'Cable jam: torque cut' while jam_flag = 1 (hint: Motor off and on), amber
  'Cable slack' while slack_flag = 1, nothing when 0; slack_count in the popover notes; flag
  changes logged.

    python test/test_run16_layout.py
"""
import json
import logging
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
    r15 = json.load(open(os.path.join(FIX, "run15_console_udp_layout.json"), encoding="utf-8"))
    g = json.load(open(os.path.join(ROUND1, "settings_guard_udp_layout.json"), encoding="utf-8"))
    n = names_of(con)
    check("round1 console layout: '<44f', 44 columns", con["format"] == "<44f" and len(n) == 44, con["format"])
    check("cols 0-30 = run 15 unchanged", n[:31] == names_of(r15), n[:31])
    import training_worker as TW
    check("cols 31-43 = slack_flag, jam_flag, slack_count, slack_last_stride, 8 guard settings, guard_seq (RUN16_TAIL)",
          n[31:] == TW.RUN16_TAIL and n[31:35] == ["slack_flag", "jam_flag", "slack_count", "slack_last_stride"]
          and n[43] == "guard_seq", n[31:])
    gf = [f["name"] for f in sorted(g["fields"], key=lambda f: f["index"])]
    check("5436 layout: '<12f', 48 B, port 5436, magic 4136", g["format"] == "<12f" and g["bytes"] == 48 and g["port"] == 5436
          and "4136" in g["fields"][0]["rule"], g["format"])
    check("guard fields in use = cols 35-42 in the 5436 order", gf[3:11] == n[35:43], (gf[3:11], n[35:43]))
    for f in ("console_udp_layout.json", "settings_guard_udp_layout.json", "settings_adv_udp_layout.json", "settings_udp_layout.json"):
        a = json.load(open(os.path.join(APP, "config", f), encoding="utf-8"))
        b = json.load(open(os.path.join(ROUND1, f), encoding="utf-8"))
        check(f"config/{f} = round1 copy", a == b)
    import udp_settings as U
    fields, rules, _ = U.load_adv_layout(os.path.join(ROUND1, "settings_guard_udp_layout.json"))
    check("guard rules from the layout (ranges, whole numbers, 0/1 switches)",
          rules["slack_thr_nm"] == {"min": -5.0, "max": -0.05, "int": False} and rules["slack_ms"]["int"]
          and rules["jam_ms"] == {"min": 10.0, "max": 2000.0, "int": True} and rules["fb_filter"] == {"min": 0.0, "max": 1.0, "int": True}
          and rules["slack_floor_on"] == {"min": 0.0, "max": 1.0, "int": True}, rules)


def receiver():
    import training_worker as TW
    from fake_run14 import FakeRun14
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    tmp = tempfile.mkdtemp(prefix="afo_r16_")
    lp = os.path.join(tmp, "lay.json")
    json.dump(dict(lay, port=15448), open(lp, "w"))
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
    dev = FakeRun14(settings_port=15449, console_port=15448, n_floats=44, side=0.0, mass=70.0)
    dev.flags.update(slack_flag=1.0, slack_count=3.0, slack_last_stride=1.0)
    dev.guard["jam_ms"] = 150.0
    dev.guard_seq = 2.0
    time.sleep(0.3)
    dev.close()
    time.sleep(0.15)
    hb = last_hb() or {}
    lt = hb.get("latest", {})
    check("receiver: 44 floats from the fake run-16 device accepted", hb.get("columns") == 44 and hb.get("bad_length") == 0,
          {k: hb.get(k) for k in ("columns", "bad_length", "packets_ok")})
    check("receiver: cols 31-43 (slack_flag 1, slack_count 3, jam_ms 150, guard_seq 2) and run-15 cols intact",
          (lt.get("slack_flag"), lt.get("slack_count"), lt.get("jam_ms"), lt.get("guard_seq"), lt.get("adv_seq"), lt.get("bif_mass_kg"))
          == (1.0, 3.0, 150.0, 2.0, 0.0, 70.0), lt)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    got = {}
    for n in (31, 18, 15, 12):
        for k in range(12):
            row = ([900.0 + 10 * n + k * 0.01, 1.0, 70.0, 3.0, 5.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0] + [0.5] * 40)[:n]
            row[1] = 1.0
            row[3] = 3.0
            s.sendto(struct.pack(f"<{n}f", *row), ("127.0.0.1", 15448))
            time.sleep(0.01)
        time.sleep(0.12)
        hb = last_hb() or {}
        got[n] = (hb.get("columns"), hb.get("bad_length"))
    stop.set()
    check("receiver: 31, 18, 15 and 12 floats still accepted with the 44-float layout",
          [got[n] for n in (31, 18, 15, 12)] == [(31, 0), (18, 0), (15, 0), (12, 0)], got)


def guard_link():
    import udp_settings as U
    from fake_run14 import GUARD_FIELDS, GUARD_DEFAULTS
    row = dict(zip(GUARD_FIELDS, GUARD_DEFAULTS), guard_seq=4.0, adv_seq=1.0)
    echo = {"row": row, "age": 0.01, "cols": 44}
    sent = []
    lk = U.GuardLink({"udp": {"send_host": "127.0.0.1", "guard_port": 15436}}, lambda: (dict(echo["row"]), echo["age"], echo["cols"]),
                     sender=lambda data, addr: sent.append((data, addr)), start_thread=False,
                     layout_path=os.path.join(ROUND1, "settings_guard_udp_layout.json"))
    check("5436 link: fields in the round1 layout order", list(lk.FIELDS) == GUARD_FIELDS, lk.FIELDS)
    lk.tick()
    check("5436: adopt from the echo, nothing sent", not sent and lk.state.get("jam_ms") == 100.0, (sent, lk.state))
    r = lk.press("slack_thr_nm", -1.0)
    data, addr = sent[-1]
    p = struct.unpack("<12f", data)
    check("5436 packet: 48 bytes to guard_port", r["ok"] and len(data) == 48 and addr == ("127.0.0.1", 15436), (r, len(data), addr))
    check("5436 packet: magic 4136, version 1, seq = guard_seq 4 + 1", p[:3] == (4136.0, 1.0, 5.0), p[:3])
    want = [f32(v) for v in GUARD_DEFAULTS]
    want[GUARD_FIELDS.index("slack_thr_nm")] = -1.0
    check("5436 packet: the 8 in-use values, only the slack threshold changed; [11] = 0", list(p[3:11]) == want and p[11] == 0.0,
          (p[3:], want))
    row.update(slack_thr_nm=-1.0, guard_seq=5.0)
    lk.tick()
    check("5436: confirmed from the echo (value + guard_seq), no resend", lk.result["slack_thr_nm"]["state"] == "confirmed"
          and len(sent) == 1, (lk.result, len(sent)))
    sent.clear()
    lk.press("fb_filter", 1)
    t0 = time.time()
    while time.time() - t0 < 1.2:
        lk.tick()
        time.sleep(0.02)
    check("5436: no echo -> max 3 retries in 1 s, then 'Not confirmed'", len(sent) == 4
          and lk.result["fb_filter"]["state"] == "error" and "Not confirmed" in lk.result["fb_filter"]["msg"], (len(sent), lk.result.get("fb_filter")))
    sent.clear()
    for f, bad in (("slack_thr_nm", -0.01), ("slack_thr_nm", -6), ("slack_ms", 2.5), ("slack_ms", 600), ("slack_floor_nm", 4),
                   ("jam_apnm", 0.5), ("jam_ms", 5), ("fb_filter", 2), ("slack_floor_on", 0.5), ("jam_cut_on", -1)):
        r = lk.press(f, bad)
        check(f"5436 refused before sending: {f} = {bad}", not r["ok"], r)
    check("5436: nothing sent for refused values", not sent, sent)
    lk.pending.clear()
    echo["age"] = 2.0
    lk.tick()
    r = lk.press("jam_ms", 200)
    check("5436 stall: frozen, refused, nothing sent", lk.frozen and not r["ok"] and not sent, (lk.frozen, r, sent))
    echo["age"] = 0.01
    lk.tick()
    check("5436 back: re-adopted, unfrozen, nothing sent", not lk.frozen and not sent)
    echo["cols"] = 31
    check("5436 link inactive on 31 floats", not lk.active())


def fake_socket():
    import udp_settings as U
    from fake_run14 import FakeRun14
    dev = FakeRun14(settings_port=15450, console_port=15452, n_floats=44, side=0.0, mass=70.0, guard_port=15451)

    def echo():
        with dev.lock:
            return dict(dev.guard, guard_seq=dev.guard_seq), 0.01, 44
    lk = U.GuardLink({"udp": {"send_host": "127.0.0.1", "guard_port": 15451}}, echo, start_thread=False)
    lk.tick()
    lk.press("jam_apnm", 7.5)
    t0 = time.time()
    while time.time() - t0 < 0.5 and lk.result.get("jam_apnm", {}).get("state") != "confirmed":
        lk.tick()
        time.sleep(0.02)
    dev.close()
    check("fake run-16 device over UDP: one 48-byte packet applied and confirmed", dev.guard["jam_apnm"] == 7.5
          and lk.result["jam_apnm"]["state"] == "confirmed" and len(dev.guard_received) == 1, (dev.guard, lk.result))


class Cap(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, rec):
        self.lines.append((rec.levelname, rec.getMessage()))


def status_flags():
    from status import top_status
    from test_round5 import make_ctx
    cap = Cap()
    logging.getLogger("afo.status").addHandler(cap)
    logging.getLogger("afo.status").setLevel(logging.INFO)
    base = {"side": 0.0, "assist_mode": 3.0, "cmd_motor": 1.0, "cmd_assist": 1.0, "cmd_k": 1.0, "imu_ok": 1.0,
            "slack_flag": 0.0, "jam_flag": 0.0, "slack_count": 2.0, "slack_last_stride": 0.0, "guard_seq": 1.0}
    ctx = make_ctx({"connected": False, "running": False}, echo=dict(base))
    ctx.training.st["columns"] = 44
    st = top_status(ctx)
    keys = [i["key"] for i in st["issues"]]
    check("flags 0: no cable issue on the button", "cable-jam" not in keys and "cable-slack" not in keys, keys)
    check("popover note: cable slack events (slack_count)", any("Cable slack events: 2" in n for n in st["notes"]), st["notes"])
    ctx.training._latest.update(slack_flag=1.0, slack_count=3.0, slack_last_stride=1.0)
    st = top_status(ctx)
    check("slack_flag = 1: amber 'Cable slack' (now)", any(i["key"] == "cable-slack" and i["level"] == "amber" and i["text"] == "Cable slack"
                                                          for i in st["issues"]), (st["text"], st["issues"]))
    ctx.training._latest.update(jam_flag=1.0)
    st = top_status(ctx)
    jam = next((i for i in st["issues"] if i["key"] == "cable-jam"), {})
    check("jam_flag = 1: red 'Cable jam: torque cut' on the button, hint Motor off and on",
          st["text"] == "Cable jam: torque cut" and st["level"] == "red" and "Motor off and on" in jam.get("todo", ""), (st["text"], jam))
    ctx.training._latest.update(jam_flag=0.0, slack_flag=0.0)
    st = top_status(ctx)
    keys = [i["key"] for i in st["issues"]]
    check("flags back to 0: both gone at once (no latch on the page)", "cable-jam" not in keys and "cable-slack" not in keys, keys)
    logs = [m for lv, m in cap.lines if "flag" in m]
    check("flag changes logged (WARNING set, INFO cleared)", any(m.startswith("slack_flag set") for m in logs)
          and any(m.startswith("jam_flag set") for m in logs) and any(m.startswith("jam_flag cleared") for m in logs)
          and any(lv == "WARNING" for lv, m in cap.lines if m.startswith("jam_flag set")), cap.lines)


def page():
    import udp_settings as U
    from test_run14_layout import make_session
    from test_run15_layout import Dev31
    from fake_run14 import GUARD_FIELDS, GUARD_DEFAULTS

    class Dev44(Dev31):
        def __init__(self):
            super().__init__()
            self.guard, self.guard_seq = dict(zip(GUARD_FIELDS, GUARD_DEFAULTS)), 2.0
            self.gpk = []

        def recv(self, data, addr):
            if len(data) == 48:
                from fake_run14 import FakeRun14
                self.gpk.append(struct.unpack("<12f", data))
                FakeRun14.apply_guard(self, self.gpk[-1])
                return
            super().recv(data, addr)

        def status(self):
            st = super().status()
            if self.on:
                st["latest"].update(self.guard, guard_seq=self.guard_seq, slack_flag=0.0, jam_flag=0.0, slack_count=0.0,
                                    slack_last_stride=0.0)
                st["columns"] = 44
            return st
    dev, calls = Dev44(), []
    dev.v.update(side=0.0, weight_kg=80.0, bif_mass_kg=80.0, settings_seq=3.0)
    ctx, s = make_session(dev, calls)
    ctx.guard_link = U.GuardLink({"udp": {"send_host": "127.0.0.1", "guard_port": 15436}}, s.echo_for_link, sender=dev.recv)
    dev.on = True
    time.sleep(0.4)
    from pages import console_api as CA
    v = CA._guard_view(ctx)
    check("page state: guard udp + send on 44 floats, values from the echo, rules", v["udp"] and v["send"] and not v["frozen"]
          and v["values"]["jam_ms"] == 100.0 and v["rules"]["slack_ms"]["int"], v)
    check("44 floats: the run-15 Advanced profile stays on (>= 31)", s.adv_profile() and s.udp_profile(), s.echo_cols())
    dev.on = False
    time.sleep(0.9)
    v = CA._guard_view(ctx)
    check("stall: guard card frozen (profile sticky)", v["udp"] and v["frozen"], v)
    ctx.guard_link.stop()
    ctx.settings_link.stop()
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: Torque guard card in Advanced (hidden below 44 floats), checks before sending, posts /api/console/guard",
          'id="advGuard" hidden' in js and "fs.hidden = !gv.udp" in js and "var bad = guardCheck(f, v);" in js
          and "post('/api/console/guard'" in js and "renderGuard(st);" in js)
    api = open(os.path.join(APP, "pages", "console_api.py"), encoding="utf-8").read()
    check("api: /api/console/guard refuses a stalled echo and builds below 44 floats", '"/api/console/guard"' in api
          and "ctx.session.echo_stale()" in api and "Torque guard: not on this build" in api)
    app = open(os.path.join(APP, "app.py"), encoding="utf-8").read()
    check("app: GuardLink wired", "self.guard_link = GuardLink(" in app)


if __name__ == "__main__":
    layouts()
    receiver()
    guard_link()
    fake_socket()
    status_flags()
    page()
    print("FAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
