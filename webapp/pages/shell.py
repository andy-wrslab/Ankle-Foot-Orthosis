"""App shell (design v18): top bar, popovers, banner and dock are built in the
browser by assets/afo_console.js (from the mock markup) and driven by
/api/console/state; Dash renders the page frames and the Plotly graphs.

Pages: Live (Gait | Sensors | Training sub-pages, start page), Trials, DAQ (was Teensy;
the Signals page was removed Nov 23). All pages are in the layout at once; the script shows one (hidden
attribute) and keeps dcc.Location in sync so server callbacks know the page.
Home and Run control are gone (merged into the top bar and the status popover).
"""
from __future__ import annotations

import os
import threading
import time

import dash
from dash import dcc, html
from flask import Response, jsonify, request

from state import snapshots, MAX_CLIENTS
from pages import live, trials, teensy, console_api
from pages.common import is_local

NAV = [("live", "Live"), ("trials", "Trials"), ("daq", "DAQ")]      # Andy 14:36: Signals removed, Teensy -> DAQ
_SSE_IDLE_TIMEOUT = 0.5
_clients = {"n": 0}
_clients_lock = threading.Lock()


def load_path_ok(cfg, f):
    """The resolved path when *f* is an existing <afo_root>\\round1\\target_build*\\AFO_r1.mldatx, else None."""
    import fnmatch
    if not f or not isinstance(f, str):
        return None
    root = (cfg.get("paths") or {}).get("afo_root") or r"C:\Users\Andy\Desktop\AFO"
    real = os.path.realpath(f)
    pat = os.path.normcase(os.path.join(os.path.realpath(root), "round1", "target_build*", "AFO_r1.mldatx"))
    if not fnmatch.fnmatch(os.path.normcase(real), pat) or not os.path.isfile(real):
        return None
    # one directory level only (target_build* must be a direct child of round1)
    if os.path.normcase(os.path.dirname(os.path.dirname(real))) != os.path.normcase(os.path.join(os.path.realpath(root), "round1")):
        return None
    return real


def load_request(ctx, body):
    """/api/run/load checks (OMEN-local is checked by the route): view-only 403, running 409,
    path not an existing round1/target_build*/AFO_r1.mldatx 400; else (200, {"file": path})."""
    if (ctx.cfg.get("console") or {}).get("view_only"):
        return 403, {"ok": False, "err": "View-only console: Load is disabled in this app."}
    if (ctx.runctl.status or {}).get("running"):
        return 409, {"ok": False, "err": "The app is running: stop it before loading."}
    path = load_path_ok(ctx.cfg, (body or {}).get("file"))
    if not path:
        return 400, {"ok": False, "err": r"file must be an existing round1\target_build*\AFO_r1.mldatx"}
    return 200, {"ok": True, "file": path}


def register_legacy_routes(server) -> None:
    """Removed / renamed pages: /signals -> /live (Signals page removed), /teensy -> /daq."""
    from flask import redirect

    @server.route("/signals")
    def legacy_signals():  # type: ignore
        return redirect("/live", code=302)

    @server.route("/teensy")
    def legacy_teensy():  # type: ignore
        return redirect("/daq", code=302)


def serve_layout(ctx):
    def layout():
        local = is_local()
        return html.Div(className="app", id="app", **{"data-local": "1" if local else "0"}, children=[
            dcc.Location(id="url"),
            # live snapshots: assets/sse.js keeps ONE EventSource per tab open and writes
            # each message into this store (the dash_extensions EventSource reconnected
            # on every render: ~21 /events connections per second per tab)
            dcc.Store(id="es", data=None),
            html.Div(id="chrome-top", style={"display": "contents"}),     # top bar, popovers, banner (JS)
            html.Main(className="page live", id="page-live", **{"data-page": "live"}, children=live.layout(ctx)),
            html.Main(className="page", id="page-trials", hidden=True, **{"data-page": "trials"},
                      children=html.Div(className="narrow", id="trials-root")),            # JS
            html.Main(className="page", id="page-daq", hidden=True, **{"data-page": "daq"},
                      children=html.Div(className="narrow", children=teensy.layout())),
            html.Footer(className="dock", id="dock"),                                       # JS
        ])
    return layout


def build_app(ctx) -> dash.Dash:
    meta = [
        {"name": "apple-mobile-web-app-capable", "content": "yes"},
        {"name": "viewport", "content": "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no"},
    ]
    app = dash.Dash(__name__, assets_folder=os.path.join(ctx.app_dir, "assets"), serve_locally=True,
                    update_title=None, meta_tags=meta, suppress_callback_exceptions=True)
    app.title = "AFO"
    app.layout = serve_layout(ctx)

    for page in (live, teensy):
        page.register(app, ctx)

    server = app.server
    console_api.register(server, ctx)


    @server.route("/events")
    def sse_stream():  # type: ignore
        with _clients_lock:
            if _clients["n"] >= MAX_CLIENTS:
                return Response("Too many clients", status=503, headers={"Retry-After": "2"})
            _clients["n"] += 1
        released = threading.Event()

        def release():
            # once, from whichever comes first: the generator closing (GeneratorExit
            # when a write to a gone client fails) or the response being closed
            if not released.is_set():
                released.set()
                with _clients_lock:
                    _clients["n"] -= 1

        def generate():
            try:
                yield "retry: 2000\n\n"
                last = snapshots.seq
                # first message: the whole 100 Hz window; every later one is a delta
                full = snapshots.full_text()
                if full:
                    yield f"data:{full}\n\n"
                while not ctx.stopping.is_set():
                    seq, text = snapshots.wait_next(last, _SSE_IDLE_TIMEOUT)
                    if text is None:
                        yield ": keep-alive\n\n"
                        continue
                    last = seq
                    yield f"data:{text}\n\n"
            finally:
                release()

        resp = Response(generate(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        resp.call_on_close(release)
        return resp

    @server.route("/api/sse/clients")
    def api_sse_clients():  # type: ignore
        return jsonify({"clients": _clients["n"], "max": MAX_CLIENTS})

    @server.route("/api/status")
    def api_status():  # type: ignore
        jobs = {k: (ctx.jobs.get(k).view() if ctx.jobs.get(k) else None) for k in ("teensy", "trial-load", "rc")}
        for j in jobs.values():
            if j:
                j["log"] = j["log"][-2000:]
        return jsonify({"live": ctx.live.get_status(), "poller": ctx.poller.get(), "matlab": ctx.matlab.get_status(),
                        "jobs": jobs, "local": is_local(), "trial": getattr(ctx.trials, "path", None)})

    @server.route("/api/teensy/build", methods=["POST"])
    def api_build():  # type: ignore
        if not is_local():
            return jsonify({"ok": False, "err": "OMEN only"}), 403
        import teensy_tools
        from workers import run_process
        source = (request.get_json(silent=True) or {}).get("source")  # branch name; default newest firmware
        job, started = ctx.jobs.start_exclusive("teensy", "build",
                                                lambda j: teensy_tools.compile_job(ctx.cfg, j, run_process, source))
        if not started:
            return jsonify({"ok": False, "err": "busy", "job": job.id}), 409
        return jsonify({"ok": True, "job": job.id})

    @server.route("/api/trials/open", methods=["POST"])
    def api_trial_open():  # type: ignore
        src = (request.get_json(silent=True) or {}).get("path")
        if src not in {s["path"] for s in ctx.trials.sources()}:
            return jsonify({"ok": False, "err": "unknown file"}), 404
        job = ctx.trials.load(src)
        return jsonify({"ok": True, "job": job.id})

    # ---- run control backend for the top-bar Connect | Start | Stop (OMEN only)
    @server.route("/api/run/status")
    def api_run_status():  # type: ignore
        job = ctx.jobs.get("rc")
        return jsonify({"target": ctx.runctl.status, "status_age_s": (time.time() - ctx.runctl.status_at)
                        if ctx.runctl.status_at else None, "banner": ctx.runctl.banner,
                        "job": job.view() if job else None, "matlab": ctx.matlab.get_status(),
                        "udp_live": ctx.live.stream_live(), "local": is_local()})

    @server.route("/api/run/export", methods=["POST"])
    def api_run_export():  # type: ignore
        if not is_local():
            return jsonify({"ok": False, "err": "OMEN only"}), 403
        if ctx.jobs.running("rc"):
            return jsonify({"ok": False, "err": "another run-control action is running"}), 409
        job, msg = ctx.runctl.export((request.get_json(silent=True) or {}).get("name", ""))
        if job is None:
            return jsonify({"ok": False, "err": msg}), 400
        return jsonify({"ok": True, "job": job.id, "msg": msg})

    @server.route("/api/run/export-name")
    def api_run_export_name():  # type: ignore
        return jsonify(ctx.runctl.export_name())

    @server.route("/api/training/status")
    def api_training_status():  # type: ignore
        st = ctx.training.get_status()
        st.pop("latest", None)
        return jsonify({"status": st, "latest": ctx.training.latest(max_age_s=2.0)})

    @server.route("/api/training/plots")
    def api_training_plots():  # type: ignore
        from plot_style import training_plots, MARGIN, Y_PAD
        return jsonify({"plots": training_plots(), "margin": MARGIN, "y_pad": Y_PAD})

    @server.route("/api/training/data")
    def api_training_data():  # type: ignore
        # Live > Training plots come from the main bus 5431 (sv 1, sv_target 23, uc 24,
        # assistance_level 27), kept for 330 s at ~100 Hz in the live worker
        names = [n for n in (request.args.get("names") or "").split(",") if n]
        win = min(330.0, float(request.args.get("window", 120)))
        return jsonify(ctx.live.slow_data(names, win, max_points=int(request.args.get("points", 1500))))

    @server.route("/api/session", methods=["GET"])
    def api_session():  # type: ignore
        return jsonify(ctx.session.view())

    # ---- Trials: runs in the Speedgoat file log (design v17)
    @server.route("/api/trials/runs")
    def api_trials_runs():  # type: ignore
        d = ctx.filelog.runs()
        for r in d["runs"]:
            if not r["exported"] and not r["recording"]:
                n = ctx.filelog.default_name(r)
                r["default_name"] = n.get("name")
        return jsonify(d)

    @server.route("/api/trials/runs/refresh", methods=["POST"])
    def api_trials_runs_refresh():  # type: ignore
        if not is_local():
            return jsonify({"ok": False, "err": "OMEN only"}), 403
        job, msg = ctx.filelog.refresh()
        return jsonify({"ok": job is not None, "msg": msg, "job": job.id if job else None}), (200 if job else 409)

    @server.route("/api/trials/runs/export", methods=["POST"])
    def api_trials_runs_export():  # type: ignore
        if not is_local():
            return jsonify({"ok": False, "err": "OMEN only"}), 403
        b = request.get_json(silent=True) or {}
        job, msg, code = ctx.filelog.export(str(b.get("id", "")), b.get("name", ""), replace=b.get("replace") is True,
                                            join=b.get("join", True) is not False)
        return jsonify({"ok": job is not None, "msg": msg, "job": job.id if job else None}), code

    @server.route("/api/status/top")
    def api_status_top():  # type: ignore
        from status import top_status
        return jsonify(top_status(ctx))

    @server.route("/api/session/target")
    def api_session_target():  # type: ignore
        return jsonify({"rows": ctx.session.target_table(), "echo_active": bool(ctx.session.echo()),
                        "model": ctx.session.model(), "writes_enabled": ctx.session.writes_enabled})

    @server.route("/api/run/<action>", methods=["POST"])
    def api_run_action(action):  # type: ignore
        if not is_local():
            return jsonify({"ok": False, "err": "OMEN only"}), 403
        if action not in ("connect", "disconnect", "status", "start", "stop", "save", "load"):
            return jsonify({"ok": False, "err": "unknown action"}), 404
        if action in ("start", "stop", "load") and (ctx.cfg.get("console") or {}).get("view_only"):
            return jsonify({"ok": False, "err": "View-only console: Start, Stop and Load are disabled in this app."}), 403
        if ctx.jobs.running("rc"):
            return jsonify({"ok": False, "err": "another run-control action is running"}), 409
        args = []
        if action == "load":
            # load a built AFO_r1 app from the page's own MATLAB session (run 14 go-live)
            code, payload = load_request(ctx, request.get_json(silent=True) or {})
            if code != 200:
                return jsonify(payload), code
            args = [payload["file"]]
        if action == "save":
            import re as _re
            body = request.get_json(silent=True) or {}
            part, trial = body.get("participant", ""), body.get("trial", "")
            ok_name = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$")
            if not ok_name.match(part or "") or not ok_name.match(trial or ""):
                return jsonify({"ok": False, "err": "participant and trial: letters, digits, _ and -"}), 400
            out = os.path.join(ctx.cfg["paths"]["afo_root"], f"{part}_{trial}.mat")
            if os.path.exists(out):
                return jsonify({"ok": False, "err": f"{os.path.basename(out)} exists"}), 409
            args = [out]
        job = ctx.runctl.run_action(action, *args)
        return jsonify({"ok": True, "job": job.id})

    # Signals page removed (Andy 14:36): /signals and the old /teensy land on the pages that remain
    register_legacy_routes(server)

    return app
