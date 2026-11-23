"""One top-bar status for the whole app (design round 5).

top_status(ctx) -> {"state", "text", "level", "issues", ...}

Base state (what the target is doing):
  busy verb      a run-control action is in progress ("Connecting…", "Starting…", ...)
  Ready          app running, every required UDP stream live, no setting problem
  Connected      MATLAB connected, app stopped
  Not connected  no MATLAB connection and no live data
  Speedgoat offline / Speedgoat busy / Connect failed  (amber) why the last Connect failed (no
                 answer / another MATLAB session / any other error); until Disconnect or a successful connect
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

import logging
import time
from typing import Any, Dict, List

IMU_NOT_READY_FAULT_S = 10.0     # bias_ready 0 this long = a fault (a normal recal takes ~5 s)
# Speedgoat restarted into its startup app (15:24 power loss, 15:32 boot into the old AFO):
# 5431 flows again, model time restarted near 0, and no console echo (any echo_sizes.ECHO_SIZES length)
RESTART_T_MAX_S = 30.0          # model time this low after a jump back = a fresh start
RESTART_ECHO_WAIT_S = 3.0       # no r1 echo this long after the restart (or while 5431 flows) -> flag
# any console echo length a build sends (12 / 15 / 18 / 31 / 44 / 45, echo_sizes.ECHO_SIZES) clears /
# prevents it; missing 44 / 45 made healthy run-16b / 16c devices read 'Speedgoat restarted'
from echo_sizes import ECHO_SIZES as R1_ECHO_COLS  # noqa: E402
STARTUP_APP_TEXT = "Speedgoat restarted: AFO_r1 not running (startup app)"

import model_profile as mp
from session import SHORT, _num

_log = logging.getLogger("afo.status")

NO_DATA_S = 0.5          # SPEC: no 5431 packet for > 0.5 s -> "No data"
IMU_NOT_OK_S = 0.2       # console imu_ok = 0 NOW (onset debounce against flicker) -> "IMU fault"; clears at once
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
    """'' when the IMU looks fine, else why not. Andy 15:39-15:40 ("a little drop is not an
    issue", "fault only shows when it CURRENTLY has no data"): ONLY console imu_ok = 0 right now,
    after a 0.2 s onset debounce; clears the moment imu_ok is 1 again. No latch, no window, no
    count: bad packets (byte slips) stay a plain number in the Rig status row."""
    tr = {}
    try:
        tr = ctx.training.latest(max_age_s=1.0) or {}
    except Exception:
        tr = {}
    ok = tr.get("imu_ok")
    now = time.monotonic()
    if isinstance(ok, (int, float)) and ok == ok and ok < 0.5:
        t0 = getattr(ctx.session, "_imu_not_ok_since", None)
        if t0 is None:
            t0 = ctx.session._imu_not_ok_since = now
        if now - t0 > IMU_NOT_OK_S:
            return f"imu_ok = 0 (console) for {now - t0:.1f} s"
    else:
        ctx.session._imu_not_ok_since = None
    return ""


def cable_issues(ctx, notes: List[str]) -> List[Dict[str, Any]]:
    """Run 16 (44-float echo): red 'Cable jam: torque cut' while jam_flag = 1 (the model latches
    it until Motor OFF -> ON), amber 'Cable slack' while slack_flag = 1, both only while set NOW
    (fresh echo). slack_count / slack_last_stride go to the popover notes. Flag changes are
    logged (WARNING when set, INFO when cleared)."""
    try:
        e = ctx.training.latest(max_age_s=1.0) or {}
    except Exception:
        e = {}
    out = []
    if e.get("jam_flag") is None and e.get("slack_flag") is None:
        return out
    sess = ctx.session
    prev = getattr(sess, "_cable_prev", None) or {}
    now_f = {}
    for k in ("jam_flag", "slack_flag"):
        v = e.get(k)
        now_f[k] = bool(isinstance(v, (int, float)) and v == v and v >= 0.5)
        if now_f[k] != prev.get(k, False):
            (_log.warning if now_f[k] else _log.info)("%s %s (slack_count %s, slack_last_stride %s)", k,
                                                      "set" if now_f[k] else "cleared", e.get("slack_count"),
                                                      e.get("slack_last_stride"))
    sess._cable_prev = now_f
    if now_f["jam_flag"]:
        out.append({"level": "red", "key": "cable-jam", "text": "Cable jam: torque cut",
                    "detail": "jam_flag = 1 (latched in the model)",
                    "todo": "Check the cable, then switch Motor off and on to clear."})
    if now_f["slack_flag"]:
        out.append({"level": "amber", "key": "cable-slack", "text": "Cable slack",
                    "detail": f"slack events {int(e.get('slack_count') or 0)}, last stride {int(e.get('slack_last_stride') or 0)}",
                    "todo": "The cable went slack (torque below the slack threshold); it clears when torque is positive again."})
    if e.get("slack_count") is not None:
        notes.append(f"Cable slack events: {int(e.get('slack_count') or 0)} (last stride {int(e.get('slack_last_stride') or 0)})")
    return out


def _hm(t):
    return time.strftime("%H:%M:%S", time.localtime(t)) if t else "–"


def startup_app_issue(ctx, live_now: bool, tr_st: Dict[str, Any], tr_age) -> Dict[str, Any]:
    """The Speedgoat came back with its startup app instead of AFO_r1: 5431 flows (model time
    restarted near 0) but no r1 console echo arrives. {} when not the case. State lives on
    ctx.session (sg_*); one WARNING line per detection; cleared by the next r1 echo."""
    sess = ctx.session
    now = time.time()
    echo_cols = tr_st.get("columns")
    if tr_age is not None and tr_age < 1.0 and echo_cols in R1_ECHO_COLS:
        sess.sg_r1_echo_at = now                  # an AFO_r1 echo: the r1 app is running
        if getattr(sess, "sg_flag", None):
            _log.info("AFO_r1 console echo back (%s floats): 'Speedgoat restarted' cleared", echo_cols)
        sess.sg_flag = None
        sess.sg_restart_at = None
    rb = {}
    try:
        rb = ctx.live.readback() or {} if hasattr(ctx.live, "readback") else {}
    except Exception:
        rb = {}
    t = rb.get("t_model")
    if isinstance(t, (int, float)) and t == t:
        last = getattr(sess, "sg_last_t", None)
        if last is not None and t < last - 1.0 and t < RESTART_T_MAX_S:
            sess.sg_restart_at = now - float(t)       # model time t s ago it was 0
            sess.sg_restart_from = last
        sess.sg_last_t = float(t)
    r1_echo_at = getattr(sess, "sg_r1_echo_at", None)
    r1_known = r1_echo_at is not None or getattr(sess, "last_model", None) == "AFO_r1"
    restart_at = getattr(sess, "sg_restart_at", None)
    echo_absent = tr_age is None or tr_age >= RESTART_ECHO_WAIT_S or echo_cols not in R1_ECHO_COLS
    if live_now and echo_absent:
        if getattr(sess, "sg_absent_since", None) is None:
            sess.sg_absent_since = now
    else:
        sess.sg_absent_since = None
    absent_s = now - sess.sg_absent_since if getattr(sess, "sg_absent_since", None) is not None else 0.0
    flag = None
    if live_now and r1_known and echo_absent:
        if restart_at is not None and now - restart_at > RESTART_ECHO_WAIT_S and (r1_echo_at or 0) < restart_at:
            flag = "restart"
        elif absent_s > RESTART_ECHO_WAIT_S or (r1_echo_at is not None and now - r1_echo_at > RESTART_ECHO_WAIT_S):
            flag = "no-echo"
    if not flag:
        if getattr(sess, "sg_flag", None) and not live_now:
            sess.sg_flag = None
        return {}
    detail = ("Model time on 5431 restarted near 0 at " + _hm(restart_at) if restart_at else
              "5431 is flowing but the AFO_r1 console echo (5433) is absent") + \
        "; last known app AFO_r1; console echo stopped at " + _hm(r1_echo_at)
    if getattr(sess, "sg_flag", None) != flag:
        _log.warning("Speedgoat restarted into its startup app? %s", detail)
        sess.sg_flag = flag
    return {"level": "amber", "key": "speedgoat-restarted", "text": STARTUP_APP_TEXT, "detail": detail,
            "restart_at": restart_at, "echo_stopped_at": r1_echo_at,
            "todo": "The Speedgoat booted its startup app (the old AFO model). Load and Start AFO_r1 "
                    "(Trials: Connect, then Start); settings are frozen and nothing is sent until the AFO_r1 echo returns."}


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

    # ---- base: live-relevant only (Andy 16:11). The MATLAB link and run-control jobs
    # (Connecting / Starting / Exporting / status refresh) never show on this button: they show on
    # the Trials 'MATLAB link' row and the Start / Stop / Export buttons.
    if running:
        base = {"state": "ready", "text": "Ready", "level": "green"}
    elif connected:
        base = {"state": "connected", "text": "No data", "level": "grey"}
    else:
        base = {"state": "not-connected", "text": "No data", "level": "grey"}

    issues: List[Dict[str, Any]] = []
    notes: List[str] = []
    sg = startup_app_issue(ctx, live_now, tr_st, tr_age)
    if sg:
        issues.append(sg)
    rc_issues: List[Dict[str, Any]] = []      # MATLAB link results: Trials row only, never the button
    off = getattr(ctx.runctl, "offline", None)
    if not connected and off:
        # the last Connect failed: say why (amber) until Disconnect or a successful connect
        addr = rc.get("target") or "192.168.7.5"
        kind = off.get("kind") or "offline"
        detail = (f"Connect failed at {time.strftime('%H:%M:%S', time.localtime(off['at']))}: "
                  f"{off.get('err') or 'no answer'}")
        if kind == "busy":
            rc_issues.append({"level": "amber", "key": "speedgoat-busy", "text": "Speedgoat busy", "detail": detail,
                           "todo": "Another MATLAB session is connected to the Speedgoat (a load script or "
                                   "Simulink). Wait for it to disconnect, then press Connect again."})
        elif kind == "offline":
            rc_issues.append({"level": "amber", "key": "speedgoat-offline", "text": "Speedgoat offline", "detail": detail,
                           "todo": f"No answer from the Speedgoat at {addr}. Check that it is switched on and "
                                   "booted (it may be off for charging) and that the Ethernet cable is in, "
                                   "then press Connect again."})
        else:
            rc_issues.append({"level": "amber", "key": "connect-failed", "text": "Connect failed", "detail": detail,
                           "todo": "Read the error, fix what it names, then press Connect again."})
    if running or connected:
        if running:
            for name, age, needed in (("live", live_age, True), ("console", tr_age, need_training)):
                if name == "console" and sg:
                    continue                  # said as "Speedgoat restarted …", not a red "No data"
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
            for it in cable_issues(ctx, notes):
                issues.append(it)
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
                # Bi-LSTM phase (console 15 / 18-float tail)
                try:
                    b = ctx.session.bif_view() or {}
                except Exception:
                    b = {}
                ph = b.get("phase")
                # IMU not ready only as a FAULT (Andy 15:23): bias_ready 0 for more than 10 s; the
                # normal ~5 s recal after Calibrate IMU / Start shows nothing
                sess = ctx.session
                if ph == "bias":
                    now = time.time()
                    if getattr(sess, "bias_low_since", None) is None:
                        sess.bias_low_since = now
                    if now - sess.bias_low_since > IMU_NOT_READY_FAULT_S:
                        issues.append({"level": "amber", "key": "imu-not-ready", "text": "IMU not ready",
                                       "detail": f"bias not ready for {now - sess.bias_low_since:.0f} s",
                                       "todo": "The wearer holds still for 5 s; check the IMU if it stays."})
                else:
                    sess.bias_low_since = None
                if ph == "walk":
                    pct = b.get("progress_pct")
                    n = int(round(30 * pct / 100.0)) if pct is not None else None
                    issues.append({"level": "amber", "key": "calibrating",
                                   "text": f"Calibrating {n}/30 s" if n is not None else "Calibration walk",
                                   "detail": b.get("text"), "todo": "Walk normally for about 30 s."})
                elif ph == "unknown":
                    # not actionable: a grey note in the popover only (the button can be green Ready)
                    notes.append("Bi-LSTM state unknown: needs the 15-float console packet")
        # no 'X differs' issues (Andy 16:15): the page shows the device's values; a pending edit
        # is amber until the echo confirms it
    # the oldest silent stream first among the reds
    prio = {"cable-jam": 1.2, "cable-slack": 5.5, "speedgoat-restarted": 0, "speedgoat-offline": 0, "speedgoat-busy": 0, "connect-failed": 0, "no-data": 0, "side-differs": 1, "imu-fault": 1.5, "drive-fault": 2, "app-elsewhere": 2.5, "confirm-side": 3, "side-pending": 4,
            "bif-mass": 5, "imu-not-ready": 6, "calibrating": 7, "bif-unknown": 10}   # "... differs": 9
    # the wrong app running explains the rest (a dead drive is expected then): it outranks
    # every red, e.g. "Drive fault (STO)"
    first = ("speedgoat-restarted",)
    issues.sort(key=lambda i: (0 if i["key"] in first else 1, 0 if i["level"] == "red" else 1,
                               prio.get(i["key"], 9), -(i.get("age_s") or 0)))
    out = dict(base)
    if issues:
        top = issues[0]
        out = {"state": top["key"], "text": top["text"], "level": top["level"]}
    out.update(base_state=base["state"], issues=issues, rc_issues=rc_issues, notes=notes, connected=connected, running=running, model=model,
               streams={"live_age_s": live_age, "console_age_s": tr_age, "console_required": need_training},
               writes_enabled=ctx.session.writes_enabled, at=time.time())
    return out
