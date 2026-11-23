"""Run 14 go-live (safety-critical side): the page matches round1\\settings_udp_layout.json
and round1\\console_udp_layout.json EXACTLY. Seconds, no browser, no app server, no target.

- 5434 packet: 32 bytes, '<8f', magic 4134, version 1, field order as in the JSON;
- 5433: the layout's 'column' key (no 'index'), '<18f'; the receiver parses 18 floats (and
  still 12 / 15) with cols 12-17 bif_valid, bif_cal_progress, bif_bias_ready,
  gyro_cal_request, settings_seq, bif_mass_kg (pinned copies in test/fixtures since run 15
  replaced the round1 files; config/ now parses 12 / 15 / 18 / 31, see test_run15_layout);
- a side or mass press carries the ECHOED gyro_cal_request unchanged (any change re-runs
  the 5 s gyro bias), also after the device counter moved; only Calibrate IMU sends
  echoed + 1; nothing remembered is ever sent;
- field rules: side 0/1 (-1 = keep), mass 20..200, mode 1/3, K 0..10;
- /api/run/load: bad path 400, view-only 403, running 409; a valid target_build path loads.

    python test/test_run14_layout.py
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
import types

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import udp_settings as U  # noqa: E402

ROUND1 = os.path.join(os.path.dirname(APP), "round1") if os.path.isdir(os.path.join(os.path.dirname(APP), "round1")) \
    else r"C:\Users\Andy\Desktop\AFO\round1"
FIX = os.path.join(HERE, "fixtures")      # the run-14 layouts, pinned (round1 now has run 15)
FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def settings_packet():
    lay = json.load(open(os.path.join(FIX, "run14_settings_udp_layout.json"), encoding="utf-8"))
    names = [f["name"] for f in sorted(lay["fields"], key=lambda f: f["index"])]
    check("settings layout: '<8f', 32 B, port 5434", lay["format"] == "<8f" and lay["bytes"] == 32 and lay["port"] == 5434, lay)
    check("settings layout: field order", names == ["magic", "version", "seq", "side", "body_mass_kg", "assist_mode",
                                                    "fixed_k_pct", "gyro_cal_request"], names)
    check("page: '<8f' = 32 bytes, magic 4134, version 1", U.PACKET.format == "<8f" and U.PACKET.size == 32
          and (U.MAGIC, U.VERSION) == (4134.0, 1.0))
    echo = {"row": {"side": 1.0, "weight_kg": 70.0, "assist_mode": 3.0, "fixed_k_pct": 5.0, "gyro_cal_request": 7.0,
                    "settings_seq": 12.0, "bif_mass_kg": 70.0}}
    sent = []
    lk = U.SettingsLink({"udp": {"send_host": "127.0.0.1", "session_port": 15434}},
                        lambda: (dict(echo["row"]), 0.01, 18), sender=lambda data, addr: sent.append((data, addr)),
                        start_thread=False)
    lk.tick()                                      # adopt
    check("adopt: nothing sent", not sent, sent)
    lk.press("side", 0.0)
    data, addr = sent[-1]
    p = struct.unpack("<8f", data)
    check("side press: 32 bytes to session_port", len(data) == 32 and addr == ("127.0.0.1", 15434), (len(data), addr))
    check("side press: magic, version, seq 13, side 0, mass 70, mode 3, K 5", p[:7] == (4134.0, 1.0, 13.0, 0.0, 70.0, 3.0, 5.0), p)
    check("side press: gyro_cal_request = echoed 7 (unchanged)", p[7] == 7.0, p)
    echo["row"]["gyro_cal_request"] = 9.0          # the device counter moved (Calibrate elsewhere / Start)
    echo["row"]["side"] = 0.0; echo["row"]["settings_seq"] = 13.0
    lk.tick()
    lk.press("mass", 72.5)
    p = struct.unpack("<8f", sent[-1][0])
    check("mass press after the device counter moved: gyro = echoed 9 (never the remembered 7)", p[7] == 9.0 and p[4] == 72.5, p)
    echo["row"]["bif_mass_kg"] = 72.5; echo["row"]["weight_kg"] = 72.5; echo["row"]["settings_seq"] = 14.0
    lk.tick()
    lk.press("gyro", 123.0)                        # the caller's number is ignored
    p = struct.unpack("<8f", sent[-1][0])
    check("Calibrate IMU: gyro = echoed 9 + 1 = 10 (only change of the counter)", p[7] == 10.0 and p[3:7] == (0.0, 72.5, 3.0, 5.0), p)
    for f, bad in (("side", -1), ("side", 2), ("mass", 10), ("mass", 250), ("mode", 2), ("k", 11)):
        r = lk.press(f, bad)
        check(f"refused before sending: {f} {bad}", not r["ok"], r)
    # after Start the device shows side -1 / mass 0 (unset): the resend carries the page's values
    echo["row"].update(side=-1.0, bif_mass_kg=0.0, weight_kg=0.0, gyro_cal_request=0.0, settings_seq=0.0)
    lk.pending.clear(); lk.tick()
    pkt = lk.after_start()
    check("after Start: resend side 0 / mass 72.5, gyro = echoed 0 (no bias re-run)", pkt and pkt[3:5] == (0.0, 72.5) and pkt[7] == 0.0, pkt)


def console_parse():
    lay = json.load(open(os.path.join(FIX, "run14_console_udp_layout.json"), encoding="utf-8"))
    cols = lay["columns"]
    check("console layout: '<18f', 'column' key and no 'index'", lay["format"] == "<18f" and all("column" in c and "index" not in c for c in cols)
          and len(cols) == 18, lay["format"])
    names = [c["name"] for c in sorted(cols, key=lambda c: c["column"])]
    check("console layout: cols 12-17", names[12:] == ["bif_valid", "bif_cal_progress", "bif_bias_ready", "gyro_cal_request",
                                                       "settings_seq", "bif_mass_kg"], names[12:])
    cfg_lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    cfg_names = [c["name"] for c in sorted(cfg_lay["columns"], key=lambda c: c["column"])]
    check("config/console_udp_layout.json keeps the run-14 columns 0-17 unchanged", cfg_names[:18] == names, cfg_names[:18])
    import training_worker as TW
    _, tw_names = TW.load_layout(os.path.join(FIX, "run14_console_udp_layout.json"))
    check("receiver reads the 'column' key in order", tw_names == names, tw_names)
    out_q = Q.Queue()
    stop = threading.Event()
    tmp = tempfile.mkdtemp(prefix="afo_r14_")
    lay2 = dict(lay, port=15437)
    lp = os.path.join(tmp, "lay.json")
    json.dump(lay2, open(lp, "w"))
    threading.Thread(target=TW.worker_main, args=(lp, "127.0.0.1", out_q, Q.Queue(), Q.Queue(), stop, tmp), daemon=True).start()
    time.sleep(0.5)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    got = {}
    for n in (18, 15, 12):
        for k in range(15):
            row = [50.0 * n + k * 0.01, 1.0, 70.0, 3.0, 5.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0,
                   1.0, 0.5, 1.0, 7.0, 12.0, 70.0][:n]
            s.sendto(struct.pack(f"<{n}f", *row), ("127.0.0.1", 15437))
            time.sleep(0.01)
        time.sleep(0.12)
        last = None
        while True:
            try:
                kind, pl = out_q.get_nowait()
            except Q.Empty:
                break
            if kind == "hb":
                last = pl
        got[n] = ((last or {}).get("columns"), (last or {}).get("latest", {}))
    stop.set()
    check("receiver: 18, 15 and 12 floats accepted", [got[n][0] for n in (18, 15, 12)] == [18, 15, 12], {n: got[n][0] for n in got})
    l18 = got[18][1]
    check("receiver: 18 floats -> gyro_cal_request 7, settings_seq 12, bif_mass_kg 70",
          (l18.get("gyro_cal_request"), l18.get("settings_seq"), l18.get("bif_mass_kg")) == (7.0, 12.0, 70.0), l18)


def load_endpoint():
    import pages.shell as SH
    root = tempfile.mkdtemp(prefix="afo_root_")
    good = os.path.join(root, "round1", "target_build_run14", "AFO_r1.mldatx")
    os.makedirs(os.path.dirname(good))
    open(good, "wb").write(b"x")
    cfg = {"paths": {"afo_root": root}}
    check("load path: valid build accepted", SH.load_path_ok(cfg, good) == os.path.realpath(good))
    for bad in (os.path.join(root, "round1", "AFO_r1.mldatx"), os.path.join(root, "round1", "target_build_x", "other.mldatx"),
                os.path.join(root, "round1", "target_build_run14", "..", "..", "evil", "AFO_r1.mldatx"),
                os.path.join(root, "round1", "target_build_missing", "AFO_r1.mldatx"), r"C:\Windows\notepad.exe", "", None):
        check(f"load path refused: {bad!r:.60}", SH.load_path_ok(cfg, bad) is None)
    # the checks the route runs (load_request), and that the route uses them
    ctx = types.SimpleNamespace(cfg=dict(cfg), runctl=types.SimpleNamespace(status={"connected": True, "running": False}))
    code, p = SH.load_request(ctx, {"file": good})
    check("load: valid path -> 200 with the resolved file", code == 200 and p["file"] == os.path.realpath(good), (code, p))
    code, p = SH.load_request(ctx, {"file": "C:/Windows/notepad.exe"})
    check("load: bad path -> 400", code == 400, (code, p))
    ctx.runctl.status["running"] = True
    code, p = SH.load_request(ctx, {"file": good})
    check("load: while running -> 409 'stop it before loading'", code == 409 and "stop it before loading" in p["err"], (code, p))
    ctx.runctl.status["running"] = False
    ctx.cfg["console"] = {"view_only": True}
    code, p = SH.load_request(ctx, {"file": good})
    check("load: view-only -> 403", code == 403, (code, p))
    src = open(SH.__file__, encoding="utf-8").read()
    check("route: /api/run/load uses load_request and run_action('load', path)", '"save", "load")' in src
          and "code, payload = load_request(ctx, request.get_json(silent=True) or {})" in src
          and 'args = [payload["file"]]' in src and "ctx.runctl.run_action(action, *args)" in src)


class Dev:
    """In-process run-14 device: applies 5434 packets by the model's rules, echoes 18 floats."""
    def __init__(self, cols=18):
        self.cols, self.on = cols, False
        self.v = {"side": -1.0, "weight_kg": 0.0, "assist_mode": 3.0, "fixed_k_pct": 5.0, "gyro_cal_request": 0.0,
                  "settings_seq": 0.0, "bif_mass_kg": 0.0, "cmd_motor": 0.0}
        self.packets = []

    def recv(self, data, addr):
        self.packets.append(struct.unpack("<8f", data))
        p = self.packets[-1]
        if len(data) != 32 or p[0] != 4134.0 or p[1] != 1.0 or self.cols != 18:
            return
        self.v["settings_seq"] = p[2]
        if p[3] in (0.0, 1.0):
            self.v["side"] = p[3]
        if 20.0 <= p[4] <= 200.0:
            self.v["weight_kg"] = self.v["bif_mass_kg"] = p[4]
        if p[5] in (1.0, 3.0):
            self.v["assist_mode"] = p[5]
        if 0.0 <= p[6] <= 10.0:
            self.v["fixed_k_pct"] = p[6]
        self.v["gyro_cal_request"] = p[7]

    def status(self):
        if not self.on:
            return {"latest": {}, "age_s": None, "columns": None}
        row = dict(self.v)
        if self.cols != 18:
            for k in ("gyro_cal_request", "settings_seq", "bif_mass_kg"):
                row.pop(k)
        return {"latest": row, "age_s": 0.01, "columns": self.cols}


def make_session(dev, calls):
    import session as S
    from test_round5 import Cmd
    tmp = tempfile.mkdtemp(prefix="afo_r14s_")

    class Jobs:
        def running(self, kind):
            return None

        def start(self, kind, title, fn):
            calls.append(("job", title))
            fn(types.SimpleNamespace(add=lambda l: None, meta={}))
            return types.SimpleNamespace(id=1)
    ml = types.SimpleNamespace(call=lambda fn, action, *a, **k: calls.append(("matlab", action, a)) or
                               json.dumps({"ok": True, "readback": a[-1] if a else 0}))
    tr = types.SimpleNamespace(get_status=dev.status, latest=lambda max_age_s=1.0: dev.status()["latest"])
    tr.last_hb = time.monotonic()
    ctx = types.SimpleNamespace(app_dir=tmp, cfg={"paths": {"log_dir": tmp}, "target": {"model": "AFO_r1"},
                                                  "session": {"target_writes_enabled": True}},
                                runctl=types.SimpleNamespace(status={"connected": True, "running": True, "app": "AFO_r1"}),
                                jobs=Jobs(), commands=Cmd(), matlab=ml, training=tr)
    s = S.SessionSetup(ctx)
    ctx.session = s
    s.set_sid("S1")
    s.values.update(side=0, weight=83.0, mode=3, k_percent=5.0)
    s.src.update(side="entered", weight="entered", bif_mass="entered", mode="entered", k_percent="entered")
    s.side_confirmed = {"sid": "S1", "side": 0, "at": time.time()}
    s.adopted_echo = True

    def hb():                                    # keep the fake heartbeat fresh
        while True:
            tr.last_hb = time.monotonic()
            time.sleep(0.02)
    threading.Thread(target=hb, daemon=True).start()
    ctx.settings_link = U.SettingsLink({"udp": {"send_host": "127.0.0.1", "session_port": 15434}}, s.echo_for_link,
                                       on_status=s.link_status, on_adopt=s.link_adopted, sender=dev.recv)
    return ctx, s


def page_start():
    import session as S
    # (1) 18 floats: Start, the echo comes 0.4 s later showing the reloaded device (side -1, mass 0)
    dev, calls = Dev(18), []
    ctx, s = make_session(dev, calls)
    s.after_connect_or_start("start")
    time.sleep(0.4)
    dev.on = True
    t0 = time.time()
    while time.time() - t0 < 3 and not (dev.v["bif_mass_kg"] == 83.0 and dev.v["side"] == 0.0):
        time.sleep(0.02)
    check("page Start (18 floats): device gets mass 83 and side LEFT over 5434", dev.v["bif_mass_kg"] == 83.0
          and dev.v["weight_kg"] == 83.0 and dev.v["side"] == 0.0, dev.v)
    check("page Start: exactly one packet (no retry needed), gyro = echoed 0", len(dev.packets) == 1 and dev.packets[0][7] == 0.0,
          dev.packets)
    check("page Start: not adopted (page still shows 83, not the device's 0)", s.values.get("weight") == 83.0, s.values)
    check("page Start: no MATLAB call", not [c for c in calls if c[0] == "matlab"], calls)
    t1 = time.time()
    while time.time() - t1 < 1.5 and (s.status.get("weight") or {}).get("state") != "confirmed":
        time.sleep(0.02)
    check("page Start: mass confirmed by the echo", (s.status.get("weight") or {}).get("state") == "confirmed", s.status.get("weight"))
    ctx.settings_link.stop()
    # side not confirmed this session: mass is sent, side is not
    dev, calls = Dev(18), []
    ctx, s = make_session(dev, calls)
    s.side_confirmed = None
    s.after_connect_or_start("start")
    dev.on = True
    time.sleep(0.6)
    check("page Start, side not confirmed: mass sent, side kept (-1)", dev.v["bif_mass_kg"] == 83.0 and dev.v["side"] == -1.0
          and dev.packets and dev.packets[0][3] == -1.0, dev.packets)
    ctx.settings_link.stop()
    # (1b) 15 floats (run <= 13): setparam, side AND mass
    dev, calls = Dev(15), []
    ctx, s = make_session(dev, calls)
    s.entered.clear()                             # nothing entered since start: mass must still go
    s.after_connect_or_start("start")
    dev.on = True
    time.sleep(0.8)
    sets = [c[1] for c in calls if c[0] == "job"]
    check("page Start (15 floats): setparam side AND mass", "set side" in sets and "set weight" in sets, sets)
    check("page Start (15 floats): nothing on 5434", not dev.packets, dev.packets)
    ctx.settings_link.stop()
    # (2) reconnect / reload (no page Start) onto a device with mass 0: amber, page value kept
    dev, calls = Dev(18), []
    dev.v.update(side=0.0, assist_mode=3.0)
    ctx, s = make_session(dev, calls)
    dev.on = True
    time.sleep(0.4)
    st = s.status.get("weight") or {}
    check("adopt onto mass 0: 'Not set on device: press to send' (amber pending), page value kept",
          st.get("state") == "pending" and st.get("msg") == S.NOT_ON_DEVICE and s.values.get("weight") == 83.0, (st, s.values))
    check("adopt: nothing sent", not dev.packets, dev.packets)
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: Mass tag 'not on device' for that state", "/Not set on device/.test(mmsg) ? 'not on device'" in js)
    ctx.settings_link.stop()


def fresh_session(dev, calls):
    """A page / server restart: no S-ID values, nothing entered, nothing adopted yet."""
    ctx, s = make_session(dev, calls)
    s.values.clear(); s.src.clear(); s.entered.clear(); s.side_confirmed = None; s.adopted_echo = False
    return ctx, s


def mass_defaults():
    """14:26 live: run 13's built weight 55 (15-float col 2) was adopted as the mass and sent to
    run 14 after the page Start; the user's 83 was lost."""
    import session as S
    # (1) 15 floats: col 2 weight is never adopted as a mass
    dev, calls = Dev(15), []
    dev.v.update(side=-1.0, weight_kg=55.0, assist_mode=1.0, fixed_k_pct=2.0)      # run 13 in use: mode 1, K 2
    ctx, s = fresh_session(dev, calls)
    dev.on = True
    s.adopt_echo()
    check("15 floats: weight_kg 55 NOT adopted as the mass", s.values.get("weight") is None and "weight" not in s.src,
          (s.values, s.src))
    check("15 floats: mode / K shown but marked adopted15 (never sent)", s.src.get("mode") == "adopted15", s.src)
    ctx.settings_link.stop()
    # the 14:26 sequence: run 13 adopted, then a page Start onto run 14 (18 floats, reloaded)
    dev.cols = 18
    dev.v.update(side=-1.0, weight_kg=0.0, bif_mass_kg=0.0, gyro_cal_request=0.0, settings_seq=0.0,
                 assist_mode=3.0, fixed_k_pct=5.0)                                  # run 14 reloaded: mode 3, K 5
    ctx.settings_link = U.SettingsLink({"udp": {"send_host": "127.0.0.1", "session_port": 15434}}, s.echo_for_link,
                                       on_status=s.link_status, on_adopt=s.link_adopted, sender=dev.recv)
    s.after_connect_or_start("start")
    time.sleep(0.8)
    p = dev.packets[0] if dev.packets else None
    check("page Start after a run-13 adopt: mass NOT sent (0 = keep), never 55", p is not None and p[4] == 0.0, dev.packets)
    check("... mode / K: the run-14 device's own values (3, 5), never run-13 memory (1, 2)",
          p is not None and (p[5], p[6]) == (3.0, 5.0), p)
    check("... device mass stays unset (not 55)", dev.v["bif_mass_kg"] == 0.0, dev.v)
    check("... amber 'Mass not set'", (s.status.get("weight") or {}).get("msg") == S.MASS_NOT_SET, s.status.get("weight"))
    ctx.settings_link.stop()
    # (3) entered this page session for this S-ID: sent
    dev, calls = Dev(18), []
    ctx, s = fresh_session(dev, calls)
    s.set_sid("S2")
    s.enter_value("weight", 83.0)
    s.after_connect_or_start("start")
    dev.on = True
    time.sleep(0.8)
    check("entered 83 this session: sent after Start", dev.v["bif_mass_kg"] == 83.0, dev.packets)
    ctx.settings_link.stop()
    # (2) 18 floats: mass only from col 17 (> 0)
    for col17, want in ((70.0, 70.0), (0.0, None)):
        dev, calls = Dev(18), []
        dev.v.update(side=0.0, weight_kg=55.0, bif_mass_kg=col17)
        ctx, s = fresh_session(dev, calls)
        dev.on = True
        time.sleep(0.4)
        check(f"18 floats, col 17 = {col17:g} (col 2 = 55): adopted mass {want}", s.values.get("weight") == want
              and (s.src.get("weight") == "adopted18") == (want is not None), (s.values, s.src))
        ctx.settings_link.stop()
    # adopted from a valid col 17: resent after a page Start
    dev, calls = Dev(18), []
    dev.v.update(side=0.0, bif_mass_kg=70.0, weight_kg=70.0)
    ctx, s = fresh_session(dev, calls)
    dev.on = True
    time.sleep(0.4)
    dev.v.update(side=-1.0, bif_mass_kg=0.0, weight_kg=0.0)        # the Start reloads the device
    s.after_connect_or_start("start")
    time.sleep(0.8)
    check("adopted from col 17 (70): resent after Start", dev.v["bif_mass_kg"] == 70.0, dev.packets)
    ctx.settings_link.stop()
    # 15-float page Start without an entered mass: setparam of the side only, never a default mass
    dev, calls = Dev(15), []
    dev.v.update(weight_kg=55.0)
    ctx, s = fresh_session(dev, calls)
    s.set_sid("S3"); s.confirm_side("LEFT", "S3"); calls.clear()
    s.after_connect_or_start("start")
    dev.on = True
    time.sleep(0.8)
    sets = [c[1] for c in calls if c[0] == "job"]
    check("15 floats, mass never entered: no 'set weight' (no default)", "set weight" not in sets and "set side" in sets, sets)
    ctx.settings_link.stop()
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("design v17: no check marks; 'Confirmed by device' in the tooltips", "✓" not in js
          and "mass.title = 'Confirmed by device (5433 echo)'" in js and "'Confirmed by device (5433 echo)' : 'Foot side on the target'" in js)


def main():
    settings_packet()
    console_parse()
    page_start()
    mass_defaults()
    load_endpoint()
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
