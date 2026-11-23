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


_CFG = {}       # set by register(): layout() fills the branch list from the warm cache


def _source_options(s):
    opts = [{"label": tt.source_label(b), "value": b["name"]} for b in s["branches"]]
    if s["worktree"]["dirty"]:
        opts.append({"label": f"{s['worktree']['branch']} working copy · {len(s['worktree']['dirty'])} "
                              f"uncommitted file(s) · build only", "value": tt.WORKTREE})
    return opts


def layout() -> html.Div:
    s = tt.sources_peek()
    opts = _source_options(s) if s else []
    val = s["newest"] if s else None
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
                    dcc.Dropdown(id="ty-source", clearable=False, searchable=False, placeholder="Loading branches…",
                                 options=opts, value=val),
                ]),
                _kv([("Commit", "ty-commit"), ("Compared with main", "ty-vsmain"),
                     ("Board settings", "ty-board")]),
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
            _kv([("Teensy USB", "ty-port"), ("Speedgoat stream", "ty-stream"), ("Last build", "ty-build-summary"),
                 ("Last flash", "ty-flash-summary")]),
            html.Div(className="card-foot", children=[
                html.Button("Build", id="ty-build-btn", className="btn primary"),
                html.Button("Flash", id="ty-flash-btn", className="btn danger"),
                dcc.Checklist(id="ty-dry", options=[{"label": " Dry run", "value": "dry"}], value=[],
                              className="ty-check", inputClassName="ty-check-input"),
                html.Span(id="ty-flash-msg", className="hint"),
            ]),
            html.Div(id="ty-job-stage", className="ty-stage", **{"aria-live": "polite"}),
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
                            title="Fresh USB list now. The list also updates by itself when a board is "
                                  "plugged in or out."),
                html.Span(id="ty-scan-state", className="hint", **{"aria-live": "polite"}),
                html.Button("Start", id="ty-serial-start", className="btn sm primary"),
                html.Button("Stop", id="ty-serial-stop", className="btn sm"),
                html.Button("Pause", id="ty-serial-pause", className="btn sm"),
                dcc.Input(id="ty-serial-filter", placeholder="Filter", className="input ty-filter", debounce=False),
                html.Span(id="ty-serial-state", className="hint"),
            ]),
            html.Pre(id="ty-serial-out", className="log ty-log tall"),
        ]),
    ])


def _scan_view(st, ports):
    """(Rescan label, disabled, status text) from PortScanner.status()."""
    if st["scanning"]:
        return "Scanning…", True, "Scanning USB…"
    n = sum(1 for p in ports if p.get("teensy"))
    found = f"{n} Teensy found" if n else "No Teensy found"
    if st.get("rescan_at") and st.get("scanned") and time.time() - st["rescan_at"] < 15:
        when = time.strftime("%H:%M:%S", time.localtime(st["scanned"]))
        return "Rescan", False, f"Rescanned {when} · {found}"
    return "Rescan", False, ""


def _fetch_view(f):
    """(button label, disabled, status text, status tooltip) from tt.fetch_state()."""
    if f.get("running"):
        return "Fetching…", True, "Fetching from GitHub…", ""
    if f.get("error"):
        when = (" · last OK " + time.strftime("%H:%M", time.localtime(f["time"]))) if f.get("time") else ""
        return "Fetch latest", False, "GitHub not reachable, showing local copy" + when, f["error"]
    if f.get("time"):
        return "Fetch latest", False, "Fetched " + time.strftime("%H:%M:%S", time.localtime(f["time"])), ""
    return "Fetch latest", False, "", ""


def _block_reason(ctx, cfg, source, dry_run=False):
    """'' when Flash may run, else the reason (shown next to the disabled button)."""
    if not source:
        return "Pick a firmware branch." if tt.sources_peek() else "Loading branches…"
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


def _mmss(sec) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def _flash_row(cfg):
    """'OK · 6f5fa6c · COM4 · 09:42' from flash_log.csv (real flashes only)."""
    lf = tt.last_flash_any(cfg)
    if not lf:
        return "No flash from this app yet"
    ok = lf["result"] == "ok"
    return html.Span([html.B("OK" if ok else ("UNVERIFIED" if lf["result"] == "unverified" else "FAILED"),
                             className="" if ok else "ty-bad"), " · ",
                      html.Span(lf["commit"], className="mono"), f" {lf['branch']} · {lf['port'].split(' ')[0]} · "
                      f"{lf['time'][5:16]}"])


def _build_row(build):
    if not build:
        return "No build in this app session"
    return html.Span([html.B("OK" if build.get("ok") else "FAILED", className="" if build.get("ok") else "ty-bad"),
                      f" · {build.get('branch')} @ ", html.Span(build.get("commit"), className="mono"),
                      f" · {(build.get('time') or '')[11:16]}"])


def _stage_line(job):
    """One line under the buttons: what the running job is doing, or how the last one ended."""
    if not job or job.title not in ("build", "flash", "flash (dry run)"):
        return ""
    m = job.meta or {}
    verb = "Building" if job.title == "build" else "Flashing"
    if job.state == "running":
        bits = [verb, m.get("stage") or "Starting"]
        if job.title == "build" and (m.get("compiled") or m.get("reused")):
            bits.append(f"{m.get('compiled', 0)} files compiled, {m.get('reused', 0)} reused")
        bits.append(_mmss(time.time() - job.started))
        txt = " · ".join(bits)
        if job.title.startswith("flash"):
            txt += " · the Teensy Loader window may open in the background; no action needed"
        return html.Span([html.Span(className="ty-spin", **{"aria-hidden": "true"}), txt])
    took = _mmss((job.finished or time.time()) - job.started)
    r = job.result if isinstance(job.result, dict) else {}
    if job.title == "build":
        return html.Span(("Build OK" if r.get("ok") else "Build FAILED") + f" in {took}",
                         className="" if r.get("ok") else "ty-bad")
    if r.get("dry_run"):
        return f"Dry run done in {took} (nothing uploaded)"
    if r.get("ok"):
        secs = f" ({r.get('back_after_s')} s)" if r.get("back_after_s") is not None else ""
        return html.Span([html.B("Flash OK"), f" · {r.get('commit')} · Reboot OK · back on {r.get('port')}{secs}"
                          f" · {(r.get('time') or '')[11:16]}"])
    return html.Span([html.B("Flash FAILED"), f" · {r.get('reason') or r.get('result') or ''} · {r.get('commit') or ''}"
                      " · see the log below"], className="ty-bad")


def _last_build(ctx):
    job = ctx.jobs.get("teensy")
    if job and job.title == "build" and job.state == "done" and isinstance(job.result, dict):
        return job.result
    return getattr(ctx, "_teensy_last_build", None)


def register(app, ctx) -> None:
    cfg = ctx.cfg
    serial = ctx.serial
    imu = tt.ImuWatch()
    _CFG["cfg"] = cfg
    tt.warm_sources(cfg)

    # ---- firmware source list (fetch on open, cached git reads)
    # The list reloads when a fetch finished ("Fetched …"), so new commits show up at once
    # instead of on the next 5 s tick; "Fetching…" and errors do not reload it.
    @app.callback(Output("ty-source", "options"), Output("ty-source", "value"),
                  Input("url", "pathname"), Input("ty-slow", "n_intervals"), Input("ty-fetched", "children"),
                  State("ty-source", "value"))
    @local_only
    def source_list(path, _n, fetched, current):
        if path != "/teensy":
            return no_update, no_update
        trig = dctx.triggered_id
        if trig == "ty-fetched" and not str(fetched or "").startswith("Fetched"):
            return no_update, no_update
        if trig in ("url", None):
            tt.fetch_in_background(cfg, min_age_s=60)
        try:
            s = tt.sources_cached(cfg)
        except Exception as exc:
            return [{"label": f"Repo error: {exc}", "value": "", "disabled": True}], None
        opts = _source_options(s)
        values = {o["value"] for o in opts}
        value = current if current in values else s["newest"]
        return opts, value

    # ---- Fetch latest: busy while git fetch runs, then the time (or why it failed)
    @app.callback(Output("ty-fetch-btn", "children"), Output("ty-fetch-btn", "disabled"),
                  Output("ty-fetched", "children"), Output("ty-fetched", "title"),
                  Input("ty-fetch-btn", "n_clicks"), Input("ty-poll", "n_intervals"), State("url", "pathname"),
                  State("ty-fetched", "children"))
    @local_only
    def fetch_ui(_n, _i, path, shown):
        if path != "/teensy":
            return no_update, no_update, no_update, no_update
        if dctx.triggered_id == "ty-fetch-btn":
            tt.fetch_in_background(cfg, min_age_s=0)
        view = _fetch_view(tt.fetch_state())
        if view[2] == shown:        # unchanged: do not re-trigger the branch list
            return no_update, no_update, no_update, no_update
        return view

    # ---- details of the chosen source; feeds every tab
    @app.callback(Output("ty-commit", "children"), Output("ty-vsmain", "children"), Output("ty-board", "children"),
                  Output("ty-file", "options"), Output("ty-file", "value"),
                  Output("ty-diff", "children"), Output("ty-code-src", "children"),
                  Input("ty-source", "value"), Input("ty-slow", "n_intervals"), Input("url", "pathname"),
                  State("ty-file", "value"))
    @local_only
    def source_details(source, _n, path, cur_file):
        trig = dctx.triggered_id
        if path != "/teensy" and trig == "ty-slow":
            return [no_update] * 7          # other pages: no git reads every 5 s
        if not source:
            return ["–"] * 3 + [[], None, "", ""]
        try:
            src = tt.resolve(cfg, source)
            files = tt.daq_files(cfg, source)
        except Exception as exc:
            return [f"Cannot read: {exc}", "–", "–", [], None, "", ""]
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
        file_val = cur_file if cur_file in files else ("DAQ.ino" if "DAQ.ino" in files else (files[0] if files else None))
        try:
            diff = tt.changes_vs_main(cfg, source) if trig != "ty-slow" else no_update
        except Exception as exc:
            diff = f"Cannot diff: {exc}"
        return commit, vs, board_txt, files, file_val, diff, f"{src['name']} @ {src['short']}"

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

    # ---- build (atomic: a double click starts one job; the button goes busy at once)
    @app.callback(Output("ty-job-stage", "children", allow_duplicate=True),
                  Output("ty-build-btn", "children", allow_duplicate=True),
                  Output("ty-build-btn", "className", allow_duplicate=True),
                  Output("ty-build-btn", "disabled", allow_duplicate=True),
                  Input("ty-build-btn", "n_clicks"), State("ty-source", "value"), prevent_initial_call=True)
    @local_only
    def build(_n, source):
        if not source:
            return "Pick a firmware branch first.", no_update, no_update, no_update
        job, started = ctx.jobs.start_exclusive("teensy", "build",
                                                lambda j: tt.compile_job(cfg, j, run_process, source))
        if not started:
            what = "Already building" if job.title == "build" else "A flash is running"
            return f"{what} (started {_mmss(time.time() - job.started)} ago).", no_update, no_update, no_update
        return "Building · Preparing · 0:00", "Building… 0:00", "btn primary busy", True

    # ---- flash: two-step confirm on the button itself (first click arms for 3 s, second flashes)
    @app.callback(Output("ty-flash-msg", "children", allow_duplicate=True), Output("ty-flash-arm", "data"),
                  Output("ty-flash-btn", "children", allow_duplicate=True),
                  Output("ty-flash-btn", "className", allow_duplicate=True),
                  Output("ty-flash-btn", "disabled", allow_duplicate=True),
                  Output("ty-job-stage", "children", allow_duplicate=True),
                  Input("ty-flash-btn", "n_clicks"), State("ty-flash-arm", "data"), State("ty-source", "value"),
                  State("ty-dry", "value"), prevent_initial_call=True)
    @local_only
    def flash(_n, armed, source, dry):
        dry_run = "dry" in (dry or [])
        running = ctx.jobs.running("teensy")
        if running is not None:
            what = "Already flashing" if running.title.startswith("flash") else "A build is running"
            return f"{what}.", None, no_update, no_update, no_update, no_update
        reason = _block_reason(ctx, cfg, source, dry_run)
        if reason:
            return reason, None, no_update, no_update, no_update, no_update
        if not armed or time.time() - armed > CONFIRM_S:
            return ("Click again within 3 s to flash.", time.time(), f"Confirm flash? ({int(CONFIRM_S)} s)",
                    "btn danger confirming", False, no_update)
        build = _last_build(ctx)
        ports = [p for p in tt.scanner(cfg).get()["ports"] if p.get("teensy")]
        port = ports[0] if ports else {"port": "COM?", "label": "no Teensy (dry run)"}
        if serial.running():
            serial.stop()  # the loader needs the port
        title = "flash" + (" (dry run)" if dry_run else "")
        job, started = ctx.jobs.start_exclusive("teensy", title,
                                                lambda j: tt.flash_job(cfg, j, run_process, port, build, dry_run))
        if not started:
            return "Already flashing.", None, no_update, no_update, no_update, no_update
        return ((f"Dry run of {build['branch']} @ {build['commit']}." if dry_run else
                 f"Flashing {build['branch']} @ {build['commit']}…"), None, "Flashing… 0:00", "btn danger busy", True,
                "Flashing · Uploading · 0:00")

    # ---- 1 s refresh: USB, stream, job stage/log, buttons, result rows, IMU card, port list
    @app.callback(Output("ty-port", "children"), Output("ty-stream", "children"), Output("ty-job-log", "children"),
                  Output("ty-build-summary", "children"), Output("ty-flash-btn", "children"),
                  Output("ty-flash-btn", "className"), Output("ty-flash-btn", "aria-disabled"),
                  Output("ty-flash-btn", "title"), Output("ty-flash-msg", "children"),
                  Output("ty-serial-port", "options"), Output("ty-serial-port", "value"),
                  Output("ty-imu-state", "children"), Output("ty-imu-recent", "children"),
                  Output("ty-imu-total", "children"), Output("ty-imu-spells", "children"),
                  Output("ty-flash-summary", "children"), Output("ty-job-stage", "children"),
                  Output("ty-build-btn", "children"), Output("ty-build-btn", "className"),
                  Output("ty-build-btn", "disabled"), Output("ty-flash-btn", "disabled"),
                  Input("ty-poll", "n_intervals"), State("url", "pathname"), State("ty-source", "value"),
                  State("ty-dry", "value"), State("ty-flash-arm", "data"), State("ty-serial-port", "value"))
    @local_only
    def refresh(_n, path, source, dry, armed, port_val):
        if path != "/teensy":
            return [no_update] * 21
        sc = tt.scanner(cfg)
        sc.touch()
        scan = sc.get()
        teensys = [p for p in scan["ports"] if p.get("teensy")]
        port_txt = ", ".join(p["label"] for p in teensys) if teensys else "Not connected (USB only when debugging)"
        if not teensys and sc.status()["scanning"]:
            port_txt = "Scanning USB…"
        if scan.get("error"):
            port_txt += f" · {scan['error']}"
        live = ctx.live.stream_live()
        stream = "Live: flashing locked" if live else "Not live"

        job = ctx.jobs.get("teensy")
        log = no_update
        running = bool(job and job.state == "running")
        if job:
            log = f"[{job.state}] {job.title}\n" + "\n".join(list(job.lines)[-80:])
            if job.title == "build" and job.state != "running" and isinstance(job.result, dict):
                ctx._teensy_last_build = job.result
        summary = _build_row(_last_build(ctx))       # builds only; a flash never writes here
        stage = _stage_line(job)
        el = _mmss(time.time() - job.started) if running else ""

        if running and job.title == "build":
            b_txt, b_cls, b_dis = f"Building… {el}", "btn primary busy", True
        else:
            b_txt, b_cls, b_dis = "Build", "btn primary", running

        dry_run = "dry" in (dry or [])
        reason = _block_reason(ctx, cfg, source, dry_run)
        left = CONFIRM_S - (time.time() - armed) if armed else -1
        arming = bool(armed) and left > 0 and not reason
        if running and job.title.startswith("flash"):
            btn_txt, btn_cls, f_dis = f"Flashing… {el}", "btn danger busy", True
            msg = ""
        elif arming:
            btn_txt, btn_cls, f_dis = f"Confirm flash? ({max(1, int(left + 0.999))} s)", "btn danger confirming", False
            msg = "Click again to flash."
        else:
            btn_txt, btn_cls, f_dis = ("Flash (dry run)" if dry_run else "Flash"), "btn danger", False
            msg = reason or "Ready: flashes the last build."

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
        return (port_txt, stream, log, summary, btn_txt, btn_cls, "true" if (reason or f_dis) else "false",
                reason or "", msg, opts, pval, state_txt, recent, total, spells,
                _flash_row(cfg), stage, b_txt, b_cls, b_dis, f_dis)

    # ---- Rescan: busy while the scan runs, then the result with its time
    @app.callback(Output("ty-rescan", "children"), Output("ty-rescan", "disabled"),
                  Output("ty-scan-state", "children"),
                  Input("ty-rescan", "n_clicks"), Input("ty-poll", "n_intervals"), State("url", "pathname"))
    @local_only
    def scan_ui(_n, _i, path):
        if path != "/teensy":
            return no_update, no_update, no_update
        sc = tt.scanner(cfg)
        if dctx.triggered_id == "ty-rescan":
            sc.rescan()
        return _scan_view(sc.status(), sc.get()["ports"])

    # ---- serial monitor
    @app.callback(Output("ty-serial-state", "children"), Output("ty-serial-paused", "data"),
                  Input("ty-serial-start", "n_clicks"), Input("ty-serial-stop", "n_clicks"),
                  Input("ty-serial-pause", "n_clicks"), Input("ty-serial-clear", "n_clicks"),
                  State("ty-serial-port", "value"), State("ty-serial-paused", "data"), prevent_initial_call=True)
    @local_only
    def serial_ctrl(_s, _t, _p, _c, port, paused):
        trig = dctx.triggered_id
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
