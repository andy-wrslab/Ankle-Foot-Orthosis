"""Session settings over UDP 5434 (run 14 AFO_r1, Nov 23; Andy: "everything based on UDP,
except for file log saving").

Packet host -> target, udp.send_host : udp.session_port (default 5434), '<8f':
    [0] magic 4134  [1] version 1  [2] seq  [3] side -1/0/1  [4] body_mass_kg
    [5] assist_mode 1/3  [6] fixed_k_pct 0-10  [7] gyro_cal_request (counter)
The model ignores a packet with a wrong magic or version; per field an invalid value
keeps the last one; values are held until the next valid packet (after Start: side -1,
mass 0 until the first valid packet).

Echo: the 5433 console packet grows to '<18f' (the 15 + col 15 gyro_cal_request in use,
col 16 last accepted seq (0 = none), col 17 bif_mass_kg in use (0 = unset)). 18 floats
= this profile ("udp_settings"); 12 / 15 floats = runs 12/13, setparam stays the path.

Rules (Andy 14:01: "in case of small stall of internet connection, we need to have the
device keep its current setting, and the GUI inherit whatever setting that's on the
device"):
* nothing is sent on page start, a new tab, a reconnect or a server restart: the page
  ADOPTS the device state from the echo (side, mass = col 17, mode, K, gyro counter) and
  continues seq from the echoed last seq + 1;
* a packet is sent only on a user press (side, mass, mode, K %, Calibrate IMU), built from
  the adopted values with that one field changed, and once right after Start;
* a press is confirmed when the echo shows the value with last seq >= the packet's seq
  (~10-100 ms); without a matching echo it is resent up to 3 times within 1 s, then
  "Not confirmed: no echo from model";
* echo missing for > 0.75 s (link stall): FROZEN, nothing is sent, "No data from device:
  settings unchanged on the device"; when it returns, re-adopt, then unfreeze;
* view-only console: never sends.

Run 15 (Advanced over UDP 5435, AdvLink below): the same rules for the 11 Advanced
values. Packet '<16f' magic 4135, version 1, seq, the 11 values (order of
round1/settings_adv_udp_layout.json), [14] reserved_spring, [15] reserved (both sent 0,
ignored by the model). Echo: 5433 grows to '<31f', cols 18-28 = the values in use, col 29
adv_seq, col 30 spring_stiffness (read-only, ignored here). 31 floats = AdvLink active and
no getparam for Advanced; 18 floats = run 14 (getparam / setparam for Advanced).
"""
from __future__ import annotations

import logging
import math
import socket
import struct
import threading
import time
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

MAGIC, VERSION = 4134.0, 1.0
PACKET = struct.Struct("<8f")
FIELDS = ("side", "mass", "mode", "k", "gyro")          # packet slots 3..7
ECHO_COL = {"side": "side", "mass": "bif_mass_kg", "mode": "assist_mode", "k": "fixed_k_pct",
            "gyro": "gyro_cal_request"}
from echo_sizes import ADV_UDP_MIN, GUARD_UDP_MIN, UDP_SETTINGS_MIN  # noqa: E402

ECHO_N = UDP_SETTINGS_MIN                 # 18 (echo_sizes)
STALE_S = 0.75             # echo older than this: link stalled -> frozen
RETRY_EVERY_S = 0.25       # resend after 0.25, 0.5, 0.75 s ...
MAX_RETRIES = 3
CONFIRM_WINDOW_S = 1.0     # ... and give up at 1 s
FROZEN_MSG = "No data from device: settings unchanged on the device"
NOT_CONFIRMED_MSG = "Not confirmed: no echo from model"

_log = logging.getLogger("afo.udp_settings")


def valid(field: str, v: Any) -> bool:
    """What the model accepts per field (round1/settings_udp_layout.json); anything else
    keeps the value in use: side 0/1 (-1 = keep), body mass 20..200 (sets weight AND
    BIF_mass_kg), assist_mode 1/3, fixed_k_pct 0..10, gyro_cal_request any finite."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(f):
        return False
    return {"side": f in (0.0, 1.0), "mass": 20.0 <= f <= 200.0, "mode": f in (1.0, 3.0),
            "k": 0.0 <= f <= 10.0, "gyro": True}[field]


def same(field: str, a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) <= (1e-3 if field in ("side", "mode", "gyro") else 1e-2)
    except (TypeError, ValueError):
        return False


class SettingsLink:
    """One per app. echo_fn() -> (latest 5433 row dict or {}, its age in s or None, columns)."""
    NAME = "5434"
    MAGIC, VERSION = MAGIC, VERSION
    PACKET = PACKET
    FIELDS = FIELDS
    ECHO_COL = ECHO_COL
    SEQ_COL = "settings_seq"
    ECHO_N = ECHO_N                       # active from this many echo columns on
    PORT_KEY, PORT_DEFAULT = "session_port", 5434
    COUNTER: Optional[str] = "gyro"       # sent as the echoed value (+ 1 on a press), never remembered
    KEEP = {"side": -1.0, "mass": 0.0, "mode": 0.0, "k": -1.0}
    TAIL: Tuple[float, ...] = ()          # packet slots after the fields
    UNSET = {"side": -1.0, "mass": 0.0}   # adopted as "unset on the device" when not valid

    def valid(self, field: str, v: Any) -> bool:
        return valid(field, v)

    def same(self, field: str, a: Any, b: Any) -> bool:
        return same(field, a, b)

    def check(self, field: str, value: Any) -> Optional[str]:
        """Why a press of *field* = *value* is not sent, or None."""
        return None if self.valid(field, value) else f"{field} {value!r} is not a valid value"

    def check_many(self, values: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        """(field, why) for the first refused field of a batch, else None."""
        for f, v in values.items():
            why = self.check(f, v)
            if why:
                return f, why
        return None

    def __init__(self, cfg: Dict[str, Any], echo_fn: Callable[[], tuple], view_only: bool = False,
                 on_status: Optional[Callable[[str, str, str], None]] = None, sender=None, start_thread: bool = True,
                 on_adopt: Optional[Callable[[Dict[str, float]], None]] = None):
        u = cfg.get("udp") or {}
        self.addr = (str(u.get("send_host", "192.168.7.5")), int(u.get(self.PORT_KEY, self.PORT_DEFAULT)))
        self.echo_fn = echo_fn
        self.view_only = bool(view_only)
        self.on_status = on_status or (lambda field, state, msg: None)
        self.on_adopt = on_adopt or (lambda state: None)
        self.lock = threading.RLock()
        self.state: Optional[Dict[str, float]] = None      # adopted device state (None: not adopted)
        self.seq = 0
        self.pending: Dict[str, Dict[str, Any]] = {}       # field -> {value, seqs, t0, last, tries}
        self.result: Dict[str, Dict[str, Any]] = {}        # field -> {state, msg, at}
        self.frozen = False
        self.adopted_at: Optional[float] = None
        self.sent = []                                     # (time, packet tuple) - kept short, for tests / log
        self._sock = None
        self._sender = sender
        self._stop = threading.Event()
        if start_thread:
            threading.Thread(target=self._loop, name=f"udp-settings-{self.NAME}", daemon=True).start()

    # ------------------------------------------------------------ echo
    def _echo(self):
        try:
            row, age, cols = self.echo_fn()
        except Exception:
            return {}, None, None
        return row or {}, age, cols

    def _row_active(self, row: Dict[str, Any], cols) -> bool:
        if cols is not None:
            return cols >= self.ECHO_N
        return row.get(self.SEQ_COL) is not None

    def active(self) -> bool:
        """This profile is on: the 5433 echo has at least ECHO_N columns (5434: 18 = run 14
        and later; 5435: 31 = run 15)."""
        row, age, cols = self._echo()
        return self._row_active(row, cols)

    def _adopt(self, row: Dict[str, Any]) -> None:
        st = {f: float(row[self.ECHO_COL[f]]) for f in self.FIELDS if row.get(self.ECHO_COL[f]) is not None}
        for f, unset in self.UNSET.items():
            if f in st and not self.valid(f, st[f]):
                st[f] = unset                                   # unset on the device
        self.state = st
        try:
            self.seq = max(self.seq, int(float(row.get(self.SEQ_COL) or 0)))
        except (TypeError, ValueError):
            pass
        self.adopted_at = time.time()
        _log.info("%s: adopted device settings %s (seq %d)", self.NAME, st, self.seq)

    # ------------------------------------------------------------ send
    def _send(self, pkt) -> None:
        self.sent.append((time.time(), pkt))
        del self.sent[:-50]
        data = self.PACKET.pack(*pkt)
        if self._sender is not None:
            self._sender(data, self.addr)
            return
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.sendto(data, self.addr)

    def _packet(self, values: Dict[str, float]):
        self.seq += 1
        return (self.MAGIC, self.VERSION, float(self.seq)) + tuple(float(values[f]) for f in self.FIELDS) + self.TAIL

    def _values(self) -> Dict[str, float]:
        """The page's values (adopted from the device, then pressed) with every still-pending
        press applied. A field without a valid value is sent as 'keep' (side -1, mass 0,
        mode 0, K -1). gyro_cal_request is ALWAYS the value echoed right now (col 15): a
        change re-runs the 5 s gyro bias, so a stale or remembered counter is never sent;
        only a pending Calibrate IMU press sends echoed + 1."""
        c = self.COUNTER
        v = {f: x for f, x in (self.state or {}).items() if f != c and self.valid(f, x)}
        for f, p in self.pending.items():
            if f != c:
                v[f] = p["value"]
        for f in self.FIELDS:
            if f != c:
                v.setdefault(f, self.KEEP.get(f, float("nan")))
        if c is not None:
            row, age, cols = self._echo()
            g = row.get(self.ECHO_COL[c])
            if g is None:
                raise RuntimeError(f"no echoed {self.ECHO_COL[c]}: not sending")
            v[c] = float(g) + (1.0 if c in self.pending else 0.0)
        return v

    def press(self, field: str, value: Any) -> Dict[str, Any]:
        """A user press: send the device values with this one field changed."""
        with self.lock:
            if self.view_only:
                return {"ok": False, "state": "error", "msg": "View-only console: settings are not sent from this app"}
            if self.frozen:
                return {"ok": False, "state": "error", "msg": FROZEN_MSG}
            if self.state is None:
                return {"ok": False, "state": "error", "msg": "Waiting for the device state (5433 echo)"}
            why = self.check(field, value)
            if why:
                return {"ok": False, "state": "error", "msg": why}
            if field == self.COUNTER:
                row, age, cols = self._echo()
                if row.get(self.ECHO_COL[field]) is None:
                    return {"ok": False, "state": "error", "msg": f"No echoed {self.ECHO_COL[field]} yet"}
                value = float(row[self.ECHO_COL[field]]) + 1.0       # echoed + 1, never remembered
            self.pending[field] = {"value": float(value), "seqs": [], "t0": time.time(), "last": time.time(), "tries": 0}
            try:
                v = self._values()
            except RuntimeError as exc:
                self.pending.pop(field, None)
                return {"ok": False, "state": "error", "msg": str(exc)}
            v[field] = float(value)
            pkt = self._packet(v)
            self.pending[field]["seqs"].append(pkt[2])
            self.result[field] = {"state": "sending", "msg": "", "at": time.time()}
            self._send(pkt)
        self.on_status(field, "sending", "")
        return {"ok": True, "state": "sending", "msg": ""}

    def press_many(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """Advanced Confirm (Andy Nov 24 14:34): several user edits in ONE packet. Every field
        is checked first; one bad field sends nothing. Confirmed / retried like a press."""
        with self.lock:
            if self.view_only:
                return {"ok": False, "state": "error", "msg": "View-only console: settings are not sent from this app"}
            if self.frozen:
                return {"ok": False, "state": "error", "msg": FROZEN_MSG}
            if self.state is None:
                return {"ok": False, "state": "error", "msg": "Waiting for the device state (5433 echo)"}
            if not values:
                return {"ok": False, "state": "error", "msg": "nothing to send"}
            for field in values:
                if field not in self.FIELDS or field == self.COUNTER:
                    return {"ok": False, "state": "error", "msg": f"{field}: not a setting on this port", "field": field}
            bad = self.check_many(values)
            if bad:
                return {"ok": False, "state": "error", "msg": f"{bad[0]}: {bad[1]}", "field": bad[0]}
            vals = {f: float(v) for f, v in values.items()}
            now = time.time()
            for f, v in vals.items():
                self.pending[f] = {"value": v, "seqs": [], "t0": now, "last": now, "tries": 0}
            try:
                v = self._values()
            except RuntimeError as exc:
                for f in vals:
                    self.pending.pop(f, None)
                return {"ok": False, "state": "error", "msg": str(exc)}
            v.update(vals)
            pkt = self._packet(v)
            for f in vals:
                self.pending[f]["seqs"].append(pkt[2])
                self.result[f] = {"state": "sending", "msg": "", "at": now}
            self._send(pkt)
        for f in vals:
            self.on_status(f, "sending", "")
        return {"ok": True, "state": "sending", "msg": "", "fields": sorted(vals), "seq": pkt[2]}

    def send_values(self, values: Dict[str, float]) -> Optional[tuple]:
        """After a PAGE-initiated Start: one packet with the page's values (side only when
        given), the ECHOED gyro counter; confirmed / retried like a press. No adopt callback:
        the page's values are not replaced by the device's unset ones (side -1, mass 0)."""
        row, age, cols = self._echo()
        with self.lock:
            if self.view_only or not row or age is None or age > STALE_S:
                return None
            if self.state is None or self.frozen:
                self._adopt(row)                    # base for the fields not given (no on_adopt)
                self.frozen = False
            sending = {f: float(v) for f, v in values.items()
                       if f in self.FIELDS and f != self.COUNTER and self.valid(f, v)}
            for f, v in sending.items():
                self.state[f] = v
                self.pending[f] = {"value": v, "seqs": [], "t0": time.time(), "last": time.time(), "tries": 0}
            try:
                v = self._values()
            except RuntimeError:
                for f in sending:
                    self.pending.pop(f, None)
                return None
            pkt = self._packet(v)
            for f in sending:
                self.pending[f]["seqs"].append(pkt[2])
                self.result[f] = {"state": "sending", "msg": "", "at": time.time()}
            self._send(pkt)
        for f in sending:
            self.on_status(f, "sending", "")
        return pkt

    def after_start(self) -> Optional[tuple]:
        """Start reloads the app (side -1, mass 0 until the first valid packet): send the
        page's values once."""
        with self.lock:
            if self.view_only or self.frozen or self.state is None:
                return None
            try:
                v = self._values()
            except RuntimeError:
                return None
            pkt = self._packet(v)
            for f in self.FIELDS:
                if f == self.COUNTER or not self.valid(f, v[f]):
                    continue
                self.pending[f] = {"value": v[f], "seqs": [pkt[2]], "t0": time.time(), "last": time.time(), "tries": 0}
            self._send(pkt)
            return pkt

    # ------------------------------------------------------------ confirm / retry / freeze
    def tick(self) -> None:
        row, age, cols = self._echo()
        fresh = bool(row) and age is not None and age <= STALE_S
        changes = []
        if not fresh:
            with self.lock:
                if self.state is not None and not self.frozen:
                    self.frozen = True
                    _log.warning("5433 echo stalled: %s settings frozen (nothing sent)", self.NAME)
                    for f in list(self.pending):
                        changes.append((f, "error", FROZEN_MSG))
                        self.result[f] = {"state": "error", "msg": FROZEN_MSG, "at": time.time()}
                    self.pending.clear()
            for f, st, m in changes:
                self.on_status(f, st, m)
            return
        with self.lock:
            if not self._row_active(row, cols):
                # not this profile (runs 12/13 for 5434, <= 14 for 5435): forget any adopted state
                self.state, self.frozen = None, False
                self.pending.clear()
                return
            if self.state is None or self.frozen:
                self._adopt(row)                    # first echo or back after a stall: adopt, then unfreeze
                self.frozen = False
                adopted = dict(self.state)
            else:
                adopted = None
        if adopted is not None:
            self.on_adopt(adopted)
            return
        with self.lock:
            try:
                last_seq = float(row.get(self.SEQ_COL) or 0)
            except (TypeError, ValueError):
                last_seq = 0.0
            now = time.time()
            for f, p in list(self.pending.items()):
                if last_seq >= min(p["seqs"]) and self.same(f, row.get(self.ECHO_COL[f]), p["value"]):
                    self.pending.pop(f)
                    self.result[f] = {"state": "confirmed", "msg": "", "at": now}
                    changes.append((f, "confirmed", ""))
                    continue
                if now - p["t0"] >= CONFIRM_WINDOW_S:
                    self.pending.pop(f)
                    self.result[f] = {"state": "error", "msg": NOT_CONFIRMED_MSG, "at": now}
                    changes.append((f, "error", NOT_CONFIRMED_MSG))
                    continue
                if p["tries"] < MAX_RETRIES and now - p["last"] >= RETRY_EVERY_S:
                    try:
                        vals = self._values()
                    except RuntimeError:
                        continue
                    if f == self.COUNTER:
                        vals[f] = p["value"]            # the retry repeats the same requested counter
                    pkt = self._packet(vals)
                    p["seqs"].append(pkt[2]); p["last"] = now; p["tries"] += 1
                    self._send(pkt)
            # keep the page's copy current for fields nobody is changing; an "unset" echo
            # (side -1 / mass 0 after Start) keeps the page's value for the resend after Start
            for f in self.FIELDS:
                if f not in self.pending and row.get(self.ECHO_COL[f]) is not None and self.valid(f, row[self.ECHO_COL[f]]):
                    self.state[f] = float(row[self.ECHO_COL[f]])
        for f, s, m in changes:
            self.on_status(f, s, m)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                _log.exception("udp settings %s tick failed", self.NAME)
            time.sleep(0.02)

    def stop(self):
        self._stop.set()

    def view(self) -> Dict[str, Any]:
        with self.lock:
            return {"active": self.active(), "frozen": self.frozen, "msg": FROZEN_MSG if self.frozen else "",
                    "adopted": dict(self.state) if self.state else None, "seq": self.seq,
                    "pending": sorted(self.pending), "result": {k: dict(v) for k, v in self.result.items()}}


# ---------------------------------------------------------------- run 15: Advanced (5435)
ADV_LAYOUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "settings_adv_udp_layout.json")
# session key (session.SPECS, the Advanced popover) -> 5435 field / 5433 echo column name
ADV_FIELD = {"sv_target_min": "sv_target_min", "sv_target_max": "sv_target_max",
             "target_step_up": "target_step_up", "target_step_down": "target_step_down",
             "window_up": "step_up_window", "window_down": "step_down_window",
             "assist_threshold": "high_assist_level", "min_cycles": "high_assist_strides",
             "p_gain": "torque_p_gain", "i_gain": "torque_i_gain", "threshold_pressure": "standing_still_cutoff",
             "fade_ms": "standstill_fade_ms",      # run 16c (5435 [15], echo col 44)
             "assist_ramp_step": "assist_ramp_step"}   # run 16g (5435 [14], echo col 45)
_RANGE = re.compile(r"(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)")


_SWITCH = re.compile(r"(^|\b)0 or 1\b|^\s*0 = .*\b1 = ")


def load_adv_layout(path: str = ADV_LAYOUT) -> Tuple[List[str], Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """(the value fields in packet order, {field: {min, max, int}}, the layout) from a UDP
    settings layout (5435 / 5436): slots 3.. except the reserved ones; the rule text gives the
    range ("0.2..2.0", "-5..-0.05"), "whole number" = integers only, "0 or 1" / "0 = ..., 1 =
    ..." = a 0/1 switch."""
    lay = json.load(open(path, encoding="utf-8"))
    fields, rules = [], {}
    for f in sorted(lay["fields"], key=lambda x: x["index"]):
        if f["index"] < 3 or f["name"].startswith("reserved"):
            continue
        rule = f.get("rule") or ""
        m = _RANGE.search(rule)
        if m:
            r = {"min": float(m.group(1)), "max": float(m.group(2)), "int": "whole number" in rule}
        elif _SWITCH.search(rule):
            r = {"min": 0.0, "max": 1.0, "int": True}
        else:
            raise ValueError(f"{path}: no range in the rule of {f['name']!r}")
        fields.append(f["name"])
        rules[f["name"]] = r
    return fields, rules, lay


class AdvLink(SettingsLink):
    """Run 15: the 11 Advanced values over UDP 5435 with the 5434 rules (adopt from the echo,
    send only on a press with the in-use values and one field changed, confirm from the echo
    = value + adv_seq >= the packet's seq, 3 retries within 1 s, frozen on a stall). Active
    with a 31-float 5433 echo; spring stiffness (col 30) is never read or sent."""
    NAME = "5435"
    MAGIC, VERSION = 4135.0, 1.0
    PACKET = struct.Struct("<16f")
    SEQ_COL = "adv_seq"
    ECHO_N = ADV_UDP_MIN                       # 31 (echo_sizes)
    PORT_KEY, PORT_DEFAULT = "adv_port", 5435
    COUNTER = None
    KEEP: Dict[str, float] = {}                # NaN = keep (any invalid value keeps the one in use)
    TAIL = ()                                  # slots come from the layout (SLOTS): reserved = 0
    UNSET: Dict[str, float] = {}

    LAYOUT = ADV_LAYOUT

    def __init__(self, cfg, echo_fn, layout_path: Optional[str] = None, **kw):
        fields, rules, lay = load_adv_layout(layout_path or self.LAYOUT)
        # every packet slot by index, as in the layout (run 16c: [14] reserved_spring, [15]
        # standstill_fade_ms; run 15/16b: [14] reserved_spring, [15] reserved)
        self.SLOTS = [f["name"] for f in sorted(lay["fields"], key=lambda x: x["index"])]
        assert struct.calcsize(lay["format"]) == self.PACKET.size == 4 * len(self.SLOTS), lay["format"]
        assert self.SLOTS[:3] == ["magic", "version", "seq"], self.SLOTS[:3]
        self.FIELDS = tuple(fields)
        self.ECHO_COL = {f: f for f in fields}           # 5433 cols 18-28 carry the same names
        self.RULES = rules
        super().__init__(cfg, echo_fn, **kw)

    def valid(self, field: str, v: Any) -> bool:
        r = self.RULES.get(field)
        try:
            f = float(v)
        except (TypeError, ValueError):
            return False
        if r is None or not math.isfinite(f) or not (r["min"] <= f <= r["max"]):
            return False
        return not r["int"] or f == int(f)

    def same(self, field: str, a: Any, b: Any) -> bool:
        try:
            return abs(float(a) - float(b)) <= 1e-4 * max(1.0, abs(float(b)))
        except (TypeError, ValueError):
            return False

    def in_use(self, field: str) -> Optional[float]:
        if field in self.pending:
            return self.pending[field]["value"]
        v = (self.state or {}).get(field)
        return v if v is not None and self.valid(field, v) else None

    def check(self, field: str, value: Any) -> Optional[str]:
        r = self.RULES.get(field)
        if r is None:
            return f"{field}: not an Advanced value"
        try:
            f = float(value)
        except (TypeError, ValueError):
            return "not a number"
        if not math.isfinite(f) or not (r["min"] <= f <= r["max"]):
            return f"{f:g} is outside {r['min']:g}..{r['max']:g}"
        if r["int"] and f != int(f):
            return f"must be a whole number ({r['min']:g}..{r['max']:g})"
        # min < max, else the model keeps both: refused here instead of a silent keep
        if field == "sv_target_min":
            hi = self.in_use("sv_target_max")
            if hi is not None and f >= hi:
                return f"must be below the max target speed ({hi:g})"
        if field == "sv_target_max":
            lo = self.in_use("sv_target_min")
            if lo is not None and f <= lo:
                return f"must be above the min target speed ({lo:g})"
        return None

    def check_many(self, values: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        """A Confirm may change min AND max target speed together: the pair is checked with
        the batch's values (the other one from the device when it is not in the batch)."""
        pair = ("sv_target_min", "sv_target_max")
        for f, v in values.items():
            if f in pair:
                r = self.RULES.get(f)
                try:
                    x = float(v)
                except (TypeError, ValueError):
                    return f, "not a number"
                if r is None:
                    return f, "not an Advanced value"
                if not math.isfinite(x) or not (r["min"] <= x <= r["max"]):
                    return f, f"{x:g} is outside {r['min']:g}..{r['max']:g}"
                continue
            why = self.check(f, v)
            if why:
                return f, why
        if any(f in values for f in pair):
            lo = float(values["sv_target_min"]) if "sv_target_min" in values else self.in_use("sv_target_min")
            hi = float(values["sv_target_max"]) if "sv_target_max" in values else self.in_use("sv_target_max")
            if lo is not None and hi is not None and lo >= hi:
                f = "sv_target_min" if "sv_target_min" in values else "sv_target_max"
                return f, f"min target speed ({lo:g}) must be below the max ({hi:g})"
        return None

    def _packet(self, values: Dict[str, float]):
        """seq = echoed adv_seq + 1 for a fresh press (nothing pending); retries and a press
        while another is pending count on from the last seq sent. Slots by the layout:
        reserved ones 0, a value the echo does not carry (e.g. the fade on a 44-float run-16b
        build) NaN = keep."""
        if not self.pending or all(not p["seqs"] for p in self.pending.values()):
            row, age, cols = self._echo()
            try:
                self.seq = int(float(row.get(self.SEQ_COL)))
            except (TypeError, ValueError):
                pass
        self.seq += 1
        out = []
        for name in self.SLOTS:
            if name == "magic":
                out.append(self.MAGIC)
            elif name == "version":
                out.append(self.VERSION)
            elif name == "seq":
                out.append(float(self.seq))
            elif name.startswith("reserved"):
                out.append(0.0)
            elif name == "assist_ramp_step" and (self.state or {}).get(name) is None and name not in self.pending:
                # [14] was reserved_spring before run 16g: a build that does not echo the ramp
                # step gets 0 there (ignored), as before; on 16g the echoed step in use is sent
                # (never 0 by accident: that would switch the fade-in off on every Confirm)
                out.append(0.0)
            else:
                out.append(float(values.get(name, float("nan"))))
        return tuple(out)

    def rules_for_page(self) -> Dict[str, Dict[str, Any]]:
        """{session key: {min, max, int}} for the page's own check before sending."""
        return {k: dict(self.RULES[f]) for k, f in ADV_FIELD.items() if f in self.RULES}


# ---------------------------------------------------------------- run 16: torque guard (5436)
GUARD_LAYOUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "settings_guard_udp_layout.json")


class GuardLink(AdvLink):
    """Run 16: the 8 torque-guard settings over UDP 5436 ('<12f', magic 4136, seq echoed as
    guard_seq = 5433 col 43, values in use = cols 35-42) with the same adopt / confirm / retry /
    freeze rules. Active with a 44-float echo. No min < max pair here."""
    NAME = "5436"
    MAGIC, VERSION = 4136.0, 1.0
    PACKET = struct.Struct("<12f")
    SEQ_COL = "guard_seq"
    ECHO_N = GUARD_UDP_MIN                     # 44 (echo_sizes)
    PORT_KEY, PORT_DEFAULT = "guard_port", 5436
    LAYOUT = GUARD_LAYOUT                      # [11] reserved -> 0 (SLOTS)

    def check(self, field: str, value: Any) -> Optional[str]:
        r = self.RULES.get(field)
        if r is None:
            return f"{field}: not a torque-guard setting"
        try:
            f = float(value)
        except (TypeError, ValueError):
            return "not a number"
        if not math.isfinite(f) or not (r["min"] <= f <= r["max"]):
            return f"{f:g} is outside {r['min']:g}..{r['max']:g}"
        if r["int"] and f != int(f):
            return f"must be a whole number ({r['min']:g}..{r['max']:g})"
        return None

    def rules_for_page(self) -> Dict[str, Dict[str, Any]]:
        return {f: dict(r) for f, r in self.RULES.items()}
