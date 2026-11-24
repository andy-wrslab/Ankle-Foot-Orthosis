"""Page batch, Andy Nov 24 14:29-14:34:
- Live sub-tabs (Gait | Sensors | Training) centred, window buttons stay right;
- every plot line ~2x thicker (dashed command / solid measured kept);
- Mass / ID / K % / Advanced inputs: Enter ALWAYS commits, also an unchanged number
  ("i literally entered and clicked enter": an unchanged 80 kg was never sent);
- Advanced panel: nothing is sent on Enter; edits are staged (old -> new) and Confirm sends
  them, one 5435 packet and one 5436 packet; Cancel drops them;
- Advanced labels in one column, inputs + units in one fixed column (long labels wrap).

    python test/test_page_batch_1124.py
"""
import os
import struct
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


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


css = open(os.path.join(APP, "assets", "afo-ui.css"), encoding="utf-8").read()
js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()


def static():
    check("Live sub-tabs centred (grid 1fr auto 1fr), window buttons right",
          "#page-live > .toolbar { display: grid; grid-template-columns: 1fr auto 1fr; }" in css
          and "#page-live > .toolbar > .seg { grid-column: 2; }" in css
          and "#page-live > .toolbar > .tb-right { grid-column: 3; justify-self: end; }" in css)
    import plot_style as P
    check("plot lines 2x: measured / command 3.0 px (was 1.5), IMU 2.5 (was 1.25)",
          P.SERIES["meas"]["width"] == 3.0 and P.SERIES["cmd"]["width"] == 3.0
          and all(P.SERIES[k]["width"] == 2.5 for k in ("imu_x", "imu_y", "imu_z")))
    check("command still dashed, measured solid", P.SERIES["cmd"].get("dash") == "dash" and not P.SERIES["meas"].get("dash"))
    from pages.live import live_spec
    widths = {(pid, s["label"]): s["width"] for pid, p in live_spec()["plots"].items() for s in p["series"]}
    check("Live (Gait, Sensors, Training): every series at least 2.5 px", min(widths.values()) >= 2.5, widths)
    tr = open(os.path.join(APP, "pages", "trials.py"), encoding="utf-8").read()
    check("Trials plots: 2.4 px (was 1.2)", "line=dict(width=2.4," in tr and "width=1.2" not in tr)
    # Enter always commits
    check("onCommit: Enter sets the commit flag; blur sends on Enter, on typing, or on a change",
          "if (e.key === 'Enter') { el._enter = true; el.blur(); }" in js
          and "var send = el._enter || el._typed || el.value !== start;" in js
          and "el.addEventListener('input', function () { el._typed = true; });" in js)
    check("onCommit: Escape restores and clears the flags (nothing sent)",
          "if (e.key === 'Escape') { el.value = start; el._typed = false; el._enter = false; el.blur(); }" in js)
    check("old rule gone (blur sent only on a change)",
          "if (el.value !== start && el.value.trim() !== '') { fn(el.value.trim()); }" not in js)
    check("Mass box uses onCommit -> /api/console/value weight",
          "onCommit($('sMass'), function (v) { commitField($('sMass'), 'sMass', '/api/console/value', {key: 'weight', value: v}); });" in js)
    check("K %: same Enter-always rule", "kp._enter = true; kp.blur();" in js
          and "var send = kp._enter || kp._typed || kp.value !== start;" in js)
    # Advanced: staged, Confirm
    check("Advanced edits staged, not posted (no /api/console/guard from the panel, no adv commitField)",
          "post('/api/console/guard'" not in js and "commitField(inp, 'adv-' + k" not in js
          and js.count("stageAdv(inp, '") == 2)
    check("Confirm posts all staged values to /api/console/advanced; Cancel clears them",
          "post('/api/console/advanced', body)" in js and "$('advCancel').addEventListener('click', function () { clearAdvPend(); poll(); });" in js)
    check("staged inputs are not overwritten by the 10 Hz render",
          "if (S.advPend['adv:' + inp.getAttribute('data-k')]) { inp.classList.add('adv-staged'); return; }" in js
          and "if (S.advPend['guard:' + f]) { inp.classList.add('adv-staged'); return; }" in js)
    check("old -> new list next to Confirm / Cancel", 'id="advConfirm"' in js and 'id="advChanges"' in js
          and "' → <b>' + esc(p.value) + '</b>'" in js)
    check("Advanced alignment: label | fixed 152 px input+unit column, long labels wrap",
          ".adv-sec label { display: grid; grid-template-columns: minmax(0, 1fr) 152px;" in css
          and "white-space: normal;" in css.split(".adv-sec label { display: grid;")[1].split("}")[0])



def hover():
    """Andy Nov 24 15:20: no units in any plot hover; values right-aligned in one column."""
    up = open(os.path.join(APP, "assets", "live_uplot.js"), encoding="utf-8").read()
    check("Live hover: no unit after the value", "(s.unit ? ' ' + s.unit : '')" not in up and "s.unit" not in up.split("function tooltipPlugin")[1].split("}};")[0])
    check("Live hover: swatch | name | value grid, time header kept",
          "'<div class=\"u-tip-t\">' + x.toFixed(3) + ' s</div><div class=\"u-tip-g\">'" in up
          and ".u-tip .u-tip-g { display: grid; grid-template-columns: 10px auto auto;" in css
          and ".u-tip .u-tip-g b { justify-self: end;" in css)
    import plot_style as P
    check("Plotly hover (trace_hover): no unit even when one is passed",
          P.trace_hover("Torque", ".2f", "Nm")["hovertemplate"] == "Torque  <b>%{y}</b><extra></extra>")
    tr = open(os.path.join(APP, "pages", "trials.py"), encoding="utf-8").read()
    check("Trials hover: name and value only (the unified header shows the time)",
          'hovertemplate=f"{label}  <b>%{{y:.4g}}</b><extra></extra>"' in tr and "t=%{{x:.3f}} s" not in tr)

def press_many():
    import udp_settings as U
    from fake_run14 import GUARD_FIELDS, GUARD_DEFAULTS, ADV_FIELDS, ADV_DEFAULTS
    # 5436: two fields, one packet
    row = dict(zip(GUARD_FIELDS, GUARD_DEFAULTS), guard_seq=4.0, adv_seq=1.0)
    echo = {"row": row, "age": 0.01, "cols": 44}
    sent = []
    g = U.GuardLink({"udp": {"send_host": "127.0.0.1", "guard_port": 15436}}, lambda: (dict(echo["row"]), echo["age"], echo["cols"]),
                    sender=lambda data, addr: sent.append((data, addr)), start_thread=False,
                    layout_path=os.path.join(ROUND1, "settings_guard_udp_layout.json"))
    g.tick()
    r = g.press_many({"jam_apnm": 9.0, "jam_ms": 200})
    check("5436 Confirm: two values -> ONE packet", r["ok"] and len(sent) == 1, (r, len(sent)))
    p = struct.unpack("<12f", sent[-1][0])
    want = [f32(v) for v in GUARD_DEFAULTS]
    want[GUARD_FIELDS.index("jam_apnm")] = 9.0
    want[GUARD_FIELDS.index("jam_ms")] = 200.0
    check("5436 Confirm packet: both changed, the rest in use", list(p[3:11]) == want, (p[3:11], want))
    row.update(jam_apnm=9.0, jam_ms=200.0, guard_seq=5.0)
    g.tick()
    check("5436 Confirm: both confirmed by the echo", g.result["jam_apnm"]["state"] == "confirmed"
          and g.result["jam_ms"]["state"] == "confirmed", g.result)
    sent.clear()
    r = g.press_many({"jam_apnm": 8.0, "jam_ms": 5})
    check("5436 Confirm: one bad value -> nothing sent", not r["ok"] and not sent and r.get("field") == "jam_ms", (r, sent))
    # 5435: min AND max target speed raised together (each alone would fail against the device pair)
    arow = dict(zip(ADV_FIELDS, ADV_DEFAULTS), adv_seq=7.0, spring_stiffness=1.25, settings_seq=3.0)
    aecho = {"row": arow, "age": 0.01, "cols": 31}
    asent = []
    a = U.AdvLink({"udp": {"send_host": "127.0.0.1", "adv_port": 15435}}, lambda: (dict(aecho["row"]), aecho["age"], aecho["cols"]),
                  sender=lambda data, addr: asent.append((data, addr)), start_thread=False,
                  layout_path=os.path.join(APP, "config", "settings_adv_udp_layout.json"))
    a.tick()
    check("5435: min 1.6 alone refused (above the max 1.5 in use)", a.check("sv_target_min", 1.6) is not None)
    r = a.press_many({"sv_target_min": 1.6, "sv_target_max": 1.9})
    check("5435 Confirm: min 1.6 + max 1.9 together -> accepted, ONE packet", r["ok"] and len(asent) == 1, (r, len(asent)))
    asent.clear()
    r = a.press_many({"sv_target_min": 1.2, "sv_target_max": 1.1})
    check("5435 Confirm: min >= max in the batch refused, nothing sent", not r["ok"] and not asent, (r, asent))


def no_send_before_confirm():
    """The page sends nothing from the Advanced panel until Confirm: the only network calls in
    the panel's commit handlers are stageAdv (local); the POST lives in the advOk handler."""
    seg = js.split("document.querySelectorAll('.guard-in').forEach(function (inp) {\n            var f = inp.getAttribute('data-g');\n            onCommit(")[1]
    seg = seg.split("$('advOk').addEventListener")[0]
    check("Advanced commit handlers: no post() before Confirm", "post(" not in seg and "commitField(" not in seg, seg[:200])
    ok = js.split("$('advOk').addEventListener('click', function () {")[1].split("$('advCancel')")[0]
    check("Confirm handler: the one POST", ok.count("post(") == 1 and "/api/console/advanced" in ok)


static()
hover()
press_many()
no_send_before_confirm()
print("\nFAILS:", FAILS)
sys.exit(1 if FAILS else 0)
