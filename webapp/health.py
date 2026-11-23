"""Per-group data-health bookkeeping for the incoming stream.

Every decoded packet reports, per signal group, how many values it carried and
how many of them were rejected (non-finite or outside the plausible range).
Packet-level problems (wrong length, unusable time stamp, decode errors) are
counted against the "sync" group. The dashboard shows one lamp per group, so
a broken IMU turns its own lamp red while the FSR lamp stays green.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple

GROUPS = ("sync", "imu", "fsr", "drive")
PACKET_KINDS = ("bad_length", "bad_time", "stale_time", "time_jump", "errors", "lost")


class DataHealth:
    def __init__(self, window_sec: float = 10.0, bad_fraction: float = 0.2) -> None:
        self.window_sec = float(window_sec)
        self.bad_fraction = float(bad_fraction)
        self._lock = threading.Lock()
        self._totals = {g: [0, 0] for g in GROUPS}  # [bad, total]
        self._packets = {k: 0 for k in PACKET_KINDS}
        self._packets["ok"] = 0
        # one bucket per second: (second, {group: [bad, total]})
        self._buckets: Deque[Tuple[int, Dict[str, list]]] = deque()

    def _bucket(self, now: float) -> Dict[str, list]:
        sec = int(now)
        if not self._buckets or self._buckets[-1][0] != sec:
            self._buckets.append((sec, {g: [0, 0] for g in GROUPS}))
            cutoff = sec - int(self.window_sec)
            while self._buckets and self._buckets[0][0] < cutoff:
                self._buckets.popleft()
        return self._buckets[-1][1]

    def record(self, counts: Dict[str, Tuple[int, int]]) -> None:
        """Add per-group ``(bad, total)`` counts for one packet."""
        now = time.monotonic()
        with self._lock:
            bucket = self._bucket(now)
            for group, (bad, total) in counts.items():
                tot = self._totals.get(group)
                if tot is None:
                    continue
                tot[0] += bad
                tot[1] += total
                bucket[group][0] += bad
                bucket[group][1] += total
            self._packets["ok"] += 1

    def count_lost(self, n: int) -> None:
        """Packets never received (model-time gaps); not charged to a lamp group."""
        if n > 0:
            with self._lock:
                self._packets["lost"] = self._packets.get("lost", 0) + int(n)

    def count_packet(self, kind: str) -> None:
        """Count a packet-level problem; it is charged to the sync group."""
        now = time.monotonic()
        with self._lock:
            self._packets[kind] = self._packets.get(kind, 0) + 1
            bucket = self._bucket(now)
            bucket["sync"][0] += 1
            bucket["sync"][1] += 1
            self._totals["sync"][0] += 1
            self._totals["sync"][1] += 1

    def snapshot(self) -> Dict[str, object]:
        now = time.monotonic()
        with self._lock:
            cutoff = int(now) - int(self.window_sec)
            recent = {g: [0, 0] for g in GROUPS}
            for sec, bucket in self._buckets:
                if sec < cutoff:
                    continue
                for g in GROUPS:
                    recent[g][0] += bucket[g][0]
                    recent[g][1] += bucket[g][1]
            groups = {}
            for g in GROUPS:
                bad, total = recent[g]
                if total == 0:
                    state = "idle"
                elif bad == 0:
                    state = "ok"
                elif bad > self.bad_fraction * total:
                    state = "bad"
                else:
                    state = "warn"
                groups[g] = {
                    "state": state,
                    "recent_bad": bad,
                    "recent_total": total,
                    "bad_total": self._totals[g][0],
                    "total": self._totals[g][1],
                }
            return {"groups": groups, "packets": dict(self._packets), "window_sec": self.window_sec}
