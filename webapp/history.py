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
        # 5431 cols 23 (SV target), 24 (Uc), 27 (assistance level in use)
        self._extra: Dict[str, Deque[float]] = {k: deque(maxlen=cap) for k in ("sv_target", "uc", "assistance_level")}
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
        for channel in self._extra.values():
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
        for k, channel in self._extra.items():
            channel.append(f(sample.get(k, math.nan)))

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
            **{k: _env(ch) for k, ch in self._extra.items()},
            "statusword": self._status,
            # newest raw sample per channel for the numeric readouts (null if rejected)
            "latest": {
                "ankle": _last(self._ankle),
                "torque": _last(self._torque),
                "demand_torque": _last(self._demand),
                "gait": _last(self._gait),
                "press": [_last(ch) for ch in self._press],
                "imu": [_last(ch) for ch in self._imu],
                **{k: _last(ch) for k, ch in self._extra.items()},
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
            for channel in self._extra.values():
                channel.popleft()
            trimmed += 1
        self._last_trimmed = trimmed


class SlowBuffer:
    """Last 330 s of a few 5431 channels at ~100 Hz (one sample per 10 ms of
    model time) for the Live > Training plots (30 s / 2 min / 5 min)."""

    NAMES = ("sv", "sv_target", "uc", "assistance_level", "torque", "demand_torque")

    def __init__(self, keep_s: float = 330.0, dt: float = 0.01) -> None:
        self.keep_s, self.dt = keep_s, dt
        cap = int(keep_s / dt) + 1000
        self._t: Deque[float] = deque(maxlen=cap)
        self._v: Dict[str, Deque[float]] = {k: deque(maxlen=cap) for k in self.NAMES}
        self._last_bin = None

    def reset(self) -> None:
        self._t.clear()
        for d in self._v.values():
            d.clear()
        self._last_bin = None

    def add(self, sample: Dict[str, object]) -> None:
        try:
            t = float(sample.get("t"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        if not math.isfinite(t):
            return
        b = int(t // self.dt)
        if self._last_bin is not None and b <= self._last_bin:
            if b < self._last_bin - int(5.0 / self.dt):     # model restarted
                self.reset()
            else:
                return
        self._last_bin = b
        self._t.append(t)
        src = {"sv": sample.get("gait"), "torque": sample.get("torque")}
        for k, d in self._v.items():
            v = src[k] if k in src else sample.get(k)
            try:
                d.append(float(v))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                d.append(math.nan)
        while self._t and self._t[-1] - self._t[0] > self.keep_s:
            self._t.popleft()
            for d in self._v.values():
                d.popleft()

    def data(self, names, window_s: float, max_points: int = 1500) -> Dict[str, object]:
        n = len(self._t)
        if n == 0:
            return {"t_latest": None, "series": {}}
        t = np.fromiter(self._t, dtype=np.float64, count=n)
        newest = t[-1]
        m = t >= newest - float(window_s)
        tt = t[m]
        bw = max(float(window_s) / (max(32, int(max_points)) / 2.0), self.dt)
        bins = np.floor(tt / bw).astype(np.int64)
        starts = np.flatnonzero(np.concatenate(([True], bins[1:] != bins[:-1])))
        out: Dict[str, object] = {"t_latest": float(newest), "bin_width": bw, "series": {}}
        for nm in names:
            if nm not in self._v:
                continue
            y = np.fromiter(self._v[nm], dtype=np.float64, count=n)[m]
            with np.errstate(all="ignore"):
                lo = np.fmin.reduceat(y, starts)
                hi = np.fmax.reduceat(y, starts)
            x = np.empty(2 * len(starts))
            x[0::2] = bins[starts] * bw - newest
            x[1::2] = bins[starts] * bw + 0.5 * bw - newest
            v = np.empty(2 * len(starts))
            v[0::2], v[1::2] = lo, hi
            out["series"][nm] = {"t": [round(float(q), 4) for q in x],
                                 "v": [None if not math.isfinite(q) else float(f"{q:.6g}") for q in v]}
        return out
