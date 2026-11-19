from __future__ import annotations

import math
from collections import deque
from typing import Deque, Dict, List

import numpy as np


class SignalHistory:
    """Keep a rolling time-series window capped by ``max_seconds``.

    Rejected values are stored as NaN (a gap in that trace only). The time
    axis itself only ever holds finite values, and every buffer also has a hard
    length cap, so a bad clock can never stall trimming or grow memory.
    """

    def __init__(
        self,
        max_seconds: float,
        press_channels: int = 8,
        imu_channels: int = 3,
        max_emit_points: int = 600,
        max_samples: int = 50000,
        bin_width: float = 0.02,
    ) -> None:
        self.max_seconds = max_seconds
        self._bin_width = float(bin_width)
        self._press_channels = press_channels
        self._imu_channels = imu_channels
        self._max_emit_points = max(32, int(max_emit_points))
        self._trim_margin = max(0.1, self.max_seconds * 0.05)
        cap = max(1000, int(max_samples))
        self._max_samples = cap

        self._t: Deque[float] = deque(maxlen=cap)
        self._ankle: Deque[float] = deque(maxlen=cap)
        self._torque: Deque[float] = deque(maxlen=cap)
        self._demand: Deque[float] = deque(maxlen=cap)
        self._gait: Deque[float] = deque(maxlen=cap)
        self._press: List[Deque[float]] = [deque(maxlen=cap) for _ in range(self._press_channels)]
        self._imu: List[Deque[float]] = [deque(maxlen=cap) for _ in range(self._imu_channels)]
        self._status: float = 0.0
        self._last_trimmed = 0

    def reset(self) -> None:
        """Drop every buffered sample.

        Called when the data source restarts: its time base goes back to zero,
        so mixing the old samples with the new ones would corrupt the window.
        """
        self._t.clear()
        self._ankle.clear()
        self._torque.clear()
        self._demand.clear()
        self._gait.clear()
        for channel in self._press:
            channel.clear()
        for channel in self._imu:
            channel.clear()
        self._status = 0.0
        self._last_trimmed = 0

    @staticmethod
    def _as_float(value: object) -> float:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return math.nan

    def add_sample(self, sample: Dict[str, float | List[float]]) -> None:
        """Append a decoded *sample* to the rolling window."""
        t_val = self._as_float(sample.get("t"))
        if not math.isfinite(t_val):
            # never put a non-finite time on the axis: trimming compares
            # against it, and NaN would stop the window from ever shrinking
            return
        f = self._as_float
        self._t.append(t_val)
        self._ankle.append(f(sample.get("ankle", math.nan)))
        self._torque.append(f(sample.get("torque", math.nan)))
        self._demand.append(f(sample.get("demand_torque", math.nan)))
        self._gait.append(f(sample.get("gait", math.nan)))

        press_vals = sample.get("press") or []
        imu_vals = sample.get("imu") or []
        for idx, channel in enumerate(self._press):
            try:
                channel.append(f(press_vals[idx]))  # type: ignore[index]
            except (IndexError, TypeError):
                channel.append(math.nan)
        for idx, channel in enumerate(self._imu):
            try:
                channel.append(f(imu_vals[idx]))  # type: ignore[index]
            except (IndexError, TypeError):
                channel.append(math.nan)

        # hold the last good status word: the button colour is derived from it
        status = f(sample.get("statusword", math.nan))
        if math.isfinite(status):
            self._status = status

        self._trim()

    def snapshot(self) -> Dict[str, object]:
        """Return a serialized snapshot for SSE clients.

        The 1 kHz stream is reduced to a min/max envelope over time bins that
        are anchored to absolute model time (bin = floor(t / bin_width)).
        Completed bins therefore come out identical in every snapshot, so the
        plot no longer "flashes" (the old stride decimation started at a
        different sample each update and narrow peaks aliased in and out), and
        a peak is never lost: each bin keeps both its minimum and maximum.
        All series share one x axis (two points per bin: bin start and bin
        middle). A bin whose values were all rejected is a gap (NaN -> null).
        """
        length = len(self._t)
        if length == 0:
            return {}

        t = np.fromiter(self._t, dtype=np.float64, count=length)
        bw = self._bin_width
        bins = np.floor(t / bw).astype(np.int64)
        # the time axis is strictly increasing (network.py drops stale/rewound
        # samples), so equal bin numbers are contiguous
        starts = np.flatnonzero(np.concatenate(([True], bins[1:] != bins[:-1])))
        if len(starts) > 2:
            # the oldest bin is being trimmed sample by sample, so its min/max
            # would change between updates: start at the first whole bin
            first = starts[1]
            starts = starts[1:] - first
            t = t[first:]
            bins = bins[first:]
        else:
            first = 0
        nb = len(starts)
        length_used = length - first
        x = np.empty(2 * nb)
        x[0::2] = bins[starts] * bw
        x[1::2] = bins[starts] * bw + 0.5 * bw

        def _env(series: Deque[float]) -> np.ndarray:
            y = np.fromiter(series, dtype=np.float64, count=length)[first:]
            out = np.empty(2 * nb)
            with np.errstate(all="ignore"):
                # fmin/fmax skip NaN; an all-NaN bin stays NaN (a gap)
                out[0::2] = np.fmin.reduceat(y, starts)
                out[1::2] = np.fmax.reduceat(y, starts)
            return out

        def _last(series: Deque[float]) -> float | None:
            v = series[-1] if series else math.nan
            return v if math.isfinite(v) else None

        payload = {
            # bin times are multiples of bin_width; rounding strips float noise
            # (1597.1200000000001 -> 1597.12) so the JSON stays short and exact
            "t": [round(v, 6) for v in x.tolist()],
            "t_latest": float(t[-1]),
            "bin_width": bw,
            "ankle": _env(self._ankle),
            "torque": _env(self._torque),
            "demand_torque": _env(self._demand),
            "gait": _env(self._gait),
            "press": [_env(ch) for ch in self._press],
            "imu": [_env(ch) for ch in self._imu],
            "statusword": self._status,
            # newest raw sample per channel for the numeric readouts (null if rejected)
            "latest": {
                "ankle": _last(self._ankle),
                "torque": _last(self._torque),
                "demand_torque": _last(self._demand),
                "gait": _last(self._gait),
                "press": [_last(ch) for ch in self._press],
                "imu": [_last(ch) for ch in self._imu],
            },
        }
        payload["meta"] = {
            "emit_points": int(2 * nb),
            "source_points": length,
            "samples_trimmed": self._last_trimmed,
        }
        return payload

    def _trim(self) -> None:
        if not self._t:
            return
        cutoff = self._t[-1] - (self.max_seconds + self._trim_margin)
        trimmed = 0
        while self._t and self._t[0] < cutoff:
            self._t.popleft()
            self._ankle.popleft()
            self._torque.popleft()
            self._demand.popleft()
            self._gait.popleft()
            for channel in self._press:
                channel.popleft()
            for channel in self._imu:
                channel.popleft()
            trimmed += 1
        self._last_trimmed = trimmed
