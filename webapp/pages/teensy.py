"""Teensy page (OMEN only): firmware source, build, guarded flash, code, changes, serial monitor.

One firmware source drives every tab: pick a branch and the page uses that branch's
newest commit (GitHub is fetched when the page opens and on "Fetch latest") for the
Code, Changes, Build and Flash tabs. The firmware repo's working tree is never checked
out or changed. Nothing here sends anything to the Speedgoat; opening the page only
reads (git, USB scan).
"""
from __future__ import annotations

import time

from dash import dcc, html, Input, Output, State, no_update, ctx as dctx

import teensy_tools as tt
from pages.common import is_local, local_only, locked_notice
from workers import run_process

TABS = [("build", "Build and flash"), ("code", "Code"), ("changes", "Changes vs main"), ("serial", "Serial monitor")]
CONFIRM_S = 3.0


def _kv(rows):
    out = []
    for label, vid in rows:
        out += [html.Dt(label), html.Dd("–", id=vid)]
    return html.Dl(className="kv", children=out)


def _panel(key, children):
    return html.Section(id=f"ty-panel-{key}", className="card", children=children,
                        style={} if key == "build" else {"display": "none"})


def layout() -> html.Div:
    if not is_local():
        return html.Div(className="narrow", children=[html.H1("Teensy", className="page-title"), locked_notice("Teensy")])
    return html.Div(className="narrow teensy", children=[
        dcc.Interval(id="ty-poll", interval=1000, n_intervals=0),
        dcc.Interval(id="ty-slow", interval=5000, n_intervals=0),
        dcc.Store(id="ty-tab", data="build"),
        dcc.Store(id="ty-flash-arm", data=None),
        dcc.Store(id="ty-serial-paused", data=False),
        html.Div(className="toolbar", children=[
            html.H1("Teensy", className="page-title"),
            html.Span("Debugging only. The Teensy USB is unplugged during collection; that is normal.",
                      className="hint"),
        ]),
        html.Div(className="grid2", children=[
            html.Section(className="card", children=[
                html.Div(className="card-head", children=[
                    html.Span("Firmware", className="card-title"), html.Span(className="spacer"),
                    html.Span(id="ty-fetched", className="hint"),
                    html.Button("Fetch latest", id="ty-fetch-btn", className="btn sm",
                                title="git fetch from GitHub. Only updates the branch list; files are never changed."),
                ]),
                html.Div(className="ty-source", children=[
                    dcc.Dropdown(id="ty-source", clearable=False, searchable=False, placeholder="Loading branches…"),
                ]),
                _kv([("Commit", "ty-commit"), ("Compared with main", "ty-vsmain"),
                     ("Board settings", "ty-board"), ("Last flashed here", "ty-lastflash")]),
            ]),
            html.Section(className="card", children=[
                html.Div(className="card-head", children=[html.Span("IMU data", className="card-title")]),
                _kv([("State", "ty-imu-state"), ("Invalid, last 10 s", "ty-imu-recent"),
                     ("Invalid since app start", "ty-imu-total"), ("Invalid spells seen", "ty-imu-spells")]),
                html.P("From the live UDP stream. A byte slip makes every IMU value invalid until the IMU "
                       "is unplugged for about 1 s.", className="hint ty-note"),
            ]),
        ]),
        html.Div(className="seg", role="group", **{"aria-label": "Teensy tools"}, children=[
            html.Button(label, id={"type": "ty-tab-btn", "tab": key}, n_clicks=0,
                        **{"aria-pressed": "true" if key == "build" else "false"}) for key, label in TABS
        ]),
        _panel("build", [
            html.Div(className="card-head", children=[html.Span("Build and flash", className="card-title")]),
            _kv([("Teensy USB", "ty-port"), ("Speedgoat stream", "ty-stream"), ("Last build", "ty-build-summary")]),
            html.Div(className="card-foot", children=[
                html.Button("Build", id="ty-build-btn", className="btn primary"),
                html.Button("Flash", id="ty-flash-btn", className="btn danger"),
                dcc.Checklist(id="ty-dry", options=[{"label": " Dry run", "value": "dry"}], value=[],
                              className="ty-check", inputClassName="ty-check-input"),
                html.Span(id="ty-flash-msg", className="hint"),
            ]),
            html.Pre(id="ty-job-log", className="log ty-log"),
        ]),
        _panel("code", [
            html.Div(className="card-head", children=[
                html.Span("Code", className="card-title"), html.Span(id="ty-code-src", className="hint mono"),
                html.Span(className="spacer"),
                dcc.Dropdown(id="ty-file", clearable=False, searchable=False, className="ty-file"),
            ]),
            html.Pre(id="ty-file-view", className="log ty-log tall"),
        ]),
        _panel("changes", [
            html.Div(className="card-head", children=[
                html.Span("Changes vs main", className="card-title"),
                html.Span("DAQ/ only", className="hint")]),
            html.Pre(id="ty-diff", className="log ty-log tall"),
        ]),
        _panel("serial", [
            html.Div(className="card-head", children=[
                html.Span("Serial monitor", className="card-title"),
                html.Span(f"{tt.SERIAL_BAUD} baud", className="hint mono"), html.Span(className="spacer"),
                html.Button("Clear", id="ty-serial-clear", className="btn sm"),
            ]),
            html.Div(className="card-foot ty-serial-bar", children=[
                dcc.Dropdown(id="ty-serial-port", placeholder="No serial port found", clearable=False,
                             searchable=False, className="ty-port"),
                html.Button("Rescan", id="ty-rescan", className="btn sm",
                            title="Scan USB now (it also scans every 3 s while this page is open)"),
                html.Button("Start", id="ty-serial-start", className="btn sm primary"),
                html.Button("Stop", id="ty-serial-stop", className="btn sm"),
                html.Button("Pause", id="ty-serial-pause", className="btn sm"),
                dcc.Input(id="ty-serial-filter", placeholder="Filter", className="input ty-filter", debounce=False),
                html.Span(id="ty-serial-state", className="hint"),
            ]),
            html.Pre(id="ty-serial-out", className="log ty-log tall"),
        ]),
    ])


def _block_reason(ctx, cfg, source, dry_run=False):
    """'' when Flash may run, else the reason (shown next to the disabled button)."""
    if not source:
        return "Pick a firmware branch."
    if ctx.jobs.running("teensy"):
        return "A build or flash is running."
    if ctx.live.stream_live():
        return "Locked while the UDP stream is live."
    teensys = [p for p in tt.scanner(cfg).get()["ports"] if p.get("teensy")]
    if not teensys and not dry_run:
        return "Connect the Teensy USB."
    try:
        src = tt.resolve(cfg, source)
    except Exception as exc:
        return f"Cannot read the branch: {exc}"
    return tt.flash_block_reason(_last_build(ctx), src, tt.board_settings(cfg))


def _last_build(ctx):
    job = ctx.jobs.get("teensy")
    if job and job.title == "build" and job.state == "done" and isinstance(job.result, dict):
        return job.result
    return getattr(ctx, "_teensy_last_build", None)


def register(app, ctx) -> None:
    cfg = ctx.cfg
    serial = ctx.serial
    imu = tt.ImuWatch()

    # ---- firmware source list (fetch on open, cached git reads)
    @app.callback(Output("ty-source", "options"), Output("ty-source", "value"), Output("ty-fetched", "children"),
                  Input("url", "pathname"), Input("ty-slow", "n_intervals"), Input("ty-fetch-btn", "n_clicks"),
                  State("ty-source", "value"))
    @local_only
    def source_list(path, _n, _f, current):
        if path != "/teensy":
            return no_update, no_update, no_update
        trig = dctx.triggered_id
        if trig == "ty-fetch-btn":
            tt.fetch_in_background(cfg, min_age_s=0)
        elif trig == "url" or trig is None:
            tt.fetch_in_background(cfg, min_age_s=60)
        try:
            s = tt.sources_cached(cfg)
        except Exception as exc:
            return [], None, f"Repo error: {exc}"
        opts = [{"label": tt.source_label(b), "value": b["name"]} for b in s["branches"]]
        if s["worktree"]["dirty"]:
            opts.append({"label": f"{s['worktree']['branch']} working copy · {len(s['worktree']['dirty'])} "
                                  f"uncommitted file(s) · build only", "value": tt.WORKTREE})
        values = {o["value"] for o in opts}
        value = current if current in values else s["newest"]
        f = tt.fetch_state()
        if f.get("running"):
            fetched = "Fetching…"
        elif f.get("error"):
            fetched = "GitHub not reachable, showing local copy"
        elif f.get("time"):
            fetched = "Fetched " + time.strftime("%H:%M:%S", time.localtime(f["time"]))
        else:
            fetched = ""
        return opts, value, fetched

    # ---- details of the chosen source; feeds every tab
    @app.callback(Output("ty-commit", "children"), Output("ty-vsmain", "children"), Output("ty-board", "children"),
                  Output("ty-lastflash", "children"), Output("ty-file", "options"), Output("ty-file", "value"),
                  Output("ty-diff", "children"), Output("ty-code-src", "children"),
                  Input("ty-source", "value"), Input("ty-slow", "n_intervals"), State("ty-file", "value"))
    @local_only
    def source_details(source, _n, cur_file):
        if not source:
            return ["–"] * 4 + [[], None, "", ""]
        try:
            src = tt.resolve(cfg, source)
            files = tt.daq_files(cfg, source)
        except Exception as exc:
            return [f"Cannot read: {exc}", "–", "–", "–", [], None, "", ""]
        board = tt.board_settings(cfg)
        commit = html.Span([html.Span(src["short"], className="mono"), f"  {src.get('subject', '')}  · ",
                            time.strftime("%Y-%m-%d %H:%M", time.localtime(src["time"]))])
        if src["kind"] == "worktree":
            vs = f"{len(src['dirty'])} uncommitted file(s) in DAQ/"
        else:
            b = next((x for x in tt.sources_cached(cfg)["branches"] if x["name"] == source), {})
            n = b.get("ahead_of_main")
            vs = ("same firmware as main" if n == 0 else f"{n} firmware commit(s) not on main") if n is not None else "–"
            if src.get("note"):
                vs += f" · {src['note']}"
        board_txt = html.Span([board["summary"], html.Br(),
                               html.Span(("from " if board["pinned"] else "") + board["source"], className="hint")],
                              title=board["fqbn"])
        lf = tt.last_flash(cfg)
        last = (html.Span([html.Span(lf["commit"], className="mono"), f" {lf['branch']} · {lf['time']}"])
                if lf else "No flash from this app yet")
        file_val = cur_file if cur_file in files else ("DAQ.ino" if "DAQ.ino" in files else (files[0] if files else None))
        trig = dctx.triggered_id
        try:
            diff = tt.changes_vs_main(cfg, source) if trig != "ty-slow" else no_update
        except Exception as exc:
            diff = f"Cannot diff: {exc}"
        return commit, vs, board_txt, last, files, file_val, diff, f"{src['name']} @ {src['short']}"

    @app.callback(Output("ty-file-view", "children"), Input("ty-file", "value"), Input("ty-source", "value"))
    @local_only
    def show_file(name, source):
        if not name or not source:
            return ""
        try:
            return tt.read_daq_file(cfg, source, name)
        except Exception as exc:
            return f"cannot read: {exc}"

    # ---- tabs
    @app.callback(Output("ty-tab", "data"),
                  Input({"type": "ty-tab-btn", "tab": "build"}, "n_clicks"),
                  Input({"type": "ty-tab-btn", "tab": "code"}, "n_clicks"),
                  Input({"type": "ty-tab-btn", "tab": "changes"}, "n_clicks"),
                  Input({"type": "ty-tab-btn", "tab": "serial"}, "n_clicks"), prevent_initial_call=True)
    def pick_tab(*_):
        trig = dctx.triggered_id
        return trig["tab"] if isinstance(trig, dict) else no_update

    @app.callback(*[Output(f"ty-panel-{k}", "style") for k, _ in TABS],
                  *[Output({"type": "ty-tab-btn", "tab": k}, "aria-pressed") for k, _ in TABS],
                  Input("ty-tab", "data"))
    def show_tab(tab):
        styles = [{} if k == tab else {"display": "none"} for k, _ in TABS]
        pressed = ["true" if k == tab else "false" for k, _ in TABS]
        return *styles, *pressed

    # ---- build
    @app.callback(Output("ty-build-summary", "children", allow_duplicate=True), Input("ty-build-btn", "n_clicks"),
                  State("ty-source", "value"), prevent_initial_call=True)
    @local_only
    def build(_n, source):
        if not source:
            return "Pick a firmware branch first."
        if ctx.jobs.running("teensy"):
            return "A build or flash is already running."
        ctx.jobs.start("teensy", "build", lambda job: tt.compile_job(cfg, job, run_process, source))
        return "Building…"

    # ---- flash: inline two-step confirm (first click arms for 3 s, second click flashes)
    @app.callback(Output("ty-flash-msg", "children", allow_duplicate=True), Output("ty-flash-arm", "data"),
                  Output("ty-flash-btn", "children", allow_duplicate=True),
                  Output("ty-flash-btn", "className", allow_duplicate=True),
                  Input("ty-flash-btn", "n_clicks"), State("ty-flash-arm", "data"), State("ty-source", "value"),
                  State("ty-dry", "value"), prevent_initial_call=True)
    @local_only
    def flash(_n, armed, source, dry):
        dry_run = "dry" in (dry or [])
        reason = _block_reason(ctx, cfg, source, dry_run)
        if reason:
            return reason, None, no_update, no_update
        if not armed or time.time() - armed > CONFIRM_S:
            return "Click again within 3 s to flash.", time.time(), "Confirm flash?", "btn danger confirming"
        build = _last_build(ctx)
        ports = [p for p in tt.scanner(cfg).get()["ports"] if p.get("teensy")]
        port = ports[0] if ports else {"port": "COM?", "label": "no Teensy (dry run)"}
        if serial.running():
            serial.stop()  # the loader needs the port
        ctx.jobs.start("teensy", "flash" + (" (dry run)" if dry_run else ""),
                       lambda j: tt.flash_job(cfg, j, run_process, port, build, dry_run))
        return (("Dry run started." if dry_run else f"Flashing {build['branch']} @ {build['commit']}…"), None,
                "Flash (dry run)" if dry_run else "Flash", "btn danger")

    # ---- 1 s refresh: USB, stream, job log, flash button, IMU card, port list
    @app.callback(Output("ty-port", "children"), Output("ty-stream", "children"), Output("ty-job-log", "children"),
                  Output("ty-build-summary", "children"), Output("ty-flash-btn", "children"),
                  Output("ty-flash-btn", "className"), Output("ty-flash-btn", "aria-disabled"),
                  Output("ty-flash-btn", "title"), Output("ty-flash-msg", "children"),
                  Output("ty-serial-port", "options"), Output("ty-serial-port", "value"),
                  Output("ty-imu-state", "children"), Output("ty-imu-recent", "children"),
                  Output("ty-imu-total", "children"), Output("ty-imu-spells", "children"),
                  Input("ty-poll", "n_intervals"), State("url", "pathname"), State("ty-source", "value"),
                  State("ty-dry", "value"), State("ty-flash-arm", "data"), State("ty-serial-port", "value"))
    @local_only
    def refresh(_n, path, source, dry, armed, port_val):
        if path != "/teensy":
            return [no_update] * 15
        sc = tt.scanner(cfg)
        sc.touch()
        scan = sc.get()
        teensys = [p for p in scan["ports"] if p.get("teensy")]
        port_txt = ", ".join(p["label"] for p in teensys) if teensys else "Not connected (USB only when debugging)"
        if scan.get("error"):
            port_txt += f" · {scan['error']}"
        live = ctx.live.stream_live()
        stream = "Live: flashing locked" if live else "Not live"

        job = ctx.jobs.get("teensy")
        log = summary = no_update
        if job:
            log = f"[{job.state}] {job.title}\n" + "\n".join(list(job.lines)[-80:])
            if job.title == "build" and job.state != "running" and isinstance(job.result, dict):
                r = job.result
                ctx._teensy_last_build = r
                summary = html.Span([("Build OK" if r.get("ok") else "Build failed") + f" · {r.get('branch')} @ ",
                                     html.Span(r.get("commit"), className="mono"), f" · {r.get('time', '')[11:16]}"])
            elif job.state == "running":
                summary = f"{job.title.capitalize()}…"

        dry_run = "dry" in (dry or [])
        reason = _block_reason(ctx, cfg, source, dry_run)
        arming = bool(armed) and time.time() - armed <= CONFIRM_S and not reason
        btn_txt = "Confirm flash?" if arming else ("Flash (dry run)" if dry_run else "Flash")
        btn_cls = "btn danger confirming" if arming else "btn danger"
        msg = reason or ("Click again within 3 s to flash." if arming else
                         "Ready: flashes the build shown above.")

        opts = [{"label": p["label"], "value": p["port"]} for p in scan["ports"]]
        vals = [o["value"] for o in opts]
        pval = port_val if port_val in vals else (next((p["port"] for p in teensys), vals[0] if vals else None))

        st = imu.update((ctx.live.get_status().get("health") or {}))
        names = {"ok": "Valid", "warn": "Some invalid values", "bad": "Invalid (byte slip?)", "idle": "No data"}
        since = time.strftime("%H:%M:%S", time.localtime(st["since"])) if st["since"] else ""
        state_txt = html.Span(names.get(st["state"], st["state"]) + (f" · since {since}" if since else ""),
                              className="ty-bad" if st["state"] == "bad" else "")
        recent = f"{st['recent_bad']:,} of {st['recent_total']:,} values" if st["recent_total"] else "–"
        total = f"{st['bad_total']:,} of {st['total']:,} values" if st["total"] else "–"
        spells = str(st["invalid_spells"])
        if st["events"]:
            t, old, new = st["events"][0]
            spells += f" · last change {time.strftime('%H:%M:%S', time.localtime(t))} ({old} → {new})"
        return (port_txt, stream, log, summary, btn_txt, btn_cls, "true" if reason else "false", reason or "",
                msg, opts, pval, state_txt, recent, total, spells)

    # ---- serial monitor
    @app.callback(Output("ty-serial-state", "children"), Output("ty-serial-paused", "data"),
                  Input("ty-serial-start", "n_clicks"), Input("ty-serial-stop", "n_clicks"),
                  Input("ty-serial-pause", "n_clicks"), Input("ty-serial-clear", "n_clicks"),
                  Input("ty-rescan", "n_clicks"),
                  State("ty-serial-port", "value"), State("ty-serial-paused", "data"), prevent_initial_call=True)
    @local_only
    def serial_ctrl(_s, _t, _p, _c, _r, port, paused):
        trig = dctx.triggered_id
        if trig == "ty-rescan":
            tt.scanner(cfg).rescan()
            return "Scanning USB…", paused
        if trig == "ty-serial-start":
            entry = next((p for p in tt.scanner(cfg).get()["ports"] if p["port"] == port), None)
            if not entry:
                return "Connect the Teensy USB and pick its port.", paused
            if ctx.jobs.running("teensy") and "flash" in (ctx.jobs.get("teensy").title or ""):
                return "Wait for the flash to finish.", paused
            serial.start(entry)
            return f"Monitoring {entry['label']} · log {serial.log_path}", False
        if trig == "ty-serial-stop":
            serial.stop()
            return "Stopped.", paused
        if trig == "ty-serial-pause":
            return ("Resumed." if paused else "Paused (still logging)."), not paused
        serial.clear()
        return "Cleared.", paused

    @app.callback(Output("ty-serial-out", "children"), Input("ty-poll", "n_intervals"),
                  State("ty-serial-filter", "value"), State("ty-serial-paused", "data"), State("url", "pathname"),
                  State("ty-tab", "data"))
    @local_only
    def serial_view(_n, filt, paused, path, tab):
        if path != "/teensy" or paused or tab != "serial":
            return no_update
        txt = serial.text(filt or "")
        if not txt and not serial.running():
            txt = "Serial monitor stopped. Connect the Teensy over USB, pick its port and press Start."
        if serial.error:
            txt += f"\n[{serial.error}]"
        return txt
