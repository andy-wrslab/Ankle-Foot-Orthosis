"""One top-bar status for the whole app (design round 5).

top_status(ctx) -> {"state", "text", "level", "issues", ...}

Base state (what the target is doing):
  busy verb      a run-control action is in progress ("Connecting…", "Starting…", ...)
  Ready          app running, every required UDP stream live, no setting problem
  Connected      MATLAB connected, app stopped
  Not connected  no MATLAB connection and no live data
"Running" is known from MATLAB, or from the live UDP stream itself when this
app's MATLAB is not connected (data proves the app runs).

Problems on top of it, priority red > amber > base:
  red    "No data N.N s"     a required stream is silent while the app runs
  red    "Foot side differs" target side != confirmed side
  amber  "Confirm foot side" side not confirmed / not verified / unset (-1)
  amber  "Mass differs" etc. an echoed / read-back value != the entered value
The drive (statusword / STO) is deliberately not part of this status.

The console stream (UDP 5433) is required when it is enabled and has been
seen in this app session, or the loaded model is AFO_r1.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from session import SHORT

NO_DATA_S = 0.5          # SPEC: no 5431 packet for > 0.5 s -> "No data"
BUSY = {"connect": "Connecting…", "disconnect": "Disconnecting…", "start": "Starting…", "stop": "Stopping…",
        "load": "Loading…", "save": "Exporting…"}


HB_PERIOD_S = 1.0     # receiver workers report about once a second


def _age(sup, status: Dict[str, Any]):
    """Seconds since the last packet as of the worker's last heartbeat; only
    when the heartbeat itself is overdue is the age extrapolated (a silent or
    dead worker must still read as "No data")."""
    a = status.get("age_s")
    if a is None:
        return None
    try:
        late = time.monotonic() - sup.last_hb - 1.5 * HB_PERIOD_S
        return round(float(a) + max(0.0, late), 1)
    except Exception:
        return float(a)


def top_status(ctx) -> Dict[str, Any]:
    rc = ctx.runctl.status or {}
    connected = bool(rc.get("connected"))
    live_st = ctx.live.get_status()
    live_age = _age(ctx.live, live_st) if live_st.get("live_seen") else None
    tr_st = ctx.training.get_status()
    tr_age = _age(ctx.training, tr_st) if tr_st.get("packets_ok") else None
    live_now = live_age is not None and live_age < NO_DATA_S
    running = bool(rc.get("running")) if connected else live_now

    model = ctx.session.model() if connected and rc.get("app") else None
    need_training = (bool(getattr(ctx.training, "enabled", True)) and
                     (model == "AFO_r1" or bool(tr_st.get("packets_ok"))))

    # ---- base
    job = ctx.jobs.running("rc")
    action = None
    if job is not None:
        action = job.title.split(":")[-1].strip()
    if action in BUSY:
        base = {"state": "busy", "text": BUSY[action], "level": "busy"}
    elif running:
        base = {"state": "ready", "text": "Ready", "level": "green"}
    elif connected:
        base = {"state": "connected", "text": "Connected", "level": "neutral"}
    else:
        base = {"state": "not-connected", "text": "Not connected", "level": "grey"}

    issues: List[Dict[str, Any]] = []
    if base["state"] != "not-connected":
        if running:
            for name, age, needed in (("live", live_age, True), ("console", tr_age, need_training)):
                if needed and (age is None or age >= NO_DATA_S):
                    issues.append({"level": "red", "key": "no-data", "stream": name, "age_s": age,
                                   "text": "No data" if age is None else f"No data {age:.1f} s"})
        chip = ctx.session.side_chip()
        if chip["state"] == "bad":
            issues.append({"level": "red", "key": "side-differs", "text": "Foot side differs",
                           "detail": ctx.session.side_problem()})
        elif chip["state"] in ("warn", "unset"):
            issues.append({"level": "amber", "key": "confirm-side", "text": "Confirm foot side",
                           "detail": ctx.session.side_problem() or chip["text"]})
        seen = set()
        for row in ctx.session.target_table():
            if row["name"] == "side" or row["match"] is not False:
                continue
            label = SHORT.get(row["name"], row["label"])
            if label in seen:
                continue
            seen.add(label)
            issues.append({"level": "amber", "key": f"differs-{row['name']}", "text": f"{label} differs",
                           "detail": f"entered {row['entered']}, target {row['target']} ({row['source']})"})
    # the oldest silent stream first among the reds
    issues.sort(key=lambda i: (0 if i["level"] == "red" else 1, 0 if i["key"] == "no-data" else 1,
                               -(i.get("age_s") or 0)))
    out = dict(base)
    if base["state"] != "busy" and issues:      # a run-control action in progress wins (it pauses data)
        top = issues[0]
        out = {"state": top["key"], "text": top["text"], "level": top["level"]}
    out.update(base_state=base["state"], issues=issues, connected=connected, running=running, model=model,
               streams={"live_age_s": live_age, "console_age_s": tr_age, "console_required": need_training},
               writes_enabled=ctx.session.writes_enabled, at=time.time())
    return out
