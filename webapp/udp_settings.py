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
"""
from __future__ import annotations

import logging
import math
import socket
import struct
import threading
import time
from typing import Any, Callable, Dict, Optional

MAGIC, VERSION = 4134.0, 1.0
PACKET = struct.Struct("<8f")
FIELDS = ("side", "mass", "mode", "k", "gyro")          # packet slots 3..7
ECHO_COL = {"side": "side", "mass": "bif_mass_kg", "mode": "assist_mode", "k": "fixed_k_pct",
            "gyro": "gyro_cal_request"}
ECHO_N = 18
STALE_S = 0.75             # echo older than this: link stalled -> frozen
RETRY_EVERY_S = 0.25       # resend after 0.25, 0.5, 0.75 s ...
MAX_RETRIES = 3
CONFIRM_WINDOW_S = 1.0     # ... and give up at 1 s
FROZEN_MSG = "No data from device: settings unchanged on the device"
NOT_CONFIRMED_MSG = "Not confirmed: no echo from model"

_log = logging.getLogger("afo.udp_settings")


def valid(field: str, v: Any) -> bool:
    """What the model accepts per field (anything else keeps its last value)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(f):
        return False
    return {"side": f in (-1.0, 0.0, 1.0), "mass": 0.0 <= f <= 300.0, "mode": f in (1.0, 3.0),
            "k": 0.0 <= f <= 10.0, "gyro": f >= 0.0}[field]


def same(field: str, a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) <= (1e-3 if field in ("side", "mode", "gyro") else 1e-2)
    except (TypeError, ValueError):
        return False


class SettingsLink:
    """One per app. echo_fn() -> (latest 5433 row dict or {}, its age in s or None, columns)."""

    def __init__(self, cfg: Dict[str, Any], echo_fn: Callable[[], tuple], view_only: bool = False,
                 on_status: Optional[Callable[[str, str, str], None]] = None, sender=None, start_thread: bool = True,
                 on_adopt: Optional[Callable[[Dict[str, float]], None]] = None):
        u = cfg.get("udp") or {}
        self.addr = (str(u.get("send_host", "192.168.7.5")), int(u.get("session_port", 5434)))
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
            threading.Thread(target=self._loop, name="udp-settings", daemon=True).start()

    # ------------------------------------------------------------ echo
    def _echo(self):
        try:
            row, age, cols = self.echo_fn()
        except Exception:
            return {}, None, None
        return row or {}, age, cols

    def active(self) -> bool:
        """This profile is on: the 5433 echo has the 18-float run-14 layout."""
        row, age, cols = self._echo()
        return cols == ECHO_N or ("settings_seq" in row and row.get("settings_seq") is not None)

    def _adopt(self, row: Dict[str, Any]) -> None:
        st = {f: float(row[ECHO_COL[f]]) for f in FIELDS if row.get(ECHO_COL[f]) is not None}
        self.state = st
        try:
            self.seq = max(self.seq, int(float(row.get("settings_seq") or 0)))
        except (TypeError, ValueError):
            pass
        self.adopted_at = time.time()
        _log.info("adopted device settings %s (seq %d)", st, self.seq)

    # ------------------------------------------------------------ send
    def _send(self, pkt) -> None:
        self.sent.append((time.time(), pkt))
        del self.sent[:-50]
        data = PACKET.pack(*pkt)
        if self._sender is not None:
            self._sender(data, self.addr)
            return
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.sendto(data, self.addr)

    def _packet(self, values: Dict[str, float]):
        self.seq += 1
        return (MAGIC, VERSION, float(self.seq), values["side"], values["mass"], values["mode"], values["k"],
                values["gyro"])

    def _values(self) -> Dict[str, float]:
        """Adopted device values with every still-pending press applied."""
        v = dict(self.state or {})
        for f, p in self.pending.items():
            v[f] = p["value"]
        for f, dflt in (("side", -1.0), ("mass", 0.0), ("mode", 3.0), ("k", 0.0), ("gyro", 0.0)):
            v.setdefault(f, dflt)
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
            if not valid(field, value):
                return {"ok": False, "state": "error", "msg": f"{field} {value!r} is not a valid value"}
            v = self._values()
            v[field] = float(value)
            pkt = self._packet(v)
            self.pending[field] = {"value": float(value), "seqs": [pkt[2]], "t0": time.time(), "last": time.time(), "tries": 0}
            self.result[field] = {"state": "sending", "msg": "", "at": time.time()}
            self._send(pkt)
        self.on_status(field, "sending", "")
        return {"ok": True, "state": "sending", "msg": ""}

    def after_start(self) -> Optional[tuple]:
        """Start reloads the app (side -1, mass 0 until the first valid packet): send the
        page's values once."""
        with self.lock:
            if self.view_only or self.frozen or self.state is None:
                return None
            v = self._values()
            pkt = self._packet(v)
            for f in ("side", "mass", "mode", "k"):
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
                    _log.warning("5433 echo stalled: settings frozen (nothing sent)")
                    for f in list(self.pending):
                        changes.append((f, "error", FROZEN_MSG))
                        self.result[f] = {"state": "error", "msg": FROZEN_MSG, "at": time.time()}
                    self.pending.clear()
            for f, st, m in changes:
                self.on_status(f, st, m)
            return
        with self.lock:
            if cols is not None and cols != ECHO_N and "settings_seq" not in row:
                return                              # runs 12/13: not this profile
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
                last_seq = float(row.get("settings_seq") or 0)
            except (TypeError, ValueError):
                last_seq = 0.0
            now = time.time()
            for f, p in list(self.pending.items()):
                if last_seq >= min(p["seqs"]) and same(f, row.get(ECHO_COL[f]), p["value"]):
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
                    pkt = self._packet(self._values())
                    p["seqs"].append(pkt[2]); p["last"] = now; p["tries"] += 1
                    self._send(pkt)
            # keep the adopted copy current for fields nobody is changing
            for f in FIELDS:
                if f not in self.pending and row.get(ECHO_COL[f]) is not None:
                    self.state[f] = float(row[ECHO_COL[f]])
        for f, s, m in changes:
            self.on_status(f, s, m)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                _log.exception("udp settings tick failed")
            time.sleep(0.02)

    def stop(self):
        self._stop.set()

    def view(self) -> Dict[str, Any]:
        with self.lock:
            return {"active": self.active(), "frozen": self.frozen, "msg": FROZEN_MSG if self.frozen else "",
                    "adopted": dict(self.state) if self.state else None, "seq": self.seq,
                    "pending": sorted(self.pending), "result": {k: dict(v) for k, v in self.result.items()}}
