"""Decode saved Speedgoat trial logs and check their data health.

Reads (never modifies) the SDI-export .mat files (MATLAB v7.3 / HDF5) directly
from their '#sigstream#' group: the stream with 124-byte samples is the 31 x
float32 bus in config.yaml column order; the 28-byte stream holds 7 float32
drive values. The tee captures (_claude_live/tee_*.bin) are read too.
Decoded arrays are cached as .npz under cache/trials/.

Run as a separate process by the web app:  python trials_data.py <source> <cache_prefix>
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import sys
import time
from typing import Any, Dict, List

import numpy as np

BUS_NAMES = [
    "time", "treadmill_velocity", "ankle_angle",
    "pressure_1", "pressure_2", "pressure_3", "pressure_4",
    "pressure_5", "pressure_6", "pressure_7", "pressure_8",
    "accel_x", "accel_y", "accel_z", "yaw", "pitch", "roll",
    "gyro_x", "gyro_y", "gyro_z", "raw_accel_x", "raw_accel_y", "raw_accel_z",
    "gait_percentage", "shifted_angle_moment", "actual_torque", "heel_strike",
    "assistance_level", "demand_torque", "statusword", "sync",
]
DRIVE_NAMES = [f"drive_{i + 1}" for i in range(7)]
IMU_COLS = list(range(11, 23))
TEENSY_COLS = list(range(3, 23))      # pressure + IMU fields come from the Teensy
TEE_REC = struct.Struct("<dH")


def cache_prefix(cache_dir: str, src: str) -> str:
    st = os.stat(src)
    key = hashlib.sha1(f"{os.path.abspath(src)}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:12]
    base = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(cache_dir, f"{base}_{key}")


def decode(src: str) -> Dict[str, Any]:
    if src.lower().endswith(".bin"):
        return _decode_tee(src)
    import h5py
    try:
        f = h5py.File(src, "r")
    except OSError:
        import scipy.io
        names = [w[0] for w in scipy.io.whosmat(src)][:30]
        raise ValueError(f"not an HDF5 (v7.3) Speedgoat log; MATLAB variables: {names}")
    with f:
        if "#sigstream#" not in f:
            raise ValueError(f"no '#sigstream#' group (not a Speedgoat SDI export); top-level: {list(f.keys())[:20]}")
        g = f["#sigstream#"]
        bus = drive = None
        layout = []
        for k in sorted((k for k in g.keys() if not k.startswith("#")), key=int):
            s = g[k]
            n = int(s["#length#"][0])
            ss = int(s["#sampleSize#"][0])
            layout.append({"stream": int(k), "samples": n, "sample_size": ss})
            if ss == 124 and bus is None:
                bus = np.asarray(s["#data#"][: n * ss]).view("<f4").reshape(n, 31)
            elif ss == 28 and drive is None:
                drive = np.asarray(s["#data#"][: n * ss]).view("<f4").reshape(n, 7)
        if bus is None:
            raise ValueError(f"no 124-byte bus stream in this file; streams: {layout}")
    return {"t": bus[:, 0].astype(np.float64), "bus": bus, "drive": drive, "layout": layout, "format": "sdi-mat"}


def _decode_tee(src: str) -> Dict[str, Any]:
    data = open(src, "rb").read()
    rows, recv, pos = [], [], 0
    while pos + TEE_REC.size <= len(data):
        t, n = TEE_REC.unpack_from(data, pos)
        pos += TEE_REC.size
        if pos + n > len(data):
            break
        if n == 124:
            rows.append(data[pos:pos + n])
            recv.append(t)
        pos += n
    bus = np.frombuffer(b"".join(rows), dtype="<f4").reshape(-1, 31)
    return {"t": bus[:, 0].astype(np.float64), "bus": bus, "drive": None,
            "layout": [{"stream": "tee", "samples": len(rows), "sample_size": 124}], "format": "tee-bin",
            "recv_start": recv[0] if recv else None}


def _segments(t: np.ndarray, mask: np.ndarray, merge_gap: float = 0.5, limit: int = 12) -> List[List[float]]:
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return []
    tt = t[idx]
    breaks = np.flatnonzero(np.diff(tt) > merge_gap)
    starts = np.concatenate(([0], breaks + 1))
    ends = np.concatenate((breaks, [idx.size - 1]))
    return [[round(float(tt[a]), 3), round(float(tt[b]), 3)] for a, b in zip(starts[:limit], ends[:limit])]


def _slip_k(rows: np.ndarray) -> Dict[str, Any]:
    """Best byte shift explaining garbage IMU rows (see _claude_live/imu_slip_analysis.py)."""
    def mem(r):
        vals = (r[22], r[21], r[20], r[19], r[18], r[17], r[13], r[12], r[11])
        return b"".join(struct.pack("<f", float(v)) for v in vals)

    def dec(m, k):
        n = 52
        tmp = [None] * n
        for i in range(36):
            tmp[n - 1 - i] = m[i]
        P = [tmp[(p - k) % n] for p in range(n)]
        M = [P[n - 1 - i] for i in range(n)]
        out = []
        for off in range(0, 36, 4):
            b = M[off:off + 4]
            out.append(np.nan if any(x is None for x in b) else struct.unpack("<f", bytes(b))[0])
        rz, ry, rx, gz, gy, gx, az, ay, ax = out
        return (rx, ry, rz), (gx, gy, gz), (ax, ay, az)

    def score(raw, gyro, lacc):
        s, used = 0.0, 0
        for vec, kind in ((raw, "raw"), (gyro, "g"), (lacc, "l")):
            v = np.array(vec, dtype=float)
            if not np.all(np.isfinite(v)):
                continue
            used += 1
            if kind == "raw":
                m = np.linalg.norm(v)
                s += min(abs(m - 1.0), abs(m - 9.81) / 9.81)
            else:
                s += min(np.linalg.norm(v), 10.0) / 10.0
        return (s / used, used) if used else (math.inf, 0)

    best = []
    for k in range(52):
        sc = []
        for r in rows[:60]:
            if k == 0:
                v, u = score(r[20:23], r[17:20], r[11:14])
            else:
                with np.errstate(all="ignore"):
                    v, u = score(*dec(mem(r), k))
            if u >= 2:
                sc.append(v)
        if sc:
            best.append((float(np.median(sc)), k))
    best.sort()
    return {"k": best[0][1] if best else None, "score": round(best[0][0], 4) if best else None,
            "slip_bytes": None if not best else (52 - best[0][1]) % 52}


def analyse(d: Dict[str, Any]) -> Dict[str, Any]:
    t, bus = d["t"], d["bus"]
    n = len(t)
    issues: List[Dict[str, Any]] = []
    channels = []
    big = np.zeros(n, dtype=bool)
    for c, name in enumerate(BUS_NAMES):
        x = bus[:, c]
        nan = np.isnan(x)
        inf = np.isinf(x)
        with np.errstate(invalid="ignore"):
            huge = np.abs(x) > 1e6
        huge &= ~inf
        bad = nan | inf | huge
        if c in IMU_COLS:
            big |= bad
        info = {"col": c, "name": name, "nan": int(nan.sum()), "inf": int(inf.sum()), "over_1e6": int(huge.sum())}
        if bad.any():
            info["segments"] = _segments(t, bad)
        channels.append(info)
        if bad.any() and c not in IMU_COLS:
            for s0, s1 in info["segments"][:5]:
                issues.append({"kind": "bad values", "channel": name, "t0": s0, "t1": s1,
                               "detail": f"NaN {info['nan']}, Inf {info['inf']}, >1e6 {info['over_1e6']} in total"})
    # IMU byte slip: windows of 1 s where >5 % of IMU values are garbage
    sec = np.floor(t).astype(np.int64)
    if big.any():
        bad_rows = np.zeros(n, dtype=float)
        with np.errstate(invalid="ignore"):
            frac = np.array([np.mean(~np.isfinite(bus[i, IMU_COLS]) | (np.abs(bus[i, IMU_COLS]) > 1e6))
                             for i in range(0, n, 50)])
        coarse_t = t[::50]
        mask = np.repeat(frac > 0.05, 50)[:n]
        for s0, s1 in _segments(t, mask, merge_gap=2.0, limit=8):
            i0 = int(np.searchsorted(t, s0))
            rows = bus[i0:i0 + 2000:20]
            k = _slip_k(rows)
            detail = f"IMU garbage (NaN/±1e38) for {s1 - s0:.1f} s"
            if k["k"] not in (None, 0) and k["score"] is not None and k["score"] < 0.05:
                detail += f"; explained by a {k['slip_bytes']}-byte slip (k={k['k']}, score {k['score']})"
            issues.append({"kind": "IMU byte slip", "channel": "IMU", "t0": s0, "t1": s1, "detail": detail, **k})
    # frozen Teensy: at least 85 % of the pressure + IMU fields have not changed
    # for > 0.5 s (a couple of pressure columns are filtered on the Speedgoat and
    # keep drifting slightly even when the Teensy data stops)
    dt = float(np.median(np.diff(t[: min(n, 5000)]))) if n > 2 else 0.001
    run_min = int(round(0.5 / max(dt, 1e-4)))
    idx = np.arange(n)
    frozen_cols = np.zeros(n, dtype=np.int16)
    for c in TEENSY_COLS:
        x = bus[:, c]
        changed = np.concatenate(([True], (x[1:] != x[:-1]) & ~(np.isnan(x[1:]) & np.isnan(x[:-1]))))
        last_change = np.maximum.accumulate(np.where(changed, idx, 0))
        frozen_cols += (idx - last_change) >= run_min
    frozen = frozen_cols >= int(math.ceil(0.85 * len(TEENSY_COLS)))
    for s0, s1 in _segments(t, frozen, merge_gap=0.1, limit=10):
        s0 = max(float(t[0]), s0 - 0.5)  # the freeze began one detection window earlier
        issues.append({"kind": "Teensy frozen", "channel": "pressure+IMU", "t0": round(s0, 3), "t1": s1,
                       "detail": f"Teensy fields stopped changing for {s1 - s0:.2f} s"})
    # EtherCAT sync anomalies
    sync = bus[:, 30]
    with np.errstate(invalid="ignore"):
        odd = np.isfinite(sync) & (sync != 0) & (sync != 1)
    for s0, s1 in _segments(t, odd, limit=5):
        issues.append({"kind": "sync anomaly", "channel": "sync", "t0": s0, "t1": s1,
                       "detail": f"sync not 0/1 ({int(odd.sum())} samples in total)"})
    # time base
    dtt = np.diff(t)
    back = np.flatnonzero(dtt <= 0)
    gaps = np.flatnonzero(dtt > 10 * dt)
    for i in list(back[:3]):
        issues.append({"kind": "time went backwards", "channel": "time", "t0": round(float(t[i]), 3),
                       "t1": round(float(t[i + 1]), 3), "detail": f"{t[i]:.3f} -> {t[i + 1]:.3f}"})
    for i in list(gaps[:3]):
        issues.append({"kind": "time gap", "channel": "time", "t0": round(float(t[i]), 3),
                       "t1": round(float(t[i + 1]), 3), "detail": f"{dtt[i] * 1000:.0f} ms without samples"})
    issues.sort(key=lambda x: x["t0"])
    return {"samples": int(n), "t_start": float(t[0]) if n else None, "t_end": float(t[-1]) if n else None,
            "dt": float(dt), "channels": channels, "issues": issues, "layout": d.get("layout"),
            "format": d.get("format")}


def build_cache(src: str, prefix: str) -> Dict[str, Any]:
    t0 = time.time()
    d = decode(src)
    health = analyse(d)
    os.makedirs(os.path.dirname(prefix), exist_ok=True)
    arrays = {"t": d["t"], "bus": d["bus"]}
    if d.get("drive") is not None:
        arrays["drive"] = d["drive"]
    tmp = prefix + ".tmp.npz"
    np.savez(tmp, **arrays)
    os.replace(tmp, prefix + ".npz")
    health["source"] = src
    health["decode_s"] = round(time.time() - t0, 1)
    with open(prefix + "_health.json", "w", encoding="utf-8") as fp:
        json.dump(health, fp)
    return health


def list_sources(afo_root: str) -> List[Dict[str, Any]]:
    out = []

    def add(path, group):
        try:
            st = os.stat(path)
        except OSError:
            return
        out.append({"path": path, "name": os.path.relpath(path, afo_root), "group": group,
                    "mb": round(st.st_size / 1e6, 1), "mtime": st.st_mtime})

    for f in os.listdir(afo_root):
        if f.lower().endswith(".mat"):
            add(os.path.join(afo_root, f), "AFO")
    mat_dir = os.path.join(afo_root, "afo_mat")
    if os.path.isdir(mat_dir):
        for d in os.listdir(mat_dir):
            sub = os.path.join(mat_dir, d)
            if os.path.isdir(sub):
                for f in os.listdir(sub):
                    if f.lower().endswith(".mat"):
                        add(os.path.join(sub, f), "afo_mat")
    live = os.path.join(afo_root, "_claude_live")
    if os.path.isdir(live):
        for f in os.listdir(live):
            if (f.startswith("tee_") and f.endswith(".bin")) or (f.startswith("runcontrol_test_") and f.endswith(".mat")):
                add(os.path.join(live, f), "live captures")
    out.sort(key=lambda r: -r["mtime"])
    return out


if __name__ == "__main__":
    src, prefix = sys.argv[1], sys.argv[2]
    try:
        h = build_cache(src, prefix)
        print(json.dumps({"ok": True, "samples": h["samples"], "issues": len(h["issues"]), "decode_s": h["decode_s"]}))
    except Exception as exc:
        print(json.dumps({"ok": False, "err": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)
