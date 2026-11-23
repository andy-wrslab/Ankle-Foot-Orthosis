"""Live plot engine (assets/live_uplot.js) without a browser: the real file runs in the
Windows Script Host (JScript) with stubbed window / document / uPlot (test/js/
live_uplot_harness.js). 3 minutes of 100 Hz data in 20 Hz messages, two cases:
constant-zero torque (STO engaged, as live on Nov 23) and real-looking torque, with a
moving stride velocity. Checks: the torque and SV plots get their x range from one
shared model-time clock on EVERY frame (never more than 0.5 s apart, never stalled),
the range follows the newest sample and scrolls smoothly, hidden browser tab / other
sub-tab draw nothing, a stopped stream stops the axis, Sensors plots share the clock.
Also the spec the page carries (pages/live.py live_spec) and the Training endpoint.

    python test/test_live_uplot_unit.py        (Windows: needs cscript)
"""
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def js_cases():
    if os.name != "nt":
        print("skip: JScript harness needs Windows (cscript)")
        return
    harness = os.path.join(HERE, "js", "live_uplot_harness.js")
    engine = os.path.join(APP, "assets", "live_uplot.js")
    for case in ("stall", "real"):
        r = subprocess.run(["cscript", "//nologo", "//E:jscript", harness, engine, case], capture_output=True,
                           text=True, timeout=300, creationflags=0x08000000)
        lines = [x for x in (r.stdout or "").splitlines() if x.strip()]
        check(f"harness ran ({case})", r.returncode == 0 and lines, (r.returncode, r.stdout[-300:], r.stderr[-300:]))
        for line in lines:
            print(line, flush=True)
            if line.startswith("FAIL"):
                FAILS.append(line)


def spec_and_endpoint():
    from pages.live import live_spec, register
    s = live_spec()
    check("spec: Gait = torque + stride velocity; Sensors = FSR + linear acceleration; Training = 2",
          {k: v["group"] for k, v in s["plots"].items()} == {"torque": "gait", "gait": "gait", "press": "sensors", "imu": "sensors",
                                                              "tr-assist": "training", "tr-uc": "training"}, s["plots"].keys())
    names = [x["label"] for x in s["plots"]["press"]["series"]]
    check("spec: FSR names", names == ["Hallux (FSR1)", "Heel medial (FSR2)", "Met 1 (FSR3)", "Met 5 (FSR4)", "Arch (FSR5)",
                                       "Toes (FSR6)", "Heel lateral (FSR7)", "Met 3 (FSR8)"], names)
    check("spec: linear acceleration x/y/z", [x["label"] for x in s["plots"]["imu"]["series"]] == ["x", "y", "z"]
          and [x["src"] for x in s["plots"]["imu"]["series"]] == [["imu", 0], ["imu", 1], ["imu", 2]])
    check("spec: command traces dashed", s["plots"]["torque"]["series"][1]["dash"] == [5, 4]
          and s["plots"]["torque"]["series"][0]["dash"] is None)
    import flask
    app = types.SimpleNamespace(server=flask.Flask("t"))
    calls = []
    ctx = types.SimpleNamespace(live=types.SimpleNamespace(slow_data=lambda names, w, max_points=0: calls.append((names, w)) or
                                                            {"t_latest": 50.0, "series": {"uc": {"t": [-1.0, 0.0], "v": [0.1, 0.2]}}}))
    register(app, ctx)
    r = app.server.test_client().get("/api/live/training?w=300")
    d = r.get_json()
    check("endpoint: /api/live/training returns t_latest + series for the window", r.status_code == 200
          and d["t_latest"] == 50.0 and d["series"]["uc"]["v"] == [0.1, 0.2] and calls == [(["assistance_level", "uc"], 300.0)],
          (r.status_code, d, calls))
    r = app.server.test_client().get("/api/live/training?w=abc")
    check("endpoint: bad window -> 2 min", r.status_code == 200 and r.get_json()["window"] == 120.0, r.get_json())
    css = open(os.path.join(APP, "assets", "afo-ui.css"), encoding="utf-8").read()
    check("Sensors grid: one column (both plots full width)", ".sensor-grid { grid-template-columns: minmax(0, 1fr);" in css)
    vend = os.path.join(APP, "assets", "vendor", "uplot")
    check("uPlot bundled (no CDN)", all(os.path.exists(os.path.join(vend, f)) for f in ("uPlot.iife.min.js", "uPlot.min.css", "LICENSE")))
    hh = open(os.path.join(APP, "assets", "hover_hold.js"), encoding="utf-8").read()
    check("hover_hold.js no longer holds live plots", "'torque'" not in hh and "'tr-assist'" not in hh)


if __name__ == "__main__":
    try:
        import _lowprio  # noqa: F401
    except Exception:
        pass
    spec_and_endpoint()
    js_cases()
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
