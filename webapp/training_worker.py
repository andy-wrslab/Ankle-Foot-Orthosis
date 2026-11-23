"""Console UDP receiver (own process, supervised by workers.TrainingSupervisor).

Layout from config/console_udp_layout.json (written by the Simulink thread's
make_afo_r1): '<12f' = 48 bytes every 10 ms to OMEN :5433. Col 0 t_model (same
clock as main bus 5431 col 0), 1 side (-1 unset / 0 L / 1 R), 2 weight_kg,
3 assist_mode (1 RL, 2 ILC, 3 fixed K), 4 fixed_k_pct, 5-9 cmd_motor,
cmd_assist, cmd_k, cmd_calibrate_pressure, cmd_reset_sv, 10 imu_ok,
11 imu_bad_count. Optional tail (AFO_r1, if added): 3 more floats, cols 12-14 =
bif_valid, bif_cal_progress (BIF_Dbg element 8, 0..1), bif_bias_ready
(layout key "optional_columns" overrides the names). A 48-byte packet leaves
them unset (NaN in the history, absent from "latest"); a 60-byte one fills them.

The packet has no version or counter column, so every packet is checked by:
exact length; every value finite; side in {-1, 0, 1}; assist_mode in {1, 2, 3};
model time increasing (a repeat/older time is dropped; a jump back of more than
5 s is a model restart and starts over). Gaps are counted from model time.
Rejected packets are counted (and logged rate-limited), never used.
An older layout with layout_version / packet_counter columns is still checked
the old way.

Run 14 (UDP settings, '<18f'): 3 more after those, cols 15-17 = gyro_cal_request in
use, last accepted 5434 seq, bif_mass_kg in use (RUN14_TAIL).
Run 15 (Advanced over UDP 5435, '<31f'): 13 more, cols 18-28 = the 11 Advanced values in
use (order of round1/settings_adv_udp_layout.json), 29 adv_seq, 30 spring_stiffness
(read-only; the page ignores it) (RUN15_TAIL). Any layout parses 12, 15, 18 and 31 floats.

Sends ("hb", status) 20 times a second: rates, counters, the latest valid row as
{name: value} and its age. Answers ("data", names, window_s) requests with the
recent history of the named columns (min/max binned) on a separate queue.
"""
from __future__ import annotations

import json
import logging
import math
import os
import socket
import struct
import threading
import time
from collections import deque
from queue import Empty, Full

import numpy as np

KEEP_S = 330.0
WRAP = 1 << 24
ALLOWED = {"side": (-1.0, 0.0, 1.0), "assist_mode": (1.0, 2.0, 3.0)}
RESTART_JUMP_S = 5.0
RESTART_RUN = 20          # or 20 packets in a row (0.2 s) older than the last time: a new timeline


DEFAULT_TAIL = ["bif_valid", "bif_cal_progress", "bif_bias_ready"]
# run 14 (UDP settings 5434): 3 more floats, cols 15-17 = gyro_cal_request in use, last
# accepted 5434 seq (0 = none), bif_mass_kg in use (0 = unset) -> '<18f'
RUN14_TAIL = ["gyro_cal_request", "settings_seq", "bif_mass_kg"]
# run 15 (Advanced over UDP 5435): 13 more floats, cols 18-30 -> '<31f'
RUN15_TAIL = ["sv_target_min", "sv_target_max", "target_step_up", "target_step_down", "step_up_window",
              "step_down_window", "high_assist_level", "high_assist_strides", "torque_p_gain", "torque_i_gain",
              "standing_still_cutoff", "adv_seq", "spring_stiffness"]


def load_layout(path):
    lay = json.load(open(path, encoding="utf-8"))
    cols = sorted(lay["columns"], key=lambda c: c.get("i", c.get("column")))
    names = [c.get("n", c.get("name")) for c in cols]
    return lay, names


def tail_struct(fmt: struct.Struct, tail):
    """Struct for the base packet plus the optional float tail (None if the base is not '<Nf')."""
    f = fmt.format if isinstance(fmt.format, str) else fmt.format.decode()
    if not tail or not (f.startswith("<") and f.endswith("f") and f[1:-1].isdigit()):
        return None
    return struct.Struct(f"<{int(f[1:-1]) + len(tail)}f")


def worker_main(layout_path, host, out_q, req_q, resp_q, stop_evt, log_dir) -> None:
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(os.path.join(log_dir, time.strftime("console_worker_%Y%m%d_%H%M%S.log")),
                                      encoding="utf-8")])
    log = logging.getLogger("afo.console")
    try:
        from utils import raise_priority
        raise_priority(log)
    except Exception:
        pass
    lay, names = load_layout(layout_path)
    fmt = struct.Struct(lay["format"])
    port = int(lay["port"])
    period = float(lay.get("period_ms", 10)) / 1000.0
    n = len(names)
    assert fmt.size == 4 * n, "layout format and columns disagree"
    # A 15-column layout (the Simulink make step writes the Bi-LSTM columns at 12-14):
    # those last columns are an optional tail, so 12-float packets of older builds
    # still parse (base = the first 12 columns).
    opt = list(lay.get("optional_columns") or DEFAULT_TAIL)
    tails = [opt, RUN14_TAIL, RUN15_TAIL]
    # a longer layout (15 / 18 / 31 columns) = base 12 + the known tails: strip them from the
    # end (outermost first), so every shorter packet of an older build still parses
    if fmt.format.startswith("<") and fmt.format.endswith("f"):
        for tl in reversed(tails):
            if len(names) > len(tl) and names[-len(tl):] == tl:
                names = names[:-len(tl)]
        n = len(names)
        fmt = struct.Struct(f"<{n}f")
    # accepted sizes: base, base + opt, + run 14, + run 15 (each only if the previous one is)
    added = []
    sizes = {fmt.size: (fmt, n)}
    for tl in tails:
        more = [t for t in tl if t not in names and t not in added]
        if not more:
            break
        sx = tail_struct(fmt, added + more)
        if sx is None:
            break
        added += more
        sizes[sx.size] = (sx, n + len(added))
    names = names + added                # history rows always carry the tails (NaN when absent)
    n_all = len(names)
    sizes_txt = " / ".join(str(k) for k in sorted(sizes))
    idx = {nm: i for i, nm in enumerate(names)}
    i_time = idx.get("t_model", 0)
    versioned = "layout_version" in idx and "packet_counter" in idx
    version = float(lay.get("layout_version", 0))
    allowed = [(idx[k], v, k) for k, v in ALLOWED.items() if k in idx]

    st = {"packets_ok": 0, "bad_length": 0, "bad_version": 0, "non_finite_packets": 0, "bad_value": 0,
          "counter_gaps": 0, "lost_packets": 0, "dup_or_reordered": 0, "model_restarts": 0, "last_counter": None,
          "last_t_model": None, "back_run": 0, "last_rx": 0.0, "bind_error": None, "non_finite_by_col": {}, "bad_value_by_col": {},
          "columns": None, "packets_ext": 0}
    latest = {}
    hist_t = deque()
    hist = deque()
    lock = threading.Lock()
    last_log = {}

    def rl(key, msg):
        now = time.monotonic()
        if now - last_log.get(key, 0) > 2.0:
            last_log[key] = now
            log.warning(msg)

    def accept(row, n_used) -> bool:
        if versioned:
            if row[idx["layout_version"]] != version:
                st["bad_version"] += 1
                rl("ver", f"packet with layout_version {row[idx['layout_version']]} dropped")
                return False
        bad = [i for i, v in enumerate(row[:n_used]) if not math.isfinite(v)]
        if bad:
            st["non_finite_packets"] += 1
            for i in bad:
                st["non_finite_by_col"][names[i]] = st["non_finite_by_col"].get(names[i], 0) + 1
            rl("nf", f"packet with non-finite {', '.join(names[i] for i in bad)} dropped")
            return False
        for i, ok_vals, k in allowed:
            if row[i] not in ok_vals:
                st["bad_value"] += 1
                st["bad_value_by_col"][k] = st["bad_value_by_col"].get(k, 0) + 1
                rl("val", f"packet with {k} = {row[i]:g} dropped (allowed {ok_vals})")
                return False
        if versioned:
            c = int(row[idx["packet_counter"]]) % WRAP
            lc = st["last_counter"]
            if lc is not None:
                step = (c - lc) % WRAP
                if step == 0 or step > WRAP // 2:
                    st["dup_or_reordered"] += 1
                    return False
                if step > 1:
                    st["counter_gaps"] += 1
                    st["lost_packets"] += step - 1
            st["last_counter"] = c
        t = row[i_time]
        lt = st["last_t_model"]
        if lt is not None:
            if t <= lt:
                st["back_run"] += 1
                if lt - t > RESTART_JUMP_S or st["back_run"] >= RESTART_RUN:
                    st["back_run"] = 0
                    st["model_restarts"] += 1
                    log.info("console model time went back %.1f s -> %.1f s: model restarted", lt, t)
                    with lock:
                        hist_t.clear()
                        hist.clear()
                else:
                    st["dup_or_reordered"] += 1
                    return False
            elif not versioned and t - lt > 2.5 * period:
                st["back_run"] = 0
                st["counter_gaps"] += 1
                st["lost_packets"] += max(0, int(round((t - lt) / period)) - 1)
        if lt is None or t > lt:
            st["back_run"] = 0
        st["last_t_model"] = t
        return True

    def rx_loop():
        while not stop_evt.is_set():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:   # 4 MB receive buffer (see network._open_listen_socket)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            except OSError:
                pass
            try:
                sock.bind((host, port))
            except OSError as exc:
                st["bind_error"] = str(exc)
                log.error("cannot bind UDP %s:%d (%s)", host, port, exc)
                sock.close()
                time.sleep(2)
                continue
            st["bind_error"] = None
            sock.settimeout(0.5)
            buf = bytearray(65536)
            log.info("listening for console packets on %s:%d (%s, %d columns; %s floats accepted)", host, port,
                     lay["format"], n, ", ".join(str(v[1]) for k, v in sorted(sizes.items())))
            try:
                while not stop_evt.is_set():
                    try:
                        nbytes, _ = sock.recvfrom_into(buf)
                    except socket.timeout:
                        continue
                    except ConnectionResetError:
                        continue
                    hit = sizes.get(nbytes)
                    if hit is None:
                        st["bad_length"] += 1
                        rl("len", f"console packet of {nbytes} bytes dropped (expected {sizes_txt})")
                        continue
                    n_used = hit[1]
                    row = hit[0].unpack_from(buf) + (float("nan"),) * (n_all - n_used)
                    if not accept(row, n_used):
                        continue
                    st["packets_ok"] += 1
                    st["columns"] = n_used
                    if n_used > n:
                        st["packets_ext"] += 1
                    st["last_rx"] = time.time()
                    vals = {names[i]: row[i] for i in range(n_used)}
                    with lock:
                        latest.clear()
                        latest.update(vals)
                        hist_t.append(row[i_time])
                        hist.append(np.array(row, dtype=np.float64))
                        while hist_t and hist_t[-1] - hist_t[0] > KEEP_S:
                            hist_t.popleft()
                            hist.popleft()
            except Exception:
                log.exception("console receiver error; rebuilding socket")
                time.sleep(1)
            finally:
                sock.close()

    def req_loop():
        while not stop_evt.is_set():
            try:
                rid, kind, args = req_q.get(timeout=0.5)
            except Empty:
                continue
            try:
                with lock:
                    if not hist:
                        out = {"t_latest": None, "series": {}}
                    else:
                        arr = np.vstack(hist)
                        t = arr[:, i_time]
                        newest = t[-1]
                        window = float(args[1])
                        m = t >= newest - window
                        max_points = int(args[2]) if len(args) > 2 else 1500
                        bw = max(window / (max_points / 2.0), 0.01)
                        tt = t[m]
                        bins = np.floor(tt / bw).astype(np.int64)
                        starts = (np.flatnonzero(np.concatenate(([True], bins[1:] != bins[:-1])))
                                  if len(bins) else np.array([], dtype=np.int64))
                        out = {"t_latest": float(newest), "bin_width": bw, "series": {}}
                        for nm in args[0]:
                            if nm not in idx or len(starts) == 0:
                                continue
                            y = arr[m, idx[nm]]
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
                resp_q.put((rid, json.dumps(out)))
            except Exception as exc:
                resp_q.put((rid, json.dumps({"err": repr(exc)})))

    threading.Thread(target=rx_loop, daemon=True).start()
    threading.Thread(target=req_loop, daemon=True).start()
    import multiprocessing
    parent = multiprocessing.parent_process()
    last_ok, last_t, rate = 0, time.monotonic(), 0.0
    while not stop_evt.is_set():
        time.sleep(0.05)      # 20 Hz: the UDP-settings echo (run 14) confirms a press within ~100 ms
        if parent is not None and not parent.is_alive():
            break
        now = time.monotonic()
        if now - last_t >= 0.5:
            rate = (st["packets_ok"] - last_ok) / max(1e-3, now - last_t)
            last_ok, last_t = st["packets_ok"], now
        with lock:
            snap = dict(latest)
        status = {k: v for k, v in st.items()}
        status.update(rate_hz=round(rate, 1), age_s=round(time.time() - st["last_rx"], 2) if st["last_rx"] else None,
                      latest=snap, port=port, format=lay["format"], pid=os.getpid())
        try:
            out_q.put_nowait(("hb", status))
        except Full:
            pass
    log.info("console worker stopping")
