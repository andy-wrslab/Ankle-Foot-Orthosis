"""Session setup card for the Home page (functional; visual design comes later).

S-ID, weight, assistance mode, fixed K %, SV target band are sent when
committed (Enter / leaving the field / picking an option). The foot side is a
small chip that opens a confirm panel (pick LEFT/RIGHT and retype the S-ID).
"""
from __future__ import annotations

from dash import dcc, html, Input, Output, State, no_update, ctx as dctx

from session import MODES, SIDE_NAMES


def card(ctx) -> html.Div:
    s = ctx.session
    v = s.values
    mode = int(v["mode"]) if v.get("mode") is not None else None
    return html.Div(className="card session-card", children=[
        dcc.Interval(id="sess-poll", interval=1500, n_intervals=0),
        dcc.Store(id="sess-pending", data=None),
        dcc.ConfirmDialog(id="sess-confirm", message=""),
        html.Div(className="card-head", children=[
            html.H3("Session"),
            html.Button(id="sess-side-chip", className="side-chip", n_clicks=0, children="Side"),
        ]),
        html.Div(id="sess-side-panel", className="side-panel", style={"display": "none"}, children=[
            html.Div("Confirm the foot side. A wrong side inverts measured torque and ankle angle.",
                     className="small"),
            dcc.RadioItems(id="sess-side-pick", options=["LEFT", "RIGHT"], value=None, inline=True,
                           className="checks"),
            dcc.Input(id="sess-side-sid", placeholder="Retype the S-ID", debounce=True),
            html.Button("Confirm side", id="sess-side-ok", className="btn primary"),
            html.Button("Cancel", id="sess-side-cancel", className="btn"),
        ]),
        html.Div(className="sess-grid", children=[
            html.Label("S-ID"), dcc.Input(id="sess-sid", value=s.sid or "", placeholder="e.g. S47", debounce=True),
            html.Span(id="sess-st-sid", className="sess-st"),
            html.Label("Body weight (kg)"), dcc.Input(id="sess-weight", type="number", value=v.get("weight"),
                                                      debounce=True, min=20, max=200, step=0.5),
            html.Span(id="sess-st-weight", className="sess-st"),
            html.Label("Assistance mode"), dcc.RadioItems(id="sess-mode", value=mode, inline=True, className="checks",
                                                          options=[{"label": n, "value": k} for k, n in MODES.items()]),
            html.Span(id="sess-st-mode", className="sess-st"),
            html.Label("Fixed K (%)"), dcc.Input(id="sess-k", type="number", value=v.get("k_percent"), debounce=True,
                                                 min=0, max=10, step=0.5, disabled=(mode != 3)),
            html.Span(id="sess-st-k_percent", className="sess-st"),
            html.Label("SV target min (m/s)"), dcc.Input(id="sess-svmin", type="number", value=v.get("sv_target_min"),
                                                         debounce=True, min=0, max=3, step=0.05),
            html.Span(id="sess-st-sv_target_min", className="sess-st"),
            html.Label("SV target max (m/s)"), dcc.Input(id="sess-svmax", type="number", value=v.get("sv_target_max"),
                                                         debounce=True, min=0, max=3, step=0.05),
            html.Span(id="sess-st-sv_target_max", className="sess-st"),
        ]),
        html.Div(id="sess-msg", className="small"),
        html.Div(id="sess-banner"),
    ])


def register(app, ctx) -> None:
    s = ctx.session
    fields = {"sess-weight": "weight", "sess-mode": "mode", "sess-k": "k_percent",
              "sess-svmin": "sv_target_min", "sess-svmax": "sv_target_max"}

    @app.callback(Output("sess-msg", "children", allow_duplicate=True), Input("sess-sid", "value"),
                  prevent_initial_call=True)
    def sid(v):
        return s.set_sid(v)

    @app.callback(Output("sess-msg", "children", allow_duplicate=True), Output("sess-confirm", "displayed"),
                  Output("sess-confirm", "message"), Output("sess-pending", "data"),
                  *[Input(i, "value") for i in fields], prevent_initial_call=True)
    def edit(*_vals):
        trig = dctx.triggered_id
        key = fields.get(trig)
        if key is None:
            return no_update, False, no_update, no_update
        value = dict(zip(fields, _vals))[trig]
        if value is None:
            return no_update, False, no_update, no_update
        need = s.check_change(key, value)
        if need:
            return "Waiting for confirmation…", True, need, {"key": key, "value": value}
        return s.enter_value(key, value), False, no_update, None

    @app.callback(Output("sess-msg", "children", allow_duplicate=True), Input("sess-confirm", "submit_n_clicks"),
                  State("sess-pending", "data"), prevent_initial_call=True)
    def confirmed(_n, pending):
        if not pending:
            return no_update
        return s.enter_value(pending["key"], pending["value"])

    @app.callback(Output("sess-k", "disabled"), Input("sess-mode", "value"))
    def k_enabled(mode):
        return mode != 3

    @app.callback(Output("sess-side-panel", "style"), Input("sess-side-chip", "n_clicks"),
                  Input("sess-side-cancel", "n_clicks"), Input("sess-side-ok", "n_clicks"), prevent_initial_call=True)
    def side_panel(_a, _b, _c):
        return {"display": "block"} if dctx.triggered_id == "sess-side-chip" else {"display": "none"}

    @app.callback(Output("sess-msg", "children", allow_duplicate=True), Input("sess-side-ok", "n_clicks"),
                  State("sess-side-pick", "value"), State("sess-side-sid", "value"), prevent_initial_call=True)
    def side_ok(_n, side, typed):
        return s.confirm_side(side, typed)

    status_outputs = [Output(f"sess-st-{k}", "children") for k in
                      ("sid", "weight", "mode", "k_percent", "sv_target_min", "sv_target_max")]

    @app.callback(Output("sess-side-chip", "children"), Output("sess-side-chip", "className"),
                  Output("sess-banner", "children"), *status_outputs,
                  Input("sess-poll", "n_intervals"), Input("sess-msg", "children"))
    def refresh(_n, _m):
        v = s.view()
        chip = v["side_chip"]
        banner = html.Div(className="banner bad", children=v["side_problem"]) if v["side_problem"] else None
        out = [chip["text"], f"side-chip {chip['state']}", banner,
               ("" if v["sid"] else "not set") + ("" if v["writes_enabled"] else " · target writes disabled")]
        for row in v["rows"]:
            if row["key"] == "side":
                continue
            st = row["status"].get("state", "")
            rb = row["readback"]
            if row["key"] == "mode" and rb is not None:
                rb = MODES.get(int(round(float(rb))), rb)
            txt = st
            if rb is not None:
                txt += f" · target {rb}" + (f" ({row['readback_source']})" if row.get("readback_source") else "")
            if row["status"].get("msg"):
                txt += f" · {row['status']['msg']}"
            out.append(txt.strip(" ·"))
        return out
