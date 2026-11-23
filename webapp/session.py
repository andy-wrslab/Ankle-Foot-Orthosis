"""Session setup: per-participant model parameters (S-ID, foot side, weight, mode, K %).

* The participant is identified by an S-ID (S + number, e.g. S47); names are
  never used in files.
* Values entered in the top bar / Advanced popover are sent to the target when committed (setparam).
  Confirmation comes ONLY from the model: its console packet on UDP 5433
  (fresh: side, weight, mode, K %, commands) or getparam
  (right after each setparam, then every ~5 s while connected; all values
  until AFO_r1 is loaded). target_table() lists entered vs target values.
  Not connected -> pending, sent on Connect.
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
from typing import Any, Dict, List, Optional

import model_profile as mp

_log = logging.getLogger("afo.session")

# key, label, kind, limits, console-UDP (5433) echo column, model block|param, build default.
# "adv" = Advanced popover (confirmed by getparam only). Block names from AFO.slx
# (all top-level Constants/Gains; the same names exist in AFO_r1, checked 2026-11-19).
# "models": only in these model profiles. A '/' in a block name is escaped in the path.
SPECS = [
    {"key": "side", "label": "Foot side", "kind": "side", "udp": "side", "block": "Left 0/Right 1|Value", "default": 0},
    {"key": "weight", "label": "Body mass", "kind": "number", "min": 20, "max": 200, "udp": "weight_kg",
     "block": "weight|Gain", "block_r1": "weight|Value", "default": 55, "unit": "kg"},
    # AFO_r1: BIF_mass_kg follows Body mass (Andy, Nov 23: "only use body mass"); no field of its own
    {"key": "bif_mass", "label": "Mass (Bi-LSTM)", "kind": "number", "min": mp.BIF_MASS_MIN,
     "min_exclusive": True, "max": 250, "block": "BIF_mass_kg|Value", "models": ["AFO_r1"], "default": 0,
     "unit": "kg", "follows": "weight", "hint": "= body mass; 20 kg or less = Bi-LSTM gives no assist"},
    {"key": "mode", "label": "Assistance mode", "kind": "mode", "udp": "assist_mode", "block": "Constant4|Value",
     "default": 3},
    {"key": "k_percent", "label": "K", "kind": "number", "min": 0, "max": 10, "udp": "fixed_k_pct",
     "block": "Constant10|Value", "default": 5, "unit": "%"},
    # Advanced: Walking-speed target
    {"key": "sv_target_min", "label": "Min target speed", "kind": "number", "min": 0.1, "max": 3, "adv": True,
     "block": "SV_Target_min|Value", "default": 0.8, "unit": "m/s"},
    {"key": "sv_target_max", "label": "Max target speed", "kind": "number", "min": 0.1, "max": 3, "adv": True,
     "block": "SV_Target_max|Value", "default": 1.5, "unit": "m/s"},
    {"key": "target_step_up", "label": "Target step up", "kind": "number", "min": 0, "max": 0.5, "adv": True,
     "block": "target_speed3|Value", "default": 0.04, "unit": "m/s"},
    {"key": "target_step_down", "label": "Target step down", "kind": "number", "min": 0, "max": 0.5, "adv": True,
     "block": "target_speed4|Value", "default": 0.08, "unit": "m/s"},
    # Advanced: When the target steps
    {"key": "window_up", "label": "Step-up window", "kind": "number", "min": 1, "max": 200, "adv": True,
     "block": "window_length|Value", "default": 20, "unit": "strides"},
    {"key": "window_down", "label": "Step-down window", "kind": "number", "min": 1, "max": 200, "adv": True,
     "block": "window_length1|Value", "default": 10, "unit": "strides"},
    {"key": "assist_threshold", "label": "High-assist level", "kind": "number", "min": 0, "max": 10, "adv": True,
     "block": "assist_threshold|Value", "default": 9, "unit": "of 10"},
    {"key": "min_cycles", "label": "High-assist strides", "kind": "number", "min": 1, "max": 200, "adv": True,
     "block": "min_cycles|Value", "default": 10, "unit": "strides"},
    # Advanced: Torque controller
    {"key": "p_gain", "label": "Torque P gain", "kind": "number", "min": 0, "max": 10, "adv": True,
     "block": "P|Value", "default": 0.6},
    {"key": "i_gain", "label": "Torque I gain", "kind": "number", "min": 0, "max": 10, "adv": True,
     "block": "I|Value", "default": 0.8},
    {"key": "spring", "label": "Spring stiffness", "kind": "number", "adv": True, "readonly": True,
     "block": "Spring Constant Nm/deg|Value", "default": -0.7651, "unit": "N·m/deg"},
    # Advanced: Safety
    {"key": "threshold_pressure", "label": "Standing-still cutoff", "kind": "number", "min": 0, "max": 5000,
     "adv": True, "block": "threshold_pressure|Value", "default": 200, "unit": "counts"},
]


def spec_in(sp, model: str) -> bool:
    return not sp.get("models") or model in sp["models"]


def _model_paths(model: str) -> Dict[str, str]:
    out = {}
    for sp in SPECS:
        if not spec_in(sp, model):
            continue
        blk = sp.get("block_r1") if model == "AFO_r1" and sp.get("block_r1") else sp["block"]
        name, prm = blk.rsplit("|", 1)
        out[sp["key"]] = f"{mp.block_path(model, name)}|{prm}"
    return out


DEFAULT_MODELS = {"AFO": _model_paths("AFO"), "AFO_r1": _model_paths("AFO_r1")}
MODES = {1: "RL", 3: "Fixed K"}     # Multiport Switch selector (2 = ILC is not offered)
SIDE_NAMES = {0: "LEFT", 1: "RIGHT"}
SIDE_WARNING = ("Side mismatch: measured torque and ankle angle are sign-inverted; "
                "the controller would push the wrong way.")
SID_RE = re.compile(r"^S\d{1,4}$")
ECHO_MODEL = "AFO_r1"        # the model that sends the training UDP echo
ECHO_MAX_AGE_S = 0.5      # console packet every 10 ms; older than this -> rows grey
SHORT = {"side": "Foot side", "weight": "Mass", "mode": "Mode", "k_percent": "K", "sv_target_min": "SV target",
         "sv_target_max": "SV target", "bif_mass": "Mass (Bi-LSTM)", "motor": "Motor command", "assist": "Assist command", "k": "K command"}


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def values_match(key: str, entered, target) -> Optional[bool]:
    a, b = _num(entered), _num(target)
    if a is None or b is None:
        return None
    if key in ("side", "mode", "motor", "assist", "k"):
        return int(round(a)) == int(round(b))
    return abs(a - b) <= 1e-3 * max(1.0, abs(a))     # float32 echo of a double


class SessionSetup:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        scfg = ctx.cfg.get("session") or {}
        self.models = scfg.get("models") or DEFAULT_MODELS
        self.writes_enabled = (bool(scfg.get("target_writes_enabled", False))
                               and not bool((ctx.cfg.get("console") or {}).get("view_only", False)))
        self.path = os.path.join(ctx.app_dir, "data", "session_profiles.json")
        self.lock = threading.Lock()
        self.sid: Optional[str] = None
        self.values: Dict[str, Any] = {}
        self.status: Dict[str, Dict[str, Any]] = {}
        self.readback: Dict[str, Any] = {}
        self.readback_src: Dict[str, str] = {}
        self.readback_at: Optional[float] = None
        self.readback_t: Dict[str, float] = {}
        self.echo_port: Optional[int] = None
        self.side_confirmed: Optional[Dict[str, Any]] = None
        self.after_start = False      # SPEC: every Start ends in the Confirm state
        self.started_at: Optional[float] = None     # last Start in this app session (after-Start checklist)
        # set when setparam/getparam says "No application is loaded" while the target runs:
        # the app was loaded by another MATLAB session, so this page cannot tune it
        self.app_elsewhere: Optional[float] = None
        self.configured_model = mp.configured_model(ctx.cfg)
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
        """Loaded app when it is a known profile, else config target.model, else AFO."""
        app = (self.ctx.runctl.status or {}).get("app")
        if app in self.models:
            return app
        cm = self.configured_model
        return cm if cm in self.models else mp.DEFAULT_MODEL

    def profile(self) -> Dict[str, Any]:
        return mp.PROFILES.get(self.model(), mp.PROFILES[mp.DEFAULT_MODEL])

    def specs(self) -> List[Dict[str, Any]]:
        """The settings of the current model profile."""
        m = self.model()
        return [sp for sp in SPECS if spec_in(sp, m)]

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
        if sp.get("readonly"):
            return f"{sp['label']} is read-only here."
        if not spec_in(sp, self.model()):
            return f"{sp['label']}: not in model {self.model()}"
        if sp.get("min_exclusive") and v <= sp["min"]:
            return f"{sp['label']}: must be more than {sp['min']:g} {sp.get('unit', '')}".rstrip()
        if sp["kind"] == "number" and not (sp.get("min", -1e12) <= v <= sp.get("max", 1e12)):
            return f"{sp['label']}: {v:g} is outside {sp.get('min')}..{sp.get('max')}"
        if key == "weight" and self.profile().get("bif") and v <= mp.BIF_MASS_MIN:
            return f"Body mass must be more than {mp.BIF_MASS_MIN:g} kg (the Bi-LSTM gives no assist at or below it)."
        # SV target band: 0.8-1.5 m/s for healthy participants, min 0.5 for patients (Andy 12:53)
        lo = v if key == "sv_target_min" else self.values.get("sv_target_min")
        hi = v if key == "sv_target_max" else self.values.get("sv_target_max")
        if key in ("sv_target_min", "sv_target_max") and lo is not None and hi is not None and float(lo) >= float(hi):
            return f"Min target speed ({float(lo):g}) must be below max target speed ({float(hi):g})."
        follow = key == "weight" and self.profile().get("bif")
        with self.lock:
            self.values[key] = v
            if follow:
                self.values["bif_mass"] = v          # BIF_mass_kg = body mass
            self._save()
        self.audit("enter", f"{key}={v:g}")
        msg = self._send(key, v)
        if follow:
            self._send_after("bif_mass", v)
        return msg

    def _send_after(self, key: str, value: float) -> None:
        """Send *key* once the current session job (one MATLAB engine) has finished."""
        def later():
            t_end = time.time() + 40
            time.sleep(0.2)
            while self.ctx.jobs.running("session") and time.time() < t_end:
                time.sleep(0.2)
            self._send(key, value)
        threading.Thread(target=later, name=f"send-{key}", daemon=True).start()

    def confirm_side(self, side: str, typed_sid: str) -> str:
        side = (side or "").upper()
        if side not in ("LEFT", "RIGHT"):
            return "Pick LEFT or RIGHT."
        if not self.sid:
            return "Set the participant ID first."
        if typed_sid and typed_sid.strip().upper() != self.sid:
            return f"The ID does not match ({self.sid})."
        v = 0 if side == "LEFT" else 1
        with self.lock:
            self.values["side"] = v
            self.side_confirmed = {"sid": self.sid, "side": v, "at": time.time()}
            self.after_start = False
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
        rc = self.ctx.runctl.status or {}
        if not rc.get("running"):
            # app stopped (unloaded, or still loaded with ReloadOnStop): Start resets every
            # tunable to the build value, so the value is held and sent right after Start
            self.status[key] = {"state": "pending", "msg": "pending: sent after Start", "at": time.time()}
            return f"{sp['label']} saved; will be sent right after Start"
        blk, prm = tp

        def run(job):
            out = json.loads(self.ctx.matlab.call("afo_session", "set", blk, prm, float(value), timeout=30))
            job.add(json.dumps(out))
            ok = bool(out.get("ok"))
            msg = "" if ok else self._note_error(key, out.get("err") or f"read back {out.get('readback')}")
            self.status[key] = {"state": "confirmed" if ok else "error", "msg": msg, "at": time.time()}
            if ok:
                self._put(key, out.get("readback"), "getparam")
            self.audit("set", f"{key}={value:g} ({blk}|{prm}) -> {json.dumps(out)[:200]}")
            return out
        self.status[key] = {"state": "sending", "msg": "", "at": time.time()}
        self.ctx.jobs.start("session", f"set {key}", run)
        return f"{sp['label']}: sending…"

    ELSEWHERE_MSG = "App started elsewhere: press Stop then Start to take control"

    def clear_readback(self) -> None:
        """Forget every read-back value (Connect, Disconnect, Start): only fresh values count."""
        with self.lock:
            self.readback.clear()
            self.readback_src.clear()
            self.readback_t.clear()
            self.readback_at = None
            self.app_elsewhere = None

    def _note_error(self, key: str, err: str) -> str:
        """Map a setparam/getparam error; 'No application is loaded' while running -> app elsewhere."""
        if "No application is loaded" in (err or "") and (self.ctx.runctl.status or {}).get("running"):
            self.app_elsewhere = time.time()
            return self.ELSEWHERE_MSG
        return err

    def _put(self, key: str, value, src: str) -> None:
        self.readback[key] = value
        self.readback_src[key] = src
        self.readback_t[key] = self.readback_at = time.time()

    def echo(self) -> Dict[str, Any]:
        """The model's own echo of its settings: the console packet on UDP 5433
        while fresh (its validated layout proves the source), else {} and
        getparam is used. Adds "_port" = 5433."""
        if not hasattr(self.ctx, "training"):
            return {}
        tr = self.ctx.training.latest(max_age_s=ECHO_MAX_AGE_S) or {}
        return dict(tr, _port=5433) if tr else {}

    def refresh_readback(self) -> None:
        """Echo first (no MATLAB); getparam for every value without a fresh echo."""
        echo = self.echo()
        self.echo_port = echo.get("_port")
        for sp in self.specs():
            k = sp["key"]
            col = sp.get("udp")
            if col and echo.get(col) is not None:
                self._put(k, echo[col], "echo")
            elif self.readback_src.get(k) == "echo":
                # echo gone (stream stopped / other model): drop it, getparam takes over
                self.readback.pop(k, None)
                self.readback_src.pop(k, None)
        if not self._connected() or self.ctx.jobs.running("rc") or self.ctx.jobs.running("session"):
            return
        need = [sp["key"] for sp in self.specs() if self.readback_src.get(sp["key"]) != "echo"]
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
                    if hit and hit.get("value") not in (None, []) and not hit.get("err"):
                        self._put(k, hit["value"], "getparam")
                    elif hit and self.readback_src.get(k) != "echo":
                        # the getparam failed: drop the old value instead of showing it as current
                        self.readback.pop(k, None)
                        self.readback_src.pop(k, None)
                        self.readback_t.pop(k, None)
                        if hit.get("err"):
                            m = self._note_error(k, hit["err"])
                            if m == self.ELSEWHERE_MSG:
                                self.status[k] = {"state": "error", "msg": m, "at": time.time()}
            return out
        self.ctx.jobs.start("session", "read session params", run)

    def target_table(self) -> list:
        """'Settings on the target': name, entered, target value, source (echo/getparam), match."""
        now = time.time()
        rows = []
        for sp in self.specs():
            k = sp["key"]
            src = self.readback_src.get(k)
            tgt = self.readback.get(k)
            rows.append({"name": k, "label": sp["label"], "entered": self.values.get(k), "target": tgt,
                         "source": src, "port": self.echo_port if src == "echo" else None, "age_s": round(now - self.readback_t[k], 1) if k in self.readback_t else None,
                         "match": values_match(k, self.values.get(k), tgt)})
        echo = self.echo()
        cmd = self.ctx.commands
        sent_t = dict(getattr(cmd, "toggles", {}) or {})
        for t, col in (("motor", "cmd_motor"), ("assist", "cmd_assist"), ("k", "cmd_k")):
            tgt = echo.get(col)
            rows.append({"name": t, "label": SHORT[t], "entered": sent_t.get(t), "target": tgt,
                         "source": "echo" if tgt is not None else None, "age_s": None,
                         "port": echo.get("_port") if tgt is not None else None,
                         "match": values_match(t, sent_t.get(t), tgt)})
        sent_p = dict(getattr(cmd, "params", {}) or {})
        for p, col in (getattr(cmd, "param_echo", {}) or {}).items():
            tgt = echo.get(col)
            rows.append({"name": p, "label": p.replace("_", " "), "entered": sent_p.get(p), "target": tgt,
                         "source": "echo" if tgt is not None else None, "age_s": None,
                         "port": echo.get("_port") if tgt is not None else None,
                         "match": values_match(p, sent_p.get(p), tgt)})
        return rows

    def after_connect_or_start(self, event: str) -> None:
        """After Connect: send pending values. After Start: re-apply everything entered."""
        self.clear_readback()               # Connect / Start: only values read from now on count
        if event == "start":
            self.events.append({"start": time.strftime("%Y-%m-%d %H:%M:%S")})
            # Start reloads the build defaults (AFO_r1: side -1), so the side can only be set
            # after Start: Start is never locked by the side, and a side the operator confirmed
            # for this S-ID is sent right after Start, then read back. Motor and Assist stay
            # locked until the target reports it (side_problem).
            with self.lock:
                self.after_start = True
                self.readback.pop("side", None)
                self.readback_src.pop("side", None)
                self.started_at = time.time()
        if self.profile().get("bif") and self.values.get("weight") is not None:
            with self.lock:
                self.values["bif_mass"] = self.values["weight"]      # BIF_mass_kg follows body mass
        order = ["side"] + [sp["key"] for sp in self.specs() if sp["key"] != "side"]
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
            return "No participant: set the participant ID and confirm the foot side in the top bar first."
        want = self.values.get("side")
        c = self.side_confirmed
        if want is None or not c or c["sid"] != self.sid:
            return f"Foot side not confirmed for {self.sid}: confirm it in the top bar first."
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
            return "Foot side unset, motor locked until set. Confirm the foot side in the top bar."
        if rbi != int(want):
            return SIDE_WARNING + f" Target: {SIDE_NAMES.get(rbi, rb)}, profile: {SIDE_NAMES[int(want)]}."
        return None

    def side_chip(self) -> Dict[str, str]:
        """Low-prominence side chip: text + state (ok / pending / unset / warn / bad)."""
        rb = self.readback.get("side")
        want = self.values.get("side")
        try:
            rbi = None if rb is None else int(round(float(rb)))
        except (TypeError, ValueError):
            rbi = None
        # confirmed for this S-ID but not on the target yet (no connection, or being sent):
        # a pending side, sent by setparam on Connect and then read back
        c = self.side_confirmed
        sst = self.status.get("side") or {}
        if (want is not None and c and c.get("sid") == self.sid and c.get("side") == int(want)
                and sst.get("state") in ("pending", "sending") and rbi not in (0, 1)):
            name = SIDE_NAMES[int(want)].capitalize()
            if sst["state"] == "sending":
                return {"text": f"{name} · sending…", "state": "pending"}
            m = sst.get("msg") or ""
            tail = ("target writes off" if "disabled" in m else "sent after Start" if "after Start" in m
                    else "sent on Connect")
            return {"text": f"{name} · pending, {tail}", "state": "pending"}
        if rbi == -1:
            return {"text": "Foot side unset, motor locked until set", "state": "unset"}
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
                "target_table": self.target_table(),
                "side_confirmed": self.side_confirmed, "model": self.model(),
                "target": dict(self.ctx.runctl.status or {}), "run_events": list(self.events),
                "commands": self.ctx.commands.view()}

    # ---------------------------------------------------------- Bi-LSTM (AFO_r1)
    def bif_view(self) -> Optional[Dict[str, Any]]:
        """Bi-LSTM phase: console packet cols 12-14 when present (15-float packet),
        else the MATLAB Signals stream (bif_bias_ready, bif_valid, bif_dbg(1)/(8))."""
        if not self.profile().get("bif"):
            return None
        echo = self.echo()
        if echo.get("bif_valid") is not None or echo.get("bif_bias_ready") is not None:
            return mp.bif_status(echo, "console")
        sig: Dict[str, Any] = {}
        ml = getattr(self.ctx, "matlab", None)
        if ml is not None and hasattr(ml, "snapshot"):
            try:
                got = ml.snapshot("latest", ["bif_bias_ready", "bif_valid", mp.DBG_STATE, mp.DBG_PROGRESS],
                                  2.0, timeout=0.3) or {}
            except Exception:
                got = {}
            vals = got.get("values") or {}
            sig = {"bif_bias_ready": vals.get("bif_bias_ready"), "bif_valid": vals.get("bif_valid"),
                   "state": vals.get(mp.DBG_STATE), "bif_cal_progress": vals.get(mp.DBG_PROGRESS)}
        if any(v is not None for v in sig.values()):
            return mp.bif_status(sig, "signals")
        return mp.bif_status({}, None)

    def checklist(self, bif: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """After-Start checklist for AFO_r1 (every Start resets side and BIF mass)."""
        if not self.profile().get("bif"):
            return None
        if bif is None:
            bif = self.bif_view() or {}
        mass = _num(self.readback.get("bif_mass"))
        done = {
            "side": self.side_problem() is None,
            "bif_mass": mass is not None and mass > mp.BIF_MASS_MIN,
            "bias": None if bif.get("bias_ready") is None else bif["bias_ready"] >= 0.5,
            "walk": None if bif.get("valid") is None else bif["valid"] >= 0.5,
        }
        detail = {"bif_mass": None if mass is None else f"Bi-LSTM mass on target {mass:g} kg",
                  "walk": f"{bif['progress_pct']} %" if bif.get("progress_pct") is not None else None}
        items = [{"key": k, "text": t, "done": done[k], "detail": detail.get(k)} for k, t in mp.CHECKLIST]
        return {"items": items, "all_done": all(i["done"] for i in items), "started_at": self.started_at}

    def view(self) -> Dict[str, Any]:
        rows = []
        for sp in self.specs():
            k = sp["key"]
            rows.append({"key": k, "label": sp["label"], "value": self.values.get(k),
                         "readback": self.readback.get(k), "readback_source": self.readback_src.get(k),
                         "match": values_match(k, self.values.get(k), self.readback.get(k)),
                         "status": self.status.get(k, {})})
        return {"sid": self.sid, "rows": rows, "side_problem": self.side_problem(), "side_chip": self.side_chip(),
                "side_confirmed": self.side_confirmed, "readback_at": self.readback_at, "model": self.model(),
                "profile": self.profile(),
                "writes_enabled": self.writes_enabled, "profiles": sorted(self.profiles),
                "echo_active": bool(self.echo()), "target_table": self.target_table()}
