"""JSON API for the console UI (design v18): one state endpoint polled twice a
second, plus the operator actions. The page script (assets/afo_console.js)
renders everything from /api/console/state; nothing here sends a command or a
setting unless an action endpoint is called by an operator click.

Run control (Connect / Start / Stop) stays on /api/run/<action> (OMEN only).
Motor / Assist / K / Calibrate / Reset SV / session values work from the
tablet too (it is the treadmill console).
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from flask import jsonify, request

from pages.common import is_local
from session import MODES, SIDE_NAMES, SPECS, values_match
from status import NO_DATA_S, _age as _status_age, top_status

BUSY_TEXT = {"connect": ("Connecting…", "Connecting… attaching MATLAB"),
             "disconnect": ("Disconnecting…", "Disconnecting…"),
             "start": ("Starting…", "Starting… loading AFO"),
             "stop": ("Stopping…", "Stopping… importing log"),
             "save": ("Exporting…", "Exporting…"), "list file log": ("Reading log…", "Reading the file log…")}
PENDING_S = 1.0


# Advanced display decimals (speeds / gains 2, step sizes 3, windows / strides / level / cutoff whole)
ADV_DEC = {"sv_target_min": 2, "sv_target_max": 2, "target_step_up": 3, "target_step_down": 3, "window_up": 0,
           "window_down": 0, "assist_threshold": 0, "min_cycles": 0, "p_gain": 2, "i_gain": 2, "threshold_pressure": 0,
           "fade_ms": 0}


def _fmt(key: str, v) -> str:
    if v is None:
        return "–"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != f:
        return "---"
    if key == "side":
        return {0: "Left", 1: "Right", -1: "Unset"}.get(int(round(f)), f"{f:g}")
    if key == "mode":
        return {1: "RL", 2: "ILC", 3: "Fixed K"}.get(int(round(f)), f"{f:g}")
    if key in ("weight", "bif_mass"):
        return f"{f:g} kg"
    if key == "k_percent":
        return f"{f:.1f} %"
    if key in ADV_DEC:                     # never float32 noise like 0.800000011920929
        return f"{round(f, ADV_DEC[key]):g}" if ADV_DEC[key] else f"{int(round(f))}"
    return f"{f:g}"


def settings_rows(ctx) -> Dict[str, Any]:
    """Popover table: Foot side, Body mass, Assistance mode, K, Advanced (n of n)."""
    sess = ctx.session
    table = {r["name"]: r for r in sess.target_table()}
    console_live = bool(sess.echo())
    rows = []
    # one Body mass row: on AFO_r1 it is ok only when weight AND BIF_mass_kg both equal it
    main = [("side", "Foot side"), ("weight", "Body mass"),
            ("mode", "Assistance mode"), ("k_percent", "K")]
    for key, label in main:
        if key not in table:          # not in this model profile (bif_mass in AFO)
            continue
        r = table.get(key, {})
        st = (sess.status.get(key) or {}).get("state")
        if r.get("match") is True:
            state = "ok"
        elif st == "sending" or (r.get("entered") is not None and r.get("target") is None):
            state = "sending"
        elif r.get("match") is False:
            state = "sending"                 # not confirmed by the device yet: amber, never "differs"
        else:
            state = "none"
        if r.get("source") == "echo" and not console_live:
            state = "sending"
        row = {"key": key, "label": label, "entered": _fmt(key, r.get("entered")),
               "target": _fmt(key, r.get("target")) if r.get("target") is not None else "…",
               "state": state, "source": r.get("source")}
        if key == "weight" and "bif_mass" in table:
            b = table["bif_mass"]
            bt = b.get("target")
            row["title"] = (f"weight {_fmt('weight', r.get('target'))} · BIF_mass_kg "
                            f"{_fmt('bif_mass', bt) if bt is not None else '…'} (both are set from Body mass)")
            if state == "ok" and b.get("match") is not True:
                row["state"] = "sending"
                if bt is not None:
                    row["target"] = f"{row['target']} / {_fmt('bif_mass', bt)}"
        rows.append(row)
    # a UDP-only Advanced value (run 16c fade) counts only on a build that echoes it
    adv = [sp["key"] for sp in SPECS if sp.get("adv") and (not sp.get("udp_only") or (table.get(sp["key"]) or {}).get("target") is not None)]
    known = [table[k] for k in adv if k in table and table[k].get("target") is not None]
    n_match = sum(1 for r in known if r.get("match") is True or (r.get("entered") is None))
    differs = [r for r in known if r.get("match") is False]
    rows.append({"key": "adv", "label": f"Advanced ({len(adv)})", "entered": str(len(adv)),
                 "target": f"{n_match} match" if known else "…",
                 "state": "sending" if differs else ("ok" if len(known) == len(adv) else "sending" if known else "none"),
                 "differs": [d["label"] for d in differs]})
    ages = [r.get("age_s") for r in table.values() if r.get("age_s") is not None]
    read_at = time.strftime("%H:%M:%S", time.localtime(sess.readback_at)) if sess.readback_at else None
    return {"rows": rows, "read_back_at": read_at, "console_live": console_live,
            "oldest_age_s": max(ages) if ages else None}


def side_view(ctx) -> Dict[str, Any]:
    sess = ctx.session
    chip = sess.side_chip()
    want = sess.values.get("side")
    rb, _src = sess.side_target()                  # 5433 echo first, then getparam
    try:
        rbi = None if rb is None else int(round(float(rb)))
    except (TypeError, ValueError):
        rbi = None
    if chip["state"] == "bad":
        state = "mismatch"
    elif chip["state"] == "refused":
        state = "refused"
    elif chip["state"] == "ok":
        state = "ok"
    elif chip["state"] == "pending":
        state = "pending"
    else:
        state = "confirm"
    shown = SIDE_NAMES.get(rbi) if rbi in (0, 1) else (SIDE_NAMES.get(int(want)) if want is not None else None)
    connected = bool((ctx.runctl.status or {}).get("connected"))
    # the target counts as there when MATLAB is connected OR its live stream is fresh (data
    # proves the app runs, as for the status button); only with neither is the chip quiet
    try:
        lst = ctx.live.get_status()
        age = _status_age(ctx.live, lst) if lst.get("live_seen") else None
        live_now = age is not None and age < NO_DATA_S
    except Exception:
        live_now = False
    online = connected or live_now
    if state == "confirm" and not online:
        # offline: no attention "? CONFIRM FOOT"; the side is confirmed in the chip's popover
        # (then pending) or asked for when connected
        quiet = (f"{SIDE_NAMES[int(want)].capitalize()} foot · not confirmed" if want is not None
                 else "Foot side · not set")
    return {"state": state, "app": SIDE_NAMES.get(int(want)) if want is not None else None,
            "target": SIDE_NAMES.get(rbi) if rbi in (0, 1) else ("UNSET" if rbi == -1 else None),
            "chip": (f"{shown.capitalize()} foot" if state == "ok" and shown else
                     "! FOOT MISMATCH" if state == "mismatch" else
                     chip["text"] if state in ("pending", "refused") else
                     quiet if not online else "? CONFIRM FOOT"),
            "sid": sess.sid, "connected": online,
            "msg": chip.get("msg") or (sess.status.get("side") or {}).get("msg") or "",
            "after_start": bool(getattr(sess, "after_start", False)), "problem": sess.side_problem()}


def commands_view(ctx) -> Dict[str, Any]:
    v = ctx.commands.view()
    sent = dict(getattr(ctx.commands, "toggles", {}) or {})
    recent = v.get("last_sent_at") and time.time() - v["last_sent_at"] < PENDING_S
    out = {}
    for t, r in v["toggles"].items():
        pending = bool(recent and r.get("source") == "model" and sent.get(t) is not None and sent.get(t) != r.get("value"))
        out[t] = {"value": r.get("value"), "source": r.get("source"), "pending": pending, "mismatch": False}
    return {"toggles": out, "calibrate_busy_s": v["calibrate_busy_s"], "last_pulse": v["last_pulse"],
            "latched": v.get("latched") or {}}


def rig_view(ctx) -> Dict[str, Any]:
    rc = ctx.runctl.status or {}
    live = ctx.live.get_status()
    tr = ctx.training.get_status()
    lh = (live.get("health") or {}).get("packets") or {}
    rb = ctx.live.readback()
    latest = ctx.training.latest(max_age_s=0.5)
    sw = rb.get("statusword")
    tet = None
    if rc.get("tet_avg_us") not in (None, []):
        tet = f"{rc['tet_avg_us']:.0f} / {rc['tet_max_us']:.0f} µs"
    ecat = rc.get("ethercat_state")
    return {
        "target": f"{rc.get('target') or ctx.poller.get().get('target_host', '192.168.7.5')} · "
                  + ("MATLAB connected" if rc.get("connected") else "MATLAB: not connected (connects on Start/Stop/Export)"),
        "application": (f"{rc.get('app')} · " + ("running" if rc.get("running") else "stopped")) if rc.get("app") else "–",
        "tet": tet or "–",
        "ethercat": "–" if ecat in (None, []) else ("OP" if ecat == 8 else f"state {ecat}"),
        "file_log": rc.get("filelog") or "–",
        "main_udp": {"rate": round(live.get("rate_hz") or 0), "lost": int(lh.get("lost", 0) or 0),
                     "bad": int(lh.get("bad_length", 0) or 0) +
                     int(lh.get("bad_time", 0) or 0) + int(lh.get("errors", 0) or 0)},
        "console_udp": {"enabled": bool(getattr(ctx.training, "enabled", False)), "rate": round(tr.get("rate_hz") or 0), "columns": tr.get("columns"),
                        "lost": int(tr.get("lost_packets") or 0),
                        "rejected": int(tr.get("bad_length") or 0) + int(tr.get("non_finite_packets") or 0)
                        + int(tr.get("bad_value") or 0)},
        "statusword": f"0x{int(sw):04X}" if isinstance(sw, (int, float)) and sw == sw else "–",
        "imu": ("–" if not latest else ("Valid" if latest.get("imu_ok", 0) >= 0.5 else "INVALID")
                + f" · {int(latest.get('imu_bad_count') or 0)} bad packets"),
        "updated": time.strftime("%H:%M:%S"),
    }


def _imu_cal_view(ctx) -> Dict[str, Any]:
    ic = getattr(ctx, "imu_cal", None)
    if ic is None:
        return {"visible": False}
    try:
        ic.probe()
    except Exception:
        pass
    return ic.view()


def console_state(ctx) -> Dict[str, Any]:
    try:
        ctx.session.adopt_echo()             # first fresh 5433 echo after a server start
        ctx.session.refresh_echo()           # readbacks from the echo on every poll (no MATLAB)
    except Exception:
        pass
    st = top_status(ctx)
    job = ctx.jobs.running("rc")
    busy = None
    if job is not None:
        action = job.title.split(":")[-1].strip()
        if action in BUSY_TEXT:
            busy = {"action": action, "verb": BUSY_TEXT[action][0], "msg": BUSY_TEXT[action][1],
                    "started": getattr(job, "started", None), "stage": (getattr(job, "meta", None) or {}).get("stage")}
    sess = ctx.session
    sent_recent = any((v or {}).get("state") == "sending" for v in sess.status.values())
    if not busy and sent_recent and st["level"] not in ("red",):
        st = dict(st, state="busy", text="Sending…", level="busy")
    rc = ctx.runctl.status or {}
    values = {sp["key"]: sess.values.get(sp["key"]) for sp in SPECS}
    prof = sess.profile()
    bif = sess.bif_view()
    running = bool(st.get("running"))
    chk = sess.checklist(bif) if running else None
    return {
        "at": time.time(), "local": is_local(), "status": st, "busy": busy,
        "view_only": bool((ctx.cfg.get("console") or {}).get("view_only", False)),
        "target": {"connected": bool(rc.get("connected")), "running": bool(st.get("running")),
                   "address": rc.get("target") or "192.168.7.5", "app": rc.get("app")},
        "session": {"sid": sess.sid, "values": values, "modes": {str(k): v for k, v in MODES.items()},
                    "readback": dict(sess.readback), "readback_source": dict(sess.readback_src),
                    "adv_last": {k: v["value"] for k, v in getattr(sess, "adv_last", {}).items()},
                    "status": {k: (v or {}).get("state") for k, v in sess.status.items()},
                    "status_msg": {k: (v or {}).get("msg") for k, v in sess.status.items()},
                    "writes_enabled": sess.writes_enabled,
                    # run 15 (31-float echo): Advanced values from the echo; editable only with the
                    # 5435 sender (until then read-only, no hint)
                    "adv": _adv_view(ctx), "guard": _guard_view(ctx)},
        "model": {"name": sess.model(), "label": prof["label"], "bif": bool(prof.get("bif")),
                  "loaded": rc.get("app") or None,
                  "source": ("loaded" if rc.get("app") in sess.models else
                             "config" if sess.configured_model in sess.models else
                             "last connect" if sess.last_model in sess.models else "default")},
        "bif": bif, "checklist": chk,
        "side": side_view(ctx), "settings": settings_rows(ctx), "commands": commands_view(ctx),
        "rig": rig_view(ctx),
        "imu_cal": _imu_cal_view(ctx),
        "link": (ctx.settings_link.view() if getattr(ctx, "settings_link", None) is not None else None),
    }


def _adv_view(ctx) -> Dict[str, Any]:
    sess = ctx.session
    try:
        udp = bool(sess.adv_profile())          # sticky for the run: a stall only freezes
        stale = bool(sess.echo_stale())
    except Exception:
        udp, stale = False, False
    lk = getattr(ctx, "adv_link", None) if udp else None
    out = {"udp": udp, "send": lk is not None, "frozen": bool(udp and stale), "msg": sess.FROZEN_MSG if udp and stale else "",
           "rules": {}}
    if lk is not None:
        v = lk.view()
        if v.get("frozen"):
            out.update(frozen=True, msg=v.get("msg") or sess.FROZEN_MSG)
        out["rules"] = lk.rules_for_page()
    return out


def _guard_view(ctx) -> Dict[str, Any]:
    """Run 16 (44-float echo, sticky): the Torque guard card: values in use from the echo
    (cols 35-42), editable over 5436 with the 5434 rules, frozen in a stall."""
    sess = ctx.session
    try:
        udp = bool(sess.guard_profile())
        stale = bool(sess.echo_stale())
    except Exception:
        udp, stale = False, False
    lk = getattr(ctx, "guard_link", None) if udp else None
    out = {"udp": udp, "send": lk is not None, "frozen": bool(udp and stale),
           "msg": sess.FROZEN_MSG if udp and stale else "", "rules": {}, "values": {}, "status": {}, "status_msg": {}}
    if lk is not None:
        e = sess.echo() or {}
        out["rules"] = lk.rules_for_page()
        out["values"] = {f: e.get(f) for f in lk.FIELDS}
        res = lk.view()
        if res.get("frozen"):
            out.update(frozen=True, msg=res.get("msg") or sess.FROZEN_MSG)
        out["status"] = {f: (r or {}).get("state") for f, r in (res.get("result") or {}).items()}
        out["status_msg"] = {f: (r or {}).get("msg") for f, r in (res.get("result") or {}).items()}
        for f in res.get("pending") or []:
            out["status"][f] = "sending"
    return out


def register(server, ctx) -> None:
    def body():
        return request.get_json(silent=True) or {}

    @server.route("/api/console/state")
    def api_console_state():  # type: ignore
        return jsonify(console_state(ctx))

    @server.route("/api/console/sid", methods=["POST"])
    def api_console_sid():  # type: ignore
        msg = ctx.session.set_sid(str(body().get("sid", "")))
        ok = ctx.session.sid == str(body().get("sid", "")).strip().upper()
        return jsonify({"ok": ok, "msg": msg}), (200 if ok else 400)

    @server.route("/api/console/value", methods=["POST"])
    def api_console_value():  # type: ignore
        b = body()
        key, value = str(b.get("key", "")), b.get("value")
        if key not in {sp["key"] for sp in SPECS} or key in ("side", "bif_mass"):     # bif_mass follows weight
            return jsonify({"ok": False, "msg": "unknown setting"}), 400
        if any(sp["key"] == key and sp.get("readonly") for sp in SPECS):
            return jsonify({"ok": False, "msg": "read-only"}), 403
        if not b.get("confirmed"):
            need = ctx.session.check_change(key, value)
            if need:
                return jsonify({"ok": False, "needs_confirm": need}), 409
        msg = ctx.session.enter_value(key, value)
        st = (ctx.session.status.get(key) or {}).get("state")
        ok = st in ("sending", "pending", "confirmed")
        return jsonify({"ok": ok, "msg": msg, "state": st}), (200 if ok else 400)

    @server.route("/api/console/side", methods=["POST"])
    def api_console_side():  # type: ignore
        side = str(body().get("side", "")).upper()
        if ctx.commands.view()["toggles"]["motor"]["value"] == 1:
            return jsonify({"ok": False, "msg": "Motor is on: switch it off before changing the foot side."}), 409
        msg = ctx.session.confirm_side(side, ctx.session.sid or "")
        st = (ctx.session.status.get("side") or {}).get("state")
        ok = st in ("sending", "pending", "confirmed")
        return jsonify({"ok": ok, "msg": msg, "state": st}), (200 if ok else 400)

    @server.route("/api/console/toggle", methods=["POST"])
    def api_console_toggle():  # type: ignore
        name = str(body().get("name", ""))
        if name not in ("motor", "assist", "k"):
            return jsonify({"ok": False, "msg": "unknown toggle"}), 400
        r = ctx.commands.press_toggle(name)
        return jsonify(r), (200 if r.get("ok") else 409)

    @server.route("/api/console/pulse", methods=["POST"])
    def api_console_pulse():  # type: ignore
        r = ctx.commands.pulse(str(body().get("name", "")))
        return jsonify(r), (200 if r.get("ok") else 409)

    @server.route("/api/console/guard", methods=["POST"])
    def api_console_guard():  # type: ignore
        b = body()
        lk = getattr(ctx, "guard_link", None)
        if lk is None or not ctx.session.guard_profile():
            return jsonify({"ok": False, "msg": "Torque guard: not on this build"}), 409
        if ctx.session.echo_stale():
            return jsonify({"ok": False, "msg": ctx.session.FROZEN_MSG}), 409
        r = lk.press(str(b.get("field", "")), b.get("value"))
        return jsonify(r), (200 if r.get("ok") else 409)

    @server.route("/api/console/advanced", methods=["POST"])
    def api_console_advanced():  # type: ignore
        # Advanced panel Confirm: {"adv": {key: value}, "guard": {field: value}} -> one 5435
        # packet and one 5436 packet. Nothing in the panel is sent before this (Andy Nov 24).
        b = body()
        adv, guard = b.get("adv") or {}, b.get("guard") or {}
        if not isinstance(adv, dict) or not isinstance(guard, dict) or not (adv or guard):
            return jsonify({"ok": False, "msg": "nothing to confirm"}), 400
        r = ctx.session.confirm_advanced(adv, guard)
        return jsonify(r), (200 if r.get("ok") else 409)

    @server.route("/api/console/imucal", methods=["POST"])
    def api_console_imucal():  # type: ignore
        ic = getattr(ctx, "imu_cal", None)
        if ic is None:
            return jsonify({"ok": False, "msg": "not available"}), 409
        r = ic.press()
        return jsonify(r), (200 if r.get("ok") else 409)

    @server.route("/api/console/unknown-off", methods=["POST"])
    def api_console_unknown_off():  # type: ignore
        r = ctx.commands.set_unknown_off()
        return jsonify(r), (200 if r.get("ok") else 409)
