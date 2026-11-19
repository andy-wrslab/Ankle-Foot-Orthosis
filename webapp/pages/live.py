"""Live page: the real-time dashboard (from GUI_robust), fed by the live worker."""
from __future__ import annotations

import json
import string
from typing import Any, Dict, List, Tuple

import dash
import plotly.graph_objs as go
from dash import dcc, html, Input, Output, State

from constants import COLOR_CYCLE, N_WINDOW_SEC

_FONT = "'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"
_INK = "#1F1E1B"
_GRID = "#EFECE6"
_AXIS = "#D9D4C9"

# Latching toggle shared by the motor/assist/k buttons. A new data-link session
# means the target restarted with everything at zero, so the button follows.
_TOGGLE_JS = """
function(n, session, state){
    var ctx = window.dash_clientside ? window.dash_clientside.callback_context : null;
    var trigger = (ctx && ctx.triggered && ctx.triggered.length) ? ctx.triggered[0].prop_id : '';
    if(trigger.indexOf('link-session.') === 0){
        return [0, ''];
    }
    if(typeof state !== 'number') state = 0;
    if(n === undefined || n === null){ return [state, state ? 'on' : '']; }
    var newState = state ? 0 : 1;
    return [newState, newState ? 'on' : ''];
}
"""

_C = COLOR_CYCLE
# (graph id, title, unit, y range, y tick step, channels: (label, colour, key, index, decimals))
CARDS: List[Tuple[str, str, str, list, float, list]] = [
    ("torque", "Torque", "N·m", [-5, 15], 5,
     [("Measured", _C[0], "torque", None, 2, 7), ("Commanded", _C[1], "demand_torque", None, 2, 7)]),
    ("gait", "Stride velocity", "m/s", [0, 2], 0.5,
     [("SV", _C[3], "gait", None, 2, 5)]),
    ("press", "Plantar pressure", "raw counts", [0, 1000], 200,
     [(f"p{i + 1}", _C[i], "press", i, 0, 5) for i in range(8)]),
    ("imu", "IMU acceleration", "g", [-3, 3], 1,
     [("ax", _C[0], "imu", 0, 3, 7), ("ay", _C[1], "imu", 1, 3, 7), ("az", _C[3], "imu", 2, 3, 7)]),
]


def make_fig(unit: str, yrange: list, dtick: float, channels: list, x_title: str = "time (s)",
             xrange=None) -> go.Figure:
    data = [go.Scattergl(x=[], y=[], mode="lines", name=label, line=dict(width=1.5, color=color),
                         hoverinfo="skip", showlegend=False)
            for label, color, *_rest in channels]
    axis_common = dict(showgrid=True, gridcolor=_GRID, gridwidth=1, showline=True, linecolor=_AXIS,
                       linewidth=1, ticks="outside", ticklen=4, tickcolor=_AXIS,
                       tickfont=dict(size=12, color="#6F6B63"), fixedrange=True, automargin=True)
    layout = dict(
        xaxis=dict(range=xrange or [-N_WINDOW_SEC, 0], dtick=2, zeroline=False,
                   title=dict(text=x_title, font=dict(size=15, color="#7A756B"), standoff=4), **axis_common),
        yaxis=dict(range=yrange, dtick=dtick, zeroline=True, zerolinecolor=_AXIS, zerolinewidth=1,
                   title=dict(text=unit, font=dict(size=15, color="#7A756B"), standoff=6), **axis_common),
        margin=dict(l=60, r=30, t=8, b=44, autoexpand=True), showlegend=False, plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF", font=dict(family=_FONT, size=13, color=_INK), uirevision="afo",
    )
    return go.Figure(data=data, layout=layout)


def _card(graph_id: str, title: str, unit: str, fig: go.Figure, channels: list) -> html.Div:
    chips = [html.Span(className="chip", children=[
        html.Span(className="swatch", style={"background": color}),
        html.Span(label, className="chip-label"),
        html.Span("—", id=f"rv-{graph_id}-{i}", className="chip-value", style={"width": f"{width}ch"}),
    ]) for i, (label, color, _k, _i, _d, width) in enumerate(channels)]
    return html.Div(className=f"card card-{graph_id}", children=[
        html.Div(className="card-head", children=[
            html.Div(className="card-title", children=[html.H3(title), html.Span(unit, className="card-unit")]),
            html.Div(className="readouts", children=chips),
        ]),
        dcc.Graph(id=graph_id, className="card-graph", figure=fig,
                  config={"displayModeBar": False, "staticPlot": True, "responsive": True}),
    ])


def _param_field(label: str, input_id: str, value: float) -> html.Div:
    return html.Div(className="param-field", children=[
        html.Label(label, htmlFor=input_id),
        dcc.Input(id=input_id, type="number", debounce=True, value=value, placeholder=str(value)),
    ])


_FIGS = {gid: make_fig(unit, yr, dt, ch) for gid, _t, unit, yr, dt, ch in CARDS}


def layout(ctx=None) -> html.Div:
    sent = ctx.commands.view()["params"] if ctx is not None else {}

    def pv(key, default):
        v = sent.get(key)
        return default if v is None else v

    cards = {gid: _card(gid, title, unit, _FIGS[gid], ch) for gid, title, unit, _yr, _dt, ch in CARDS}
    return html.Div(children=[
        dcc.Store(id="momentary-event", data=None),
        dcc.Store(id="window-sec", data=N_WINDOW_SEC),
        dcc.Store(id="link-session", data=None),
        dcc.Store(id="tab-index", data=0),
        dcc.Interval(id="zero-interval", interval=100, n_intervals=0),
        html.Div(className="page-head", children=[
            html.H2("Live"),
            html.Div(className="segmented", children=[
                html.Button("2 s", id="window-2-btn", n_clicks=0),
                html.Button("10 s", id="window-10-btn", n_clicks=0, className="active"),
            ]),
        ]),
        html.Div(className="swipe-container", children=[
            html.Div(className="swipe-page", children=[
                html.Div(className="plots", children=[cards["torque"], cards["gait"]])]),
            html.Div(className="swipe-page", children=[
                html.Div(className="plots second-set", children=[cards["press"], cards["imu"]])]),
        ]),
        html.Div(id="tab-dots", children=[html.Span(className="tab-dot", id="dot-0"),
                                          html.Span(className="tab-dot", id="dot-1")]),
        html.Div(className="controls-dock", children=[
            dcc.Tabs(id="control-tabs", value="controls-tab", className="control-tabs",
                     parent_className="control-tabs-container", children=[
                dcc.Tab(label="Controls", value="controls-tab", className="control-tab",
                        selected_className="control-tab selected", children=[
                    html.Div(className="controls", children=[
                        html.Button("Zero", id="zero-btn", n_clicks=0),
                        html.Button([html.Span("Motor", className="btn-label"), html.Span("drive: no data", id="motor-drive", className="btn-sub")], id="motor-btn", n_clicks=0),
                        html.Button("Assist", id="assist-btn", n_clicks=0),
                        html.Button("K", id="k-btn", n_clicks=0),
                        html.Button("Calibrate Pressure", id="calibrate-btn", n_clicks=0),
                        html.Button("Reset SV", id="reset-btn", n_clicks=0),
                    ])]),
                dcc.Tab(label="Parameters", value="params-tab", className="control-tab",
                        selected_className="control-tab selected", children=[
                    html.Div(className="param-grid", children=[
                        _param_field("Epsilon Up", "epsup-input", pv("epsilon_up", 0.05)),
                        _param_field("Epsilon Down", "epsdown-input", pv("epsilon_down", 0.05)),
                        _param_field("Step Up", "stepup-input", pv("step_up", 0.05)),
                        _param_field("Step Down", "stepdown-input", pv("step_down", 0.05)),
                        _param_field("V Min", "vmin-input", pv("v_min", 0.5)),
                    ])]),
            ]),
            html.Div(id="cmd-warn"),
            html.Div(className="cmd-row", children=[
                html.Div(id="cmd-msg", className="cmd-msg"),
                dcc.ConfirmDialogProvider(
                    id="cmd-init",
                    message=("Send a command with every UNKNOWN toggle (shown with ?) set to OFF? Toggles this "
                             "console already set keep their state. Nothing else changes."),
                    children=html.Button("Set unknown to OFF", className="btn-small")),
            ]),
        ]),
    ])


def register(app: dash.Dash, ctx) -> None:
    cfg = ctx.cfg

    commands = ctx.commands

    # momentary buttons (Zero / Calibrate / Reset): report press and release only
    app.clientside_callback(
        """
        function(n) {
            var NU = window.dash_clientside.no_update;
            var held = window._afoHeld || (window._afoHeld = {zero: 0, seq: 0});
            var ids = [['zero', 'zero-btn']];
            var ev = NU, cls = [];
            ids.forEach(function(p){
                var el = document.getElementById(p[1]);
                var active = el && el.matches(':active') ? 1 : 0;
                if(ev === NU && active !== held[p[0]]){
                    held[p[0]] = active;
                    held.seq += 1;
                    ev = {name: p[0], value: active, seq: held.seq};
                }
                cls.push(held[p[0]] ? 'on' : '');
            });
            return [ev, cls[0]];
        }
        """,
        Output("momentary-event", "data"), Output("zero-btn", "className"),
        Input("zero-interval", "n_intervals"),
        prevent_initial_call=True,
    )

    @app.callback(Output("cmd-msg", "children", allow_duplicate=True), Input("momentary-event", "data"),
                  prevent_initial_call=True)
    def momentary(ev):
        if not ev or ev.get("name") != "zero":
            return dash.no_update
        r = commands.momentary(ev["name"], 1 if ev.get("value") else 0)
        return r["msg"] or dash.no_update

    # Calibrate pressure / Reset SV: one click = exactly two packets (field 1, then 0)
    @app.callback(Output("cmd-msg", "children", allow_duplicate=True),
                  Input("calibrate-btn", "n_clicks"), Input("reset-btn", "n_clicks"), prevent_initial_call=True)
    def pulse(_c, _r):
        trig = dash.callback_context.triggered
        if not trig or not trig[0].get("value"):
            return dash.no_update
        name = "calibrate" if trig[0]["prop_id"].startswith("calibrate-btn") else "reset"
        return commands.pulse(name)["msg"]

    @app.callback(Output("calibrate-btn", "children"), Output("calibrate-btn", "className"),
                  Input("tab-interval", "n_intervals"), Input("cmd-msg", "children"))
    def calibrate_view(_n, _m):
        left = commands.view()["calibrate_busy_s"]
        if left > 0:
            return f"Calibrating\u2026 {left:.0f} s", "busy"
        return "Calibrate Pressure", ""

    @app.callback(Output("cmd-msg", "children", allow_duplicate=True),
                  Input("motor-btn", "n_clicks"), Input("assist-btn", "n_clicks"), Input("k-btn", "n_clicks"),
                  prevent_initial_call=True)
    def toggle(_m, _a, _k):
        trig = dash.callback_context.triggered
        if not trig or not trig[0].get("value"):
            return dash.no_update
        return commands.press_toggle(trig[0]["prop_id"].split("-btn")[0])["msg"]

    @app.callback(Output("cmd-msg", "children", allow_duplicate=True), Input("cmd-init", "submit_n_clicks"),
                  prevent_initial_call=True)
    def init_unknown(_n):
        return commands.set_unknown_off()["msg"]

    # toggle display = the SERVER's command state (shared by every tab), never a page default
    @app.callback(Output("motor-btn", "className"), Output("assist-btn", "className"), Output("k-btn", "className"),
                  Output("cmd-warn", "children"),
                  Input("tab-interval", "n_intervals"), Input("cmd-msg", "children"))
    def toggle_view(_n, _msg):
        cv = commands.view()
        v = cv["toggles"]
        warn = []
        problem = ctx.session.side_problem() if hasattr(ctx, "session") else None
        if problem:
            warn.append(html.Div(className="banner bad", children=problem + " Motor and Assist are blocked."))
        for m in cv.get("mismatch") or []:
            warn.append(html.Div(className="banner bad",
                                 children=f"{m['name']}: the model holds {m['model']:g} but this console last sent "
                                          f"{m['sent']:g}."))
        return (*[{1: "on", 0: "", None: "unknown"}[v[t]["value"]] for t in ("motor", "assist", "k")], warn or None)

    @app.callback(Output("cmd-msg", "children", allow_duplicate=True),
                  Input("epsup-input", "value"), Input("epsdown-input", "value"), Input("stepup-input", "value"),
                  Input("stepdown-input", "value"), Input("vmin-input", "value"),
                  prevent_initial_call=True)
    def params(eu, ed, su, sd, vm):
        trig = dash.callback_context.triggered
        if not trig:
            return dash.no_update
        ids = {"epsup-input": "epsilon_up", "epsdown-input": "epsilon_down", "stepup-input": "step_up",
               "stepdown-input": "step_down", "vmin-input": "v_min"}
        field = ids.get(trig[0]["prop_id"].split(".")[0])
        page = dict(zip(("epsilon_up", "epsilon_down", "step_up", "step_down", "v_min"), (eu, ed, su, sd, vm)))
        return commands.set_param(field, page[field], page)["msg"]

    @app.callback(
        Output("window-sec", "data"),
        Input("window-2-btn", "n_clicks"), Input("window-10-btn", "n_clicks"),
        State("window-sec", "data"),
        prevent_initial_call=True,
    )
    def update_window(n2, n10, current):
        ctx_ = dash.callback_context
        if not ctx_.triggered:
            return current
        btn = ctx_.triggered[0]["prop_id"].split(".")[0]
        return 2 if btn == "window-2-btn" else 10 if btn == "window-10-btn" else current

    app.clientside_callback(
        "function(win){ return [win === 2 ? 'active' : '', win === 2 ? '' : 'active']; }",
        Output("window-2-btn", "className"), Output("window-10-btn", "className"),
        Input("window-sec", "data"),
    )

    readout_meta = {gid: [[key, idx, dec, width] for _l, _c, key, idx, dec, width in ch] for gid, _t, _u, _y, _d, ch in CARDS}
    app.clientside_callback(
        string.Template(_GRAPH_JS).substitute(
            default_window=N_WINDOW_SEC, max_window=N_WINDOW_SEC,
            torque_fig_json=json.dumps(_FIGS["torque"].to_plotly_json()),
            gait_fig_json=json.dumps(_FIGS["gait"].to_plotly_json()),
            press_fig_json=json.dumps(_FIGS["press"].to_plotly_json()),
            imu_fig_json=json.dumps(_FIGS["imu"].to_plotly_json()),
            readout_meta=json.dumps(readout_meta),
        ),
        Output("torque", "figure"), Output("gait", "figure"),
        Output("press", "figure"), Output("imu", "figure"),
        Output("motor-btn", "style"), Output("link-session", "data"),
        Input("es", "message"), Input("window-sec", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(n){
            var swipe = document.querySelector('.swipe-container');
            if (!swipe) return window.dash_clientside.no_update;
            var idx = Math.round(swipe.scrollLeft / Math.max(1, swipe.clientWidth));
            for (var i = 0; i < 2; ++i) {
                var d = document.getElementById('dot-' + i);
                if (d) { d.className = 'tab-dot' + (i === idx ? ' active' : ''); }
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("tab-index", "data"), Input("zero-interval", "n_intervals"),
        prevent_initial_call=False,
    )


# The plot callback (one per SSE message). Every skip path returns no_update for
# every output, so the motor button style is never reset (the old dashboard
# returned {} and the button flashed black on bad frames). Plots are only
# redrawn while the Live page is visible; the top bar is updated by the shell.
_GRAPH_JS = r"""
function(msg, window_sec){
    var NU = (window && window.dash_clientside) ? window.dash_clientside.no_update : null;
    var NONE = [NU, NU, NU, NU, NU, NU];
    var raf = (typeof window.requestAnimationFrame === 'function')
        ? window.requestAnimationFrame.bind(window) : function(cb){ return setTimeout(cb, 16); };
    try {
        var BASE = {torque: ${torque_fig_json}, gait: ${gait_fig_json},
                    press: ${press_fig_json}, imu: ${imu_fig_json}};
        var READOUTS = ${readout_meta};
        if(!window._afoFigs){
            var cache = {};
            Object.keys(BASE).forEach(function(k){ cache[k] = JSON.parse(JSON.stringify(BASE[k])); });
            window._afoFigs = cache;
        }
        var figs = window._afoFigs;
        var raw = msg ? ((typeof msg === 'string') ? msg : msg.data) : null;
        var p = raw ? window._afoParse(raw) : window._afoLastSnapshot;
        if(!p){ return NONE; }
        if(raw){ window._afoLastSnapshot = p; }
        if(!Array.isArray(p.t) || !p.t.length || typeof p.t_latest !== 'number' || !isFinite(p.t_latest)){ return NONE; }

        var st = window._afoRenderState;
        if(!st){ st = window._afoRenderState = {session: null, lastEmitted: 0, framePending: false, rev: 0, styleKey: null, styleLog: [], frames: 0}; }
        var meta = p.meta || {};
        var sessionOut = NU;
        if(meta.session !== undefined && meta.session !== st.session){
            st.session = meta.session; st.lastEmitted = 0; sessionOut = meta.session;
        }
        // motor button: border/bar from the last VALID status word only; its
        // fill comes from the user's toggle (CSS class), never from data
        var style = NU;
        var sw = p.statusword;
        if(typeof sw === 'number' && isFinite(sw) && sw >= 0 && sw <= 65535){
            // fill = drive status from the statusword (original GUI colours)
            var ms = window._afoMotorStyle(sw);
            var key = JSON.stringify(ms);
            if(key !== st.styleKey){
                st.styleKey = key;
                style = ms;
            }
        }
        if(st.styleLog.length < 2000){ st.styleLog.push(st.styleKey); }
        if(window._afoPage && window._afoPage !== 'live'){
            return [NU, NU, NU, NU, style, sessionOut];   // hidden: skip drawing
        }
        var em = (typeof meta.emitted_at === 'number') ? meta.emitted_at : 0;
        if(raw && st.lastEmitted && em && em <= st.lastEmitted && sessionOut === NU){ return NONE; }
        if(st.framePending && sessionOut === NU){ return [NU, NU, NU, NU, style, NU]; }
        st.framePending = true;
        raf(function(){ st.framePending = false; });
        if(em){ st.lastEmitted = em; }

        var win = Number(window_sec);
        if(!isFinite(win) || win <= 0){ win = ${default_window}; }
        if(win > ${max_window}){ win = ${max_window}; }
        var tl = p.t_latest;
        var bw = (typeof p.bin_width === 'number') ? p.bin_width : 0.02;
        var t = p.t;
        var x = new Array(t.length);
        for(var i = 0; i < t.length; i++){ x[i] = t[i] - tl; }
        var start = 0, cutoff = -win - bw;
        while(start < x.length && x[start] < cutoff){ start++; }
        x = x.slice(start);
        function S(a){ return Array.isArray(a) ? a.slice(start) : []; }
        var dtick = win <= 2 ? 0.5 : 2;
        st.rev += 1; st.frames += 1;
        var out = [NU, NU, NU, NU];
        function build(slot, name, ys){
            try {
                var fig = figs[name];
                for(var k = 0; k < fig.data.length; k++){ fig.data[k].x = x; fig.data[k].y = ys[k] || []; }
                fig.layout.xaxis.range = [-win, 0];
                fig.layout.xaxis.dtick = dtick;
                fig.layout.datarevision = st.rev;
                out[slot] = {data: fig.data, layout: fig.layout};
            } catch(err){ console.error('[AFO] ' + name + ' figure update failed', err); }
        }
        var press = Array.isArray(p.press) ? p.press : [];
        var imu = Array.isArray(p.imu) ? p.imu : [];
        build(0, 'torque', [S(p.torque), S(p.demand_torque)]);
        build(1, 'gait', [S(p.gait)]);
        build(2, 'press', [0, 1, 2, 3, 4, 5, 6, 7].map(function(j){ return S(press[j]); }));
        build(3, 'imu', [0, 1, 2].map(function(j){ return S(imu[j]); }));
        try {
            var L = p.latest || {};
            Object.keys(READOUTS).forEach(function(gid){
                READOUTS[gid].forEach(function(r, i){
                    var el = document.getElementById('rv-' + gid + '-' + i);
                    if(!el){ return; }
                    var v = L[r[0]];
                    if(r[1] !== null && r[1] !== undefined){ v = Array.isArray(v) ? v[r[1]] : null; }
                    var txt = window._afoFmt(v, r[2], r[3]);
                    if(el.textContent !== txt){ el.textContent = txt; }
                });
            });
        } catch(err){ console.error('[AFO] readout update failed', err); }
        return [out[0], out[1], out[2], out[3], style, sessionOut];
    } catch(err){
        console.error('[AFO] graph update failed; frame skipped', err);
        if(window._afoRenderState){ window._afoRenderState.framePending = false; }
        return NONE;
    }
}
"""
