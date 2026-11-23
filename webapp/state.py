import json
import math
import threading
from typing import Any, Dict, List, Optional, Tuple

# 100 Hz display series carried by every live message (history.DisplayHistory.payload)
SERIES = ("ankle", "torque", "demand_torque", "gait", "sv_target", "uc", "assistance_level", "ankle_vel",
          "heel_strike")


class DisplayWindow:
    """The full 100 Hz display window in the main process, merged from the worker's
    deltas (each carries the last ~0.5 s). A newly connecting page gets this window as
    its first message ("kind": "full"); every later message is a delta."""

    def __init__(self, seconds: float = 12.0, dt: float = 0.01) -> None:
        self.cap = int(round(seconds / dt))
        self.reset()

    def reset(self) -> None:
        self.t: List[float] = []
        self.series: Dict[str, list] = {k: [] for k in SERIES}
        self.press: List[list] = []
        self.imu: List[list] = []
        self.scalars: Dict[str, Any] = {}
        self.session = None

    def apply(self, d: Dict[str, Any]) -> None:
        t = d.get("t") or []
        sess = (d.get("meta") or {}).get("session")
        if (sess is not None and self.session is not None and sess != self.session) or                 (t and self.t and t[-1] < self.t[-1] - 1.0):
            self.reset()                      # target restarted: a new time base
        self.session = sess if sess is not None else self.session
        last = self.t[-1] if self.t else -math.inf
        i0 = 0
        while i0 < len(t) and t[i0] <= last:
            i0 += 1
        if i0 < len(t):
            self.t.extend(t[i0:])
            for k in SERIES:
                self.series[k].extend((d.get(k) or [None] * len(t))[i0:])
            for name in ("press", "imu"):
                src = d.get(name) or []
                dst = getattr(self, name)
                while len(dst) < len(src):
                    dst.append([None] * (len(self.t) - (len(t) - i0)))
                for j, ch in enumerate(src):
                    dst[j].extend(ch[i0:])
            if len(self.t) > self.cap + 200:      # trim in chunks (amortised)
                cut = len(self.t) - self.cap
                self.t = self.t[cut:]
                for k in SERIES:
                    self.series[k] = self.series[k][cut:]
                self.press = [ch[cut:] for ch in self.press]
                self.imu = [ch[cut:] for ch in self.imu]
        for k, v in d.items():
            if k not in SERIES and k not in ("t", "press", "imu", "kind"):
                self.scalars[k] = v

    def full_text(self) -> Optional[str]:
        if not self.t:
            return None
        out = dict(self.scalars)
        out.update(kind="full", t=self.t, press=self.press, imu=self.imu, **self.series)
        return json.dumps(out, allow_nan=False)


class SnapshotBroadcaster:
    """Hold the newest snapshot and wake every SSE client when it changes.

    The original single-slot queue handed each snapshot to only one client, so
    two open dashboards (laptop + tablet) split the updates between them. Here
    every client sees every snapshot; a slow client simply skips to the newest.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._seq = 0
        self._snap: Optional[Any] = None
        self.window = DisplayWindow()

    def publish(self, snapshot: Any) -> None:
        d = None
        if isinstance(snapshot, str):
            try:
                d = json.loads(snapshot)
            except ValueError:
                d = None
        elif isinstance(snapshot, dict):
            d = snapshot
            snapshot = json.dumps(snapshot, default=lambda o: None)
        with self._cond:
            if d is not None:
                try:
                    self.window.apply(d)
                except Exception:
                    self.window.reset()
            self._seq += 1
            self._snap = snapshot
            self._cond.notify_all()

    def full_text(self) -> Optional[str]:
        """The whole 100 Hz window (first message of a newly connecting page)."""
        with self._cond:
            return self.window.full_text()

    def clear(self) -> None:
        """Forget the current snapshot (used when the data source restarts)."""
        with self._cond:
            self._snap = None
            self.window.reset()

    def wait_next(self, last_seq: int, timeout: float) -> Tuple[int, Optional[Any]]:
        """Return ``(seq, snapshot)`` newer than *last_seq*, or ``(last_seq, None)`` on timeout."""
        with self._cond:
            if self._seq == last_seq or self._snap is None:
                self._cond.wait(timeout)
            if self._seq != last_seq and self._snap is not None:
                return self._seq, self._snap
            return last_seq, None

    @property
    def seq(self) -> int:
        with self._cond:
            return self._seq


# newest snapshot for the SSE clients
snapshots = SnapshotBroadcaster()

# Limit concurrent SSE clients
MAX_CLIENTS = 8
_active_clients = 0
_client_lock = threading.Lock()
