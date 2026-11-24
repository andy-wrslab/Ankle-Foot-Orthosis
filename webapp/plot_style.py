"""Plotly layout for the AFO live plots (design v4, Nov 19 2026).

Usage in dash_app.py:
    from plot_style import base_layout, GRAPH_CONFIG, SERIES
    fig = go.Figure(layout=base_layout(y_range=(-5, 40)))
    dcc.Graph(id="torque", figure=fig, config=GRAPH_CONFIG, style={"height": "100%"})

Rules
- No Plotly legend, no axis titles: the card head shows title, unit and legend.
- x axis is absolute model time in seconds (the last 10 s / 2 s, ticks scroll
  with the data, Andy Nov 23), y gridlines only.
- Plots never animate: no `transition`, keep `uirevision` constant so a
  20 Hz update never resets zoom/pan or re-lays out the axes.
- Fixed y ranges per signal (autorange makes the plot jump every update).
- Hover (Andy 12:16): no numbers in the card heads; instead hover shows the
  time and every trace's value at the cursor ("x unified"). Give each trace
  a name and use `trace_hover(name, fmt)` so values have fixed decimals.
- Hover hold: while the pointer is on a graph, skip that graph's updates
  (clientside callback below) so the label stays put. Data keeps buffering
  server-side and the graph catches up when the pointer leaves. The card
  gets class "holding", which shows a small "Held" tag in its head.
"""

FONT = "Inter, Segoe UI, system-ui, sans-serif"
TEXT_3 = "#73767B"
GRID = "#EEECE8"
ZERO = "#CBC7BF"

SERIES = {
    "meas": dict(color="#1D1F21", width=3.0),        # Andy Nov 24 14:32: all plot lines ~2x (was 1.5)
    "cmd": dict(color="#1F6F78", width=3.0, dash="dash"),   # was 1.5
    "imu_x": dict(color="#1F6F78", width=2.5),
    "imu_y": dict(color="#C2702E", width=2.5),
    "imu_z": dict(color="#6E5BA8", width=2.5),
    # FSR 1..8, heel -> toe
    "fsr": ["#A9D3D7", "#8CC2C7", "#6FB0B6", "#529DA4",
            "#3A8890", "#28727A", "#1B5B62", "#10444A"],
}

GRAPH_CONFIG = {
    "displayModeBar": False,
    "scrollZoom": False,
    "doubleClick": False,
    "responsive": True,
    "staticPlot": False,      # must stay False or hover is off
}

# Value formats for the hover label (fixed decimals, explicit sign).
HOVER_FMT = {"torque": ".2f", "speed": ".2f", "fsr": ".0f", "imu": ".2f",
             "assist": ".2f", "uc": ".3f"}


def trace_hover(name, fmt=".2f", unit=""):
    """Trace kwargs for the unified hover label: 'Measured  +12.41' (no unit in the hover,
    Andy Nov 24 15:20; the axis title carries it). *unit* is accepted and ignored."""
    u = ""
    # yhoverformat, not a format inside the template: in "x unified" mode
    # Plotly 2.35 printed full precision with %{y:.2f} (checked in the mock).
    return dict(name=name, yhoverformat=fmt, hovertemplate=f"{name}  <b>%{{y}}</b>{u}<extra></extra>")


# Hover hold. Put each live dcc.Graph inside html.Div(className="plot-body"),
# and gate the update callback with this store, e.g.
#   Input("hold-<id>", "data") -> if held: return dash.no_update
# The clientside snippet below sets the store on mouseenter/leave.
HOVER_HOLD_JS = """
function(id){
  const el = document.getElementById(id); if(!el || el._holdWired) return window.dash_clientside.no_update;
  el._holdWired = true; const card = el.closest('.plot-card');
  el.addEventListener('mouseenter', ()=>{ card && card.classList.add('holding');
    dash_clientside.set_props('hold-'+id, {data: true}); });
  el.addEventListener('mouseleave', ()=>{ card && card.classList.remove('holding');
    dash_clientside.set_props('hold-'+id, {data: false}); });
  return window.dash_clientside.no_update;
}
"""


def _pad(y_range, frac=0.08):
    """Pad the nominal range so no y tick label sits on the plot edge
    (Andy 12:29: the bottom label ran into the x labels)."""
    lo, hi = y_range
    p = (hi - lo) * frac
    return [lo - p, hi + p]


def base_layout(y_range, window_s=10, zeroline=True):
    return dict(
        margin=dict(l=48, r=32, t=12, b=30),  # r >= half the widest x tick ("0 s"); b keeps x labels off the card edge
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=11, color=TEXT_3),
        showlegend=False,
        hovermode="x unified",    # Andy 12:16: hover shows every trace's value at the cursor time
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E2DFD9",
                        font=dict(family=FONT, size=12, color="#1D1F21"), namelength=-1),
        spikedistance=-1,
        dragmode=False,
        uirevision="live",
        xaxis=dict(
            range=[-window_s, 0], fixedrange=True, showgrid=False,
            zeroline=False, showline=True, linecolor=GRID, ticks="outside",
            tickcolor=GRID, ticklen=4, ticksuffix=" s", hoverformat=".3f",
            showspikes=True, spikemode="across", spikesnap="cursor",
            spikethickness=1, spikecolor=ZERO, spikedash="solid",
            dtick=1 if window_s <= 2 else 2,
        ),
        yaxis=dict(
            range=_pad(y_range), fixedrange=True, showgrid=True, gridcolor=GRID,
            gridwidth=1, zeroline=zeroline, zerolinecolor=ZERO, zerolinewidth=1,
            showline=False, nticks=5, ticks="", automargin=False,
        ),
    )


# ---- AFO app additions -------------------------------------------------------
MARGIN = dict(l=48, r=32, t=12, b=30)
Y_PAD = 0.08


def pad_range(lo: float, hi: float, pad: float = Y_PAD) -> list:
    return _pad((lo, hi), pad)


def dtick_for(window_s: float) -> float:
    """x tick step: 1 s (2 s window), 2 s (10 s), then about 6 ticks."""
    if window_s <= 2:
        return 1
    if window_s <= 10:
        return 2
    for step in (5, 10, 20, 30, 60):
        if window_s / step <= 7:
            return step
    return 60


# Live > Training plots, from the main bus 5431 (SPEC v18): Assistance shows only
# the level in use (col 27), Uc is col 24. Fixed y ranges (8 % padding added).
TRAINING_PLOTS = [
    {"id": "tr-assist", "title": "Assistance", "unit": "", "y": [0.0, 10.0], "columns": ["assistance_level"],
     "names": ["Level in use"], "fmt": HOVER_FMT["assist"]},
    {"id": "tr-uc", "title": "Uc", "unit": "", "y": [0.0, 1.0], "columns": ["uc"], "names": ["Uc"],
     "fmt": HOVER_FMT["uc"]},
]


def training_plots() -> list:
    return [dict(p, y_range=pad_range(*p["y"]), margin=MARGIN) for p in TRAINING_PLOTS]


# ---- Live > Sensors: FSR and linear acceleration only (Andy, Nov 23 13:53: "we only need
# linear acceleration and FSR, like before"); the other columns stay in Signals and exports.
# FSR names by insole position (configs/gpr_default.yaml on WRSLAB). NOT yet
# confirmed by Andy (Met 1/3/5 order, which heel is medial): change only here.
FSR_NAMES = ["Hallux", "Heel medial", "Met 1", "Met 5", "Arch", "Toes", "Heel lateral", "Met 3"]   # FSR1..FSR8 = cols 3..10

# display order heel -> toe: Heel medial, Heel lateral, Arch, Met 1, Met 3, Met 5, Hallux, Toes
FSR_HEEL_TO_TOE = [FSR_NAMES.index(n) for n in ("Heel medial", "Heel lateral", "Arch", "Met 1", "Met 3", "Met 5",
                                                "Hallux", "Toes")]
# eight clearly different hues (FSR traces), readable on the light card
CATEGORICAL = ["#1F6F78", "#C2702E", "#6E5BA8", "#2E7D4F", "#B5446E", "#4C6EB5", "#8A7A2E", "#3F3F46"]
XYZ = ["#1F6F78", "#C2702E", "#6E5BA8"]

# id, title, unit, source in the snapshot ("press" k / "imu" k / "ankle" / "ankle_vel"),
# trace names, y range, decimals. imu k = imu_(k+1) = 5431 col 11+k.
SENSOR_CARDS = [
    # heel to toe (Andy 14:56), no "(FSRn)"; colour tied to the sensor (CATEGORICAL[FSR index]);
    # the channel mapping is unchanged (FSR1 = p0 = Hallux ...)
    {"id": "press", "title": "Pressure", "unit": "counts", "card_unit": None,
     "src": [("press", k) for k in FSR_HEEL_TO_TOE],
     "names": [FSR_NAMES[k] for k in FSR_HEEL_TO_TOE], "y": (0, 1000), "dec": 0,
     "colors": [CATEGORICAL[k] for k in FSR_HEEL_TO_TOE], "wide": True},
    {"id": "imu", "title": "Acceleration", "unit": "g", "card_unit": None,
     "src": [("imu", 0), ("imu", 1), ("imu", 2)], "names": ["x", "y", "z"], "y": (-3, 3), "dec": 2, "colors": XYZ,
     "wide": True},
]
