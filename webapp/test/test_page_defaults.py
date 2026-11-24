"""Page-owned defaults (Andy, Nov 24 09:31): jam cut ON at 7.5 A/(N·m) for 150 ms, torque P
0.45 / I 0.55, wherever the page has a default of its own. The device values themselves always
come from the echo; config/*.json stay exact round1 copies (the Simulink thread owns those and
rebuilds with the new model defaults). Static, seconds, no browser.

    python test/test_page_defaults.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

ROUND1 = os.path.join(os.path.dirname(APP), "round1") if os.path.isdir(os.path.join(os.path.dirname(APP), "round1")) \
    else r"C:\Users\Andy\Desktop\AFO\round1"
FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def main():
    import session as S
    d = {sp["key"]: sp.get("default") for sp in S.SPECS}
    check("session SPECS: torque P gain default 0.45, I gain 0.55", (d["p_gain"], d["i_gain"]) == (0.45, 0.55), (d["p_gain"], d["i_gain"]))
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    g = dict((m.group(1), m.group(2)) for m in re.finditer(r"\['(jam_\w+)', '[^']*', '[^']*', \d, '([^']*)'\]", js))
    check("Torque guard card: jam cut default on", "1 = on (default)" in g.get("jam_cut_on", ""), g)
    check("Torque guard card: jam current per torque default 7.5", "(default 7.5)" in g.get("jam_apnm", ""), g)
    check("Torque guard card: jam time default 150 ms", "(default 150)" in g.get("jam_ms", ""), g)
    check("no old page defaults left (jam 5 / 100, P 0.6 / I 0.8)", "(default 5)" not in js and "(default 100)" not in js)
    import fake_run14 as F
    adv = dict(zip(F.ADV_FIELDS, F.ADV_DEFAULTS))
    gd = dict(zip(F.GUARD_FIELDS, F.GUARD_DEFAULTS))
    check("fake device build values: P 0.45 / I 0.55, jam on / 7.5 / 150", (adv["torque_p_gain"], adv["torque_i_gain"]) == (0.45, 0.55)
          and (gd["jam_cut_on"], gd["jam_apnm"], gd["jam_ms"]) == (1.0, 7.5, 150.0), (adv, gd))
    import replay_senders as R
    c = R.CONSOLE_DEFAULTS
    check("replay console sender: P 0.45 / I 0.55, jam on / 7.5 / 150", (c["torque_p_gain"], c["torque_i_gain"], c["jam_cut_on"],
          c["jam_apnm"], c["jam_ms"]) == (0.45, 0.55, 1.0, 7.5, 150.0), c)
    for f in ("console_udp_layout.json", "settings_adv_udp_layout.json", "settings_guard_udp_layout.json", "settings_udp_layout.json"):
        a = json.load(open(os.path.join(APP, "config", f), encoding="utf-8"))
        b = json.load(open(os.path.join(ROUND1, f), encoding="utf-8"))
        check(f"config/{f} stays an exact round1 copy", a == b)
    gl = json.load(open(os.path.join(ROUND1, "settings_guard_udp_layout.json"), encoding="utf-8"))
    rules = {x["name"]: x["rule"] for x in gl["fields"]}
    print("info round1 guard layout defaults (owned by the Simulink thread): jam_apnm %r, jam_ms %r"
          % (rules.get("jam_apnm"), rules.get("jam_ms")), flush=True)


if __name__ == "__main__":
    main()
    print("FAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
