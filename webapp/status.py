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
  amber  "Set mass" AFO_r1: BIF_mass_kg (= body mass) read back <= 20 kg (Bi-LSTM gives no assist)
The drive (statusword / STO) is deliberately not part of this status.

The console stream (UDP 5433) is required when it is enabled and has been
seen in this app session, or the loaded model's profile expects it (AFO_r1).
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

import model_profile as mp
from session import SHORT, _num

NO_DATA_S = 0.5          # SPEC: no 5431 packet for > 0.5 s -> "No data"
IMU_ROSE_S = 10.0        # imu_bad_count rising within this window -> "IMU fault"
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


def _imu_fault(ctx) -> str:
    """'' when the IMU looks fine, else why not: console imu_ok = 0, imu_bad_count rose in
    the last 10 s, or the main bus IMU columns invalid (health group 'bad')."""
    why = []
    tr = {}
    try:
        tr = ctx.training.latest(max_age_s=1.0) or {}
    except Exception:
        tr = {}
    ok = tr.get("imu_ok")
    if isinstance(ok, (int, float)) and ok == ok and ok < 0.5:
        why.append("imu_ok = 0 (console)")
    cnt = tr.get("imu_bad_count")
    now = time.monotonic()
    hist = getattr(ctx.session, "_imu_hist", None)
    if hist is None:
        hist = ctx.session._imu_hist = []       # (monotonic time, imu_bad_count), per app session
    if isinstance(cnt, (int, float)) and cnt == cnt:
        _imu_hist = hist
        _imu_hist.append((now, float(cnt)))
        while _imu_hist and now - _imu_hist[0][0] > IMU_ROSE_S:
            _imu_hist.pop(0)
        first = min(c for _, c in _imu_hist)
        if cnt > first:
            why.append(f"imu_bad_count rose by {int(cnt - first)} in the last {IMU_ROSE_S:.0f} s")
    try:
        g = ((ctx.live.get_status().get("health") or {}).get("groups") or {}).get("imu") or {}
        if g.get("state") == "bad":
            why.append(f"bus IMU values invalid ({g.get('recent_bad', 0)} of {g.get('recent_total', 0)} in 10 s)")
    except Exception:
        pass
    return "; ".join(why)


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
    expects_console = bool(mp.PROFILES.get(model or "", {}).get("console_expected"))
    need_training = (bool(getattr(ctx.training, "enabled", True)) and
                     (expects_console or bool(tr_st.get("packets_ok"))))

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
    notes: List[str] = []
    if base["state"] != "not-connected":
        if running:
            for name, age, needed in (("live", live_age, True), ("console", tr_age, need_training)):
                if needed and (age is None or age >= NO_DATA_S):
                    issues.append({"level": "red", "key": "no-data", "stream": name, "age_s": age,
                                   "text": "No data" if age is None else f"No data {age:.1f} s",
                                   "todo": f"The {'main bus 5431' if name == 'live' else 'console 5433'} stream "
                                           "is silent: check the Speedgoat app and the network link."})
        if getattr(ctx.session, "app_elsewhere", None) and running:
            issues.append({"level": "amber", "key": "app-elsewhere", "text": ctx.session.ELSEWHERE_MSG,
                           "todo": "This page cannot set side or mass on an app another MATLAB session started. "
                                   "Press Stop, then Start (side and mass are sent right after Start)."})
        if running:
            imu = _imu_fault(ctx)
            if imu:
                issues.append({"level": "red", "key": "imu-fault", "text": "IMU fault", "detail": imu,
                               "todo": "Check the IMU cable at the Teensy and replug it; the IMU re-syncs within about 1 s."})
        chip = ctx.session.side_chip()
        if chip["state"] == "bad":
            issues.append({"level": "red", "key": "side-differs", "text": "Foot side differs",
                           "detail": ctx.session.side_problem(),
                           "todo": "Pick the correct foot in the side chip (top bar); Motor and Assist stay off."})
        elif chip["state"] == "pending":
            issues.append({"level": "amber", "key": "side-pending", "text": "Foot side pending",
                           "detail": chip["text"], "todo": "It is sent and read back once connected to a running app / right after Start."})
        elif chip["state"] in ("warn", "unset"):
            issues.append({"level": "amber", "key": "confirm-side", "text": "Confirm foot side",
                           "detail": ctx.session.side_problem() or chip["text"],
                           "todo": "Click the side chip in the top bar and confirm Left or Right."})
        if ctx.session.profile().get("bif"):
            m = _num(ctx.session.readback.get("bif_mass"))
            if m is not None and m <= mp.BIF_MASS_MIN:
                issues.append({"level": "amber", "key": "bif-mass", "text": "Set mass",
                               "detail": f"BIF_mass_kg on the target is {m:g} kg: the Bi-LSTM gives no assist "
                                         f"at {mp.BIF_MASS_MIN:g} kg or less",
                               "todo": "Type the body mass in Mass (top bar) and press Enter."})
            if running:
                # drive fault (fault bit 0x0008, e.g. 0x0628 with STO): red
                sw = (ctx.live.readback() or {}).get("statusword") if hasattr(ctx.live, "readback") else None
                if isinstance(sw, (int, float)) and sw == sw and int(sw) & 0x0008:
                    issues.append({"level": "red", "key": "drive-fault", "text": "Drive fault (STO)",
                                   "detail": f"statusword 0x{int(sw):04X}",
                                   "todo": "Release STO, then press Motor once: the model sends the fault reset."})
                # Bi-LSTM phase (console 15-float tail or the Signals stream)
                try:
                    b = ctx.session.bif_view() or {}
                except Exception:
                    b = {}
                ph = b.get("phase")
                if ph == "bias":
                    issues.append({"level": "amber", "key": "imu-not-ready", "text": "IMU not ready",
                                   "detail": b.get("text"), "todo": "The wearer holds still for 5 s."})
                elif ph == "walk":
                    pct = b.get("progress_pct")
                    n = int(round(30 * pct / 100.0)) if pct is not None else None
                    issues.append({"level": "amber", "key": "calibrating",
                                   "text": f"Calibrating {n}/30 s" if n is not None else "Calibration walk",
                                   "detail": b.get("text"), "todo": "Walk normally for about 30 s."})
                elif ph == "unknown":
                    # not actionable: a grey note in the popover only (the button can be green Ready)
                    notes.append("Bi-LSTM state unknown: needs Signals or the 15-float console packet")
        seen = set()
        for row in ctx.session.target_table():
            if row["name"] == "side" or row["match"] is not False:
                continue
            label = SHORT.get(row["name"], row["label"])
            if label in seen:
                continue
            seen.add(label)
            issues.append({"level": "amber", "key": f"differs-{row['name']}", "text": f"{label} differs",
                           "detail": f"entered {row['entered']}, target {row['target']} ({row['source']})",
                           "todo": ("Press that button in the dock again to resend it." if row["name"] in ("motor", "assist", "k")
                                    else "Press Enter in that field to send it again.")})
    # the oldest silent stream first among the reds
    prio = {"no-data": 0, "side-differs": 1, "imu-fault": 1.5, "drive-fault": 2, "app-elsewhere": 2.5, "confirm-side": 3, "side-pending": 4,
            "bif-mass": 5, "imu-not-ready": 6, "calibrating": 7, "bif-unknown": 10}   # "... differs": 9
    issues.sort(key=lambda i: (0 if i["level"] == "red" else 1, prio.get(i["key"], 9), -(i.get("age_s") or 0)))
    out = dict(base)
    if base["state"] != "busy" and issues:      # a run-control action in progress wins (it pauses data)
        top = issues[0]
        out = {"state": top["key"], "text": top["text"], "level": top["level"]}
    out.update(base_state=base["state"], issues=issues, notes=notes, connected=connected, running=running, model=model,
               streams={"live_age_s": live_age, "console_age_s": tr_age, "console_required": need_training},
               writes_enabled=ctx.session.writes_enabled, at=time.time())
    return out
