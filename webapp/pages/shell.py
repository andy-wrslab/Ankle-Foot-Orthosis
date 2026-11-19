"""App shell: one Dash app with a shared top bar and five pages.

All pages are in the layout at once and the router only shows one, so the
live stream, lamps and controls keep running whichever page is open. The two
OMEN-only pages are only rendered for loopback requests (see pages.common).
"""
from __future__ import annotations

import os
import time

import dash
from dash import dcc, html, Input, Output
from dash_extensions import EventSource
from flask import Response, jsonify, request

from state import snapshots, MAX_CLIENTS
from pages import home, live, trials, runctl, teensy, signals
from pages.common import is_local

NAV = [("home", "Home"), ("live", "Live"), ("signals", "Signals"), ("trials", "Trials"), ("teensy", "Teensy")]
_SSE_IDLE_TIMEOUT = 0.5
_clients = {"n": 0}


def serve_layout(ctx):
    def layout():
        local = is_local()
        return html.Div(className="dashboard", children=[
            dcc.Location(id="url"),
            html.Div(EventSource(id="es", url="/events"), style={"display": "none"}),
            dcc.Interval(id="tab-interval", interval=1000, n_intervals=0),
            html.Header(className="topbar", children=[
                html.Div(className="brand", children=[html.Span("AFO", className="brand-title")]),
                html.Nav(className="nav", children=[
                    dcc.Link(label + ("" if local or key not in ("run", "teensy") else " •"), href=f"/{key}",
                             id=f"nav-{key}", className="nav-link")
                    for key, label in NAV
                ]),
                html.Div(className="topbar-right", children=[
                    html.Div(className="stat", children=[html.Span("Model time", className="stat-label"),
                                                         html.Span("–", id="session-time", className="stat-value")]),
                    html.Div(className="stat", children=[html.Span("Drive state", className="stat-label"),
                                                         html.Span("no data", id="drive-state", className="stat-value drive-none")]),
                ]),
            ]),
            html.Main(children=[
                html.Section(id="page-home", className="page", children=home.layout(ctx)),
                html.Section(id="page-live", className="page", children=live.layout(ctx)),
                html.Section(id="page-signals", className="page", children=signals.layout()),
                html.Section(id="page-trials", className="page", children=trials.layout(ctx.trials)),
                html.Section(id="page-teensy", className="page", children=teensy.layout()),
            ]),
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

    # router: show one page, highlight its nav link
    keys = [k for k, _ in NAV]
    app.clientside_callback(
        """
        function(path){
            var keys = %s;
            var page = (path || '/').replace(/^\\/+|\\/+$/g, '') || 'home';
            if(keys.indexOf(page) < 0){ page = 'home'; }
            if(window._afoShowPage){ window._afoShowPage(page); }
            var out = [];
            keys.forEach(function(k){ out.push(k === page ? 'page active' : 'page'); });
            keys.forEach(function(k){ out.push(k === page ? 'nav-link active' : 'nav-link'); });
            return out;
        }
        """ % keys,
        *[Output(f"page-{k}", "className") for k in keys],
        *[Output(f"nav-{k}", "className") for k in keys],
        Input("url", "pathname"),
    )

    # top bar: health lamps, model time and drive state from every snapshot
    app.clientside_callback(
        """
        function(msg, n){
            var NU = window.dash_clientside.no_update;
            var GROUPS = [['sync', 'Packets'], ['imu', 'IMU'], ['fsr', 'FSR'], ['drive', 'Drive data']];
            try {
                var now = Date.now();
                var st = window._afoHealthState || (window._afoHealthState = {last: 0, health: null});
                var ctx = window.dash_clientside.callback_context;
                var trig = (ctx && ctx.triggered && ctx.triggered.length) ? ctx.triggered[0].prop_id : '';
                if(trig.indexOf('es.') === 0 && msg){
                    var raw = (typeof msg === 'string') ? msg : msg.data;
                    var p = raw ? window._afoParse(raw) : null;
                    if(p){
                        if(p.health){ st.health = p.health; st.last = now; }
                        if(typeof p.t_latest === 'number' && isFinite(p.t_latest)){
                            var s = Math.max(0, Math.floor(p.t_latest));
                            var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
                            var ts = document.getElementById('session-time');
                            var txt = (h ? h + ':' + (m < 10 ? '0' : '') : '') + m + ':' + (sec < 10 ? '0' : '') + sec;
                            if(ts && ts.textContent !== txt){ ts.textContent = txt; }
                        }
                        var sw = p.statusword;
                        if(typeof sw === 'number' && isFinite(sw) && sw >= 0 && sw <= 65535){
                            var d = window._afoDecodeStatus(sw);
                            var ds = document.getElementById('drive-state');
                            var label = d.text + ' (0x' + (sw >>> 0).toString(16).toUpperCase() + ')';
                            if(ds && ds.textContent !== label){ ds.textContent = label; ds.className = 'stat-value drive-' + d.cls; }
                            var md = document.getElementById('motor-drive');
                            if(md && md.textContent !== 'drive: ' + d.text){ md.textContent = 'drive: ' + d.text; }
                            var mb = document.getElementById('motor-btn');
                            var tip = d.ready ? '' : ('Drive not ready: ' + d.text + '. The motor command is sent, but the drive will not move until it is enabled.');
                            if(mb && mb.title !== tip){ mb.title = tip; }
                        }
                    }
                }
                return NU;
            } catch(err){
                console.error('[AFO] top bar update failed', err);
                return NU;
            }
        }
        """,
        Output("tab-interval", "disabled"),
        Input("es", "message"), Input("tab-interval", "n_intervals"),
        prevent_initial_call=True,
    )

    for page in (home, live, signals, trials, teensy):
        page.register(app, ctx)

    server = app.server

    @server.route("/events")
    def sse_stream():  # type: ignore
        if _clients["n"] >= MAX_CLIENTS:
            return Response("Too many clients", status=503)
        _clients["n"] += 1

        def generate():
            try:
                last = snapshots.seq
                while not ctx.stopping.is_set():
                    seq, text = snapshots.wait_next(last, _SSE_IDLE_TIMEOUT)
                    if text is None:
                        yield ": keep-alive\n\n"
                        continue
                    last = seq
                    yield f"data:{text}\n\n"
            finally:
                _clients["n"] -= 1

        return Response(generate(), mimetype="text/event-stream")

    @server.route("/api/status")
    def api_status():  # type: ignore
        jobs = {k: (ctx.jobs.get(k).view() if ctx.jobs.get(k) else None) for k in ("teensy", "trial-load", "rc")}
        for j in jobs.values():
            if j:
                j["log"] = j["log"][-2000:]
        return jsonify({"live": ctx.live.get_status(), "poller": ctx.poller.get(), "matlab": ctx.matlab.get_status(),
                        "jobs": jobs, "local": is_local(), "trial": ctx.trials.path})

    @server.route("/api/teensy/build", methods=["POST"])
    def api_build():  # type: ignore
        if not is_local():
            return jsonify({"ok": False, "err": "OMEN only"}), 403
        import teensy_tools
        from workers import run_process
        if ctx.jobs.running("teensy"):
            return jsonify({"ok": False, "err": "busy"}), 409
        job = ctx.jobs.start("teensy", "build", lambda j: teensy_tools.compile_job(ctx.cfg, j, run_process))
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

    @server.route("/api/training/data")
    def api_training_data():  # type: ignore
        names = [n for n in (request.args.get("names") or "").split(",") if n]
        win = min(330.0, float(request.args.get("window", 30)))
        return jsonify(ctx.training.data(names, win, max_points=int(request.args.get("points", 1500))))

    @server.route("/api/session", methods=["GET"])
    def api_session():  # type: ignore
        return jsonify(ctx.session.view())

    @server.route("/api/run/<action>", methods=["POST"])
    def api_run_action(action):  # type: ignore
        if not is_local():
            return jsonify({"ok": False, "err": "OMEN only"}), 403
        if action not in ("connect", "disconnect", "status", "start", "stop", "save"):
            return jsonify({"ok": False, "err": "unknown action"}), 404
        if ctx.jobs.running("rc"):
            return jsonify({"ok": False, "err": "another run-control action is running"}), 409
        args = []
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

    @server.route("/api/signals/stream", methods=["POST"])
    def api_sig_stream():  # type: ignore
        if not is_local():
            return jsonify({"ok": False, "err": "OMEN only"}), 403
        on = bool((request.get_json(silent=True) or {}).get("on"))
        job = ctx.jobs.start("signals", f"signals {'on' if on else 'off'}", lambda j: j.add(ctx.matlab.set_stream(on)))
        return jsonify({"ok": True, "job": job.id})

    @server.route("/api/signals/status")
    def api_sig_status():  # type: ignore
        return jsonify(ctx.matlab.snapshot("status", timeout=1.0))

    @server.route("/api/signals/data")
    def api_sig_data():  # type: ignore
        names = [n for n in (request.args.get("names") or "").split(",") if n]
        win = float(request.args.get("window", 10))
        return jsonify(ctx.matlab.snapshot("data", names, win, timeout=1.0))

    return app
