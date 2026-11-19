"""Session setup: per-participant model parameters (S-ID, foot side, weight, mode, K %).

* The participant is identified by an S-ID (S + number, e.g. S47); names are
  never used in files.
* Values entered on Home are sent to the target when committed (setparam) and
  read back (getparam, or the training UDP echo when present); the page shows
  them as confirmed / pending / failed. Not connected -> pending, sent on Connect.
* Every Start reloads the app (compiled defaults), so after a successful Start
  the entered values are re-applied automatically (logged). The foot SIDE is
  safety-critical: set only after an explicit confirmation (S-ID typed + LEFT/
  RIGHT) and re-applied after Start only if confirmed in this app session for
  the same S-ID; otherwise the page asks again.
* Motor/Assist presses are blocked while there is no confirmed side for the
  S-ID, or while the side read back from the target differs from it.
* Changing the assistance mode, or K % by more than 2, while Motor is ON needs
  a confirmation.
* Writes to the target are disabled until `session.target_writes_enabled` is
  true in config.yaml (target access hold, 2026-11-19).
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, Optional

_log = logging.getLogger("afo.session")

# key, label, kind, limits, training-UDP readback column
SPECS = [
    {"key": "side", "label": "Foot side", "kind": "side", "udp": "side"},
    {"key": "weight", "label": "Body weight (kg)", "kind": "number", "min": 20, "max": 200, "udp": "weight_kg"},
    {"key": "mode", "label": "Assistance mode", "kind": "mode", "udp": "assist_mode"},
    {"key": "k_percent", "label": "Fixed K (%)", "kind": "number", "min": 0, "max": 10, "udp": "fixed_k_pct"},
    {"key": "sv_target_min", "label": "SV target min (m/s)", "kind": "number", "min": 0, "max": 3},
    {"key": "sv_target_max", "label": "SV target max (m/s)", "kind": "number", "min": 0, "max": 3},
]
DEFAULT_MODELS = {
    "AFO": {"side": "AFO/Left 0/Right 1|Value", "weight": "AFO/weight|Gain", "mode": "AFO/Constant4|Value",
            "k_percent": "AFO/Constant10|Value", "sv_target_min": "AFO/SV_Target_min|Value",
            "sv_target_max": "AFO/SV_Target_max|Value"},
    "AFO_r1": {"side": "AFO_r1/Left 0/Right 1|Value", "weight": "AFO_r1/weight|Value",
               "mode": "AFO_r1/Constant4|Value", "k_percent": "AFO_r1/Constant10|Value",
               "sv_target_min": "AFO_r1/SV_Target_min|Value", "sv_target_max": "AFO_r1/SV_Target_max|Value"},
}
MODES = {1: "RL", 3: "Fixed K"}     # Multiport Switch selector (2 = ILC is not offered)
SIDE_NAMES = {0: "LEFT", 1: "RIGHT"}
SIDE_WARNING = ("Side mismatch: measured torque and ankle angle are sign-inverted; "
                "the controller would push the wrong way.")
SID_RE = re.compile(r"^S\d{1,4}$")


class SessionSetup:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        scfg = ctx.cfg.get("session") or {}
        self.models = scfg.get("models") or DEFAULT_MODELS
        self.writes_enabled = bool(scfg.get("target_writes_enabled", False))
        self.path = os.path.join(ctx.app_dir, "data", "session_profiles.json")
        self.lock = threading.Lock()
        self.sid: Optional[str] = None
        self.values: Dict[str, Any] = {}
        self.status: Dict[str, Dict[str, Any]] = {}
        self.readback: Dict[str, Any] = {}
        self.readback_src: Dict[str, str] = {}
        self.readback_at: Optional[float] = None
        self.side_confirmed: Optional[Dict[str, Any]] = None
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self.events: list = []        # start/stop times of this app session (for exports)
        self._load()

    # ---------------------------------------------------------- storage / log
    def _load(self) -> None:
        try:
            d = json.load(open(self.path, encoding="utf-8"))
            self.profiles = d.get("profiles", {})
            self.sid = d.get("current")
            self.values = dict(self.profiles.get(self.sid, {})) if self.sid else {}
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if self.sid:
            self.profiles[self.sid] = dict(self.values)
        tmp = self.path + ".tmp"
        json.dump({"profiles": self.profiles, "current": self.sid}, open(tmp, "w", encoding="utf-8"), indent=1)
        os.replace(tmp, self.path)

    def audit(self, action: str, detail: str) -> None:
        p = os.path.join(self.ctx.cfg["paths"]["log_dir"], "session_setup.csv")
        new = not os.path.exists(p)
        with open(p, "a", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            if new:
                w.writerow(["time", "sid", "action", "detail"])
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), self.sid, action, detail])

    def spec(self, key):
        return next(s for s in SPECS if s["key"] == key)

    def model(self) -> str:
        app = (self.ctx.runctl.status or {}).get("app") or "AFO"
        return app if app in self.models else "AFO"

    def target_path(self, key):
        p = self.models[self.model()].get(key)
        return p.split("|") if p else None

    # ---------------------------------------------------------- user input
    def set_sid(self, sid: str) -> str:
        sid = (sid or "").strip().upper()
        if not SID_RE.match(sid):
            return "S-ID must be S followed by a number, e.g. S47."
        with self.lock:
            if sid != self.sid:
                self.sid = sid
                self.values = dict(self.profiles.get(sid, {}))
                self.side_confirmed = None     # a new participant always needs the side confirmed
                self.status = {}
                self._save()
                self.audit("participant", sid)
        return f"{sid}" + (" (profile loaded; confirm the foot side)" if self.profiles.get(sid) else " (new profile)")

    def check_change(self, key: str, value: Any) -> Optional[str]:
        """Text for a confirmation dialog if this change needs one (Motor ON), else None."""
        motor_on = (self.ctx.commands.view()["toggles"]["motor"]["value"] == 1)
        if not motor_on:
            return None
        if key == "mode" and value != self.values.get("mode"):
            return (f"Motor is ON. Switch the assistance mode to {MODES.get(int(value), value)}? "
                    "It takes effect at the next heel strike.")
        if key == "k_percent":
            old = self.values.get("k_percent")
            try:
                if old is not None and abs(float(value) - float(old)) > 2:
                    return f"Motor is ON. Change fixed K from {old:g}% to {float(value):g}%?"
            except (TypeError, ValueError):
                pass
        return None

    def enter_value(self, key: str, value: Any) -> str:
        """A committed edit of a number or mode field (not the side)."""
        if not self.sid:
            return "Set the S-ID first."
        sp = self.spec(key)
        try:
            v = float(value)
        except (TypeError, ValueError):
            return f"{sp['label']}: not a number"
        if key == "mode" and int(v) not in MODES:
            return "Mode must be RL or Fixed K."
        if sp["kind"] == "number" and not (sp.get("min", -1e12) <= v <= sp.get("max", 1e12)):
            return f"{sp['label']}: {v:g} is outside {sp.get('min')}..{sp.get('max')}"
        with self.lock:
            self.values[key] = v
            self._save()
        self.audit("enter", f"{key}={v:g}")
        return self._send(key, v)

    def confirm_side(self, side: str, typed_sid: str) -> str:
        side = (side or "").upper()
        if side not in ("LEFT", "RIGHT"):
            return "Pick LEFT or RIGHT."
        if not self.sid or (typed_sid or "").strip().upper() != self.sid:
            return f"Type the S-ID exactly ({self.sid or 'set the S-ID first'})."
        v = 0 if side == "LEFT" else 1
        with self.lock:
            self.values["side"] = v
            self.side_confirmed = {"sid": self.sid, "side": v, "at": time.time()}
            self._save()
        self.audit("side confirmed", side)
        return self._send("side", v)

    # ---------------------------------------------------------- target I/O
    def _connected(self) -> bool:
        return bool((self.ctx.runctl.status or {}).get("connected"))

    def _send(self, key: str, value: float) -> str:
        sp = self.spec(key)
        tp = self.target_path(key)
        if tp is None:
            self.status[key] = {"state": "error", "msg": f"no block for {key} in model {self.model()}", "at": time.time()}
            return self.status[key]["msg"]
        if not self.writes_enabled:
            self.status[key] = {"state": "pending", "msg": "saved, not sent: target writes are disabled (access hold)",
                                "at": time.time()}
            return f"{sp['label']} saved; not sent (target writes disabled)"
        if not self._connected():
            self.status[key] = {"state": "pending", "msg": "pending: sent on Connect", "at": time.time()}
            return f"{sp['label']} saved; will be sent on Connect"
        blk, prm = tp

        def run(job):
            out = json.loads(self.ctx.matlab.call("afo_session", "set", blk, prm, float(value), timeout=30))
            job.add(json.dumps(out))
            ok = bool(out.get("ok"))
            self.status[key] = {"state": "confirmed" if ok else "error",
                                "msg": "" if ok else (out.get("err") or f"read back {out.get('readback')}"),
                                "at": time.time()}
            if ok:
                self.readback[key] = out.get("readback")
                self.readback_src[key] = "getparam"
                self.readback_at = time.time()
            self.audit("set", f"{key}={value:g} ({blk}|{prm}) -> {json.dumps(out)[:200]}")
            return out
        self.status[key] = {"state": "sending", "msg": "", "at": time.time()}
        self.ctx.jobs.start("session", f"set {key}", run)
        return f"{sp['label']}: sending…"

    def refresh_readback(self) -> None:
        """Training UDP echo first (no MATLAB); getparam for the rest every ~5 s while connected."""
        echo = self.ctx.training.latest() if hasattr(self.ctx, "training") else {}
        for sp in SPECS:
            col = sp.get("udp")
            if col and echo.get(col) is not None:
                self.readback[sp["key"]] = echo[col]
                self.readback_src[sp["key"]] = "udp"
                self.readback_at = time.time()
        if not self._connected() or self.ctx.jobs.running("rc") or self.ctx.jobs.running("session"):
            return
        need = [sp["key"] for sp in SPECS if self.readback_src.get(sp["key"]) != "udp" or not echo]
        paths = {k: "|".join(self.target_path(k)) for k in need if self.target_path(k)}
        if not paths:
            return

        def run(job):
            out = json.loads(self.ctx.matlab.call("afo_session", "read", list(paths.values()), timeout=20))
            if out.get("ok"):
                vals = out.get("values") or []
                if isinstance(vals, dict):
                    vals = [vals]
                for k, pth in paths.items():
                    hit = next((v for v in vals if v.get("path") == pth), None)
                    if hit and hit.get("value") not in (None, []):
                        self.readback[k] = hit["value"]
                        self.readback_src[k] = "getparam"
                self.readback_at = time.time()
            return out
        self.ctx.jobs.start("session", "read session params", run)

    def after_connect_or_start(self, event: str) -> None:
        """After Connect: send pending values. After Start: re-apply everything entered."""
        if event == "start":
            self.events.append({"start": time.strftime("%Y-%m-%d %H:%M:%S")})
        order = ["side"] + [sp["key"] for sp in SPECS if sp["key"] != "side"]
        for k in order:
            if self.values.get(k) is None:
                continue
            if k == "side":
                c = self.side_confirmed
                if not c or c["sid"] != self.sid or c["side"] != self.values.get("side"):
                    self.status["side"] = {"state": "needs-confirm", "msg": "confirm the foot side", "at": time.time()}
                    self.audit(f"side not re-applied after {event}", "not confirmed in this app session for this S-ID")
                    continue
            if event == "start" or self.status.get(k, {}).get("state") == "pending":
                self.audit(f"re-apply after {event}", f"{k}={self.values[k]}")
                self._send(k, float(self.values[k]))
                t_end = time.time() + 40
                while self.ctx.jobs.running("session") and time.time() < t_end:
                    time.sleep(0.2)

    def note_stop(self) -> None:
        self.events.append({"stop": time.strftime("%Y-%m-%d %H:%M:%S")})

    # ---------------------------------------------------------- safety
    def side_problem(self) -> Optional[str]:
        if not self.sid:
            return "No participant: set the S-ID and confirm the foot side on Home first."
        want = self.values.get("side")
        c = self.side_confirmed
        if want is None or not c or c["sid"] != self.sid:
            return f"Foot side not confirmed for {self.sid}: confirm it on Home first."
        rb = self.readback.get("side")
        if rb is None:
            # blocked until the target's side has been read back and matches
            return (f"Foot side not verified on the target yet (profile {SIDE_NAMES[int(want)]}); "
                    "waiting for the side readback.")
        try:
            rbi = int(round(float(rb)))
        except (TypeError, ValueError):
            rbi = None
        if rbi == -1:
            # AFO_r1 compiles the side as -1 (unset): the drive cannot enable until it is set
            return "Side not set: motor disabled. Confirm the foot side on Home."
        if rbi != int(want):
            return SIDE_WARNING + f" Target: {SIDE_NAMES.get(rbi, rb)}, profile: {SIDE_NAMES[int(want)]}."
        return None

    def side_chip(self) -> Dict[str, str]:
        """Low-prominence side chip: text + state (ok / unset / warn / bad)."""
        rb = self.readback.get("side")
        want = self.values.get("side")
        try:
            rbi = None if rb is None else int(round(float(rb)))
        except (TypeError, ValueError):
            rbi = None
        if rbi == -1:
            return {"text": "Side not set: motor disabled", "state": "unset"}
        if self.side_problem() is None:
            return {"text": f"Side: {SIDE_NAMES[int(want)]}", "state": "ok"}
        if rbi in (0, 1) and want is not None and rbi != int(want):
            return {"text": f"Side mismatch ({SIDE_NAMES[rbi]} on target)", "state": "bad"}
        return {"text": "Side: confirm" if want is None or not self.side_confirmed else
                f"Side: {SIDE_NAMES[int(want)]} (not verified)", "state": "warn"}

    def guard(self, name: str) -> Optional[str]:
        p = self.side_problem()
        if p:
            self.audit("blocked", f"{name}: {p}")
        return p

    def settings_record(self) -> Dict[str, Any]:
        """What gets saved next to an exported trial."""
        return {"sid": self.sid, "values": dict(self.values),
                "side": SIDE_NAMES.get(int(self.values["side"])) if self.values.get("side") is not None else None,
                "mode": MODES.get(int(self.values["mode"])) if self.values.get("mode") is not None else None,
                "readback": dict(self.readback), "readback_source": dict(self.readback_src),
                "side_confirmed": self.side_confirmed, "model": self.model(),
                "target": dict(self.ctx.runctl.status or {}), "run_events": list(self.events),
                "commands": self.ctx.commands.view()}

    def view(self) -> Dict[str, Any]:
        rows = []
        for sp in SPECS:
            k = sp["key"]
            rows.append({"key": k, "label": sp["label"], "value": self.values.get(k),
                         "readback": self.readback.get(k), "readback_source": self.readback_src.get(k),
                         "status": self.status.get(k, {})})
        return {"sid": self.sid, "rows": rows, "side_problem": self.side_problem(), "side_chip": self.side_chip(),
                "side_confirmed": self.side_confirmed, "readback_at": self.readback_at, "model": self.model(),
                "writes_enabled": self.writes_enabled, "profiles": sorted(self.profiles)}
