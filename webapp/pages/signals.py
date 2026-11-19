"""Signals page (design v18): every instrumented signal of the running model,
live, via MATLAB (the worker keeps the last 120 s). Left: list card with search
and checkboxes (built by assets/afo_console.js from /api/signals/status);
right: one plot card per picked signal (up to 6, synced x), window 10/30/60 s.

The app retries the MATLAB connection by itself (reconnect, at most 3 times;
never restarts recording). Only after that fails does the red banner offer
ONE "Reconnect Signals" (afo_recover, two-step confirm): POST
/api/signals/reconnect (OMEN only).
"""
from __future__ import annotations

import plotly.graph_objs as go
from dash import dcc, html, Input, Output, State, no_update

from plot_style import GRAPH_CONFIG, base_layout, dtick_for, trace_hover

MAX_PLOTS = 6
FAVOURITES = ["Uc", "assistance", "assistance_level", "SV_target", "median_SV", "Total Desired torque",
              "Actual Torque", "PI_with_switch"]


def layout() -> list:
    cards = []
    for i in range(MAX_PLOTS):
        cards.append(html.Section(className="card plot-card", id=f"sig-card-{i}", hidden=True, children=[
            html.Div(className="card-head", children=[html.Span("", className="card-title", id=f"sig-title-{i}"),
                                                     html.Span(className="spacer")]),
            html.Div(className="plot-body", children=dcc.Graph(
                id=f"sig-g{i}", config=GRAPH_CONFIG, style={"height": "100%"}, className="dash-graph",
                figure=go.Figure(layout=base_layout((0, 1), window_s=30)))),
        ]))
    return [
        dcc.Interval(id="sig-poll", interval=500, n_intervals=0),
        dcc.Store(id="sig-window", data=30),
        dcc.Store(id="sig-pick", data=[]),
        *[dcc.Store(id=f"hold-sig-g{i}", data=False) for i in range(MAX_PLOTS)],
        html.Aside(className="card siglist", children=[
            html.Div(className="sig-search", children=dcc.Input(
                id="sigq", className="input", placeholder="Search signals", debounce=False, name="Search signals")),
            html.Ul(id="sigul"),
        ]),
        html.Section(className="sigplots", id="sigplots", children=[
            html.Div(className="banner", id="sigBanner", hidden=True),
            html.Div(className="toolbar", children=[
                html.Div(className="tb-left", children=[
                    html.Div(className="seg", role="group", id="sigWin", **{"aria-label": "Time window"}, children=[
                        html.Button("10 s", **{"data-w": "10", "aria-pressed": "false"}),
                        html.Button("30 s", **{"data-w": "30", "aria-pressed": "true"}),
                        html.Button("60 s", **{"data-w": "60", "aria-pressed": "false"}),
                    ]),
                    html.Span("MATLAB stream, about 100 Hz", className="hint", id="sigHint"),
                ]),
                html.Span(className="tb-right", children=[
                    html.Button("Start streaming", id="sigOn", className="btn sm", hidden=True),
                    html.Button("Stop streaming", id="sigOff", className="btn sm", hidden=True),
                ]),
            ]),
            html.Div("Pick signals on the left.", className="hint", id="sigEmpty"),
            *cards,
        ]),
    ]


def _fig(name, s, win):
    lay = base_layout((0, 1), window_s=win, zeroline=False)
    lay["xaxis"]["dtick"] = dtick_for(win)
    lay["yaxis"].pop("range", None)
    lay["yaxis"]["autorange"] = True          # MATLAB signals have no fixed nominal range
    lay["uirevision"] = f"sig-{name}"
    tr = go.Scattergl(x=s["t"] if s else [], y=s["v"] if s else [], mode="lines",
                      line=dict(color="#1D1F21", width=1.5), **trace_hover(name, ".4g"))
    return go.Figure(data=[tr], layout=lay)


def register(app, ctx) -> None:
    mw = ctx.matlab
    outs = []
    for i in range(MAX_PLOTS):
        outs += [Output(f"sig-g{i}", "figure"), Output(f"sig-card-{i}", "hidden"), Output(f"sig-title-{i}", "children")]

    @app.callback(*outs, Output("sigEmpty", "hidden"),
                  Input("sig-poll", "n_intervals"), Input("sig-pick", "data"), Input("sig-window", "data"),
                  State("url", "pathname"), *[State(f"hold-sig-g{i}", "data") for i in range(MAX_PLOTS)])
    def refresh(_n, picked, win, path, *holds):
        if (path or "").strip("/") != "signals":
            return [no_update] * (3 * MAX_PLOTS + 1)
        picked = [p for p in (picked or []) if isinstance(p, str)][:MAX_PLOTS]
        win = float(win or 30)
        d = mw.snapshot("data", picked, win, timeout=0.8) if picked else None
        series = (d or {}).get("series") or {}
        res = []
        for i in range(MAX_PLOTS):
            if i < len(picked):
                name = picked[i]
                fig = no_update if holds[i] or (d is None) else _fig(name, series.get(name), win)
                res += [fig, False, name]
            else:
                res += [no_update, True, ""]
        res.append(bool(picked))
        return res


def start_recover(ctx) -> str:
    """Reconnect Signals = afo_recover; only when the worker offers it (3 failed reconnects)."""
    st = ctx.matlab.snapshot("status", timeout=0.6) or {}
    if not st.get("offer_recover"):
        return "Reconnect Signals is offered only after the automatic reconnect failed 3 times."
    if ctx.jobs.running("signals"):
        return "A Signals action is already running."
    ctx.jobs.start("signals", "Reconnect Signals (afo_recover)",
                   lambda job: job.add(ctx.matlab.call("__recover__", "afo_recover", timeout=120)))
    return "Reconnect Signals started (afo_recover) …"
