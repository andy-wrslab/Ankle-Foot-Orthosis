"""Calibrate IMU (AFO_r1): one press = one 1 ms IMU front-end reset in the model.

Model interface (Simulink thread, final): tunable Constant 'AFO_r1/Gyro_Cal_Request'
param 'Value'; every CHANGE of the value triggers one reset. The page reads the
current value (getparam) and writes value + 1 (setparam + readback).

Available only when the loaded app has that block (the getparam succeeds; the
r1 build of 2026-11-23 does not, so the button is disabled with "needs the next
r1 build") and only while Assist or Motor is OFF. After a press the page shows
"Hold still 5 s…" counting down, then "IMU ready" once BIF_Bias_Ready
('AFO_r1/Bi-LSTM Estimator' out 5, bif_bias_ready on the Signals stream) is 1
again; without Signals it shows "IMU ready (assumed)" after the 5 s.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional

BLOCK, PARAM = "Gyro_Cal_Request", "Value"
HOLD_S = 5.0          # wearer holds still
HOLD_NO_SIGNAL_S = 6.0  # without bif_bias_ready (no Signals, 12-float console): a plain 6 s countdown
READY_TIMEOUT_S = 20.0  # bias-ready must be back by then (with Signals)
PROBE_EVERY_S = 10.0


class ImuCal:
    def __init__(self, ctx, hold_s: float = HOLD_S, ready_timeout_s: float = READY_TIMEOUT_S,
                 hold_no_signal_s: float = HOLD_NO_SIGNAL_S) -> None:
        self.ctx = ctx
        self.hold_s, self.ready_timeout_s, self.hold_no_signal_s = hold_s, ready_timeout_s, hold_no_signal_s
        self.lock = threading.Lock()
        self.available: Optional[bool] = None     # None = not probed for this connection
        self.value: Optional[float] = None
        self.probe_err = ""
        self.probe_key = None                     # (connected, app) the probe belongs to
        self.probed_at = 0.0
        self.pressed_at: Optional[float] = None   # setparam confirmed at (the reset happened then)
        self.hold_len: Optional[float] = None     # fixed at confirmation: 5 s with a bias signal, else 6 s
        self.ready_at: Optional[float] = None
        self.sending = False
        self.err = ""

    # ------------------------------------------------------------------ helpers
    def _path(self) -> Optional[str]:
        model = self.ctx.session.model()
        return f"{model}/{BLOCK}" if self.ctx.session.profile().get("bif") else None

    def _rc(self) -> Dict[str, Any]:
        return self.ctx.runctl.status or {}

    def _call(self, *args, timeout: float = 20.0) -> Dict[str, Any]:
        return json.loads(self.ctx.matlab.call("afo_session", *args, timeout=timeout))

    # ------------------------------------------------------------------ probe
    def probe(self, force: bool = False) -> None:
        """getparam the request block (in a job, never on the request thread). Not on run 14:
        the counter is the 5433 echo col 15 (gyro_cal_request), no MATLAB read."""
        lk = self.ctx.session.link() if hasattr(self.ctx.session, "link") else None
        if lk is not None:
            g = ((lk.view().get("adopted") or {}).get("gyro"))
            with self.lock:
                self.available, self.probe_err = True, ""
                if g is not None:
                    self.value = float(g)
            return
        rc = self._rc()
        key = (bool(rc.get("connected")), rc.get("app"))
        if key != self.probe_key:
            self.available, self.value, self.probe_err, self.probe_key = None, None, "", key
        path = self._path()
        if not rc.get("connected") or not path:
            return
        if not force and time.time() - self.probed_at < PROBE_EVERY_S:
            return
        if self.ctx.jobs.running("session") or self.ctx.jobs.running("rc"):
            return
        self.probed_at = time.time()

        def run(job):
            out = self._call("read", [f"{path}|{PARAM}"])
            vals = out.get("values") or []
            if isinstance(vals, dict):
                vals = [vals]
            hit = vals[0] if vals else {}
            with self.lock:
                if out.get("ok") and hit.get("value") not in (None, []) and not hit.get("err"):
                    self.available, self.value, self.probe_err = True, float(hit["value"]), ""
                else:
                    self.available, self.probe_err = False, (hit.get("err") or out.get("err") or "no such block")
            job.add(json.dumps(out)[:300])
            return out
        self.ctx.jobs.start("session", "probe Gyro_Cal_Request", run)

    # ------------------------------------------------------------------ press
    def block_reason(self) -> str:
        if not self.ctx.session.profile().get("bif"):
            return "Only in AFO_r1"
        lk = self.ctx.session.link() if hasattr(self.ctx.session, "link") else None
        if lk is not None:                       # run 14: over UDP 5434, no MATLAB / Connect
            if lk.frozen:
                return lk.view()["msg"]
            t = self.ctx.commands.view()["toggles"]
            if (t.get("assist") or {}).get("value") == 1 and (t.get("motor") or {}).get("value") == 1:
                return "Switch Assist or Motor off first"
            if self.sending or self.holding():
                return "Calibrating…"
            return ""
        if not self._rc().get("connected"):
            return "Connect first"
        if self.available is None:
            return "Checking the model…"
        if not self.available:
            return "Needs the next r1 build (no Gyro_Cal_Request block in the loaded app)"
        t = self.ctx.commands.view()["toggles"]
        if (t.get("assist") or {}).get("value") == 1 and (t.get("motor") or {}).get("value") == 1:
            return "Switch Assist or Motor off first"
        if self.sending or self.holding():
            return "Calibrating…"
        if not self.ctx.session.writes_enabled:
            return "Target writes are off"
        return ""

    def holding(self) -> bool:
        if self.pressed_at is None:
            return False
        return time.time() - self.pressed_at < (self.hold_len or self.hold_no_signal_s)

    def press(self) -> Dict[str, Any]:
        reason = self.block_reason()
        if reason:
            return {"ok": False, "msg": reason}
        lk = self.ctx.session.link() if hasattr(self.ctx.session, "link") else None
        if lk is not None:
            # run 14: gyro_cal_request counter + 1 over 5434 (the model resets the IMU front end
            # on every change); the hold timer starts now, bias_ready 1 -> 0 -> 1 says when ready
            base = float((lk.view().get("adopted") or {}).get("gyro") or 0.0)
            r = lk.press("gyro", base + 1.0)
            if not r.get("ok"):
                return {"ok": False, "msg": r.get("msg")}
            has_bias = (self.ctx.session.bif_view() or {}).get("bias_ready") is not None
            with self.lock:
                self.err, self.ready_at, self.value = "", None, base + 1.0
                self.pressed_at = time.time()
                self.hold_len = self.hold_s if has_bias else self.hold_no_signal_s
            self.ctx.session.audit("imu calibrate", f"5434 gyro_cal_request {base:g} -> {base + 1:g}")
            return {"ok": True, "msg": "Calibrate IMU: hold still"}
        path = self._path()
        with self.lock:
            self.sending, self.err, self.ready_at = True, "", None

        def run(job):
            try:
                cur = self._call("read", [f"{path}|{PARAM}"])
                vals = cur.get("values") or []
                vals = [vals] if isinstance(vals, dict) else vals
                v0 = float(vals[0]["value"]) if cur.get("ok") and vals and vals[0].get("value") not in (None, []) else None
                if v0 is None:
                    raise RuntimeError((vals[0].get("err") if vals else "") or cur.get("err") or "cannot read Gyro_Cal_Request")
                out = self._call("set", path, PARAM, v0 + 1.0, timeout=30)
                job.add(json.dumps(out))
                if not out.get("ok"):
                    raise RuntimeError(out.get("err") or f"read back {out.get('readback')}")
                has_bias = (self.ctx.session.bif_view() or {}).get("bias_ready") is not None
                with self.lock:
                    self.value, self.pressed_at = float(out.get("readback")), time.time()
                    self.hold_len = self.hold_s if has_bias else self.hold_no_signal_s
                self.ctx.session.audit("imu calibrate", f"{path}|{PARAM} {v0:g} -> {v0 + 1:g}: {json.dumps(out)[:160]}")
                return out
            except Exception as exc:
                with self.lock:
                    self.err = str(exc)
                self.ctx.session.audit("imu calibrate failed", str(exc)[:200])
                raise
            finally:
                with self.lock:
                    self.sending = False
        self.ctx.jobs.start("session", "calibrate IMU", run)
        return {"ok": True, "msg": "Calibrate IMU: sending…"}

    # ------------------------------------------------------------------ view
    def view(self) -> Dict[str, Any]:
        bif = self.ctx.session.profile().get("bif")
        reason = self.block_reason() if bif else "Only in AFO_r1"
        now = time.time()
        text, state = "Calibrate IMU", "idle"
        if self.sending:
            text, state = "Calibrate IMU: sending…", "busy"
        elif self.err:
            text, state = "Calibrate IMU failed", "error"
        elif self.pressed_at is not None:
            el = now - self.pressed_at
            b = self.ctx.session.bif_view() or {}
            ready = b.get("bias_ready")
            hold = self.hold_len or self.hold_no_signal_s       # counted from the setparam confirmation
            if el < hold:
                text, state = f"Hold still {max(1, int(hold - el + 0.999))} s…", "busy"
            else:
                if self.ready_at is None and ready is not None and ready >= 0.5:
                    self.ready_at = now
                if self.ready_at is not None:
                    text, state = "IMU ready", "done"
                elif ready is None:
                    text, state = "IMU ready (assumed)", "done"
                elif el < self.hold_s + self.ready_timeout_s:
                    text, state = "Hold still… waiting for IMU ready", "busy"
                else:
                    text, state = "IMU not ready: try again", "error"
        return {"visible": bool(bif), "available": self.available, "enabled": not reason, "reason": reason,
                "text": text, "state": state, "value": self.value, "err": self.err or self.probe_err}
