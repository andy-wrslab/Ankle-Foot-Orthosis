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

        # ankle velocity (computed, deg/s): derivative of the per-bin mean ankle angle,
        # smoothed over 5 bins (0.1 s at 20 ms bins); two points per bin like the envelopes
        ank = np.fromiter(self._ankle, dtype=np.float64, count=length)[first:]
        with np.errstate(all="ignore"):
            ok = np.isfinite(ank)
            sums = np.add.reduceat(np.where(ok, ank, 0.0), starts)
            cnt = np.add.reduceat(ok.astype(np.float64), starts)
            mean = np.where(cnt > 0, sums / np.maximum(cnt, 1), np.nan)
            vel = np.gradient(mean, bw) if nb >= 2 else np.full(nb, np.nan)
            if nb >= 5:
                k = np.ones(5) / 5.0
                good = np.isfinite(vel)
                num = np.convolve(np.where(good, vel, 0.0), k, mode="same")
                den = np.convolve(good.astype(np.float64), k, mode="same")
                vel = np.where(den > 0.5, num / np.maximum(den, 1e-9), np.nan)
        ankle_vel = np.empty(2 * nb)
        ankle_vel[0::2] = vel
        ankle_vel[1::2] = vel
        fin = vel[np.isfinite(vel)]
        ankle_vel_last = float(fin[-1]) if fin.size else None

        payload = {
            # bin times are multiples of bin_width; rounding strips float noise
            # (1597.1200000000001 -> 1597.12) so the JSON stays short and exact
            "t": [round(v, 6) for v in x.tolist()],
            "t_latest": float(t[-1]),
            "bin_width": bw,
            "ankle": _env(self._ankle),
            "ankle_vel": ankle_vel,
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
                "ankle_vel": ankle_vel_last,
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


DISPLAY_CHANNELS = ("ankle", "torque", "demand_torque", "gait", "sv_target", "uc", "assistance_level")


class DisplayHistory:
    """100 Hz display history of the 1 kHz main bus (Nov 23).

    One point per 10 ms bin = the bin MEAN of every channel (NaN-aware; a bin with
    no valid value is a gap), heel_strike = 1 if any sample in the bin had it.
    The point's time is the bin start in model seconds. ankle_vel (computed) is
    the derivative of consecutive ankle means, smoothed over 5 points (50 ms).
    The 1 kHz record is the Speedgoat file log; this is only for the page.
    """

    def __init__(self, max_seconds: float = 10.0, press_channels: int = 8, imu_channels: int = 12,
                 dt: float = 0.01) -> None:
        self.dt = float(dt)
        self.max_seconds = float(max_seconds)
        self.cap = int(round(self.max_seconds / self.dt)) + 50
        self.npress, self.nimu = press_channels, imu_channels
        self.reset()

    def reset(self) -> None:
        cap = self.cap
        self.t: Deque[float] = deque(maxlen=cap)
        self.ch: Dict[str, Deque[float]] = {k: deque(maxlen=cap) for k in DISPLAY_CHANNELS + ("ankle_vel", "heel_strike")}
        self.press: List[Deque[float]] = [deque(maxlen=cap) for _ in range(self.npress)]
        self.imu: List[Deque[float]] = [deque(maxlen=cap) for _ in range(self.nimu)]
        self._bin = None
        self._acc = None
        self._vel_raw: Deque[float] = deque(maxlen=5)
        self._prev_ankle = math.nan
        self.status = 0.0

    def _new_acc(self):
        n = len(DISPLAY_CHANNELS) + self.npress + self.nimu
        return {"sum": [0.0] * n, "cnt": [0] * n, "heel": 0.0}

    def add(self, sample: Dict[str, object]) -> bool:
        """Add one 1 kHz sample; True when a 10 ms point was completed."""
        try:
            t = float(sample.get("t"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        if not math.isfinite(t):
            return False
        b = int(math.floor(t / self.dt + 1e-9))
        closed = False
        if self._bin is not None and b != self._bin:
            if b < self._bin:            # time went back (restart): start over
                self.reset()
            else:
                self._close()
                closed = True
        if self._bin is None or b != self._bin:
            self._bin, self._acc = b, self._new_acc()
        acc = self._acc
        vals = [sample.get(k) for k in DISPLAY_CHANNELS]
        press = sample.get("press") or []
        imu = sample.get("imu") or []
        vals += [press[i] if i < len(press) else None for i in range(self.npress)]  # type: ignore[index]
        vals += [imu[i] if i < len(imu) else None for i in range(self.nimu)]        # type: ignore[index]
        for i, v in enumerate(vals):
            try:
                f = float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if math.isfinite(f):
                acc["sum"][i] += f
                acc["cnt"][i] += 1
        hs = sample.get("heel_strike")
        try:
            if hs is not None and float(hs) >= 0.5:  # type: ignore[arg-type]
                acc["heel"] = 1.0
        except (TypeError, ValueError):
            pass
        st = sample.get("statusword")
        try:
            if st is not None and math.isfinite(float(st)):  # type: ignore[arg-type]
                self.status = float(st)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass
        return closed

    def _close(self) -> None:
        acc = self._acc
        means = [(s / c) if c else math.nan for s, c in zip(acc["sum"], acc["cnt"])]
        self.t.append(round(self._bin * self.dt, 6))
        nd = len(DISPLAY_CHANNELS)
        for i, k in enumerate(DISPLAY_CHANNELS):
            self.ch[k].append(means[i])
        for i in range(self.npress):
            self.press[i].append(means[nd + i])
        for i in range(self.nimu):
            self.imu[i].append(means[nd + self.npress + i])
        self.ch["heel_strike"].append(acc["heel"])
        a = means[0]
        raw = (a - self._prev_ankle) / self.dt if math.isfinite(a) and math.isfinite(self._prev_ankle) else math.nan
        self._prev_ankle = a
        self._vel_raw.append(raw)
        good = [v for v in self._vel_raw if math.isfinite(v)]
        self.ch["ankle_vel"].append(sum(good) / len(good) if len(good) >= 3 else math.nan)

    def payload(self, since: float | None = None) -> Dict[str, object]:
        """Points with t > since (all when None) + the latest values, as plain lists."""
        n = len(self.t)
        if n == 0:
            return {}
        t = list(self.t)
        i0 = 0
        if since is not None:
            i0 = n
            while i0 > 0 and t[i0 - 1] > since:
                i0 -= 1

        def clean(v):
            # strict JSON: NaN -> null (a gap); 6 significant digits keep messages small
            return None if v != v or v in (math.inf, -math.inf) else float(f"{v:.6g}")

        def sl(d):
            return [clean(v) for v in list(d)[i0:]]

        def last(d):
            v = d[-1] if d else math.nan
            return clean(v)

        out: Dict[str, object] = {"t": t[i0:], "t_latest": t[-1], "dt": self.dt}
        for k, d in self.ch.items():
            out[k] = sl(d)
        out["press"] = [sl(d) for d in self.press]
        out["imu"] = [sl(d) for d in self.imu]
        out["statusword"] = self.status
        out["latest"] = {**{k: last(d) for k, d in self.ch.items()},
                         "press": [last(d) for d in self.press], "imu": [last(d) for d in self.imu]}
        return out
