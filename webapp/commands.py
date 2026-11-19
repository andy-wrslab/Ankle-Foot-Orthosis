"""Server-side command state: the console never changes a command by itself.

The model holds the last command it received (outdoor/battery walks: the
console may be closed or checked only now and then; STO is the kill switch).
So:
* nothing is sent at server start, on first data, on a new data session, or
  when a page/tab opens, reloads or reconnects;
* a UDP control packet is sent only as the direct result of a button press
  (or a parameter edit), and it always carries the FULL command set, taken from
  the last command this console sent, with only the pressed field changed;
* after a restart the last sent command is reloaded from disk (logs/last_command.json);
  toggles never sent are inferred from the bus where possible
  (motor: statusword "operation enabled"; assist: assistance_level > 0), else
  they are UNKNOWN, and a press that would have to guess an unknown toggle is
  refused with a message instead of sending a default.

Control packet (CONTROL_FMT "<6f", to udp.send_host:send_port):
    zero, motor, assist, k, calibrate_pressure, reset_sv
zero / calibrate_pressure / reset_sv are momentary: 1 while held, 0 otherwise.
Parameter packet (PARAM_FMT "<5f", to udp.param_port):
    epsilon_up, epsilon_down, step_up, step_down, v_min
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

TOGGLES = ("motor", "assist", "k")
MOMENTARY = ("zero", "calibrate", "reset")
PARAMS = ("epsilon_up", "epsilon_down", "step_up", "step_down", "v_min")
# training stream (UDP 5433) columns = the commands actually latched in the model
MODEL_KEYS = {"motor": "cmd_motor", "assist": "cmd_assist", "k": "cmd_k"}
MODEL_PARAM_KEYS = {p: "param_" + p for p in PARAMS}

_log = logging.getLogger("afo.commands")


class CommandState:
    def __init__(self, cfg: Dict[str, Any], state_path: str,
                 send_control: Callable[..., None], send_params: Callable[..., None],
                 readback: Callable[[], Dict[str, Any]]) -> None:
        self.cfg = cfg
        self.path = state_path
        self.send_control = send_control
        self.send_params = send_params
        self.readback = readback
        self.lock = threading.Lock()
        self.toggles: Dict[str, Optional[int]] = {t: None for t in TOGGLES}
        self.params: Dict[str, Optional[float]] = {p: None for p in PARAMS}
        self.held: Dict[str, int] = {m: 0 for m in MOMENTARY}
        self.loaded_from_disk = False
        self.last_sent_at: Optional[float] = None
        self.guard: Optional[Callable[[str], Optional[str]]] = None   # e.g. session setup: block Motor/Assist
        ccfg = (cfg or {}).get("commands") or {}
        # 2026-11-19: no block in AFO.slx reads the 5 parameters (and the model's
        # receiver expects 6 singles while the console sends '<5f'), so the UI can
        # grey them out. Packet format unchanged until decided in the Simulink thread.
        self.params_used_by_model = bool(ccfg.get("params_used_by_model", False))
        # which training-stream columns echo which parameter (configurable)
        self.param_echo = dict(MODEL_PARAM_KEYS)
        self.param_echo.update(ccfg.get("param_echo_columns") or {})
        self._mismatch_since: Dict[str, float] = {}
        self.calibrate_busy_until = 0.0
        self.last_pulse: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ---------------------------------------------------------- persistence
    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fp:
                d = json.load(fp)
            for t in TOGGLES:
                if d.get("toggles", {}).get(t) in (0, 1):
                    self.toggles[t] = int(d["toggles"][t])
            for p in PARAMS:
                v = d.get("params", {}).get(p)
                if isinstance(v, (int, float)) and math.isfinite(v):
                    self.params[p] = float(v)
            self.last_sent_at = d.get("sent_at")
            self.loaded_from_disk = True
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump({"toggles": self.toggles, "params": self.params, "sent_at": self.last_sent_at}, fp)
            os.replace(tmp, self.path)
        except OSError as exc:
            _log.warning("could not save last command: %s", exc)

    # ---------------------------------------------------------- state
    def _inferred(self, name: str) -> Optional[int]:
        rb = self.readback() or {}
        if name == "motor":
            sw = rb.get("statusword")
            if isinstance(sw, (int, float)) and math.isfinite(sw):
                return 1 if (int(sw) & 0x0004) else None   # enabled -> motor on; not enabled could be STO
        if name == "assist":
            a = rb.get("assistance_level")
            if isinstance(a, (int, float)) and math.isfinite(a) and a > 0:
                return 1
        return None

    def resolved(self) -> Dict[str, Dict[str, Any]]:
        """Toggle state: the model's latched command (training stream) when available,
        else what this console last sent, else inferred from the bus, else unknown."""
        rb = self.readback() or {}
        out = {}
        for t in TOGGLES:
            mv = rb.get(MODEL_KEYS[t])
            if isinstance(mv, (int, float)) and math.isfinite(mv):
                out[t] = {"value": 1 if mv >= 0.5 else 0, "source": "model"}
                continue
            v = self.toggles[t]
            src = "sent" if v is not None else None
            if v is None:
                v = self._inferred(t)
                src = "bus" if v is not None else None
            out[t] = {"value": v, "source": src}
        return out

    def model_params(self) -> Dict[str, Optional[float]]:
        rb = self.readback() or {}
        out = {}
        for p, k in self.param_echo.items():
            v = rb.get(k)
            out[p] = float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None
        return out

    def mismatches(self) -> list:
        """Model-latched commands that differ from this console's last sent state
        for more than 1 s (e.g. another console, or a lost packet)."""
        rb = self.readback() or {}
        now = time.time()
        found = []
        pairs = [(t, self.toggles[t], rb.get(MODEL_KEYS[t])) for t in TOGGLES]
        pairs += [(p, self.params[p], rb.get(self.param_echo.get(p, ""))) for p in PARAMS]
        for name, sent, model in pairs:
            if sent is None or not isinstance(model, (int, float)) or not math.isfinite(model):
                self._mismatch_since.pop(name, None)
                continue
            model_v = (1 if model >= 0.5 else 0) if name in TOGGLES else float(model)
            differs = model_v != sent if name in TOGGLES else abs(model_v - sent) > 1e-4 * max(1.0, abs(sent))
            if differs:
                t0 = self._mismatch_since.setdefault(name, now)
                if now - t0 > 1.0:
                    found.append({"name": name, "sent": sent, "model": model_v})
            else:
                self._mismatch_since.pop(name, None)
        return found

    def view(self) -> Dict[str, Any]:
        with self.lock:
            return {"toggles": self.resolved(), "params": dict(self.params), "model_params": self.model_params(),
                    "calibrate_busy_s": max(0.0, round(self.calibrate_busy_until - time.time(), 1)),
                    "last_pulse": dict(self.last_pulse),
                    "mismatch": self.mismatches(), "held": dict(self.held),
                    "params_used_by_model": self.params_used_by_model,
                    "params_note": None if self.params_used_by_model else
                    "not used by the current model (no block reads these parameters)",
                    "last_sent_at": self.last_sent_at, "loaded_from_disk": self.loaded_from_disk}

    def _packet(self, toggles: Dict[str, Optional[int]]) -> Optional[str]:
        missing = [t for t in TOGGLES if toggles[t] is None]
        if missing:
            return ("Not sent: the current state of " + ", ".join(m.upper() if m == "k" else m.capitalize()
                                                                  for m in missing)
                    + " is unknown (this console has not set it, and it cannot be read from the bus). "
                      "Use 'Set unknown to OFF' first.")
        self.send_control(self.cfg, float(self.held["zero"]), float(toggles["motor"]), float(toggles["assist"]),
                          float(toggles["k"]), float(self.held["calibrate"]), float(self.held["reset"]), force=True)
        self.last_sent_at = time.time()
        return None

    # ---------------------------------------------------------- user actions
    def press_toggle(self, name: str) -> Dict[str, Any]:
        if self.guard is not None and name in ("motor", "assist"):
            block = self.guard(name)
            if block:
                return {"ok": False, "msg": block}
        with self.lock:
            cur = {t: r["value"] for t, r in self.resolved().items()}
            new = 0 if cur[name] == 1 else 1        # unknown -> ON (the operator pressed it)
            nxt = dict(cur)
            nxt[name] = new
            err = self._packet(nxt)
            if err:
                return {"ok": False, "msg": err}
            for t in TOGGLES:
                self.toggles[t] = nxt[t]
            self._save()
            _log.info("user pressed %s -> %s; sent %s", name, new, nxt)
            return {"ok": True, "msg": f"{name} {'ON' if new else 'OFF'} sent"}

    def set_unknown_off(self) -> Dict[str, Any]:
        """Explicit operator action (with a confirm in the page): send the current
        command with every UNKNOWN toggle set to OFF. The way out of the all-unknown
        state of a fresh install, where any single press would have to guess."""
        with self.lock:
            cur = {t: r["value"] for t, r in self.resolved().items()}
            unknown = [t for t in TOGGLES if cur[t] is None]
            if not unknown:
                return {"ok": True, "msg": "Nothing unknown; nothing sent."}
            for t in unknown:
                cur[t] = 0
            err = self._packet(cur)
            if err:
                return {"ok": False, "msg": err}
            for t in TOGGLES:
                self.toggles[t] = cur[t]
            self._save()
            _log.info("user set unknown toggles %s to OFF; sent %s", unknown, cur)
            return {"ok": True, "msg": "Sent with " + ", ".join(unknown) + " = OFF"}

    PULSE_S = 0.2
    CALIBRATE_LOCK_S = 30.0

    def pulse(self, name: str) -> Dict[str, Any]:
        """Calibrate pressure / Reset SV: exactly two packets, the full last-sent
        state with the field = 1, then ~200 ms later the same state with it = 0.
        Calibrate locks for 30 s (repeat presses refused)."""
        if name not in ("calibrate", "reset"):
            return {"ok": False, "msg": "unknown action"}
        now = time.time()
        if name == "calibrate" and now < self.calibrate_busy_until:
            return {"ok": False, "msg": f"Calibrating pressure: {self.calibrate_busy_until - now:.0f} s left; not sent again."}
        with self.lock:
            cur = {t: r["value"] for t, r in self.resolved().items()}
            self.held[name] = 1
            err = self._packet(cur)
            if err:
                self.held[name] = 0
                return {"ok": False, "msg": err}
            for t in TOGGLES:
                self.toggles[t] = cur[t]
        if name == "calibrate":
            self.calibrate_busy_until = now + self.CALIBRATE_LOCK_S
        rec = {"sent_at": now, "model_saw": None}
        self.last_pulse[name] = rec

        def release():
            seen = False
            t_end = time.time() + self.PULSE_S
            echo_key = {"calibrate": "cmd_calibrate_pressure", "reset": "cmd_reset_sv"}[name]
            while time.time() < t_end:
                v = (self.readback() or {}).get(echo_key)
                if isinstance(v, (int, float)) and v >= 0.5:
                    seen = True
                time.sleep(0.02)
            with self.lock:
                self.held[name] = 0
                self._packet({t: r["value"] for t, r in self.resolved().items()})
                self._save()
            rec["model_saw"] = seen if any(k == echo_key for k in (self.readback() or {})) else None
            _log.info("user pulsed %s; model echo saw it: %s", name, rec["model_saw"])

        threading.Thread(target=release, daemon=True).start()
        return {"ok": True, "msg": ("Calibrating pressure (30 s)…" if name == "calibrate" else "Reset SV sent")}

    def momentary(self, name: str, value: int) -> Dict[str, Any]:
        with self.lock:
            if self.held[name] == int(value):
                return {"ok": True, "msg": ""}
            cur = {t: r["value"] for t, r in self.resolved().items()}
            prev = self.held[name]
            self.held[name] = int(value)
            err = self._packet(cur)
            if err:
                self.held[name] = prev if value else 0
                return {"ok": False, "msg": err}
            for t in TOGGLES:   # the inferred values are now what was sent
                self.toggles[t] = cur[t]
            self._save()
            _log.info("user %s %s; sent with toggles %s", "pressed" if value else "released", name, cur)
            return {"ok": True, "msg": ""}

    def set_param(self, field: str, value: Any, page_values: Dict[str, Any]) -> Dict[str, Any]:
        """Send all 5 parameters: last sent, with only *field* changed. A parameter
        this console never sent takes the value shown on the page."""
        try:
            v = float(value)
        except (TypeError, ValueError):
            return {"ok": False, "msg": f"{field}: not a number, not sent"}
        if not math.isfinite(v):
            return {"ok": False, "msg": f"{field}: not a number, not sent"}
        with self.lock:
            nxt = {}
            model = self.model_params()
            for p in PARAMS:
                if p == field:
                    nxt[p] = v
                elif model.get(p) is not None:       # what the model actually holds
                    nxt[p] = model[p]
                elif self.params[p] is not None:
                    nxt[p] = self.params[p]
                else:
                    try:
                        nxt[p] = float(page_values.get(p))
                    except (TypeError, ValueError):
                        return {"ok": False, "msg": f"{p} is unknown and empty on the page; not sent"}
            self.send_params(self.cfg, *[nxt[p] for p in PARAMS])
            self.params = nxt
            self.last_sent_at = time.time()
            self._save()
            _log.info("user changed %s -> %s; sent params %s", field, v, nxt)
            return {"ok": True, "msg": f"{field} = {v:g} sent"}
