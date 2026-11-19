"""Teensy page (OMEN only): firmware branch, build, guarded flash, serial monitor."""
from __future__ import annotations

import time

from dash import dcc, html, Input, Output, State, no_update

import teensy_tools
from pages.common import is_local, local_only, locked_notice, kv
from workers import run_process


def layout() -> html.Div:
    if not is_local():
        return html.Div([html.Div(className="page-head", children=[html.H2("Teensy")]), locked_notice("Teensy")])
    return html.Div(children=[
        dcc.Interval(id="ty-poll", interval=1000, n_intervals=0),
        dcc.Store(id="ty-build", data=None),
        html.Div(className="page-head", children=[html.H2("Teensy")]),
        html.Div(className="grid-2", children=[
            html.Div(className="card", children=[
                html.Div(className="card-head", children=[html.H3("Firmware")]),
                kv("Repo", "ty-repo"), kv("Branch", "ty-branch"), kv("Last commit", "ty-head"),
                kv("Uncommitted", "ty-dirty"),
                html.Div(className="row", children=[
                    dcc.Dropdown(id="ty-branch-pick", placeholder="Choose a branch", className="grow"),
                    html.Button("Show changes", id="ty-diff-btn", className="btn"),
                    dcc.ConfirmDialogProvider(id="ty-checkout", message="Check out this branch in the firmware repo?",
                                              children=html.Button("Check out", className="btn primary")),
                    dcc.ConfirmDialogProvider(id="ty-main", message="Switch the firmware repo back to main?",
                                              children=html.Button("Back to main", className="btn")),
                ]),
                html.Div(id="ty-git-msg", className="small"),
                html.Pre(id="ty-log-commits", className="log short"),
                html.Pre(id="ty-diff", className="log code"),
            ]),
            html.Div(className="card", children=[
                html.Div(className="card-head", children=[html.H3("Build and flash")]),
                html.Div(className="row", children=[
                    html.Button("Build for Teensy 4.1", id="ty-build-btn", className="btn primary"),
                    html.Span(id="ty-build-summary", className="small"),
                ]),
                kv("Teensy USB", "ty-port"), kv("Speedgoat stream", "ty-stream"),
                html.Div(className="row", children=[
                    dcc.Input(id="ty-confirm", placeholder="Type the branch name to confirm", className="grow"),
                    dcc.Checklist(id="ty-dry", options=[{"label": " Dry run (do not call the loader)", "value": "dry"}],
                                  value=[], className="checks"),
                    html.Button("Flash", id="ty-flash-btn", className="btn warn"),
                ]),
                html.Div(id="ty-flash-msg", className="small"),
                html.Pre(id="ty-job-log", className="log"),
            ]),
        ]),
        html.Div(className="grid-2", children=[
            html.Div(className="card", children=[
                html.Div(className="card-head", children=[html.H3("Serial monitor")]),
                html.Div(className="row", children=[
                    dcc.Dropdown(id="ty-serial-port", placeholder="Connect Teensy USB", className="grow"),
                    html.Button("Start", id="ty-serial-start", className="btn primary"),
                    html.Button("Stop", id="ty-serial-stop", className="btn"),
                    html.Button("Pause", id="ty-serial-pause", className="btn"),
                    html.Button("Clear", id="ty-serial-clear", className="btn"),
                ]),
                dcc.Input(id="ty-serial-filter", placeholder="Filter", className="full", debounce=False),
                html.Div(id="ty-serial-state", className="small muted"),
                html.Pre(id="ty-serial-out", className="log tall"),
                dcc.Store(id="ty-serial-paused", data=False),
            ]),
            html.Div(className="card", children=[
                html.Div(className="card-head", children=[
                    html.H3("Code"),
                    dcc.Dropdown(id="ty-file", placeholder="DAQ file", style={"minWidth": "220px"}),
                ]),
                html.Pre(id="ty-file-view", className="log tall code"),
                html.Div(className="sub-head", children="SD session log (boots.txt)"),
                html.P("The DAQ firmware has no serial command to read its SD card, so boots.txt cannot be shown "
                       "here yet. Read it from the SD card directly, or add a dump command to the firmware.",
                       className="muted small"),
            ]),
        ]),
    ])


def register(app, ctx) -> None:
    cfg = ctx.cfg
    serial = ctx.serial

    @app.callback(Output("ty-branch-pick", "options"), Output("ty-file", "options"),
                  Output("ty-log-commits", "children"), Input("url", "pathname"), Input("ty-git-msg", "children"))
    @local_only
    def repo_lists(path, _msg):
        if path != "/teensy":
            return no_update, no_update, no_update
        d = teensy_tools.repo_details(cfg)
        return d["branches"], teensy_tools.daq_files(cfg), d["log"]

    @app.callback(Output("ty-git-msg", "children"), Output("ty-diff", "children"),
                  Input("ty-diff-btn", "n_clicks"), Input("ty-checkout", "submit_n_clicks"),
                  Input("ty-main", "submit_n_clicks"), State("ty-branch-pick", "value"), prevent_initial_call=True)
    @local_only
    def git_actions(_d, _c, _m, branch):
        from dash import ctx as dctx
        trig = dctx.triggered_id
        try:
            if trig == "ty-diff-btn":
                if not branch:
                    return "Choose a branch first.", no_update
                return f"Changes on {branch} compared with main (DAQ/):", teensy_tools.branch_diff(cfg, branch)
            if trig == "ty-checkout":
                if not branch:
                    return "Choose a branch first.", no_update
                now = teensy_tools.checkout(cfg, branch)
                return f"Checked out {now}. Build it before flashing.", teensy_tools.branch_diff(cfg, now) if now != "main" else ""
            if trig == "ty-main":
                return f"Checked out {teensy_tools.checkout(cfg, 'main')}.", ""
        except Exception as exc:
            return f"Not done: {exc}", no_update
        return no_update, no_update

    @app.callback(Output("ty-file-view", "children"), Input("ty-file", "value"), prevent_initial_call=True)
    @local_only
    def show_file(name):
        if not name:
            return ""
        try:
            return teensy_tools.read_daq_file(cfg, name)
        except Exception as exc:
            return f"cannot read: {exc}"

    @app.callback(Output("ty-build-summary", "children", allow_duplicate=True), Input("ty-build-btn", "n_clicks"),
                  prevent_initial_call=True)
    @local_only
    def build(_n):
        if ctx.jobs.running("teensy"):
            return "A build or flash is already running."
        ctx.jobs.start("teensy", "build", lambda job: teensy_tools.compile_job(cfg, job, run_process))
        return "Building …"

    @app.callback(Output("ty-flash-msg", "children"), Input("ty-flash-btn", "n_clicks"),
                  State("ty-confirm", "value"), State("ty-dry", "value"), prevent_initial_call=True)
    @local_only
    def flash(_n, typed, dry):
        dry_run = "dry" in (dry or [])
        if ctx.jobs.running("teensy"):
            return "A build or flash is already running."
        if ctx.live.stream_live():
            return "Locked: the Speedgoat stream is live (packets in the last 5 s). Stop the trial first."
        ports = [p for p in (ctx.poller.get().get("teensy_ports") or []) if p.get("port")]
        if not ports and not dry_run:
            return "Connect the Teensy USB first."
        info = teensy_tools.repo_summary(cfg)
        if (typed or "").strip() != info["branch"]:
            return f"Type the branch name exactly ({info['branch']}) to confirm."
        job = ctx.jobs.get("teensy")
        build = job.result if (job and job.kind == "teensy" and job.title == "build" and job.state == "done") else None
        commit = teensy_tools._git(cfg, "rev-parse", "--short", "HEAD").strip()
        if not build or not build.get("ok") or build.get("commit") != commit or build.get("dirty"):
            return "Build the current commit first (a clean, successful build is needed)."
        port = ports[0]["port"] if ports else "COM?"
        ctx.jobs.start("teensy", "flash" + (" (dry run)" if dry_run else ""),
                       lambda j: teensy_tools.flash_job(cfg, j, run_process, port, build, dry_run))
        return ("Dry run started." if dry_run else f"Flashing {info['branch']} @ {commit} to {port} …")

    @app.callback(Output("ty-repo", "children"), Output("ty-branch", "children"), Output("ty-head", "children"),
                  Output("ty-dirty", "children"), Output("ty-port", "children"), Output("ty-stream", "children"),
                  Output("ty-job-log", "children"), Output("ty-build-summary", "children"),
                  Output("ty-serial-port", "options"),
                  Input("ty-poll", "n_intervals"), State("url", "pathname"))
    @local_only
    def refresh(_n, path):
        if path != "/teensy":
            return [no_update] * 9
        poll = ctx.poller.get()
        repo = poll.get("repo") or {}
        ports = [p for p in (poll.get("teensy_ports") or []) if p.get("port")]
        job = ctx.jobs.get("teensy")
        log = summary = no_update
        if job:
            log = f"[{job.state}] {job.title}\n" + "\n".join(list(job.lines)[-60:])
            if job.title == "build" and job.state != "running" and isinstance(job.result, dict):
                r = job.result
                summary = (("Build OK" if r.get("ok") else "Build failed") +
                           f" · {r.get('branch')} @ {r.get('commit')}" +
                           "".join(f" · {k} {v.split('free')[0].strip()}" for k, v in (r.get("memory") or {}).items()))
        return (repo.get("repo", "?"), repo.get("branch", "?"), repo.get("head", "?"),
                ", ".join(repo.get("dirty") or []) or "none",
                ", ".join(p["port"] for p in ports) if ports else "not connected (normal during collection)",
                "live: flashing locked" if ctx.live.stream_live() else "not live",
                log, summary, [p["port"] for p in ports])

    @app.callback(Output("ty-serial-state", "children"), Output("ty-serial-paused", "data"),
                  Input("ty-serial-start", "n_clicks"), Input("ty-serial-stop", "n_clicks"),
                  Input("ty-serial-pause", "n_clicks"), Input("ty-serial-clear", "n_clicks"),
                  State("ty-serial-port", "value"), State("ty-serial-paused", "data"), prevent_initial_call=True)
    @local_only
    def serial_ctrl(_s, _t, _p, _c, port, paused):
        from dash import ctx as dctx
        trig = dctx.triggered_id
        if trig == "ty-serial-start":
            if not port:
                return "Connect Teensy USB and choose its port.", paused
            serial.start(port)
            return f"Monitoring {port} · log {serial.log_path}", False
        if trig == "ty-serial-stop":
            serial.stop()
            return "Stopped.", paused
        if trig == "ty-serial-pause":
            return ("Resumed." if paused else "Paused (still logging)."), not paused
        serial.clear()
        return "Cleared.", paused

    @app.callback(Output("ty-serial-out", "children"), Input("ty-poll", "n_intervals"),
                  State("ty-serial-filter", "value"), State("ty-serial-paused", "data"), State("url", "pathname"))
    @local_only
    def serial_view(_n, filt, paused, path):
        if path != "/teensy" or paused:
            return no_update
        txt = serial.text(filt or "")
        if serial.error:
            txt += f"\n[{serial.error}]"
        return txt
