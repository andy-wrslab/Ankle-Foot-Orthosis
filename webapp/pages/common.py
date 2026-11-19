"""Shared helpers for the AFO web app pages."""
from __future__ import annotations

import functools
import logging

from dash import html
from dash.exceptions import PreventUpdate
from flask import request

_log = logging.getLogger("afo.access")
LOCAL_ADDRS = {"127.0.0.1", "::1"}


def is_local() -> bool:
    """True only for requests from this PC over loopback (http://127.0.0.1:8050)."""
    try:
        return request.remote_addr in LOCAL_ADDRS
    except RuntimeError:  # no request context
        return False


def local_only(fn):
    """Reject a callback unless the request comes from loopback (enforced server side)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_local():
            try:
                addr = request.remote_addr
            except RuntimeError:
                addr = "?"
            _log.warning("rejected OMEN-only callback %s from %s", fn.__name__, addr)
            raise PreventUpdate
        return fn(*args, **kwargs)
    return wrapper


def locked_notice(title: str) -> html.Div:
    return html.Div(
        className="card locked",
        children=[
            html.H3(f"{title} is available on the OMEN only"),
            html.P("This page can change the Speedgoat or the Teensy, so it only works in a browser on the "
                   "OMEN itself, opened at http://127.0.0.1:8050. From other devices it stays locked."),
        ],
    )


def card(title: str, children, extra_class: str = "", right=None) -> html.Div:
    head = [html.H3(title)]
    if right is not None:
        head.append(html.Div(right, className="card-right"))
    return html.Div(className=f"card {extra_class}".strip(),
                    children=[html.Div(className="card-head", children=head), *children])


def kv(label: str, value_id: str, value: str = "–") -> html.Div:
    return html.Div(className="kv", children=[html.Span(label, className="kv-label"),
                                              html.Span(value, id=value_id, className="kv-value")])
