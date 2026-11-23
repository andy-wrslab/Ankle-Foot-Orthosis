"""Session setup: per-participant model parameters (S-ID, foot side, weight, mode, K %).

* The participant is identified by an S-ID (S + number, e.g. S47); names are
  never used in files.
* Values entered in the top bar / Advanced popover are sent to the target when committed (setparam).
  Confirmation comes ONLY from the model: its console packet on UDP 5433
  (fresh: side, weight, mode, K %, commands) or getparam
  (right after each setparam, then every ~5 s while connected; all values
  until AFO_r1 is loaded). target_table() lists entered vs target values.
  Not connected -> pending, sent when connected (at once if the app is running,
  else right after Start).
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
_log_s = logging.getLogger("afo.session")

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
NOT_ON_DEVICE = "Not set on device: press to send"
MASS_NOT_SET = "Mass not set: enter the body mass"
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
        self.lock = threading.RLock()   # re-entrant: set_sid -> _apply_device both take it
        self.sid: Optional[str] = None
        self.values: Dict[str, Any] = {}
        self.status: Dict[str, Dict[str, Any]] = {}
        self.readback: Dict[str, Any] = {}
        self.readback_src: Dict[str, str] = {}
        self.readback_at: Optional[float] = None
        self.readback_t: Dict[str, float] = {}
        self.echo_port: Optional[int] = None
        self.side_confirmed: Optional[Dict[str, Any]] = None
        # the target reported the confirmed side (5433 echo or getparam) in this app session:
        # kept when the echo goes stale or a getparam fails (no revert to "? CONFIRM FOOT");
        # only a different value from the echo / getparam, a new S-ID or Start clears it
        self.side_verified: Optional[Dict[str, Any]] = None
        # Andy 14:01: after a reconnect / page reload / server restart the GUI inherits the
        # device's settings; only values the operator entered SINCE then are re-sent after
        # Start (never stale values from session_profiles.json)
        self.entered: set = set()
        self.adopted_echo = False
        self.device_state: Optional[Dict[str, float]] = None     # last adopted device state
        # where each value came from (14:26 live: run 13's built weight 55 was adopted as the
        # mass and sent to run 14 after Start): "entered" in this page session for this S-ID,
        # "adopted18" (valid run-14 echo; mass only from col 17 > 0) or "adopted15" (shown only)
        self.src: Dict[str, str] = {}
        self.adv_last: Dict[str, Dict[str, Any]] = {}     # last Advanced values read (shown greyed offline)
        self.start_owned_until = 0.0     # a page Start owns the settings until it has sent them
        self._start_waited = False
        self.after_start = False      # SPEC: every Start ends in the Confirm state
        self.started_at: Optional[float] = None     # last Start in this app session (after-Start checklist)
        # set when setparam/getparam says "No application is loaded" while the target runs:
        # the app was loaded by another MATLAB session, so this page cannot tune it
        self.app_elsewhere: Optional[float] = None
        self._flushing = False       # flush_pending thread running
        self.configured_model = mp.configured_model(ctx.cfg)
        # last application read on a successful connect (data/last_model.json): with
        # target.model auto and the target off, the page keeps that profile (AFO_r1 controls)
        # instead of falling back to AFO (GPR)
        self.last_model_path = os.path.join(ctx.app_dir, "data", "last_model.json")
        self.last_model: Optional[str] = None
        try:
            lm = json.load(open(self.last_model_path, encoding="utf-8")).get("app")
            self.last_model = lm if lm in self.models else None
        except (OSError, ValueError, AttributeError):
            pass
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
        """Loaded app when it is a known profile, else config target.model (when not auto),
        else the app of the last successful connect, else AFO."""
        app = (self.ctx.runctl.status or {}).get("app")
        if app in self.models:
            return app
        cm = self.configured_model
        if cm in self.models:
            return cm
        return self.last_model if self.last_model in self.models else mp.DEFAULT_MODEL

    def remember_app(self, app: Optional[str]) -> None:
        """A successful connect read *app*: keep it as the offline profile (only when it changes)."""
        if app not in self.models or app == self.last_model:
            return
        old, self.last_model = self.last_model, app
        try:
            os.makedirs(os.path.dirname(self.last_model_path), exist_ok=True)
            tmp = self.last_model_path + ".tmp"
            json.dump({"app": app, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, open(tmp, "w", encoding="utf-8"))
            os.replace(tmp, self.last_model_path)
        except OSError:
            pass
        self.audit("model profile", f"{old or '-'} -> {app} (read on connect)")

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
                first = self.sid is None
                if not first and sid != self.sid:
                    self.src = {}               # values of another participant are not "entered" for this one
                self.sid = sid
                self.values = dict(self.profiles.get(sid, {}))
                self.side_confirmed = None     # a new participant always needs the side confirmed
                self.side_verified = None
                if first and self.device_state:
                    # first S-ID after a start: the device state adopted before it stays the
                    # page's state (Andy 14:01); a CHANGE of participant still asks again
                    self._apply_device(self.device_state, confirm_side=True)
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
        if key in self.ADV_ECHO_COL and self.adv_echo():
            # run 15: Advanced goes over 5435 only (never setparam); no S-ID needed
            sp = self.spec(key)
            try:
                v = float(value)
            except (TypeError, ValueError):
                return f"{sp['label']}: not a number"
            return self._send(key, v)
        if not self.sid:
            return "Set the S-ID first."
        self.entered.add(key)
        self.src[key] = "entered"
        if key == "weight":
            self.entered.add("bif_mass")
            self.src["bif_mass"] = "entered"
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
        self.entered.add("side")
        self.src["side"] = "entered"
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

    # ---------------------------------------------------------- run 14: UDP settings (5434)
    LINK_FIELD = {"side": "side", "weight": "mass", "mode": "mode", "k_percent": "k"}

    def link(self):
        """The UDP settings link when the device speaks it (18-float 5433 echo), else None."""
        lk = getattr(self.ctx, "settings_link", None)
        return lk if lk is not None and lk.active() else None

    def echo_for_link(self):
        """(latest 5433 row, its age now in s, column count) for udp_settings.SettingsLink."""
        tr = getattr(self.ctx, "training", None)
        if tr is None:
            return {}, None, None
        s = tr.get_status()
        age = s.get("age_s")
        if age is not None:
            age = float(age) + max(0.0, time.monotonic() - getattr(tr, "last_hb", time.monotonic()))
        return dict(s.get("latest") or {}), age, s.get("columns")

    def link_status(self, field: str, state: str, msg: str) -> None:
        keys = [k for k, f in self.LINK_FIELD.items() if f == field]
        for k in keys:
            self.status[k] = {"state": state, "msg": msg, "at": time.time()}
            if k == "weight":
                self.status["bif_mass"] = {"state": state, "msg": msg, "at": time.time()}

    def adopt_echo(self) -> bool:
        """Runs 12/13 (15-float 5433): on the first fresh echo after a server start, show the
        device's side / mass / mode / K as the page's values (nothing is sent). Once."""
        if self.adopted_echo or self.link() is not None:
            return False
        e = self.echo()
        if not e:
            return False
        # col 2 weight_kg of a 15-float echo is the build default until set (run 13: 55), never a
        # real mass: the mass stays unknown / unset
        st = {"side": e.get("side"), "mode": e.get("assist_mode"), "k": e.get("fixed_k_pct")}
        self.adopted_echo = True
        self.link_adopted({k: float(v) for k, v in st.items() if v is not None}, src="adopted15")
        return True

    def _start_values(self) -> Dict[str, float]:
        """What a page Start sends: mass, mode, K from the page; side only when confirmed in
        this app session for this S-ID (unchanged safety rule)."""
        v = {}
        ok = ("entered", "adopted18")
        if self.values.get("weight") is not None and self.src.get("weight") in ok:
            v["mass"] = float(self.values["weight"])
        if self.values.get("mode") is not None and self.src.get("mode") in ok:
            v["mode"] = float(self.values["mode"])
        if self.values.get("k_percent") is not None and self.src.get("k_percent") in ok:
            v["k"] = float(self.values["k_percent"])
        c = self.side_confirmed
        if (self.values.get("side") is not None and c and c.get("sid") == self.sid
                and c.get("side") == self.values.get("side")):
            v["side"] = float(self.values["side"])
        return v

    def _after_page_start(self) -> None:
        lk = getattr(self.ctx, "settings_link", None)
        t_end = time.time() + 5.0
        cols = None
        while time.time() < t_end:
            row, age, cols = self.echo_for_link()
            if row and age is not None and age < 0.5 and cols:
                break
            time.sleep(0.05)
        if lk is not None and lk.active():
            vals = self._start_values()
            pkt = lk.send_values(vals)
            self.audit("udp send after page Start", f"{vals} -> {pkt}")
            self.read_after("start")
            if "mass" not in vals:
                self.status["weight"] = {"state": "pending", "msg": MASS_NOT_SET, "at": time.time()}
        else:
            # run <= 13 (15 / 12 floats) or no echo: setparam, side AND mass always
            self._start_waited = True
            try:
                self.entered.add("side")                           # side still only if confirmed
                if self.src.get("weight") in ("entered", "adopted18"):
                    self.entered |= {"weight", "bif_mass"}         # a mass, never a default
                else:
                    self.entered -= {"weight", "bif_mass"}
                    self.status["weight"] = {"state": "pending", "msg": MASS_NOT_SET, "at": time.time()}
                for k in ("mode", "k_percent"):
                    if self.src.get(k) not in ("entered", "adopted18"):
                        self.entered.discard(k)
                self.after_connect_or_start("start")
            finally:
                self._start_waited = False
        self.start_owned_until = time.time() + 1.0

    def link_adopted(self, st: Dict[str, float], src: str = "adopted18") -> None:
        """The device state was adopted (page start, reconnect, link back after a stall):
        show it as the page's values; nothing is sent. Not right after a PAGE Start (the
        page sends its values then)."""
        if time.time() < getattr(self, "start_owned_until", 0.0):
            return
        self.device_state = dict(st)
        self._apply_device(st, confirm_side=True, src=src)
        self.audit("adopted device settings", json.dumps(st))

    def _apply_device(self, st: Dict[str, float], confirm_side: bool, src: str = "adopted18") -> None:
        with self.lock:
            side = st.get("side")
            if side in (0.0, 1.0):
                self.values["side"] = int(side)
                self.src["side"] = src
                if self.sid and confirm_side:
                    self.side_confirmed = {"sid": self.sid, "side": int(side), "at": time.time(), "adopted": True}
            if src == "adopted18" and 20.0 <= (st.get("mass") or 0) <= 200.0:      # col 17 only
                self.values["weight"] = float(st["mass"])
                self.values["bif_mass"] = float(st["mass"])
                self.src["weight"] = self.src["bif_mass"] = src
            elif self.src.get("weight") not in ("entered",):
                self.src.pop("weight", None)             # unknown: never sent as a default
                self.src.pop("bif_mass", None)
            if st.get("mode") in (1.0, 3.0):
                self.values["mode"] = int(st["mode"])
                self.src["mode"] = src
            if st.get("k") is not None:
                self.values["k_percent"] = float(st["k"])
                self.src["k_percent"] = src
            for k in ("side", "weight", "bif_mass", "mode", "k_percent"):
                self.status.pop(k, None)
            self.after_start = False
            self.entered.clear()
            # device unset (mass 0 / side -1) while the page has a value: say so, never silently
            if src == "adopted18" and not (st.get("mass") or 0) > 0 and self.values.get("weight") is not None:
                self.status["weight"] = {"state": "pending", "msg": NOT_ON_DEVICE, "at": time.time()}
            if src == "adopted18" and st.get("side") not in (0.0, 1.0) and self.values.get("side") is not None:
                self.status["side"] = {"state": "pending", "msg": NOT_ON_DEVICE, "at": time.time()}

    def _send(self, key: str, value: float) -> str:
        sp = self.spec(key)
        lk = self.link()
        if lk is not None and key in self.LINK_FIELD:
            r = lk.press(self.LINK_FIELD[key], value)
            if not r.get("ok"):
                self.status[key] = {"state": "error", "msg": r.get("msg") or "not sent", "at": time.time()}
                return f"{sp['label']}: {r.get('msg')}"
            self.audit("udp set", f"{key}={value:g} (5434)")
            return f"{sp['label']}: sending…"
        if lk is not None and key == "bif_mass":
            return f"{sp['label']}: follows Body mass (5434)"
        if key in self.ADV_ECHO_COL and self.adv_echo():
            alk = self.adv_send_link()
            if alk is None:
                self.status[key] = {"state": "error", "msg": self.ADV_READONLY_MSG, "at": time.time()}
                return f"{sp['label']}: {self.ADV_READONLY_MSG}"
            r = alk.press(self.ADV_ECHO_COL[key], value)
            if not r.get("ok"):
                self.status[key] = {"state": "error", "msg": r.get("msg") or "not sent", "at": time.time()}
                return f"{sp['label']}: {r.get('msg')}"
            self.audit("udp set", f"{key}={value:g} (5435)")
            return f"{sp['label']}: sending…"
        tp = self.target_path(key)
        if tp is None:
            self.status[key] = {"state": "error", "msg": f"no block for {key} in model {self.model()}", "at": time.time()}
            return self.status[key]["msg"]
        if not self.writes_enabled:
            self.status[key] = {"state": "pending", "msg": "saved, not sent: target writes are disabled (access hold)",
                                "at": time.time()}
            return f"{sp['label']} saved; not sent (target writes disabled)"
        if not self._connected():
            self.status[key] = {"state": "pending", "msg": "pending: sent when connected", "at": time.time()}
            return f"{sp['label']} saved; will be sent when connected"
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
                if key in self.advanced_keys():
                    self.read_after("advanced send")
            self.audit("set", f"{key}={value:g} ({blk}|{prm}) -> {json.dumps(out)[:200]}")
            return out
        self.status[key] = {"state": "sending", "msg": "", "at": time.time()}
        self.ctx.jobs.start("session", f"set {key}", run)
        return f"{sp['label']}: sending…"

    ELSEWHERE_MSG = "App started elsewhere: press Stop then Start to take control"
    REFUSED_ELSEWHERE = "Target refused: app started by another MATLAB, press Stop → Start"

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

    def refusal_text(self, key: str) -> str:
        """What the chip / field / dock say at once when the target refused a value."""
        st = self.status.get(key) or {}
        if st.get("state") != "error":
            return ""
        m = st.get("msg") or "refused"
        return self.REFUSED_ELSEWHERE if m == self.ELSEWHERE_MSG else ("Target refused: " + m)

    def _put(self, key: str, value, src: str) -> None:
        if src in ("getparam", "echo") and key in self.advanced_keys():
            self.adv_last[key] = {"value": value, "at": time.time()}     # survives a disconnect
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

    # run 14 (18-float echo): every "Target uses" value comes from the echo; BIF mass = col 17
    # (the root constant BIF_mass_kg stays 0: the UDP settings override it inside the model)
    ECHO18_COL = {"bif_mass": "bif_mass_kg"}
    ECHO_ONLY_KEYS = ("side", "weight", "bif_mass", "mode", "k_percent")
    # run 15 (31-float echo): the 11 Advanced values in use = 5433 cols 18-28, in the order of
    # round1/settings_adv_udp_layout.json; col 29 adv_seq; col 30 spring stiffness is ignored
    ADV_ECHO_COL = {"sv_target_min": "sv_target_min", "sv_target_max": "sv_target_max",
                    "target_step_up": "target_step_up", "target_step_down": "target_step_down",
                    "window_up": "step_up_window", "window_down": "step_down_window",
                    "assist_threshold": "high_assist_level", "min_cycles": "high_assist_strides",
                    "p_gain": "torque_p_gain", "i_gain": "torque_i_gain", "threshold_pressure": "standing_still_cutoff"}
    ADV_READONLY_MSG = "Advanced is read-only on this build (sending over UDP 5435 comes next)"

    def adv_echo(self, echo: Optional[Dict[str, Any]] = None) -> bool:
        """Run 15: the fresh 5433 echo carries the Advanced values (31 floats, adv_seq)."""
        e = self.echo() if echo is None else echo
        return e.get("adv_seq") is not None and all(e.get(c) is not None for c in self.ADV_ECHO_COL.values())

    def adv_send_link(self):
        """The 5435 Advanced sender when the device speaks it, else None."""
        lk = getattr(self.ctx, "adv_link", None)
        return lk if lk is not None and lk.active() else None

    def refresh_echo(self) -> None:
        """The cheap part of refresh_readback (no MATLAB): readbacks from the fresh 5433 echo.
        Called on every page state poll, so a confirmation shows within one poll."""
        echo = self.echo()
        self.echo_port = echo.get("_port")
        udp = self.link() is not None
        adv = self.adv_echo(echo)
        for sp in self.specs():
            k = sp["key"]
            col = sp.get("udp") or (self.ECHO18_COL.get(k) if udp else None) or (self.ADV_ECHO_COL.get(k) if adv else None)
            if col and echo.get(col) is not None:
                self._put(k, echo[col], "echo")
                if adv and k in self.ADV_ECHO_COL:
                    # run 15: the page adopts the device's Advanced values (nothing is sent); a
                    # value held for "after Start" from a run-14 session is dropped, never setparam'd
                    with self.lock:
                        self.values[k] = float(echo[col])
                        self.src[k] = "adopted31"
                        self.entered.discard(k)
                        if (self.status.get(k) or {}).get("state") == "pending":
                            self.status.pop(k, None)
            elif self.readback_src.get(k) == "echo" or (udp and k in self.ECHO_ONLY_KEYS):
                # echo gone (stream stopped / other model), or a getparam leftover on run 14:
                # drop it (run <= 13: getparam takes over)
                self.readback.pop(k, None)
                self.readback_src.pop(k, None)

    # ---------------------------------------------------------- Advanced params (12 root constants)
    # Run 14: side / mass / mode / K / gyro come over UDP (5434 + echo); the 11 Advanced params
    # are still root Constants -> getparam (read) / setparam (write) while connected. Run 15 will
    # move them to UDP 5435 + a 32-float echo: swap AdvancedParams.read_keys / the send path.
    def advanced_keys(self) -> List[str]:
        return [sp["key"] for sp in self.specs() if sp.get("adv")]

    def getparam_keys(self) -> List[str]:
        """What a getparam read covers now: on run 14 only the Advanced constants (never side /
        mass / BIF / mode / K / Gyro_Cal: those come from the echo); runs <= 13 everything
        without a fresh echo."""
        if self.link() is not None:
            if self.adv_echo():
                return []                     # run 15: the Advanced values come from the echo too
            return [k for k in self.advanced_keys() if k not in self.ECHO_ONLY_KEYS]
        return [sp["key"] for sp in self.specs() if self.readback_src.get(sp["key"]) != "echo"]

    def read_after(self, why: str, wait_s: float = 15.0) -> None:
        """One getparam read once the current run-control / session job has finished (after
        Connect, Start and each Advanced send)."""
        def run():
            t_end = time.time() + wait_s
            time.sleep(0.2)
            while time.time() < t_end and (self.ctx.jobs.running("rc") or self.ctx.jobs.running("session")):
                time.sleep(0.2)
            try:
                self.refresh_readback()
            except Exception:
                _log_s.exception("read after %s failed", why)
        threading.Thread(target=run, name=f"read-after-{why}", daemon=True).start()

    def refresh_readback(self) -> None:
        """Echo first (no MATLAB); getparam for every value without a fresh echo
        (run 14: getparam only for the Advanced constants)."""
        self.adopt_echo()
        self.refresh_echo()
        if not self._connected() or self.ctx.jobs.running("rc") or self.ctx.jobs.running("session"):
            return
        need = self.getparam_keys()
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

    def flush_pending(self, why: str = "running") -> None:
        """Send held (pending) values once the target is connected and the app RUNNING.

        Called on every run-control status (Connect to an app that is already running,
        an app started elsewhere, a status refresh), so nothing waits for a Start that may
        never come. Each value goes through _send (setparam, then read back). Values held
        because target writes are disabled stay held; an unconfirmed side is never sent."""
        rc = self.ctx.runctl.status or {}
        if not (rc.get("connected") and rc.get("running")) or not self.writes_enabled:
            return
        with self.lock:
            if self._flushing:
                return
            keys = [k for k, st in self.status.items()
                    if (st or {}).get("state") == "pending" and self.values.get(k) is not None]
            if not keys:
                return
            self._flushing = True

        def run():
            try:
                order = sorted(keys, key=lambda k: (k != "side", k))
                for k in order:
                    if k == "side":
                        c = self.side_confirmed
                        if not c or c["sid"] != self.sid or c["side"] != self.values.get("side"):
                            continue
                    t_end = time.time() + 40
                    while self.ctx.jobs.running("session") and time.time() < t_end:
                        time.sleep(0.2)
                    if (self.status.get(k) or {}).get("state") != "pending":
                        continue
                    self.audit(f"send pending ({why})", f"{k}={self.values[k]}")
                    self._send(k, float(self.values[k]))
            finally:
                self._flushing = False
        threading.Thread(target=run, name="send-pending", daemon=True).start()

    def after_connect_or_start(self, event: str) -> None:
        """After Connect: send pending values. After Start: re-apply everything entered.
        Run 14 (UDP settings): Connect sends nothing (the device state is adopted from the
        echo); Start sends the page's values once over 5434."""
        if event == "start" and getattr(self.ctx, "settings_link", None) is not None and not self._start_waited:
            # PAGE-initiated Start: the device reloads (side -1, mass 0) and its echo may not be
            # there yet. Do NOT adopt that; wait for the first echo (<= 5 s): 18 floats -> one
            # 5434 packet with the page's values; 12 / 15 floats or none -> setparam (side AND mass)
            self.start_owned_until = time.time() + 8.0
            self.events.append({"start": time.strftime("%Y-%m-%d %H:%M:%S")})
            self.side_verified = None
            threading.Thread(target=self._after_page_start, name="after-start", daemon=True).start()
            return
        lk = self.link()
        if lk is not None:
            self.read_after("connect")          # Connect with run 14: adopt only, nothing sent; read Advanced
            return
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
                self.side_verified = None          # Start reloads the build default (side -1)
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
            if event != "start" and self._flushing:
                continue                     # flush_pending (Connect to a running app) sends these
            if event == "start" and k not in self.entered:
                continue                     # not entered since the device state was adopted: not re-sent
            if event == "start" or self.status.get(k, {}).get("state") == "pending":
                self.audit(f"re-apply after {event}", f"{k}={self.values[k]}")
                self._send(k, float(self.values[k]))
                t_end = time.time() + 40
                while self.ctx.jobs.running("session") and time.time() < t_end:
                    time.sleep(0.2)

    def note_stop(self) -> None:
        self.events.append({"stop": time.strftime("%Y-%m-%d %H:%M:%S")})

    # ---------------------------------------------------------- safety
    def side_target(self):
        """The side the target reports: the fresh 5433 echo first (every 10 ms, so a match
        confirms within one console packet), else the last getparam readback."""
        col = self.spec("side").get("udp")
        e = self.echo()
        if col and e.get(col) is not None:
            return e[col], "echo"
        rb = self.readback.get("side")
        return rb, (self.readback_src.get("side") if rb is not None else None)

    def side_problem(self) -> Optional[str]:
        if not self.sid:
            return "No participant: set the participant ID and confirm the foot side in the top bar first."
        want = self.values.get("side")
        c = self.side_confirmed
        if want is None or not c or c["sid"] != self.sid:
            return f"Foot side not confirmed for {self.sid}: confirm it in the top bar first."
        rb, src = self.side_target()
        v = self.side_verified
        if rb is not None:
            try:
                rbi_now = int(round(float(rb)))
            except (TypeError, ValueError):
                rbi_now = None
            if rbi_now == int(want):
                self.side_verified = {"sid": self.sid, "side": int(want), "at": time.time(), "src": src}
            elif rbi_now is not None:
                self.side_verified = None
        elif v and v.get("sid") == self.sid and v.get("side") == int(want):
            return None                       # verified earlier; no new evidence against it
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
        """Low-prominence side chip: text + state (ok / pending / refused / unset / warn / bad)."""
        rb, _src = self.side_target()
        want = self.values.get("side")
        try:
            rbi = None if rb is None else int(round(float(rb)))
        except (TypeError, ValueError):
            rbi = None
        # confirmed for this S-ID but not on the target yet (no connection, or being sent):
        # a pending side, sent by setparam once connected to a running app, then read back
        c = self.side_confirmed
        sst = self.status.get("side") or {}
        if (want is not None and c and c.get("sid") == self.sid and c.get("side") == int(want)
                and sst.get("state") == "error" and rbi != int(want)):
            # the target refused it: say so at once (no silent wait for a readback)
            return {"text": f"{SIDE_NAMES[int(want)].capitalize()} · target refused", "state": "refused",
                    "msg": self.refusal_text("side")}
        if (want is not None and c and c.get("sid") == self.sid and c.get("side") == int(want)
                and sst.get("state") in ("pending", "sending") and rbi not in (0, 1)):
            name = SIDE_NAMES[int(want)].capitalize()
            if sst["state"] == "sending":
                return {"text": f"{name} · sending…", "state": "pending"}
            m = sst.get("msg") or ""
            tail = ("target writes off" if "disabled" in m else "sent after Start" if "after Start" in m
                    else "sent when connected")
            return {"text": f"{name} · pending, {tail}", "state": "pending"}
        if rbi == -1:
            return {"text": "Foot side unset, motor locked until set", "state": "unset"}
        if self.side_problem() is None:
            return {"text": f"Side: {SIDE_NAMES[int(want)]}", "state": "ok"}
        if rbi in (0, 1) and want is not None and rbi != int(want):
            return {"text": f"Side mismatch ({SIDE_NAMES[rbi]} on target)", "state": "bad"}
        return {"text": "Side: confirm" if want is None or not self.side_confirmed else
                f"Side: {SIDE_NAMES[int(want)]} (not verified)", "state": "warn"}

    def link_frozen(self) -> Optional[str]:
        """Link stalled (run 14): nothing may be sent; the device keeps its settings."""
        lk = getattr(self.ctx, "settings_link", None)
        return lk.view()["msg"] if lk is not None and lk.frozen else None

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
        """Bi-LSTM phase from the console packet cols 12-14 (15 / 18-float packet). The MATLAB
        Signals fallback is gone with the Signals page (Andy 14:36): no getsignal calls; a
        12-float build shows the state as unknown (a grey note)."""
        if not self.profile().get("bif"):
            return None
        echo = self.echo()
        if echo.get("bif_valid") is not None or echo.get("bif_bias_ready") is not None:
            return mp.bif_status(echo, "console")
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
