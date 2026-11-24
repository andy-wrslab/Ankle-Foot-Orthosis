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
zero / calibrate_pressure are latched toggles (Andy 15:06 "they should all just be toggle"):
a press sends the field = 1 and it stays 1 in every packet until pressed again (both act on the
0 -> 1 edge in the model). reset_sv stays a ~200 ms 1 -> 0 pulse: the SV estimator resets on
every tick while it is 1.
UDP 5430 (the old 5-float parameter packet) is gone (Nov 24): nothing in the model read it.
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
LATCHED: tuple = ()     # Andy 16:15 "why is zero a switch now?": Zero / Calibrate FSR are pulses again
# 5433 echo of a latched field (zero has none: its lit state is the commanded one)
LATCH_ECHO = {"calibrate": "cmd_calibrate_pressure"}
# training stream (UDP 5433) columns = the commands actually latched in the model
MODEL_KEYS = {"motor": "cmd_motor", "assist": "cmd_assist", "k": "cmd_k"}

_log = logging.getLogger("afo.commands")


class CommandState:
    def __init__(self, cfg: Dict[str, Any], state_path: str,
                 send_control: Callable[..., None],
                 readback: Callable[[], Dict[str, Any]]) -> None:
        self.cfg = cfg
        # view-only console (config console.view_only): nothing is ever sent to the target
        self.view_only = bool((cfg.get("console") or {}).get("view_only", False))
        self.path = state_path
        self.send_control = send_control
        self.readback = readback
        self.lock = threading.Lock()
        self.toggles: Dict[str, Optional[int]] = {t: None for t in TOGGLES}
        self.held: Dict[str, int] = {m: 0 for m in MOMENTARY}
        self.loaded_from_disk = False
        self.last_sent_at: Optional[float] = None
        self.echo_expected: Optional[Callable[[], bool]] = None    # model has a 5433 echo (AFO_r1)
        self.guard: Optional[Callable[[str], Optional[str]]] = None   # e.g. session setup: block Motor/Assist
        # run 14: the 5433 echo stalled -> the device keeps its settings and nothing is sent
        self.frozen: Optional[Callable[[], Optional[str]]] = None
        self._mismatch_since: Dict[str, float] = {}
        self.calibrate_busy_until = 0.0      # no lock any more (Calibrate FSR is a toggle); kept for the view
        self.last_pulse: Dict[str, Dict[str, Any]] = {}
        self.latch_sent_at: Dict[str, float] = {m: 0.0 for m in LATCHED}
        self._load()

    # ---------------------------------------------------------- persistence
    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fp:
                d = json.load(fp)
            for t in TOGGLES:
                if d.get("toggles", {}).get(t) in (0, 1):
                    self.toggles[t] = int(d["toggles"][t])
            for m in LATCHED:
                if d.get("held", {}).get(m) in (0, 1):
                    self.held[m] = int(d["held"][m])
            self.last_sent_at = d.get("sent_at")
            self.loaded_from_disk = True
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump({"toggles": self.toggles, "sent_at": self.last_sent_at,
                           "held": {m: self.held[m] for m in LATCHED}}, fp)
            os.replace(tmp, self.path)
        except OSError as exc:
            _log.warning("could not save last command: %s", exc)

    # ---------------------------------------------------------- state
    LATCH_ADOPT_S = 1.0

    def latched(self) -> Dict[str, int]:
        """Zero / Calibrate FSR toggle state: the last one sent, or, once the echo has had time to
        show a press (> 1 s), what the model echoes (cmd_calibrate_pressure, col 8), adopted
        without sending anything (reconnect / refresh / restart)."""
        rb = self.readback() or {}
        now = time.time()
        for m in LATCHED:
            v = rb.get(LATCH_ECHO.get(m, ""))
            if isinstance(v, (int, float)) and math.isfinite(v) and now - self.latch_sent_at[m] > self.LATCH_ADOPT_S:
                self.held[m] = 1 if v >= 0.5 else 0
        return {m: self.held[m] for m in LATCHED}

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
        device_only = bool(self.echo_expected()) if self.echo_expected else False
        for t in TOGGLES:
            mv = rb.get(MODEL_KEYS[t])
            if isinstance(mv, (int, float)) and math.isfinite(mv):
                out[t] = {"value": 1 if mv >= 0.5 else 0, "source": "model"}
                continue
            if device_only:
                # a model with a console echo and no echo now: unknown / frozen, never the
                # remembered last command (last_command.json is a write log only)
                out[t] = {"value": None, "source": None}
                continue
            v = self.toggles[t]
            src = "sent" if v is not None else None
            if v is None:
                v = self._inferred(t)
                src = "bus" if v is not None else None
            out[t] = {"value": v, "source": src}
        return out

    def mismatches(self) -> list:
        """Nothing 'differs' any more (Andy Nov 23 16:15): Motor / Assist / K show the device echo,
        and the old 5430 parameters are gone (Nov 24). Kept for the view's shape."""
        return []

    def view(self) -> Dict[str, Any]:
        with self.lock:
            return {"toggles": self.resolved(),
                    "calibrate_busy_s": 0.0, "latched": self.latched(),
                    "last_pulse": dict(self.last_pulse),
                    "mismatch": self.mismatches(), "held": dict(self.held),
                    "last_sent_at": self.last_sent_at, "loaded_from_disk": self.loaded_from_disk}

    VIEW_ONLY_MSG = "View-only console: commands are not sent from this app."

    def _packet(self, toggles: Dict[str, Optional[int]]) -> Optional[str]:
        if self.view_only:
            return self.VIEW_ONLY_MSG
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
        fz = self.frozen() if self.frozen else None
        if fz:
            return {"ok": False, "msg": fz}
        with self.lock:
            cur = {t: r["value"] for t, r in self.resolved().items()}
        new = 0 if cur[name] == 1 else 1            # unknown -> ON (the operator pressed it)
        # the side guard blocks switching Motor/Assist ON; switching OFF always works
        if self.guard is not None and name in ("motor", "assist") and new == 1:
            block = self.guard(name)
            if block:
                return {"ok": False, "msg": block}
        with self.lock:
            cur = {t: r["value"] for t, r in self.resolved().items()}
            new = 0 if cur[name] == 1 else 1
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
        fz = self.frozen() if self.frozen else None
        if fz:
            return {"ok": False, "msg": fz}
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
        """Dock one-shot buttons Zero (field 0), Calibrate FSR (field 4), Reset SV (field 5):
        exactly two packets, the echoed motor / assist / k with the field = 1, then ~200 ms later
        the same with it = 0. Zero and Calibrate FSR act on the rising edge in the model (run 15
        code: RISING_ZERO_CROSSING / 'ok && !prevTrig' / trig_edge), so one pulse fires once.
        Zero only with Assist off."""
        fz = self.frozen() if self.frozen else None
        if fz:
            return {"ok": False, "msg": fz}
        if name not in ("zero", "calibrate", "reset"):
            return {"ok": False, "msg": "unknown action"}
        if self.held[name]:
            return {"ok": False, "msg": "already sending"}
        now = time.time()
        with self.lock:
            cur = {t: r["value"] for t, r in self.resolved().items()}
            if name == "zero" and cur["assist"] != 0:
                return {"ok": False, "msg": "Zero: switch Assist off first (hold the ankle still in neutral)"}
            self.held[name] = 1
            err = self._packet(cur)
            if err:
                self.held[name] = 0
                return {"ok": False, "msg": err}
            for t in TOGGLES:
                self.toggles[t] = cur[t]
        rec = {"sent_at": now, "model_saw": None}
        self.last_pulse[name] = rec

        def release():
            seen = False
            t_end = time.time() + self.PULSE_S
            echo_key = {"reset": "cmd_reset_sv", "calibrate": "cmd_calibrate_pressure", "zero": "cmd_zero"}[name]
            samples, mx = set(), {"cmd_calibrate_pressure": None, "cmd_reset_sv": None}

            def look():
                nonlocal seen
                rb = self.readback() or {}
                tm = rb.get("t_model")
                if isinstance(tm, (int, float)):
                    samples.add(tm)
                for k in mx:
                    v = rb.get(k)
                    if isinstance(v, (int, float)) and math.isfinite(v):
                        mx[k] = v if mx[k] is None else max(mx[k], v)
                v = rb.get(echo_key)
                if isinstance(v, (int, float)) and v >= 0.5:
                    seen = True
            while time.time() < t_end:
                look()
                time.sleep(0.02)
            with self.lock:
                self.held[name] = 0
                self._packet({t: r["value"] for t, r in self.resolved().items()})
                self._save()
            t0 = time.time()
            for _ in range(5):        # the 1 can still be on its way back: look ~100 ms past the 0
                time.sleep(0.02)
                look()
            rec["model_saw"] = seen if any(k == echo_key for k in (self.readback() or {})) else None
            _log.info("user pulsed %s; model echo saw it: %s; 1 sent %.3f, 0 sent %.3f (%.0f ms); "
                      "%d echo samples; max cmd_calibrate_pressure %s, max cmd_reset_sv %s",
                      name, rec["model_saw"], now, t0, (t0 - now) * 1000.0, len(samples),
                      mx["cmd_calibrate_pressure"], mx["cmd_reset_sv"])

        threading.Thread(target=release, daemon=True).start()
        return {"ok": True, "msg": ""}

    def press_latch(self, name: str) -> Dict[str, Any]:
        """Zero / Calibrate FSR toggle: one packet, the last-sent state with only this field
        flipped. Zero ON needs Assist off; OFF always works. Nothing else is ever sent."""
        fz = self.frozen() if self.frozen else None
        if fz:
            return {"ok": False, "msg": fz}
        with self.lock:
            new = 0 if self.latched()[name] == 1 else 1
            cur = {t: r["value"] for t, r in self.resolved().items()}
            if name == "zero" and new == 1 and cur["assist"] != 0:
                return {"ok": False, "msg": "Zero: switch Assist off first (hold the ankle still in neutral)"}
            prev, prev_at = self.held[name], self.latch_sent_at[name]
            self.held[name], self.latch_sent_at[name] = new, time.time()
            err = self._packet(cur)
            if err:
                self.held[name], self.latch_sent_at[name] = prev, prev_at
                return {"ok": False, "msg": err}
            for t in TOGGLES:
                self.toggles[t] = cur[t]
            self._save()
        _log.info("user pressed %s -> %s; sent with toggles %s", name, new, cur)
        return {"ok": True, "msg": "", "state": new}

    def momentary(self, name: str, value: int) -> Dict[str, Any]:
        fz = self.frozen() if self.frozen else None
        if fz:
            return {"ok": False, "msg": fz}
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

