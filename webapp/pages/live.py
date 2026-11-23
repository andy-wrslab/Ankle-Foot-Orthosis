"""Live page (design v18): toolbar (Gait | Sensors | Training, window), two plot
cards per sub-page. The dock (Motor / Assist / K / Mode / one-shot actions) and
the top bar are built by assets/afo_console.js from /api/console/state.

* All live plots are uPlot (canvas, assets/vendor/uplot), drawn by assets/live_uplot.js on
  every animation frame from one shared model-time clock (Nov 23: the Plotly scattergl
  plots ran at 20 redraws / s and a plot could stop its time axis). This module only
  emits the cards, an empty host div per plot and the plot spec (#liveSpec, JSON).
* Gait: Torque = col 25 measured / col 28 command; Stride velocity = col 1 sv / col 23
  sv_target. Sensors: FSR 1-8 by insole position and linear acceleration (gravity
  removed), each trace named with its current value in the legend; a legend click hides
  it. Values at the cursor in a small label (time + every trace).
* x axis = absolute model time (the last 10 s / 2 s), ticks scroll with the data.
* Training plots: 5431 cols 27 (assistance level in use) and 24 (Uc) from the live
  worker's 330 s / 100 Hz buffer via /api/live/training, 30 s / 2 min / 5 min windows,
  axis [max(0, t - w), max(w, t)].
* Hold: pointer on a plot freezes it so the label can be read; released 2 s after the
  pointer last moved.
"""
from __future__ import annotations

import json


import dash
import plotly.graph_objs as go
from dash import dcc, html
from flask import jsonify, request

from constants import N_WINDOW_SEC
from plot_style import (GRID, HOVER_FMT, SENSOR_CARDS, SERIES, TEXT_3, TRAINING_PLOTS, ZERO, base_layout,
                        dtick_for, pad_range, trace_hover)

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


def _legend(items):
    out = []
    for name, color, dashed in items:
        out.append(html.Span([html.I(className="dash" if dashed else None, style={"color": color}), name]))
    return html.Span(className="legend", children=out)


def live_spec() -> dict:
    """Everything assets/live_uplot.js needs to draw: per plot the group (sub-tab), the
    padded y range and the series (source in the 100 Hz buffer, label, colour, width,
    dash, unit, decimals)."""
    def ser(label, src, style_key=None, color=None, width=None, unit="", dec=2):
        st = SERIES.get(style_key, {}) if style_key else {}
        return {"label": label, "src": list(src), "color": color or st.get("color"), "width": width or st.get("width", 1.5),
                "dash": [5, 4] if st.get("dash") else None, "unit": unit, "dec": dec}
    plots = {
        "torque": {"group": "gait", "y": pad_range(-5, 15), "ylabel": "Torque (Nm)", "xlabels": False, "series": [
            ser("Measured", ("torque", None), "meas", unit="Nm"), ser("Command", ("demand_torque", None), "cmd", unit="Nm")]},
        "gait": {"group": "gait", "y": pad_range(0, 2), "ylabel": "Stride velocity (m/s)", "xlabels": True, "series": [
            ser("Current", ("gait", None), "meas", unit="m/s"), ser("Target", ("sv_target", None), "cmd", unit="m/s")]},
    }
    for i, c in enumerate(SENSOR_CARDS):
        plots[c["id"]] = {"group": "sensors", "y": pad_range(*c["y"]), "ylabel": c["title"] +
                          (f" ({c['card_unit']})" if c.get("card_unit") else ""),
                          "xlabels": i == len(SENSOR_CARDS) - 1, "series": [
            ser(n, c["src"][k], color=c["colors"][k % len(c["colors"])], width=1.25, unit=c["unit"], dec=c["dec"])
            for k, n in enumerate(c["names"])]}
    for i, p in enumerate(TRAINING_PLOTS):
        dec = int(p["fmt"].strip(".f") or 2)
        plots[p["id"]] = {"group": "training", "y": pad_range(*p["y"]), "ylabel": p["title"],
                          "xlabels": i == len(TRAINING_PLOTS) - 1, "series": [
            ser(n, (col, None), "meas", dec=dec) for n, col in zip(p["names"], p["columns"])]}
    return {"window_default": N_WINDOW_SEC, "style": {"text": TEXT_3, "grid": GRID, "zero": ZERO}, "plots": plots}


def _value_legend(c):
    """Legend chips with the current value; a click hides / shows that trace."""
    chips = []
    for k, n in enumerate(c["names"]):
        short = n.split(" (")[0]                      # "Hallux (FSR1)" -> "Hallux"; full name in the tooltip
        chips.append(html.Button(className="lg", type="button", title=f"{n}: show / hide",
                                 **{"data-g": c["id"], "data-k": str(k), "aria-pressed": "true"}, children=[
                                     html.I(style={"color": c["colors"][k % len(c["colors"])]}),
                                     html.Span(short, className="lg-n"),
                                     html.B("–", className="lg-v mono")]))
    return html.Span(className="legend lg-vals", children=chips)


def _card(graph_id, title, unit, legend, live, hidden=False, extra_class=""):
    """A live plot card: no header row (Andy 14:54: the rotated y label names the plot)."""
    attrs = {"data-live": live} if live else {}
    return html.Section(className="card plot-card" + (f" {extra_class}" if extra_class else ""), hidden=hidden,
                        **attrs, children=[
        html.Div(className="plot-body", children=html.Div(id=graph_id, className="uplot-host")),
    ])


def layout(ctx=None) -> html.Div:
    return [
        html.Div(id="liveSpec", hidden=True, **{"data-spec": json.dumps(live_spec())}),
        dcc.Store(id="window-sec", data=N_WINDOW_SEC),
        dcc.Store(id="tr-window", data=120),
        dcc.Store(id="live-sub", data="gait"),
        dcc.Store(id="link-session", data=None),
        html.Div(className="toolbar", children=[
            html.Div(className="seg", role="group", **{"aria-label": "Live page"}, children=[
                html.Button("Gait", id="pgGait", **{"aria-pressed": "true"}),
                html.Button("Sensors", id="pgSensors", **{"aria-pressed": "false"}),
                html.Button("Training", id="pgTraining", **{"aria-pressed": "false"}),
            ]),
            html.Span(className="tb-right", children=[
                html.Div(className="seg", role="group", id="liveWin", **{"aria-label": "Time window"}, children=[
                    html.Button("2 s", id="w2", **{"aria-pressed": "false"}),
                    html.Button("10 s", id="w10", **{"aria-pressed": "true"}),
                ]),
                html.Div(className="seg", role="group", id="trWin", hidden=True, style={"display": "none"},
                         **{"aria-label": "Time window"},
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
            _card(c["id"], c["title"], c.get("card_unit", c["unit"]), _value_legend(c), None,
                  extra_class="wide" if c.get("wide") else "") for c in SENSOR_CARDS]),
        _card("tr-assist", "Assistance", None, None, "training", hidden=True),     # single trace: the title is enough
        _card("tr-uc", "Uc", None, None, "training", hidden=True),
    ]


def register(app: dash.Dash, ctx) -> None:
    # Live > Training data for assets/live_uplot.js (polled once a second while visible)
    @app.server.route("/api/live/training")
    def api_live_training():  # type: ignore
        try:
            win = min(300.0, max(10.0, float(request.args.get("w", 120))))
        except ValueError:
            win = 120.0
        d = ctx.live.slow_data(["assistance_level", "uc"], win, max_points=1500) or {}
        return jsonify({"t_latest": d.get("t_latest"), "series": d.get("series") or {}, "window": win})
