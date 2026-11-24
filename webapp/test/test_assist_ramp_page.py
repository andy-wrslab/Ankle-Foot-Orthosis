"""Page side of the run-16g assist fade-in (Andy Nov 24 16:00-16:27), offline (in-process fake
device, no sockets to the Speedgoat):
- 5433 echo '<47f': col 45 assist_ramp_step in use, col 46 assist_ramp_cap now;
- 5435 [14] = assist_ramp_step: on a 47-float build every Advanced Confirm sends the ECHOED step
  (an unrelated Confirm never switches the fade-in off); on a 45-float build (16f) [14] stays 0;
- the Advanced field "Assist ramp per step" goes through Confirm (one packet), 0..10, a value
  outside is refused; the cap is read-only (never sent);
- both rows show only when the device echoes them.

    python test/test_assist_ramp_page.py
"""
import json
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import _lowprio  # noqa: E402,F401

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def layouts():
    import echo_sizes as ES
    check("echo sizes: ... 45, 47", ES.ECHO_SIZES[-2:] == (45, 47) and ES.RAMP_MIN == 47, ES.ECHO_SIZES)
    con = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    cols = {c["column"]: c["name"] for c in con["columns"]} if "columns" in con else {}
    check("page console layout '<47f': col 45 assist_ramp_step, col 46 assist_ramp_cap",
          con["format"] == "<47f" and cols.get(45) == "assist_ramp_step" and cols.get(46) == "assist_ramp_cap", (con["format"], cols.get(45), cols.get(46)))
    adv = json.load(open(os.path.join(APP, "config", "settings_adv_udp_layout.json"), encoding="utf-8"))
    f14 = [f for f in adv["fields"] if f["index"] == 14]
    check("page 5435 layout: [14] = assist_ramp_step, 0..10", f14 and f14[0]["name"] == "assist_ramp_step" and "0..10" in f14[0]["rule"], f14)
    r1 = os.path.join(os.path.dirname(APP), "round1")
    if os.path.isdir(r1):
        for n in ("settings_adv_udp_layout.json", "console_udp_layout.json"):
            a = json.load(open(os.path.join(APP, "config", n), encoding="utf-8"))
            b = json.load(open(os.path.join(r1, n), encoding="utf-8"))
            check(f"page copy of {n} == round1 (16g)", a == b)


def link_packets():
    import udp_settings as U
    from fake_run14 import ADV_FIELDS, ADV_DEFAULTS
    for cols, step, want14 in ((47, 1.0, 1.0), (47, 2.5, 2.5), (45, None, 0.0)):
        row = dict(zip(ADV_FIELDS, ADV_DEFAULTS), adv_seq=7.0, spring_stiffness=1.25, standstill_fade_ms=200.0)
        if step is not None:
            row.update(assist_ramp_step=step, assist_ramp_cap=0.0)
        sent = []
        lk = U.AdvLink({"udp": {"send_host": "127.0.0.1", "adv_port": 15435}}, lambda r=row, c=cols: (dict(r), 0.01, c),
                       sender=lambda data, addr: sent.append(struct.unpack("<16f", data)), start_thread=False,
                       layout_path=os.path.join(APP, "config", "settings_adv_udp_layout.json"))
        lk.tick()
        r = lk.press_many({"torque_p_gain": 0.5})
        p = sent[-1] if sent else None
        check(f"{cols} floats (step in use {step}): an unrelated Confirm (P 0.5) sends [14] = {want14}",
              r["ok"] and p is not None and p[14] == f32(want14) and p[11] == f32(0.5), p)
        if cols == 47:
            sent.clear()
            r = lk.press_many({"assist_ramp_step": 0.5})
            check(f"47 floats: Confirm of the ramp step 0.5 -> one packet, [14] = 0.5, the rest as before",
                  r["ok"] and len(sent) == 1 and sent[0][14] == 0.5 and sent[0][3] == f32(0.8), sent)
            sent.clear()
            for bad in (10.5, -1):
                r = lk.press_many({"assist_ramp_step": bad})
                check(f"47 floats: ramp step {bad} refused, nothing sent", not r["ok"] and not sent, (r, sent))
            r = lk.press_many({"assist_ramp_cap": 3})
            check("the cap is not a setting (refused, nothing sent)", not r["ok"] and not sent, (r, sent))


def session_and_page():
    import session as S
    check("session: 'Assist ramp per step' 0..10 (UDP only), 'Ramp cap' read-only",
          any(sp["key"] == "assist_ramp_step" and sp["min"] == 0 and sp["max"] == 10 for sp in S.SPECS)
          and any(sp["key"] == "assist_ramp_cap" and sp.get("readonly") for sp in S.SPECS))
    check("session: both optional in the Advanced echo (a 45-float build keeps its Advanced profile)",
          {"assist_ramp_step", "assist_ramp_cap"} <= set(S.SessionSetup.ADV_OPTIONAL))
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("Advanced: 'Assist ramp per step' (%) and read-only 'Ramp cap' rows, no help text",
          "['assist_ramp_step', 'Assist ramp per step', '%']," in js and "['assist_ramp_cap', 'Ramp cap', '%', '', true]" in js)
    check("Advanced: the rows show only when the device echoes them",
          "if (k === 'fade_ms' || k === 'assist_ramp_step' || k === 'assist_ramp_cap') {" in js
          and "has = advUdp && (sv.readback || {})[k] != null;" in js)
    check("Advanced: the ramp step goes through Confirm like the others (read-only rows never staged)",
          "if (inp.getAttribute('data-ro') === '1') { return; }" in js)


layouts()
link_packets()
session_and_page()
print("\nFAILS:", FAILS)
sys.exit(1 if FAILS else 0)
