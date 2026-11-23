"""Run control page (OMEN only): Speedgoat connect/status, start/stop, load, save.

All MATLAB work goes through the MatlabWorker (one engine, own process, every
call with a timeout) inside background jobs, so the page never blocks.
Start/stop/load ask for confirmation in the page. There are deliberately no
torque, assist or motor controls here: those stay on the Live page, with STO as
the hardware stop. Every action is appended to logs/run_control.csv.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import shutil
import time

from dash import dcc, html, Input, Output, State, no_update

from pages.common import is_local, local_only, locked_notice, kv

TIMEOUTS = {"status": 30, "connect": 60, "disconnect": 30, "start": 90, "stop": 90, "load": 240, "save": 600}


class RunControl:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.status = {}
        self.status_at = 0.0
        self.banner = None

    def audit(self, action: str, detail: str, ok) -> None:
        path = os.path.join(self.ctx.cfg["paths"]["log_dir"], "run_control.csv")
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            if new:
                w.writerow(["time", "action", "ok", "detail"])
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), action, ok, detail])

    def call(self, job, action: str, *args):
        job.add(f"afo_rc('{action}'{''.join(', ' + repr(a) for a in args)}) ...")
        out = self.ctx.matlab.call("afo_rc", action, *args, timeout=TIMEOUTS.get(action, 60))
        res = json.loads(out) if isinstance(out, str) else {"ok": False, "err": repr(out)}
        job.add(json.dumps(res))
        if "connected" in res:
            self.status, self.status_at = res, time.time()
        return res

    def run_action(self, action: str, *args, _meta=None):
        def fn(job):
            job.export_meta = _meta
            stage = {"connect": "Connecting…", "disconnect": "Disconnecting…", "start": "Loading / starting…",
                     "stop": "Stopping…", "load": "Loading…", "save": "Exporting…"}.get(action)
            if stage and hasattr(job, "meta"):
                job.meta["stage"] = stage
            res = self.call(job, action, *args)
            if action in ("connect", "start") and res.get("ok") and hasattr(job, "meta"):
                job.meta["stage"] = "Sending side, mass…"
            ok = bool(res.get("ok"))
            if action == "stop" and not ok:
                self.banner = res.get("err", "failed to stop")
            elif action in ("stop", "start") and ok:
                self.banner = None
            if action == "save" and ok and not getattr(job, "export_meta", None):
                res.update(self._copy_to_afo_mat(res["file"]))
            if action == "save" and ok and getattr(job, "export_meta", None):
                meta = job.export_meta
                meta["saved"] = res
                sp = res.get("splits") or []
                if isinstance(sp, dict):
                    sp = [sp]
                # recording restarts inside this app session: where the joined runs meet
                meta["file_log_runs_joined"] = int(res.get("n_runs") or 1)
                meta["split_t_model_s"] = [s.get("t_model") for s in sp]
                with open(meta["json_path"], "w", encoding="utf-8") as fp:
                    json.dump(meta, fp, indent=1, default=str)
                res["settings_json"] = meta["json_path"]
            if action in ("connect", "start") and ok and hasattr(self.ctx, "session"):
                try:
                    self.ctx.session.after_connect_or_start(action)
                except Exception as exc:
                    job.add(f"session re-apply failed: {exc}")
            if action == "disconnect" and ok and hasattr(self.ctx, "session"):
                self.ctx.session.clear_readback()
            if action == "stop" and ok and hasattr(self.ctx, "session"):
                self.ctx.session.note_stop()
            if action == "stop" and ok and hasattr(self.ctx, "filelog"):
                try:   # the run that was recording is now complete and exportable
                    self.ctx.filelog.refresh_job(job)
                except Exception as exc:
                    job.add(f"file-log list after stop failed: {exc}")
            self.audit(action, " ".join(str(a) for a in args) + " -> " + json.dumps(res)[:400], ok)
            if action not in ("status",):
                try:
                    self.call(job, "status")
                except Exception as exc:
                    job.add(f"status after {action} failed: {exc}")
            return res
        return self.ctx.jobs.start("rc", f"run control: {action}", fn)

    def export_name(self) -> dict:
        """Default export name: {S-ID}_{YYYYMMDD}_{HHMM}_T{nn}; T{nn} = next free trial
        number for that S-ID today. Folder: afo_mat/{S-ID}_{YYYYMMDD}/."""
        sess = self.ctx.session
        if not sess.sid:
            return {"ok": False, "err": "Set the participant S-ID first; nothing exported."}
        day = time.strftime("%Y%m%d")
        folder = os.path.join(self.ctx.cfg["paths"]["afo_root"], "afo_mat", f"{sess.sid}_{day}")
        used = set()
        if os.path.isdir(folder):
            for f in os.listdir(folder):
                m = re.match(rf"^{re.escape(sess.sid)}_{day}_\d{{4}}_T(\d+)", f)
                if m:
                    used.add(int(m.group(1)))
        nn = max(used) + 1 if used else 1
        return {"ok": True, "folder": folder, "name": f"{sess.sid}_{day}_{time.strftime('%H%M')}_T{nn:02d}"}

    def export(self, name: str = ""):
        """Save the newest run as <folder>/<name>.mat (never overwrite: _2, _3, ...) plus
        <name>.json with the session settings. An edited name is sanitised."""
        d = self.export_name()
        if not d["ok"]:
            return None, d["err"]
        folder = d["folder"]
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip())[:80].strip("_") or d["name"]
        os.makedirs(folder, exist_ok=True)
        cand, n = base, 1
        while os.path.exists(os.path.join(folder, cand + ".mat")) or os.path.exists(os.path.join(folder, cand + ".json")):
            n += 1
            cand = f"{base}_{n}"
        mat = os.path.join(folder, cand + ".mat")
        meta = self.ctx.session.settings_record()
        meta.update({"file": mat, "json_path": os.path.join(folder, cand + ".json"),
                     "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"), "file_log_run": None})
        job = self.run_action("save", mat, _meta=meta)
        return job, f"Exporting {os.path.basename(mat)}"

    def _copy_to_afo_mat(self, f: str):
        m = re.match(r"(.+?)_(.+)\.mat$", os.path.basename(f))
        participant = m.group(1) if m else "unknown"
        dest_dir = os.path.join(self.ctx.cfg["paths"]["afo_root"], "afo_mat",
                                f"{participant}_{time.strftime('%y_%m_%d')}")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(f))
        if os.path.exists(dest):
            return {"copy": None, "copy_err": f"{dest} exists, not overwritten"}
        shutil.copy2(f, dest)
        return {"copy": dest}


def layout() -> html.Div:
    if not is_local():
        return html.Div([html.Div(className="page-head", children=[html.H2("Run control")]),
                         locked_notice("Run control")])
    return html.Div(children=[
        dcc.Interval(id="rc-poll", interval=1000, n_intervals=0),
        html.Div(className="page-head", children=[html.H2("Run control")]),
        html.Div(id="rc-banner"),
        html.Div(className="grid-2", children=[
            html.Div(className="card", children=[
                html.Div(className="card-head", children=[html.H3("Speedgoat"),
                                                          html.Div(className="row", children=[
                                                              html.Button("Connect", id="rc-connect", className="btn primary"),
                                                              html.Button("Refresh", id="rc-refresh", className="btn"),
                                                              html.Button("Disconnect", id="rc-disconnect", className="btn")])]),
                kv("Target", "rc-target"), kv("Connected", "rc-connected"), kv("Application", "rc-app"),
                kv("State", "rc-state"), kv("Execution time", "rc-exec"), kv("TET avg / max", "rc-tet"),
                kv("EtherCAT", "rc-ecat"), kv("File log", "rc-filelog"), kv("UDP stream", "rc-udp"),
                kv("MATLAB worker", "rc-matlab"),
            ]),
            html.Div(className="card", children=[
                html.Div(className="card-head", children=[html.H3("Run")]),
                html.P("Start and stop the application on the target. Stop is verified: the page polls until the "
                       "target no longer reports running.", className="muted"),
                html.Div(className="row", children=[
                    dcc.ConfirmDialogProvider(id="rc-start-confirm", message="Start the application on the Speedgoat?",
                                              children=html.Button("Start", className="btn primary")),
                    dcc.ConfirmDialogProvider(id="rc-stop-confirm", message="Stop the application on the Speedgoat?",
                                              children=html.Button("Stop", className="btn warn")),
                ]),
                html.Div(className="sub-head", children="Load application (only when stopped)"),
                html.Div(className="row", children=[
                    dcc.Dropdown(id="rc-app-file", placeholder="Choose an .mldatx", className="grow"),
                    dcc.ConfirmDialogProvider(id="rc-load-confirm", message="Load this application onto the target?",
                                              children=html.Button("Load", className="btn")),
                ]),
                html.Div(className="sub-head", children="Save the file log"),
                html.Div(className="row", children=[
                    dcc.Input(id="rc-participant", placeholder="Participant (e.g. Caleb)", className="grow"),
                    dcc.Input(id="rc-trial", placeholder="Trial (e.g. Lab_Test_5min)", className="grow"),
                    html.Button("Save", id="rc-save", className="btn primary"),
                ]),
                html.Div(id="rc-save-result", className="small"),
            ]),
        ]),
        html.Div(className="card", children=[
            html.Div(className="card-head", children=[html.H3("Activity")]),
            html.Pre(id="rc-log", className="log"),
        ]),
    ])


def register(app, ctx) -> None:
    rc: RunControl = ctx.runctl

    @app.callback(Output("rc-app-file", "options"), Input("url", "pathname"))
    @local_only
    def app_files(path):
        if path != "/run":
            return no_update
        root = ctx.cfg["paths"]["afo_root"]
        files = sorted(glob.glob(os.path.join(root, "*.mldatx")), key=os.path.getmtime, reverse=True)
        return [{"label": f"{os.path.basename(f)}  ·  {time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(f)))}",
                 "value": f} for f in files]

    @app.callback(Output("rc-log", "children", allow_duplicate=True),
                  Input("rc-connect", "n_clicks"), Input("rc-refresh", "n_clicks"), Input("rc-disconnect", "n_clicks"),
                  Input("rc-start-confirm", "submit_n_clicks"), Input("rc-stop-confirm", "submit_n_clicks"),
                  Input("rc-load-confirm", "submit_n_clicks"), State("rc-app-file", "value"),
                  prevent_initial_call=True)
    @local_only
    def actions(c, r, d, start, stop, load, app_file):
        from dash import ctx as dctx
        if ctx.jobs.running("rc"):
            return "Another run-control action is still running."
        trig = dctx.triggered_id
        action = {"rc-connect": "connect", "rc-refresh": "status", "rc-disconnect": "disconnect",
                  "rc-start-confirm": "start", "rc-stop-confirm": "stop", "rc-load-confirm": "load"}.get(trig)
        if action is None:
            return no_update
        if action == "load":
            if not app_file:
                return "Choose an .mldatx first."
            if rc.status.get("running"):
                return "The application is running; stop it before loading."
            rc.run_action("load", app_file)
        else:
            rc.run_action(action)
        return f"{action} requested …"

    @app.callback(Output("rc-save-result", "children"), Input("rc-save", "n_clicks"),
                  State("rc-participant", "value"), State("rc-trial", "value"), prevent_initial_call=True)
    @local_only
    def save(_n, participant, trial):
        if ctx.jobs.running("rc"):
            return "Another run-control action is still running."
        ok_name = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$")
        if not participant or not trial or not ok_name.match(participant) or not ok_name.match(trial):
            return "Enter a participant and a trial name (letters, digits, _ and -)."
        out = os.path.join(ctx.cfg["paths"]["afo_root"], f"{participant}_{trial}.mat")
        if os.path.exists(out):
            return f"{os.path.basename(out)} already exists; choose another trial name."
        rc.run_action("save", out)
        return f"Saving {os.path.basename(out)} … (see Activity)"

    @app.callback(Output("rc-target", "children"), Output("rc-connected", "children"), Output("rc-app", "children"),
                  Output("rc-state", "children"), Output("rc-exec", "children"), Output("rc-tet", "children"),
                  Output("rc-ecat", "children"), Output("rc-filelog", "children"), Output("rc-udp", "children"),
                  Output("rc-matlab", "children"), Output("rc-log", "children"), Output("rc-banner", "children"),
                  Input("rc-poll", "n_intervals"), State("url", "pathname"))
    @local_only
    def refresh(_n, path):
        if path != "/run":
            return [no_update] * 12
        s = rc.status
        # keep the status fresh while connected and the page is open
        if s.get("connected") and time.time() - rc.status_at > 2.0 and not ctx.jobs.running("rc"):
            ctx.jobs.start("rc", "run control: status", lambda job: rc.call(job, "status"))
        poll = ctx.poller.get()
        reach = poll.get("target_reachable")
        live = ctx.live.get_status()
        job = ctx.jobs.get("rc")
        log = ""
        if job:
            log = f"[{job.state}] {job.title}\n" + "\n".join(list(job.lines)[-30:])
        ecat = s.get("ethercat_state")
        ecat_txt = "–" if ecat in (None, []) else ("OP (8)" if ecat == 8 else f"state {ecat} (not OP)")
        tet = "–"
        if s.get("tet_avg_us") not in (None, []):
            tet = f"{s['tet_avg_us']:.0f} / {s['tet_max_us']:.0f} µs"
        banner = None
        if rc.banner:
            banner = html.Div(className="banner bad", children=[
                html.B("The application did not stop. "), html.Span(rc.banner),
                html.Div("Recovery: 1) press Stop once more; 2) if it still runs, in MATLAB run "
                         "tg = slrealtime; stop(tg) and check tg.isRunning; 3) if the target does not respond, "
                         "power-cycle the Speedgoat (STO engaged first). The action log is in logs/run_control.csv."),
            ])
        mw = ctx.matlab.get_status()
        return (
            f"{poll.get('target_host', '192.168.7.5')} · " + ("reachable" if reach else "unreachable" if reach is False else "checking"),
            "yes" if s.get("connected") else "no",
            s.get("app") or "–",
            (s.get("state") or "–") + (" (running)" if s.get("running") else ""),
            f"{s['exec_time']:.1f} s" if isinstance(s.get("exec_time"), (int, float)) else "–",
            tet, ecat_txt, s.get("filelog") or "–",
            f"live · {live.get('rate_hz', 0):.0f} Hz" if ctx.live.stream_live() else "not receiving",
            mw["state"] + (f" · {mw['error']}" if mw.get("error") else ""),
            log, banner,
        )
