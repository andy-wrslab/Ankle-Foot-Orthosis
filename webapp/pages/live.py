"""Live page (design v18): toolbar (Gait | Sensors | Training, window), two plot
cards per sub-page. The dock (Motor / Assist / K / Mode / one-shot actions) and
the top bar are built by assets/afo_console.js from /api/console/state.

* Gait and Sensors plots: main bus 5431 via SSE, drawn by a clientside
  callback (min/max envelope per time bin; no numbers on the page, values via
  the unified hover). Torque = col 25 measured / col 28 command; Stride
  velocity = col 1 sv / col 23 sv_target. Sensors (Nov 23): every sensor column,
  one card per group (plot_style.SENSOR_CARDS): FSR 1-8 by insole position, raw
  accel, gyro, linear accel, orientation, ankle angle, ankle velocity (computed);
  each trace named with its current value in the legend; a legend click hides it.
* x axis = absolute model time (the last 10 s / 2 s), ticks scroll with the data.
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
from plot_style import (GRAPH_CONFIG, HOVER_FMT, SENSOR_CARDS, SERIES, base_layout, dtick_for, trace_hover,
                        TRAINING_PLOTS)

SENSOR_IDS = [c["id"] for c in SENSOR_CARDS]
LIVE_GRAPHS = ["torque", "gait"] + SENSOR_IDS
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
    figs = {"torque": torque, "gait": gait}
    for c in SENSOR_CARDS:
        figs[c["id"]] = _fig([sg(line=dict(color=c["colors"][k % len(c["colors"])], width=1.25),
                                 **trace_hover(n, f".{c['dec']}f", c["unit"]))
                              for k, n in enumerate(c["names"])], c["y"])
    return figs


def training_range(t_latest: float, window_s: float):
    """[max(0, t - w), max(w, t)]: from 0 until the model time passes the window, then scrolling."""
    return [max(0.0, t_latest - window_s), max(float(window_s), t_latest)]


def training_fig(plot, series=None, window_s=120, t_latest=None):
    """Training plots on the same absolute model-time axis as Gait / Sensors: the slow
    buffer gives times relative to its newest sample plus t_latest; x = t + t_latest.
    The axis never goes below 0: range [max(0, t - w), max(w, t)], so it starts at 0 and
    scrolls once the model time passes the window (ticks in model seconds)."""
    lay = base_layout(tuple(plot["y"]), window_s=window_s, zeroline=False)
    lay["xaxis"]["dtick"] = dtick_for(window_s)
    tl = float(t_latest) if isinstance(t_latest, (int, float)) else None
    if tl is not None:
        lay["xaxis"]["range"] = training_range(tl, window_s)
    traces = []
    for col, name in zip(plot["columns"], plot["names"]):
        s = (series or {}).get(col) or {"t": [], "v": []}
        x = [v + tl for v in s["t"]] if tl is not None else s["t"]
        traces.append(go.Scattergl(x=x, y=s["v"], mode="lines", line=_line("meas"),
                                   **trace_hover(name, plot["fmt"])))
    return go.Figure(data=traces, layout=lay)


_FIGS = make_figs()


def _legend(items):
    out = []
    for name, color, dashed in items:
        out.append(html.Span([html.I(className="dash" if dashed else None, style={"color": color}), name]))
    return html.Span(className="legend", children=out)


def _value_legend(c):
    """Legend chips with the current value; a click hides / shows that trace."""
    chips = []
    for k, n in enumerate(c["names"]):
        chips.append(html.Button(className="lg", type="button", title=f"Show / hide {n}",
                                 **{"data-g": c["id"], "data-k": str(k), "aria-pressed": "true"}, children=[
                                     html.I(style={"color": c["colors"][k % len(c["colors"])]}),
                                     html.Span(n, className="lg-n"),
                                     html.B("–", className="lg-v mono")]))
    return html.Span(className="legend lg-vals", children=chips)


def _card(graph_id, title, unit, legend, live, hidden=False, fig=None, extra_class=""):
    head = [html.Span(title, className="card-title")]
    if unit:
        head.append(html.Span(unit, className="card-unit"))
    if legend is not None:
        head.append(legend)
    head.append(html.Span(className="spacer"))
    attrs = {"data-live": live} if live else {}
    return html.Section(className="card plot-card" + (f" {extra_class}" if extra_class else ""), hidden=hidden,
                        **attrs, children=[
        html.Div(className="card-head", children=head),
        html.Div(className="plot-body", children=dcc.Graph(
            id=graph_id, figure=fig if fig is not None else _FIGS[graph_id], config=GRAPH_CONFIG,
            style={"height": "100%"}, className="dash-graph")),
    ])


def layout(ctx=None) -> html.Div:
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
        html.Div(className="sensor-grid", id="sensorGrid", hidden=True, **{"data-live": "sensors"}, children=[
            _card(c["id"], c["title"], c["unit"], _value_legend(c), None,
                  extra_class="wide" if c.get("wide") else "") for c in SENSOR_CARDS]),
        _card("tr-assist", "Assistance", None, _legend([("Level in use", "var(--s-meas)", False)]), "training",
              hidden=True, fig=training_fig(train["tr-assist"])),
        _card("tr-uc", "Uc", None, None, "training", hidden=True, fig=training_fig(train["tr-uc"])),
    ]


def register(app: dash.Dash, ctx) -> None:
    app.clientside_callback(
        string.Template(_GRAPH_JS).substitute(
            default_window=N_WINDOW_SEC, max_window=N_WINDOW_SEC,
            figs_json=json.dumps({k: v.to_plotly_json() for k, v in _FIGS.items()}),
            graphs_json=json.dumps(LIVE_GRAPHS),
            cards_json=json.dumps([{"id": c["id"], "src": c["src"], "dec": c["dec"]} for c in SENSOR_CARDS]),
        ),
        Output("link-session", "data"),
        Input("es", "data"), Input("window-sec", "data"),
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
        series, tl = d.get("series") or {}, d.get("t_latest")
        return (no_update if hold_a else training_fig(train["tr-assist"], series, win, tl),
                no_update if hold_u else training_fig(train["tr-uc"], series, win, tl))


# Live plots (Nov 23): the page keeps its own 100 Hz buffer. The first SSE message
# is the full window, later ones are deltas (the last ~0.5 s); points with t > the
# newest buffered t are appended. Drawing is separate from receiving: at most 20 redraws
# per second in requestAnimationFrame (Sensors, 7 plots: 5 per second, all plots in the
# same tick), only the visible sub-tab of a visible page, new points via
# Plotly.extendTraces (maxPoints = window x 100), a full Plotly.react only when a
# graph becomes visible, the window changes, the stream restarts or a trace is
# hidden. A held graph (pointer on it) is skipped and catches up on release.
# The Dash callback ingests the first message and window changes; later SSE messages
# call window._afoLiveMsg directly (assets/sse.js), without a Dash cycle each.
_GRAPH_JS = r"""
function(msg, window_sec){
    var GRAPHS = ${graphs_json}, CARDS = ${cards_json};
    var SERIES = ['ankle', 'torque', 'demand_torque', 'gait', 'sv_target', 'uc', 'assistance_level', 'ankle_vel', 'heel_strike'];
    var NU = (window && window.dash_clientside) ? window.dash_clientside.no_update : null;
    var raf = (typeof window.requestAnimationFrame === 'function')
        ? window.requestAnimationFrame.bind(window) : function(cb){ return setTimeout(function(){ cb(Date.now()); }, 16); };
    var MAXWIN = ${max_window};
    try {
        if(!window._afoFigs){ window._afoFigs = ${figs_json}; }
        var win = Number(window_sec);
        if(!isFinite(win) || win <= 0){ win = ${default_window}; }
        if(win > MAXWIN){ win = MAXWIN; }
        window._afoWinSec = win;

        if(!window._afoLive){
            var L = window._afoLive = {R: {}, rev: 0, pending: false, last: 0, session: null};
            var lowerT = function(arr, x){ var lo = 0, hi = arr.length; while(lo < hi){ var m = (lo + hi) >> 1; if(arr[m] < x){ lo = m + 1; } else { hi = m; } } return lo; };
            var upperT = function(arr, x){ var lo = 0, hi = arr.length; while(lo < hi){ var m = (lo + hi) >> 1; if(arr[m] <= x){ lo = m + 1; } else { hi = m; } } return lo; };
            L.ingest = function(p){
                var B = window._afoBuf, t = Array.isArray(p.t) ? p.t : [];
                var sess = (p.meta || {}).session;
                var reset = !B || p.kind === 'full' || (sess !== undefined && B.session !== undefined && sess !== B.session) ||
                    (t.length && B.t.length && t[t.length - 1] < B.t[B.t.length - 1] - 1);
                var i0 = 0;
                if(reset){
                    B = window._afoBuf = {t: [], s: {}, press: [], imu: [], gen: (B ? B.gen + 1 : 1), session: sess, dt: p.dt || 0.01};
                    SERIES.forEach(function(n){ B.s[n] = []; });
                } else {
                    i0 = upperT(t, B.t.length ? B.t[B.t.length - 1] : -Infinity);
                }
                if(i0 < t.length){
                    var nOld = B.t.length;
                    B.t = B.t.concat(t.slice(i0));
                    SERIES.forEach(function(n){ var a = p[n]; B.s[n] = B.s[n].concat(Array.isArray(a) ? a.slice(i0) : new Array(t.length - i0).fill(null)); });
                    ['press', 'imu'].forEach(function(g){
                        var src = Array.isArray(p[g]) ? p[g] : [];
                        for(var j = 0; j < src.length; j++){
                            if(!B[g][j]){ B[g][j] = new Array(nOld).fill(null); }
                            B[g][j] = B[g][j].concat(src[j].slice(i0));
                        }
                    });
                    var keep = MAXWIN * 100 + 300;
                    if(B.t.length > keep + 200){
                        var cut = B.t.length - keep;
                        B.t = B.t.slice(cut);
                        SERIES.forEach(function(n){ B.s[n] = B.s[n].slice(cut); });
                        ['press', 'imu'].forEach(function(g){ B[g] = B[g].map(function(a){ return a.slice(cut); }); });
                    }
                }
                if(p.latest){ B.latest = p.latest; }
                B.statusword = p.statusword;
            };
            var srcOf = function(B, id){
                if(id === 'torque'){ return [B.s.torque, B.s.demand_torque]; }
                if(id === 'gait'){ return [B.s.gait, B.s.sv_target]; }
                for(var c = 0; c < CARDS.length; c++){
                    if(CARDS[c].id !== id){ continue; }
                    return CARDS[c].src.map(function(sk){
                        var a = sk[0], k = sk[1];
                        if(a === 'press' || a === 'imu'){ return B[a][k] || []; }
                        return B.s[a] || [];
                    });
                }
                return [];
            };
            var latestOf = function(B, sk){
                var Lt = B.latest || {}, a = sk[0], k = sk[1];
                if(a === 'press' || a === 'imu'){ return (Array.isArray(Lt[a]) ? Lt[a] : [])[k]; }
                return Lt[a];
            };
            L.drawOne = function(id, B, winS, tl){
                var gd = document.querySelector('#' + id + ' .js-plotly-plot');
                var r = L.R[id] || (L.R[id] = {stale: true});
                if(!gd || !gd._fullLayout || !window.Plotly){ return; }
                if(gd.offsetParent === null){ r.stale = true; return; }
                var H = window._afoHold || {};
                if(H[id]){ return; }                        // held: keep the hover label; catch up on release
                var figs = window._afoFigs, srcs = srcOf(B, id), hid = (window._afoHidden || {})[id] || {};
                var vis = window._afoVisDirty || {};
                var range = [tl - winS, tl];
                if(r.stale || r.lastT == null || r.win !== winS || r.gen !== B.gen || vis[id]){
                    var i0 = lowerT(B.t, tl - winS - 0.02);
                    var data = figs[id].data.map(function(tr, k){
                        var d = Object.assign({}, tr);
                        d.x = B.t.slice(i0); d.y = (srcs[k] || []).slice(i0);
                        d.visible = hid[k] ? 'legendonly' : true;
                        return d;
                    });
                    var lay = JSON.parse(JSON.stringify(figs[id].layout));
                    lay.xaxis.range = range; lay.xaxis.autorange = false; lay.xaxis.dtick = winS <= 2 ? 1 : 2;
                    lay.datarevision = ++L.rev;
                    window.Plotly.react(gd, data, lay);
                    r.stale = false; r.lastT = tl; r.win = winS; r.gen = B.gen;
                    if(vis[id]){ vis[id] = false; }
                    return;
                }
                if(!(tl > r.lastT)){ return; }
                var i1 = upperT(B.t, r.lastT), xs = [], yv = [], idx = [];
                for(var k = 0; k < srcs.length; k++){ idx.push(k); xs.push(B.t.slice(i1)); yv.push((srcs[k] || []).slice(i1)); }
                gd.layout.xaxis.range = range; gd.layout.xaxis.autorange = false;
                gd.layout.datarevision = ++L.rev;
                window.Plotly.extendTraces(gd, {x: xs, y: yv}, idx, Math.ceil(winS * 100) + 20);
                r.lastT = tl;
            };
            L.render = function(){
                var B = window._afoBuf;
                if(!B || !B.t.length){ return; }
                if(document.hidden){ return; }                       // hidden browser tab: nothing to draw
                if(window._afoPage && window._afoPage !== 'live'){ return; }
                var sub = window._afoLiveSub || 'gait';
                if(sub === 'training'){ return; }
                var winS = window._afoWinSec || ${default_window}, tl = B.t[B.t.length - 1];
                var ids = sub === 'gait' ? ['torque', 'gait'] : CARDS.map(function(c){ return c.id; });
                // all plots of the sub-tab at the same model time tl; Sensors splits its 7 plots over
                // two animation frames (same tl), so no single task runs ~50 ms
                var draw = function(list){
                    list.forEach(function(id){
                        try { L.drawOne(id, B, winS, tl); } catch(e){ console.error('[AFO] ' + id + ' draw failed', e); }
                    });
                };
                if(sub === 'sensors' && ids.length > 4){
                    draw(ids.slice(0, 4));
                    L.splitPending = true;           // ~16 ms until the second half shows the same tl
                    raf(function(){
                        L.splitPending = false;
                        if((window._afoLiveSub || 'gait') === 'sensors'){ draw(ids.slice(4)); }
                    });
                } else {
                    draw(ids);
                }
                if(sub === 'sensors'){                                       // legend values, each tick
                    CARDS.forEach(function(c){
                        var chips = document.querySelectorAll('.lg[data-g="' + c.id + '"]');
                        for(var i = 0; i < chips.length; i++){
                            var kk = Number(chips[i].getAttribute('data-k')), v = latestOf(B, c.src[kk]);
                            var txt = (typeof v === 'number' && isFinite(v)) ? v.toFixed(c.dec) : '–';
                            var b = chips[i].querySelector('.lg-v');
                            if(b && b.textContent !== txt){ b.textContent = txt; }
                        }
                    });
                }
            };
            L.request = function(){
                if(L.pending){ return; }
                L.pending = true;
                var step = function(ts){
                    var now = (typeof ts === 'number') ? ts : Date.now();
                    // 20 ticks / s at most; Sensors (7 WebGL plots; each plot redraw ~6 ms plus the
                    // page's layout, paint and compositing per tick) 5 ticks / s, all plots together
                    var gap = (window._afoLiveSub === 'sensors') ? 200 : 50;
                    if(now - L.last < gap){ raf(step); return; }
                    L.pending = false; L.last = now;
                    L.render();
                };
                raf(step);
            };
            window._afoRequestRender = L.request;
            // SSE messages after the first go straight here (assets/sse.js), not through the
            // Dash store + callback (20 Dash cycles / s were ~25 % of the main thread); the
            // link session still goes to Dash, only when it changes
            L.onMessage = function(raw){
                try {
                    var p = raw ? window._afoParse(raw) : null;
                    if(!p){ return; }
                    window._afoLastSnapshot = p; window._afoLastPacketAt = Date.now();
                    L.ingest(p);
                    var meta = p.meta || {};
                    if(meta.session !== undefined && meta.session !== L.session){
                        L.session = meta.session;
                        try { window.dash_clientside.set_props('link-session', {data: meta.session}); } catch(e){}
                    }
                    if(window._afoOnSnapshot){ try { window._afoOnSnapshot(p); } catch(e){ console.error('[AFO] snapshot hook', e); } }
                    L.request();
                } catch(err){ console.error('[AFO] live update failed; message skipped', err); }
            };
            window._afoLiveMsg = L.onMessage;
        }
        var L2 = window._afoLive;
        var raw = msg ? ((typeof msg === 'string') ? msg : msg.data) : null;
        // the store keeps the last message it got (the direct path does not update it): a
        // window change must not ingest that old (full) message again and reset the buffer
        if(raw && raw === L2.lastStoreRaw){ raw = null; }
        if(raw){ L2.lastStoreRaw = raw; }
        var p = raw ? window._afoParse(raw) : null;
        var sessionOut = NU;
        if(p){
            window._afoLastSnapshot = p; window._afoLastPacketAt = Date.now();
            L2.ingest(p);
            var meta = p.meta || {};
            if(meta.session !== undefined && meta.session !== L2.session){ L2.session = meta.session; sessionOut = meta.session; }
            if(window._afoOnSnapshot){ try { window._afoOnSnapshot(p); } catch(e){ console.error('[AFO] snapshot hook', e); } }
        }
        L2.request();
        return sessionOut;
    } catch(err){
        console.error('[AFO] live update failed; message skipped', err);
        return NU;
    }
}
"""
