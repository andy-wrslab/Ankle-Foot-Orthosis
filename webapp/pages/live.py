"""Live page (design v18): toolbar (Gait | Sensors | Training, window), two plot
cards per sub-page. The dock (Motor / Assist / K / Mode / one-shot actions) and
the top bar are built by assets/afo_console.js from /api/console/state.

* Gait and Sensors plots: main bus 5431 via SSE, drawn by a clientside
  callback (min/max envelope per time bin; no numbers on the page, values via
  the unified hover). Torque = col 25 measured / col 28 command; Stride
  velocity = col 1 sv / col 23 sv_target; FSR 1-8; IMU accel x/y/z.
* Training plots: 5431 cols 27 (assistance level in use) and 24 (Uc) from the
  live worker's 330 s / 100 Hz buffer, 30 s / 2 min / 5 min windows.
* Hover hold: while the pointer is on a plot it is not redrawn
  (hold-<id> stores, set by assets/hover_hold.js).
"""
from __future__ import annotations

import json
import string

import dash
import plotly.graph_objs as go
from dash import dcc, html, Input, Output, State, no_update

from constants import N_WINDOW_SEC
from plot_style import GRAPH_CONFIG, HOVER_FMT, SERIES, base_layout, dtick_for, trace_hover, TRAINING_PLOTS

LIVE_GRAPHS = ["torque", "gait", "press", "imu"]
TRAIN_GRAPHS = [p["id"] for p in TRAINING_PLOTS]


def _line(style_key, **extra):
    st = SERIES[style_key]
    d = dict(color=st["color"], width=st["width"])
    if st.get("dash"):
        d["dash"] = st["dash"]
    d.update(extra)
    return d


def _fig(traces, y_range, window_s=N_WINDOW_SEC):
    lay = base_layout(y_range, window_s=window_s)
    return go.Figure(data=traces, layout=lay)


def make_figs():
    sg = lambda **k: go.Scattergl(x=[], y=[], mode="lines", **k)  # noqa: E731
    torque = _fig([sg(line=_line("meas"), **trace_hover("Measured", HOVER_FMT["torque"], "N·m")),
                   sg(line=_line("cmd"), **trace_hover("Command", HOVER_FMT["torque"], "N·m"))], (-5, 15))
    gait = _fig([sg(line=_line("meas"), **trace_hover("Current", HOVER_FMT["speed"], "m/s")),
                 sg(line=_line("cmd"), **trace_hover("Target", HOVER_FMT["speed"], "m/s"))], (0, 2))
    press = _fig([sg(line=dict(color=c, width=1.25), **trace_hover(f"FSR {i + 1}", HOVER_FMT["fsr"]))
                  for i, c in enumerate(SERIES["fsr"])], (0, 1000), )
    imu = _fig([sg(line=_line(k), **trace_hover(n, HOVER_FMT["imu"], "g"))
                for k, n in (("imu_x", "x"), ("imu_y", "y"), ("imu_z", "z"))], (-3, 3))
    return {"torque": torque, "gait": gait, "press": press, "imu": imu}


def training_fig(plot, series=None, window_s=120):
    lay = base_layout(tuple(plot["y"]), window_s=window_s, zeroline=False)
    lay["xaxis"]["dtick"] = dtick_for(window_s)
    traces = []
    for col, name in zip(plot["columns"], plot["names"]):
        s = (series or {}).get(col) or {"t": [], "v": []}
        traces.append(go.Scattergl(x=s["t"], y=s["v"], mode="lines", line=_line("meas"),
                                   **trace_hover(name, plot["fmt"])))
    return go.Figure(data=traces, layout=lay)


_FIGS = make_figs()


def _legend(items):
    out = []
    for name, color, dashed in items:
        out.append(html.Span([html.I(className="dash" if dashed else None, style={"color": color}), name]))
    return html.Span(className="legend", children=out)


def _card(graph_id, title, unit, legend, live, hidden=False, fig=None):
    head = [html.Span(title, className="card-title")]
    if unit:
        head.append(html.Span(unit, className="card-unit"))
    if legend is not None:
        head.append(legend)
    head.append(html.Span(className="spacer"))
    return html.Section(className="card plot-card", hidden=hidden, **{"data-live": live}, children=[
        html.Div(className="card-head", children=head),
        html.Div(className="plot-body", children=dcc.Graph(
            id=graph_id, figure=fig if fig is not None else _FIGS[graph_id], config=GRAPH_CONFIG,
            style={"height": "100%"}, className="dash-graph")),
    ])


def layout(ctx=None) -> html.Div:
    fsr_ramp = html.Span(className="legend", children=html.Span(className="ramp", children=[
        html.B("Heel"), html.I(className="r"), html.B("Toe")]))
    train = {p["id"]: p for p in TRAINING_PLOTS}
    return [
        dcc.Store(id="window-sec", data=N_WINDOW_SEC),
        dcc.Store(id="tr-window", data=120),
        dcc.Store(id="live-sub", data="gait"),
        dcc.Store(id="link-session", data=None),
        *[dcc.Store(id=f"hold-{g}", data=False) for g in LIVE_GRAPHS + TRAIN_GRAPHS],
        dcc.Interval(id="tr-poll", interval=1000, n_intervals=0),
        html.Div(className="toolbar", children=[
            html.Div(className="seg", role="group", **{"aria-label": "Live page"}, children=[
                html.Button("Gait", id="pgGait", **{"aria-pressed": "true"}),
                html.Button("Sensors", id="pgSensors", **{"aria-pressed": "false"}),
                html.Button("Training", id="pgTraining", **{"aria-pressed": "false"}),
            ]),
            html.Span(className="tb-right", children=[
                html.Span("UDP only", className="hint", id="liveSrc"),
                html.Div(className="seg", role="group", id="liveWin", **{"aria-label": "Time window"}, children=[
                    html.Button("2 s", id="w2", **{"aria-pressed": "false"}),
                    html.Button("10 s", id="w10", **{"aria-pressed": "true"}),
                ]),
                html.Div(className="seg", role="group", id="trWin", hidden=True, **{"aria-label": "Time window"},
                         children=[html.Button("30 s", **{"data-w": "30", "aria-pressed": "false"}),
                                   html.Button("2 min", **{"data-w": "120", "aria-pressed": "true"}),
                                   html.Button("5 min", **{"data-w": "300", "aria-pressed": "false"})]),
            ]),
        ]),
        _card("torque", "Torque", "N·m", _legend([("Measured", "var(--s-meas)", False),
                                                  ("Command", "var(--s-cmd)", True)]), "gait"),
        _card("gait", "Stride velocity", "m/s", _legend([("Current", "var(--s-meas)", False),
                                                         ("Target", "var(--s-cmd)", True)]), "gait"),
        _card("press", "Pressure", "FSR 1–8, raw", fsr_ramp, "sensors", hidden=True),
        _card("imu", "IMU acceleration", "g", _legend([("x", "var(--s-x)", False), ("y", "var(--s-y)", False),
                                                       ("z", "var(--s-z)", False)]), "sensors", hidden=True),
        _card("tr-assist", "Assistance", None, _legend([("Level in use", "var(--s-meas)", False)]), "training",
              hidden=True, fig=training_fig(train["tr-assist"])),
        _card("tr-uc", "Uc", None, None, "training", hidden=True, fig=training_fig(train["tr-uc"])),
    ]


def register(app: dash.Dash, ctx) -> None:
    app.clientside_callback(
        string.Template(_GRAPH_JS).substitute(
            default_window=N_WINDOW_SEC, max_window=N_WINDOW_SEC,
            figs_json=json.dumps({k: v.to_plotly_json() for k, v in _FIGS.items()}),
        ),
        Output("torque", "figure"), Output("gait", "figure"), Output("press", "figure"), Output("imu", "figure"),
        Output("link-session", "data"),
        Input("es", "message"), Input("window-sec", "data"),
        State("hold-torque", "data"), State("hold-gait", "data"), State("hold-press", "data"),
        State("hold-imu", "data"),
        prevent_initial_call=True,
    )

    train = {p["id"]: p for p in TRAINING_PLOTS}

    @app.callback(Output("tr-assist", "figure"), Output("tr-uc", "figure"),
                  Input("tr-poll", "n_intervals"), Input("tr-window", "data"),
                  State("live-sub", "data"), State("url", "pathname"),
                  State("hold-tr-assist", "data"), State("hold-tr-uc", "data"))
    def training(_n, win, sub, path, hold_a, hold_u):
        if sub != "training" or (path or "/").strip("/") not in ("", "live"):
            return no_update, no_update
        win = float(win or 120)
        d = ctx.live.slow_data(["assistance_level", "uc"], win, max_points=1500) or {}
        series = d.get("series") or {}
        return (no_update if hold_a else training_fig(train["tr-assist"], series, win),
                no_update if hold_u else training_fig(train["tr-uc"], series, win))


# One run per SSE message. Every skip path returns no_update for every output.
# Only the visible sub-page is drawn (hidden cards are display:none); a held
# graph (pointer on it) is skipped so its hover label stays readable. The
# Motor fill and the model time are written to the DOM here (no Dash output).
_GRAPH_JS = r"""
function(msg, window_sec, hold_torque, hold_gait, hold_press, hold_imu){
    var NU = (window && window.dash_clientside) ? window.dash_clientside.no_update : null;
    var NONE = [NU, NU, NU, NU, NU];
    var raf = (typeof window.requestAnimationFrame === 'function')
        ? window.requestAnimationFrame.bind(window) : function(cb){ return setTimeout(cb, 16); };
    try {
        if(!window._afoFigs){ window._afoFigs = ${figs_json}; }
        var figs = window._afoFigs;
        var raw = msg ? ((typeof msg === 'string') ? msg : msg.data) : null;
        var p = raw ? window._afoParse(raw) : window._afoLastSnapshot;
        if(!p){ return NONE; }
        if(raw){ window._afoLastSnapshot = p; window._afoLastPacketAt = Date.now(); }
        if(!Array.isArray(p.t) || !p.t.length || typeof p.t_latest !== 'number' || !isFinite(p.t_latest)){ return NONE; }
        var st = window._afoRenderState;
        if(!st){ st = window._afoRenderState = {session: null, lastEmitted: 0, framePending: false, rev: 0, frames: 0, drive: null}; }
        var meta = p.meta || {};
        var sessionOut = NU;
        if(meta.session !== undefined && meta.session !== st.session){
            st.session = meta.session; st.lastEmitted = 0; sessionOut = meta.session;
        }
        if(window._afoOnSnapshot){ try { window._afoOnSnapshot(p); } catch(e){ console.error('[AFO] snapshot hook', e); } }
        if(window._afoPage && window._afoPage !== 'live'){ return [NU, NU, NU, NU, sessionOut]; }
        var sub = window._afoLiveSub || 'gait';
        if(sub === 'training'){ return [NU, NU, NU, NU, sessionOut]; }
        var em = (typeof meta.emitted_at === 'number') ? meta.emitted_at : 0;
        if(raw && st.lastEmitted && em && em <= st.lastEmitted && sessionOut === NU){ return NONE; }
        if(st.framePending && sessionOut === NU){ return NONE; }
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
        st.rev += 1; st.frames += 1;
        var H = window._afoHold || {};
        var HOLD = {torque: hold_torque || H.torque, gait: hold_gait || H.gait,
                    press: hold_press || H.press, imu: hold_imu || H.imu};
        var out = [NU, NU, NU, NU];
        function build(slot, name, ys){
            if(HOLD[name]){ return; }
            try {
                var fig = figs[name];
                for(var k = 0; k < fig.data.length; k++){ fig.data[k].x = x; fig.data[k].y = ys[k] || []; }
                fig.layout.xaxis.range = [-win, 0];
                fig.layout.xaxis.dtick = win <= 2 ? 1 : 2;
                fig.layout.datarevision = st.rev;
                out[slot] = {data: fig.data, layout: fig.layout};
            } catch(err){ console.error('[AFO] ' + name + ' figure update failed', err); }
        }
        if(sub === 'gait'){
            build(0, 'torque', [S(p.torque), S(p.demand_torque)]);
            build(1, 'gait', [S(p.gait), S(p.sv_target)]);
        } else {
            var press = Array.isArray(p.press) ? p.press : [];
            var imu = Array.isArray(p.imu) ? p.imu : [];
            build(2, 'press', [0, 1, 2, 3, 4, 5, 6, 7].map(function(j){ return S(press[j]); }));
            build(3, 'imu', [0, 1, 2].map(function(j){ return S(imu[j]); }));
        }
        return [out[0], out[1], out[2], out[3], sessionOut];
    } catch(err){
        console.error('[AFO] graph update failed; frame skipped', err);
        if(window._afoRenderState){ window._afoRenderState.framePending = false; }
        return NONE;
    }
}
"""
