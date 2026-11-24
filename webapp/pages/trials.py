"""Trials page: open a saved Speedgoat log, plot it, check its data health, export."""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np
import plotly.graph_objs as go
from plotly.subplots import make_subplots
from dash import ALL, ctx as dash_ctx, dcc, html, Input, Output, State, no_update

import trials_data
from constants import COLOR_CYCLE

GROUPS = {
    "Torque (Nm)": [("bus", 25, "actual"), ("bus", 28, "demand")],
    "Ankle angle (deg)": [("bus", 2, "ankle")],
    "Stride velocity (m/s)": [("bus", 1, "SV")],
    "Pressure (raw)": [("bus", c, f"p{c - 2}") for c in range(3, 11)],
    "IMU accel (g)": [("bus", 11, "ax"), ("bus", 12, "ay"), ("bus", 13, "az")],
    "IMU euler (rad)": [("bus", 14, "yaw"), ("bus", 15, "pitch"), ("bus", 16, "roll")],
    "Gyro (rad/s)": [("bus", 17, "gx"), ("bus", 18, "gy"), ("bus", 19, "gz")],
    "Raw accel (g)": [("bus", 20, "rx"), ("bus", 21, "ry"), ("bus", 22, "rz")],
    "Gait / assist": [("bus", 23, "SV target"), ("bus", 24, "Uc"), ("bus", 26, "heel strike"), ("bus", 27, "assist")],
    "Status / sync": [("bus", 29, "statusword"), ("bus", 30, "sync")],
    "Drive stream": [("drive", i, f"drive {i + 1}") for i in range(7)],
}
DEFAULT_GROUPS = ["Torque (Nm)", "Pressure (raw)", "IMU accel (g)", "Status / sync"]
MAX_POINTS = 4000  # per trace before min/max decimation


class TrialStore:
    """Holds the one trial currently open (decoded arrays live in a cache .npz)."""

    def __init__(self, cfg, jobs, cache_dir: str) -> None:
        self.cfg = cfg
        self.jobs = jobs
        self.cache_dir = cache_dir
        self.path: Optional[str] = None
        self.data: Dict[str, Any] = {}
        self.health: Dict[str, Any] = {}
        self.version = 0
        self._lock = threading.Lock()

    def sources(self) -> List[Dict[str, Any]]:
        return trials_data.list_sources(self.cfg["paths"]["afo_root"])

    def load(self, src: str):
        def run(job):
            prefix = trials_data.cache_prefix(self.cache_dir, src)
            if not os.path.exists(prefix + ".npz") or not os.path.exists(prefix + "_health.json"):
                job.add(f"decoding {src} (separate process) ...")
                r = subprocess.run([sys.executable, os.path.join(os.path.dirname(trials_data.__file__), "trials_data.py"),
                                    src, prefix], capture_output=True, text=True, timeout=900,
                                   creationflags=0x08000000 if os.name == "nt" else 0)
                job.add((r.stdout or "").strip())
                if r.returncode != 0:
                    msg = r.stdout.strip() or r.stderr.strip()
                    try:
                        msg = json.loads(r.stdout).get("err", msg)
                    except Exception:
                        pass
                    raise RuntimeError(msg)
            else:
                job.add("using cached decode")
            z = np.load(prefix + ".npz")
            data = {k: z[k] for k in z.files}
            with open(prefix + "_health.json", encoding="utf-8") as fp:
                health = json.load(fp)
            with self._lock:
                self.path, self.data, self.health = src, data, health
                self.version += 1
            job.add(f"loaded {health['samples']} samples, {len(health['issues'])} issues")
            return {"ok": True}
        return self.jobs.start("trial-load", f"open {os.path.basename(src)}", run)


def _envelope(t: np.ndarray, y: np.ndarray):
    n = len(t)
    if n <= MAX_POINTS:
        return t, y
    bins = MAX_POINTS // 2
    edges = np.linspace(0, n, bins + 1).astype(np.int64)[:-1]
    with np.errstate(all="ignore"):
        lo = np.fmin.reduceat(y, edges)
        hi = np.fmax.reduceat(y, edges)
    tx = np.empty(2 * bins)
    yy = np.empty(2 * bins)
    tx[0::2] = t[edges]
    tx[1::2] = t[np.minimum(edges + np.diff(np.append(edges, n)) // 2, n - 1)]
    yy[0::2] = lo
    yy[1::2] = hi
    return tx, yy


def build_figure(store: TrialStore, groups: List[str], xr) -> go.Figure:
    d = store.data
    if not d or not groups:
        fig = go.Figure()
        fig.update_layout(height=200, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                          annotations=[dict(text="Open a trial to plot it", showarrow=False, font=dict(color="#8E897F"))],
                          xaxis=dict(visible=False), yaxis=dict(visible=False))
        return fig
    t = d["t"]
    i0, i1 = 0, len(t)
    if xr:
        i0 = max(0, int(np.searchsorted(t, xr[0])) - 1)
        i1 = min(len(t), int(np.searchsorted(t, xr[1])) + 1)
    ts = t[i0:i1]
    fig = make_subplots(rows=len(groups), cols=1, shared_xaxes=True, vertical_spacing=0.035,
                        subplot_titles=groups)
    for r, g in enumerate(groups, start=1):
        for j, (src, col, label) in enumerate(GROUPS[g]):
            arr = d.get(src)
            if arr is None:
                continue
            y = arr[i0:i1, col].astype(np.float64)
            with np.errstate(invalid="ignore"):
                y = np.where(np.isfinite(y) & (np.abs(y) < 1e6), y, np.nan)
            tx, yy = _envelope(ts, y)
            fig.add_trace(go.Scattergl(x=tx, y=yy, mode="lines", name=label, legendgroup=g,
                                       line=dict(width=2.4, color=COLOR_CYCLE[j % len(COLOR_CYCLE)]),
                                       hovertemplate=f"{label}  <b>%{{y:.4g}}</b><extra></extra>"),   # no unit / time per row (Andy Nov 24)
                          row=r, col=1)
    fig.update_layout(height=max(320, 210 * len(groups)), margin=dict(l=60, r=16, t=36, b=40),
                      paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", showlegend=False, uirevision="trial",
                      font=dict(family="'Segoe UI', Helvetica, Arial, sans-serif", size=12, color="#1F1E1B"),
                      hovermode="x unified")
    fig.update_xaxes(gridcolor="#EFECE6", linecolor="#D9D4C9", showline=True, zeroline=False)
    fig.update_yaxes(gridcolor="#EFECE6", linecolor="#D9D4C9", showline=True, zerolinecolor="#D9D4C9")
    fig.update_xaxes(title_text="time (s)", row=len(groups), col=1)
    if xr:
        fig.update_xaxes(range=list(xr))
    for a in fig.layout.annotations:
        a.font = dict(size=13, color="#6F6B63")
        a.x = 0
        a.xanchor = "left"
    return fig


def layout(store: TrialStore) -> html.Div:
    return html.Div(children=[
        dcc.Store(id="trials-range", data=None),
        dcc.Store(id="trials-version", data=0),
        dcc.Interval(id="trials-poll", interval=1000, n_intervals=0, disabled=True),
        dcc.Download(id="trials-download"),
        html.Div(className="page-head", children=[html.H2("Trials")]),
        html.Div(className="card", children=[
            html.Div(className="row", children=[
                dcc.Dropdown(id="trials-file", placeholder="Choose a saved log…", className="grow",
                             optionHeight=40),
                html.Button("Open", id="trials-open", className="btn primary"),
                html.Button("Refresh list", id="trials-refresh", className="btn"),
            ]),
            html.Div(id="trials-status", className="muted small"),
        ]),
        html.Div(className="trials-grid", children=[
            html.Div(className="card", children=[
                html.Div(className="card-head", children=[
                    html.H3(id="trials-title", children="No trial open"),
                    html.Div(className="row", children=[
                        html.Button("Whole trial", id="trials-reset", className="btn"),
                        html.Button("Export view to CSV", id="trials-export", className="btn"),
                    ]),
                ]),
                dcc.Checklist(id="trials-groups", options=list(GROUPS), value=DEFAULT_GROUPS, inline=True,
                              className="checks"),
                dcc.Graph(id="trials-graph", figure=build_figure(store, [], None),
                          config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                                  "scrollZoom": True}),
            ]),
            html.Div(className="card", children=[
                html.Div(className="card-head", children=[html.H3("Data health")]),
                html.Div(id="trials-health", className="issues", children=html.Div("–", className="muted")),
            ]),
        ]),
    ])


def _fmt_src(s):
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(s["mtime"]))
    return {"label": f"{s['name']}  ·  {s['mb']} MB  ·  {when}", "value": s["path"]}


def register(app, ctx) -> None:
    store: TrialStore = ctx.trials

    @app.callback(Output("trials-file", "options"), Input("trials-refresh", "n_clicks"), Input("url", "pathname"))
    def list_files(_n, path):
        if path != "/trials":
            return no_update
        return [_fmt_src(s) for s in store.sources()]

    @app.callback(Output("trials-poll", "disabled"), Output("trials-status", "children", allow_duplicate=True),
                  Input("trials-open", "n_clicks"), State("trials-file", "value"), prevent_initial_call=True)
    def open_file(_n, src):
        if not src:
            return True, "Choose a file first."
        if src not in {s["path"] for s in store.sources()}:
            return True, "That file is not in the list."
        store.load(src)
        return False, f"Opening {os.path.basename(src)} …"

    @app.callback(Output("trials-status", "children"), Output("trials-version", "data"),
                  Output("trials-poll", "disabled", allow_duplicate=True),
                  Input("trials-poll", "n_intervals"), State("trials-version", "data"), prevent_initial_call=True)
    def poll(_n, ver):
        job = ctx.jobs.get("trial-load")
        if job is None:
            return no_update, no_update, True
        last = job.lines[-1] if job.lines else ""
        if job.state == "running":
            return f"{job.title}: {last}", no_update, False
        if job.state == "failed":
            return f"Could not open: {(job.result or {}).get('err', last)}", no_update, True
        return f"{job.title}: done · {last}", store.version, True

    @app.callback(Output("trials-range", "data"),
                  Input("trials-graph", "relayoutData"), Input("trials-reset", "n_clicks"),
                  Input({"type": "issue", "index": ALL}, "n_clicks"), Input("trials-version", "data"),
                  State("trials-range", "data"), prevent_initial_call=True)
    def set_range(relayout, _reset, _issues, _ver, current):
        trig = dash_ctx.triggered_id
        if trig == "trials-reset" or trig == "trials-version":
            return None
        if isinstance(trig, dict) and trig.get("type") == "issue":
            if not any(_issues):
                return no_update
            iss = store.health.get("issues", [])[trig["index"]]
            span = max(2.0, min(20.0, iss["t1"] - iss["t0"] + 2.0))
            return [iss["t0"] - 1.0, iss["t0"] - 1.0 + span]
        if not relayout:
            return no_update
        if any(k.endswith("autorange") for k in relayout):
            return None
        lo = hi = None
        for k, v in relayout.items():
            if re.fullmatch(r"xaxis\d*\.range\[0\]", k):
                lo = float(v)
            elif re.fullmatch(r"xaxis\d*\.range\[1\]", k):
                hi = float(v)
            elif re.fullmatch(r"xaxis\d*\.range", k):
                lo, hi = float(v[0]), float(v[1])
        if lo is None or hi is None:
            return no_update
        return [lo, hi]

    @app.callback(Output("trials-graph", "figure"), Output("trials-title", "children"),
                  Input("trials-range", "data"), Input("trials-groups", "value"), Input("trials-version", "data"))
    def draw(xr, groups, _ver):
        title = os.path.basename(store.path) if store.path else "No trial open"
        if store.health:
            title += f"  ·  {store.health['t_end'] - store.health['t_start']:.0f} s"
        return build_figure(store, [g for g in GROUPS if g in (groups or [])], xr), title

    @app.callback(Output("trials-health", "children"), Input("trials-version", "data"))
    def health(_ver):
        h = store.health
        if not h:
            return html.Div("Open a trial to check it.", className="muted")
        issues = h.get("issues", [])
        items = []
        if not issues:
            items.append(html.Div("No problems found.", className="ok-text"))
        for i, iss in enumerate(issues[:40]):
            items.append(html.Button(className="issue", id={"type": "issue", "index": i}, children=[
                html.Span(iss["kind"], className="issue-kind"),
                html.Span(f"{iss['t0']:.2f}–{iss['t1']:.2f} s", className="issue-time"),
                html.Span(iss["detail"], className="issue-detail"),
            ]))
        bad = [c for c in h.get("channels", []) if c["nan"] or c["inf"] or c["over_1e6"]]
        if bad:
            items.append(html.Div("Channels with NaN / Inf / >1e6", className="sub-head"))
            items.append(html.Table(className="mini", children=[
                html.Tr([html.Th("channel"), html.Th("NaN"), html.Th("Inf"), html.Th(">1e6")])] + [
                html.Tr([html.Td(c["name"]), html.Td(c["nan"]), html.Td(c["inf"]), html.Td(c["over_1e6"])])
                for c in bad]))
        items.append(html.Div(f"{h['samples']:,} samples · dt {h['dt'] * 1000:.3f} ms · {h.get('format')}",
                              className="muted small"))
        return items

    @app.callback(Output("trials-download", "data"), Input("trials-export", "n_clicks"),
                  State("trials-range", "data"), State("trials-groups", "value"), prevent_initial_call=True)
    def export(_n, xr, groups):
        d = store.data
        if not d:
            return no_update
        t = d["t"]
        i0, i1 = (0, len(t)) if not xr else (int(np.searchsorted(t, xr[0])), int(np.searchsorted(t, xr[1])))
        i1 = min(i1, i0 + 500_000)  # cap: 500k rows per export
        cols, names = [t[i0:i1]], ["time_s"]
        for g in (groups or []):
            for src, col, label in GROUPS.get(g, []):
                arr = d.get(src)
                if arr is not None:
                    cols.append(arr[i0:i1, col])
                    names.append(re.sub(r"\W+", "_", f"{g.split(' (')[0]}_{label}").strip("_").lower())
        buf = io.StringIO()
        buf.write(",".join(names) + "\n")
        np.savetxt(buf, np.column_stack(cols), delimiter=",", fmt="%.7g")
        sid = getattr(getattr(ctx, "session", None), "sid", None)
        m = re.match(r"^(S\d{1,4})_", os.path.basename(store.path or ""))
        sid = m.group(1) if m else sid       # the trial's own S-ID wins over the current one
        if sid:
            base = f"{sid}_{time.strftime('%y_%m_%d')}_{time.strftime('%H%M')}"
        else:
            base = os.path.splitext(os.path.basename(store.path))[0]
        return dcc.send_string(buf.getvalue(), f"{base}_{t[i0]:.1f}-{t[i1 - 1]:.1f}s.csv")
