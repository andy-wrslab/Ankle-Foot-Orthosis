"""Run 15 (Advanced over UDP): the page matches round1\\console_udp_layout.json ('<31f') and
round1\\settings_adv_udp_layout.json (5435) EXACTLY. Seconds, no browser, no app server,
no target, a few packets on test ports only.

- 5433 '<31f': cols 0-17 = run 14 unchanged; 18-28 = the 11 Advanced values in use in the
  order of settings_adv_udp_layout.json; 29 adv_seq; 30 spring_stiffness (ignored);
- config/ copies = round1; the receiver parses 31, 18, 15 and 12 floats;
- 31 floats: the Advanced values come from the echo (no getparam, nothing setparam'd), the
  page adopts them, spring stiffness never shows; nothing is sent on connect / refresh;
- 18 floats: getparam for Advanced as on run 14.
- (B) 5435: one '<16f' 64-byte packet per edit (magic 4135, v1, seq = adv_seq + 1, all 11
  in-use values with only the edited one changed, [14] / [15] = 0), fast confirm from the
  echo, max 3 retries in 1 s, frozen on a stall, range / whole-number / min < max checks.

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
    # the run-15 console layout, pinned (round1 moved on to run 16, '<44f')
    con = json.load(open(os.path.join(FIX, "run15_console_udp_layout.json"), encoding="utf-8"))
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
    for f in ("settings_adv_udp_layout.json", "settings_udp_layout.json"):
        a = json.load(open(os.path.join(APP, "config", f), encoding="utf-8"))
        b = json.load(open(os.path.join(ROUND1, f), encoding="utf-8"))
        if f == "settings_adv_udp_layout.json":
            # Andy 16:31: the standing-still cutoff may be 0 (0..5000); round1 matches once the
            # Simulink thread's rebuilt layout lands, until then only that rule may differ
            cut = [x["rule"] for x in a["fields"] if x["name"] == "standing_still_cutoff"]
            check("config: standing-still cutoff 0..5000", cut == ["0..5000 (threshold_pressure); else keep"], cut)
            for lay in (a, b):
                for x in lay["fields"]:
                    if x["name"] == "standing_still_cutoff":
                        x["rule"] = "0..5000 (threshold_pressure); else keep"
        check(f"config/{f} = round1 copy", a == b)
    cfg = names_of(json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8")))
    check("config/console_udp_layout.json keeps the run-15 columns 0-30", cfg[:31] == n, cfg[:31])


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

    def recv(self, data, addr):
        if len(data) == 64:                          # 5435 Advanced
            from fake_run14 import FakeRun14
            self.adv_packets = getattr(self, "adv_packets", []) + [struct.unpack("<16f", data)]
            if self.cols31 == 31:
                FakeRun14.apply_adv(self, self.adv_packets[-1])
            return
        super().recv(data, addr)

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


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def adv_link():
    import udp_settings as U
    from fake_run14 import ADV_FIELDS, ADV_DEFAULTS
    row = dict(zip(ADV_FIELDS, ADV_DEFAULTS), adv_seq=7.0, spring_stiffness=1.25, settings_seq=3.0)
    echo = {"row": row, "age": 0.01, "cols": 31}
    sent = []
    lk = U.AdvLink({"udp": {"send_host": "127.0.0.1", "adv_port": 15435}},
                   lambda: (dict(echo["row"]), echo["age"], echo["cols"]),
                   sender=lambda data, addr: sent.append((data, addr)), start_thread=False,
                   layout_path=os.path.join(APP, "config", "settings_adv_udp_layout.json"))   # the page copy (cutoff 0..5000)
    check("5435 link: fields in the round1 layout order", list(lk.FIELDS) == ADV_FIELDS, lk.FIELDS)
    lk.tick()
    check("5435: adopt from the echo, nothing sent", not sent and lk.state.get("torque_p_gain") == 0.6, (sent, lk.state))
    r = lk.press("torque_p_gain", 0.9)
    check("5435 press: accepted, sending", r["ok"] and r["state"] == "sending", r)
    data, addr = sent[-1]
    p = struct.unpack("<16f", data)
    check("5435 packet: 64 bytes to adv_port", len(data) == 64 and addr == ("127.0.0.1", 15435), (len(data), addr))
    check("5435 packet: magic 4135, version 1, seq = adv_seq 7 + 1", p[:3] == (4135.0, 1.0, 8.0), p[:3])
    want = [f32(v) for v in ADV_DEFAULTS]
    want[ADV_FIELDS.index("torque_p_gain")] = f32(0.9)
    check("5435 packet: all 11 in-use values, only P gain changed", list(p[3:14]) == want, (p[3:14], want))
    check("5435 packet: [14] reserved_spring and [15] reserved = 0", p[14:] == (0.0, 0.0), p[14:])
    row.update(torque_p_gain=f32(0.9), adv_seq=8.0)
    lk.tick()
    check("5435: confirmed from the echo (value + adv_seq >= seq), no resend",
          lk.result["torque_p_gain"]["state"] == "confirmed" and len(sent) == 1, (lk.result, len(sent)))
    # no echo of the next press: 3 retries within 1 s, then "Not confirmed"
    sent.clear()
    lk.press("standing_still_cutoff", 300)
    t0 = time.time()
    while time.time() - t0 < 1.2:
        lk.tick()
        time.sleep(0.02)
    i_cut = 3 + ADV_FIELDS.index("standing_still_cutoff")
    check("5435: max 3 retries (4 packets) within 1 s, each with the same values",
          len(sent) == 4 and all(struct.unpack("<16f", d)[i_cut] == 300.0 for d, a in sent),
          (len(sent), [struct.unpack("<16f", d)[2] for d, a in sent]))
    check("5435: then 'Not confirmed: no echo from model'", lk.result["standing_still_cutoff"]["state"] == "error"
          and "Not confirmed" in lk.result["standing_still_cutoff"]["msg"], lk.result["standing_still_cutoff"])
    # the layout's rules (also checked on the page): nothing sent when refused
    sent.clear()
    for f, bad in (("sv_target_min", 0.1), ("sv_target_max", 2.5), ("target_step_up", 0.6), ("step_up_window", 2.5),
                   ("step_down_window", 61), ("high_assist_strides", 10.5), ("torque_p_gain", 0.01), ("torque_i_gain", 6),
                   ("standing_still_cutoff", 5001), ("sv_target_min", 1.5), ("sv_target_max", 0.8)):
        r = lk.press(f, bad)
        check(f"5435 refused before sending: {f} = {bad}", not r["ok"], r)
    check("5435: nothing sent for refused values", not sent, sent)
    r = lk.press("step_up_window", 25)
    check("5435: a whole number in range is sent", r["ok"] and len(sent) == 1, r)
    r = lk.press("standing_still_cutoff", 0)
    check("5435: standing-still cutoff 0 is allowed and sent (Andy 16:31)", r["ok"] and len(sent) == 2
          and struct.unpack("<16f", sent[-1][0])[3 + ADV_FIELDS.index("standing_still_cutoff")] == 0.0, r)
    # stall: frozen, nothing sent; back: re-adopt, nothing sent
    lk.pending.clear()
    sent.clear()
    echo["age"] = 2.0
    lk.tick()
    r = lk.press("torque_i_gain", 1.0)
    check("5435 stall: frozen, press refused, nothing sent", lk.frozen and not r["ok"] and not sent, (lk.frozen, r, sent))
    echo["age"] = 0.01
    lk.tick()
    check("5435 back: re-adopted and unfrozen, nothing sent", not lk.frozen and lk.state is not None and not sent,
          (lk.frozen, sent))
    # 18 floats (run 14): not active, never sends
    echo["cols"] = 18
    check("5435 link inactive on 18 floats", not lk.active())
    lk.tick()
    r = lk.press("torque_i_gain", 1.0)
    check("5435 on 18 floats: nothing sent", not sent and not r["ok"], (r, sent))


def session_send():
    import udp_settings as U
    dev, calls = Dev31(), []
    dev.v.update(side=0.0, weight_kg=80.0, bif_mass_kg=80.0, settings_seq=3.0)
    ctx, s = make_session(dev, calls)
    ctx.adv_link = U.AdvLink({"udp": {"send_host": "127.0.0.1", "adv_port": 15435}}, s.echo_for_link,
                             on_status=s.adv_link_status, on_adopt=s.adv_link_adopted, sender=dev.recv)
    dev.on = True
    time.sleep(0.4)
    s.refresh_echo()
    calls.clear()
    msg = s.enter_value("i_gain", 1.1)
    check("session 31 floats: Advanced edit goes over 5435 (no MATLAB)", "sending" in msg
          and not [c for c in calls if c[0] == "matlab"], (msg, calls))
    t0 = time.time()
    while time.time() - t0 < 1.0 and (s.status.get("i_gain") or {}).get("state") != "confirmed":
        time.sleep(0.02)
    s.refresh_echo()
    check("session: confirmed from the echo within 1 s; readback 1.1",
          (s.status.get("i_gain") or {}).get("state") == "confirmed" and abs(s.readback.get("i_gain") - f32(1.1)) < 1e-6,
          (s.status.get("i_gain"), s.readback.get("i_gain")))
    pk = dev.adv_packets[-1]
    check("session: one packet, seq = adv_seq 3 + 1, the other values = the device's", len(dev.adv_packets) == 1
          and pk[2] == 4.0 and pk[3 + 9] == f32(1.1) and pk[3 + 8] == f32(0.6), dev.adv_packets)
    msg = s.enter_value("sv_target_min", 1.6)
    check("session: min >= max refused with the reason, nothing sent", "below the max" in msg and len(dev.adv_packets) == 1, msg)
    from pages import console_api as CA
    v = CA._adv_view(ctx)
    check("page state: adv udp + send on, rules from the layout", v["udp"] and v["send"]
          and v["rules"]["window_up"] == {"min": 1.0, "max": 60.0, "int": True} and v["rules"]["sv_target_min"]["min"] == 0.2, v)
    ctx.adv_link.stop()
    ctx.settings_link.stop()
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: client-side range / whole number / min < max before sending", "function advCheck(k, v)" in js
          and "r.int && f !== Math.round(f)" in js and "var bad = advCheck(k, v);" in js)
    app = open(os.path.join(APP, "app.py"), encoding="utf-8").read()
    check("app: AdvLink wired", "self.adv_link = AdvLink(" in app and "on_status=self.session.adv_link_status" in app)


def fake_socket():
    """Real UDP round trip with the fake run-15 device (0.5 s, test ports)."""
    import udp_settings as U
    from fake_run14 import FakeRun14, ADV_FIELDS
    dev = FakeRun14(settings_port=15440, console_port=15442, n_floats=31, side=0.0, mass=70.0, adv_port=15441)

    def echo():
        with dev.lock:
            return dict(dev.adv, adv_seq=dev.adv_seq), 0.01, 31
    lk = U.AdvLink({"udp": {"send_host": "127.0.0.1", "adv_port": 15441}}, echo, start_thread=False)
    lk.tick()
    lk.press("high_assist_level", 7.5)
    t0 = time.time()
    while time.time() - t0 < 0.5 and lk.result.get("high_assist_level", {}).get("state") != "confirmed":
        lk.tick()
        time.sleep(0.02)
    dev.close()
    check("fake run-15 device over UDP: one 64-byte packet applied and confirmed", dev.adv["high_assist_level"] == 7.5
          and lk.result["high_assist_level"]["state"] == "confirmed" and len(dev.adv_received) == 1, (dev.adv, lk.result))


def cloud_fixes():
    """The 3 failures the cloud suite found in aad9345."""
    import udp_settings as U
    from pages import console_api as CA
    # 1) 5433 stall on a 31-float build: the profile stays (sticky); Advanced locked; no setparam / UDP
    dev, calls = Dev31(), []
    dev.v.update(side=0.0, weight_kg=80.0, bif_mass_kg=80.0, settings_seq=3.0)
    ctx, s = make_session(dev, calls)
    ctx.adv_link = U.AdvLink({"udp": {"send_host": "127.0.0.1", "adv_port": 15435}}, s.echo_for_link,
                             on_status=s.adv_link_status, on_adopt=s.adv_link_adopted, sender=dev.recv)
    dev.on = True
    time.sleep(0.4)
    s.refresh_echo()
    check("31 floats: run-15 profile known", s.adv_profile() and s.echo_cols() == 31, s.echo_cols())
    dev.on = False                                   # 5433 stalls
    time.sleep(0.9)
    v = CA._adv_view(ctx)
    check("stall (< 1 s): profile stays run 15 (sticky), popover locked (frozen)", v["udp"] and v["frozen"] and s.adv_profile(), v)
    calls.clear()
    n_adv = len(getattr(dev, "adv_packets", []))
    n_set = len(dev.packets)
    msg = s.enter_value("p_gain", 0.9)
    check("stall: an Advanced edit is refused server-side (no setparam, no 5435)",
          "No data from device" in msg and not [c for c in calls if c[0] == "matlab"]
          and len(getattr(dev, "adv_packets", [])) == n_adv, (msg, calls))
    check("stall: getparam keys stay empty (no Advanced getparam fallback)", s.getparam_keys() == [], s.getparam_keys())
    msg = s.enter_value("weight", 75.0)
    check("stall: a settings edit (mass) is refused too, nothing sent (5434 sticky)", "No data from device" in msg
          and len(dev.packets) == n_set and not [c for c in calls if c[0] == "matlab"], (msg, dev.packets[n_set:], calls))
    dev.on = True                                    # echo back
    time.sleep(0.4)
    v = CA._adv_view(ctx)
    check("echo back: unfrozen, editable again", v["udp"] and not v["frozen"] and v["send"], v)
    ctx.adv_link.stop()
    ctx.settings_link.stop()

    # 2) 18-float device + MATLAB connected: Advanced editable by setparam as before
    dev18, calls18 = Dev(18), []
    dev18.v.update(side=0.0, weight_kg=80.0, bif_mass_kg=80.0, settings_seq=3.0)
    ctx18, s18 = make_session(dev18, calls18)
    dev18.on = True
    time.sleep(0.3)
    s18.refresh_echo()
    v = CA._adv_view(ctx18)
    check("18 floats: adv {udp: false} (the run-14 path)", v["udp"] is False and v["frozen"] is False, v)
    calls18.clear()
    msg = s18.enter_value("p_gain", 0.9)
    sets = [c for c in calls18 if c[0] == "matlab" and c[1] == "set"]
    check("18 floats + connected: an Advanced edit goes by setparam", sets and "P" in str(sets[0]), (msg, calls18))
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: static read-only by data-ro, never by the readonly attribute (.readOnly = true adds it)",
          "hasAttribute('readonly')" not in js and "inp.readOnly = inp.getAttribute('data-ro') === '1';" in js
          and "if (inp.getAttribute('data-ro') === '1') { return; }" in js)
    ctx18.settings_link.stop()
    # an unknown echo on an r1 model: no Advanced setparam
    dev0, calls0 = Dev(18), []
    ctx0, s0 = make_session(dev0, calls0)
    calls0.clear()
    msg = s0.enter_value("p_gain", 0.9)
    check("r1 model, echo never seen: no Advanced setparam ('Waiting for the device echo')",
          "Waiting for the device echo" in msg and not [c for c in calls0 if c[0] == "matlab" and c[1] == "set"], (msg, calls0))
    ctx0.settings_link.stop()

    # 3) display rounding per field, never float32 noise
    f = CA._fmt
    check("popover: speeds 2 decimals (0.800000011920929 -> 0.8)", f("sv_target_min", 0.800000011920929) == "0.8"
          and f("sv_target_max", 1.5049999952316284) == "1.5", (f("sv_target_min", 0.800000011920929), f("sv_target_max", 1.5049999952316284)))
    check("popover: gains 2, steps 3", f("p_gain", 0.6000000238418579) == "0.6" and f("i_gain", 1.100000023841858) == "1.1"
          and f("target_step_up", 0.03999999910593033) == "0.04" and f("target_step_down", 0.0825) == "0.083",
          (f("p_gain", 0.6000000238418579), f("target_step_down", 0.0825)))
    check("popover: windows / strides / level / cutoff as integers", f("window_up", 20.0) == "20" and f("min_cycles", 10.0) == "10"
          and f("assist_threshold", 9.0) == "9" and f("threshold_pressure", 200.00000001) == "200", f("window_up", 20.0))
    check("page: per-field decimals in the Advanced inputs (advFmt)", "function advFmt(k, v)" in js
          and "var tu = advFmt(k, v);" in js and "var t = advFmt(k, v);" in js
          and "sv_target_min: 2" in js and "target_step_up: 3" in js and "window_up: 0" in js)


if __name__ == "__main__":
    layouts()
    receiver()
    session_31()
    adv_link()
    session_send()
    fake_socket()
    cloud_fixes()
    print("FAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
