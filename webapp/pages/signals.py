"""Signals page: every instrumented signal of the running model, live, via MATLAB.

The MATLAB worker streams the target's SDI-instrumented signals (Uc,
assistance, SV estimator, PID terms, drive words, ...) with the host_tools
helpers and keeps the last 120 s. This page only reads that buffer, so it is
cheap and never blocks on MATLAB. Turning the stream on or off is OMEN only.
"""
from __future__ import annotations

import plotly.graph_objs as go
from plotly.subplots import make_subplots
from dash import dcc, html, Input, Output, State, no_update

from constants import COLOR_CYCLE
from pages.common import is_local, local_only

FAVOURITES = ["Uc", "assistance", "assistance_level", "SV_target", "median_SV", "Total Desired torque",
              "Actual Torque", "PI_with_switch"]


def layout() -> html.Div:
    local = is_local()
    return html.Div(children=[
        dcc.Interval(id="sig-poll", interval=500, n_intervals=0),
        html.Div(className="page-head", children=[
            html.H2("Signals"),
            html.Div(className="row", children=[
                html.Button("Start streaming", id="sig-on", className="btn primary") if local else None,
                html.Button("Stop", id="sig-off", className="btn") if local else None,
                html.Div(className="segmented", children=[
                    html.Button("10 s", id="sig-w10", n_clicks=0, className="active"),
                    html.Button("30 s", id="sig-w30", n_clicks=0),
                    html.Button("60 s", id="sig-w60", n_clicks=0),
                ]),
            ]),
        ]),
        dcc.Store(id="sig-window", data=10),
        html.Div(id="sig-banner"),
        html.Div(id="sig-status", className="muted small"),
        html.Div(className="row", children=[
            html.Span("Recovery:", className="muted small"),
            html.Button("Reconnect MATLAB", id="sig-rec-reconnect", className="btn"),
            dcc.ConfirmDialogProvider(
                id="sig-rec-recording",
                message=("Restart target recording? This stops and restarts SDI + file-log recording on the "
                         "Speedgoat. The target's file log is SPLIT at this moment (one run ends, a new one "
                         "starts). The model keeps running; nothing else changes."),
                children=html.Button("Restart recording…", className="btn warn")),
            dcc.ConfirmDialogProvider(
                id="sig-rec-recover",
                message=("Run afo_recover? It removes all of this PC's instruments on the target, "
                         "disconnects, reconnects after 3 s and starts recording if it is not running. "
                         "It does not stop, start or load the app and does not change parameters. If "
                         "recording had stopped, a new file-log run begins."),
                children=html.Button("Full recovery (afo_recover)…", className="btn warn")),
        ]) if local else None,
        html.Div(className="card", children=[
            dcc.Dropdown(id="sig-pick", multi=True, placeholder="Choose signals…", value=[]),
            dcc.Graph(id="sig-graph", config={"displayModeBar": False, "responsive": True},
                      figure=go.Figure(layout=dict(height=200, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                                                   xaxis=dict(visible=False), yaxis=dict(visible=False)))),
        ]),
    ])


def register(app, ctx) -> None:
    mw = ctx.matlab

    @app.callback(Output("sig-status", "children", allow_duplicate=True),
                  Input("sig-on", "n_clicks"), Input("sig-off", "n_clicks"), prevent_initial_call=True)
    @local_only
    def toggle(on, off):
        from dash import ctx as dctx
        want = dctx.triggered_id == "sig-on"
        def run(job):
            job.add(mw.set_stream(want))
            return {"ok": True}
        ctx.jobs.start("signals", "signals on" if want else "signals off", run)
        return "Starting the MATLAB stream (first time: about 15-30 s)…" if want else "Stopping…"

    @app.callback(Output("sig-status", "children", allow_duplicate=True),
                  Input("sig-rec-reconnect", "n_clicks"), Input("sig-rec-recording", "submit_n_clicks"),
                  Input("sig-rec-recover", "submit_n_clicks"), prevent_initial_call=True)
    @local_only
    def recover(a, b, c):
        from dash import ctx as dctx
        mode = {"sig-rec-reconnect": "reconnect", "sig-rec-recording": "recording_restart",
                "sig-rec-recover": "afo_recover"}.get(dctx.triggered_id)
        if not mode:
            return no_update
        ctx.jobs.start("signals", f"signals recovery: {mode}",
                       lambda job: job.add(mw.call("__recover__", mode, timeout=120)))
        return f"Recovery started: {mode} …"

    @app.callback(Output("sig-window", "data"), Output("sig-w10", "className"), Output("sig-w30", "className"),
                  Output("sig-w60", "className"), Input("sig-w10", "n_clicks"), Input("sig-w30", "n_clicks"),
                  Input("sig-w60", "n_clicks"), prevent_initial_call=True)
    def window(a, b, c):
        from dash import ctx as dctx
        w = {"sig-w10": 10, "sig-w30": 30, "sig-w60": 60}.get(dctx.triggered_id, 10)
        return w, *["active" if w == x else "" for x in (10, 30, 60)]

    @app.callback(Output("sig-status", "children"), Output("sig-pick", "options"), Output("sig-pick", "value"),
                  Output("sig-graph", "figure"), Output("sig-banner", "children"),
                  Input("sig-poll", "n_intervals"), State("sig-pick", "value"), State("sig-window", "data"),
                  State("url", "pathname"))
    def refresh(_n, picked, win, path):
        if path != "/signals":
            return no_update, no_update, no_update, no_update, no_update
        st = mw.snapshot("status", timeout=0.6)
        wanted = mw.stream_wanted
        if st is None:
            msg = "MATLAB is not running. " + ("Press Start streaming." if is_local() else
                                               "Start the stream on the OMEN (Signals page).")
            banner = _lost_banner("the MATLAB worker is restarting") if wanted else None
            return msg, no_update, no_update, no_update, banner
        lost = wanted and (st.get("state") != "streaming" or (st.get("silent_s") or 0) > 5)
        banner = _lost_banner(st.get("err") or st.get("state")) if lost else None
        chans = st.get("channels") or []
        names = [c["name"] for c in chans]
        status = f"{st.get('state')}"
        if st.get("nsig"):
            status += f" · {st['nsig']} signals ({st.get('mode')} mode)"
        if st.get("silent_s") is not None and st.get("state") == "streaming":
            status += f" · last data {st['silent_s']:.1f} s ago"
        if st.get("err"):
            status += f" · {st['err'][:160]}"
        value = no_update
        if not picked and names:
            value = [n for n in FAVOURITES if n in names][:6] or names[:4]
            picked = value
        picked = [p for p in (picked or []) if p in names]
        if not picked:
            return status, names, value, no_update, banner
        d = mw.snapshot("data", picked, win or 10, timeout=0.8)
        if not d or not d.get("series"):
            return status, names, value, no_update, banner
        fig = make_subplots(rows=len(picked), cols=1, shared_xaxes=True, vertical_spacing=0.04,
                            subplot_titles=picked)
        for i, n in enumerate(picked, start=1):
            s = d["series"].get(n)
            if not s:
                continue
            fig.add_trace(go.Scattergl(x=s["t"], y=s["v"], mode="lines", name=n, hoverinfo="skip",
                                       line=dict(width=1.5, color=COLOR_CYCLE[(i - 1) % len(COLOR_CYCLE)])),
                          row=i, col=1)
        fig.update_layout(height=max(260, 150 * len(picked)), margin=dict(l=56, r=12, t=28, b=36),
                          showlegend=False, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", uirevision="sig",
                          font=dict(family="'Segoe UI', Helvetica, Arial, sans-serif", size=12, color="#1F1E1B"))
        fig.update_xaxes(range=[-(win or 10), 0], gridcolor="#F1EEE8", linecolor="#D9D4C9", showline=True,
                         zeroline=False, fixedrange=True)
        fig.update_yaxes(gridcolor="#F1EEE8", linecolor="#D9D4C9", showline=True, zerolinecolor="#D9D4C9",
                         fixedrange=True)
        fig.update_xaxes(title_text="time (s)", row=len(picked), col=1)
        for a in fig.layout.annotations:
            a.font = dict(size=12, color="#6F6B63")
            a.x = 0
            a.xanchor = "left"
        if st.get("notes"):
            status += " · " + st["notes"][-1]
        return status, names, value, fig, banner


def _lost_banner(reason):
    return html.Div(className="banner bad", children=[
        html.B("Signals stream lost — Live UDP data is unaffected. "),
        html.Span(f"Reason: {reason}. " if reason else ""),
        html.Span("The app retries automatically (restart MATLAB, reconnect, set up again). Restarting "
                  "recording or afo_recover are manual buttons below."),
    ])
