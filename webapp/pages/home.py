"""Home page: one tile per tool with its live status."""
from __future__ import annotations

import glob
import os
import time

from dash import dcc, html, Input, Output

from pages.common import is_local
from pages import session_ui


def _tile(page: str, title: str, body_id: str, omen_only: bool = False) -> html.A:
    return html.A(className="tile", href=f"/{page}", children=[
        html.Div(className="tile-head", children=[
            html.H3(title),
            html.Span("OMEN only", className="tag") if omen_only else None,
        ]),
        html.Div(id=body_id, className="tile-body", children="…"),
    ])


def layout(ctx=None) -> html.Div:
    return html.Div(children=[
        dcc.Interval(id="home-tick", interval=2000, n_intervals=0),
        html.Div(className="page-head", children=[html.H2("Home")]),
        session_ui.card(ctx) if ctx is not None else None,
        html.Div(className="tiles", children=[
            _tile("live", "Live", "home-live"),
            _tile("trials", "Trials", "home-trials"),
            _tile("signals", "Target (MATLAB)", "home-run", omen_only=True),
            _tile("teensy", "Teensy", "home-teensy", omen_only=True),
        ]),
        html.Div(className="card", children=[
            html.Div(className="card-head", children=[html.H3("Recent logs")]),
            html.Div(id="home-logs", className="log-list"),
        ]),
    ])


def _line(label, value, cls=""):
    return html.Div(className="tl", children=[html.Span(label, className="tl-label"),
                                              html.Span(value, className=f"tl-value {cls}".strip())])


def register(app, ctx) -> None:
    session_ui.register(app, ctx)
    @app.callback(
        Output("home-live", "children"), Output("home-trials", "children"), Output("home-run", "children"),
        Output("home-teensy", "children"), Output("home-logs", "children"),
        Input("home-tick", "n_intervals"), Input("url", "pathname"),
    )
    def refresh(_n, path):
        if path not in ("/", "/home", None):
            from dash import no_update
            return [no_update] * 5
        live = ctx.live.get_status()
        poll = ctx.poller.get()
        groups = (live.get("health") or {}).get("groups", {})
        live_on = ctx.live.stream_live()
        lamp = lambda g: groups.get(g, {}).get("state", "idle")  # noqa: E731
        live_body = [
            _line("Speedgoat stream", f"live · {live.get('rate_hz', 0):.0f} Hz" if live_on else "not receiving",
                  "ok" if live_on else "muted"),
            _line("IMU / FSR", f"{lamp('imu')} / {lamp('fsr')}",
                  "warn" if "bad" in (lamp('imu'), lamp('fsr')) or "warn" in (lamp('imu'), lamp('fsr')) else ""),
            _line("Receiver", f"{live.get('state', '?')} · restarts {live.get('restarts', 0)}",
                  "warn" if live.get("restarts") else ""),
        ]
        try:
            n_files = len(ctx.trial_sources())
        except Exception:
            n_files = "?"
        trials_body = [_line("Saved logs", str(n_files))]
        cur = ctx.trials_current()
        if cur:
            trials_body.append(_line("Open", os.path.basename(cur)))
        reach = poll.get("target_reachable")
        mw = ctx.matlab.get_status()
        run_body = [
            _line("Target 192.168.7.5", "reachable" if reach else ("unreachable" if reach is False else "checking"),
                  "ok" if reach else "warn"),
            _line("MATLAB worker", mw["state"], "warn" if mw["state"] == "error" else ""),
        ]
        ports = poll.get("teensy_ports")
        repo = poll.get("repo") or {}
        teensy_body = [
            _line("Teensy USB", ", ".join(p["port"] for p in ports if p.get("port")) if ports else
                  "not connected (normal during collection)", "ok" if ports else "muted"),
            _line("Firmware branch", repo.get("branch", "?") + (" (uncommitted changes)" if repo.get("dirty") else "")),
            _line("Last commit", (repo.get("head") or "?")[:60]),
            _line("Teensy data (bus)", f"IMU {lamp('imu')} · FSR {lamp('fsr')}"),
        ]
        logs = []
        for pattern in ("logs/*.log", "logs/*.csv"):
            logs += glob.glob(os.path.join(ctx.app_dir, pattern))
        logs = sorted(logs, key=os.path.getmtime, reverse=True)[:6]
        log_rows = [html.Div(className="log-row", children=[
            html.Span(os.path.basename(p)),
            html.Span(time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(p))), className="muted")])
            for p in logs] or [html.Div("No logs yet", className="muted")]
        return live_body, trials_body, run_body, teensy_body, log_rows
