"""Signals page removed, Teensy renamed DAQ (Andy 14:36). Seconds, no browser, no server.
- /signals redirects to /live, /teensy to /daq; no /api/signals/* route is left;
- no getsignal / MATLAB stream calls: bif_view makes no MATLAB call, nothing calls set_stream;
- nav: Live, Trials, DAQ; the DAQ page answers on /daq.

    python test/test_pages_removed.py
"""
import os
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


def main():
    from flask import Flask
    import pages.shell as SH
    srv = Flask("t")
    SH.register_legacy_routes(srv)
    c = srv.test_client()
    r = c.get("/signals")
    check("/signals -> 302 /live", r.status_code == 302 and r.headers["Location"].endswith("/live"), (r.status_code, r.headers.get("Location")))
    r = c.get("/teensy")
    check("/teensy -> 302 /daq", r.status_code == 302 and r.headers["Location"].endswith("/daq"), (r.status_code, r.headers.get("Location")))
    r = c.get("/api/signals/status")
    check("/api/signals/* gone (404)", r.status_code == 404, r.status_code)
    src = open(SH.__file__, encoding="utf-8").read()
    check("shell: no /api/signals routes, no signals page", "/api/signals" not in src and "signals.layout" not in src
          and "from pages import live, trials, teensy, console_api" in src)
    check("nav: Live, Trials, DAQ", 'NAV = [("live", "Live"), ("trials", "Trials"), ("daq", "DAQ")]' in src)
    check("pages/signals.py removed", not os.path.exists(os.path.join(APP, "pages", "signals.py")))
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: nav link DAQ, no Signals link / client code", 'data-nav="daq">DAQ</a>' in js and "loadSignals" not in js
          and "/api/signals" not in js and "data-nav=\"signals\"" not in js)
    ty = open(os.path.join(APP, "pages", "teensy.py"), encoding="utf-8").read()
    check("DAQ page: heading 'DAQ', callbacks on /daq", 'html.H1("DAQ"' in ty and '"/teensy"' not in ty and 'path != "/daq"' in ty)
    calls = []
    import session as S
    from test_round5 import make_ctx
    ctx = make_ctx({"connected": True, "running": True, "app": "AFO_r1"}, bif=None)
    ctx.matlab = types.SimpleNamespace(snapshot=lambda *a, **k: calls.append(a) or {}, call=lambda *a, **k: calls.append(a) or "{}")
    ctx.training.latest = lambda max_age_s=1.0: {"side": 0.0}          # 12 floats: no Bi-LSTM columns
    bv = ctx.session.bif_view()
    check("bif_view on 12 floats: no MATLAB getsignal / snapshot call", not calls and bv is not None, (calls, bv))
    hits = []
    for root, _, files in os.walk(APP):
        if any(x in root for x in (os.sep + "test", os.sep + ".git", "__pycache__", os.sep + "cache", os.sep + "logs")):
            continue
        for f in files:
            if f.endswith(".py") and f != "workers.py":
                if "set_stream(" in open(os.path.join(root, f), encoding="utf-8", errors="replace").read():
                    hits.append(f)
    check("nothing starts the MATLAB signal stream (set_stream)", not hits, hits)
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
