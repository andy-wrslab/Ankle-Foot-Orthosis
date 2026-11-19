"""Training-data UDP receiver (own process, supervised by workers.TrainingSupervisor).

Layout from config/training_udp_layout.json (v1: 46 x float32, 184 bytes,
~100 Hz to OMEN :5433). Every packet is checked: exact length, column 1 ==
layout_version, packet_counter continuity (24-bit wrap), every value finite.
Rejected packets are counted (and logged rate-limited), never used.

Sends ("hb", status) twice a second: rates, counters, the latest valid row as
{name: value} and its age. Answers ("data", names, window_s) requests with the
last 120 s of the named columns (min/max decimated) on a separate queue.
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

KEEP_S = 330.0          # >= 5 min for the Training tab (30 s / 2 min / 5 min windows)
WRAP = 1 << 24


def worker_main(layout_path, host, out_q, req_q, resp_q, stop_evt, log_dir) -> None:
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(os.path.join(log_dir, time.strftime("training_worker_%Y%m%d_%H%M%S.log")),
                                      encoding="utf-8")])
    log = logging.getLogger("afo.training")
    lay = json.load(open(layout_path, encoding="utf-8"))
    fmt = struct.Struct(lay["format"])
    names = [c["n"] for c in sorted(lay["columns"], key=lambda c: c["i"])]
    version = float(lay["layout_version"])
    port = int(lay["port"])
    n = len(names)
    assert fmt.size == 4 * n, "layout format and columns disagree"

    st = {"packets_ok": 0, "bad_length": 0, "bad_version": 0, "non_finite_packets": 0, "counter_gaps": 0,
          "lost_packets": 0, "dup_or_reordered": 0, "last_counter": None, "last_rx": 0.0, "bind_error": None,
          "non_finite_by_col": {}}
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

    def rx_loop():
        while not stop_evt.is_set():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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
            log.info("listening for training data on %s:%d (layout v%d, %d columns)", host, port, int(version), n)
            try:
                while not stop_evt.is_set():
                    try:
                        nbytes, _ = sock.recvfrom_into(buf)
                    except socket.timeout:
                        continue
                    except ConnectionResetError:
                        continue
                    if nbytes != fmt.size:
                        st["bad_length"] += 1
                        rl("len", f"training packet of {nbytes} bytes dropped (expected {fmt.size})")
                        continue
                    row = fmt.unpack_from(buf)
                    if row[1] != version:
                        st["bad_version"] += 1
                        rl("ver", f"training packet with layout_version {row[1]} dropped (expected {version:g})")
                        continue
                    bad = [i for i, v in enumerate(row) if not math.isfinite(v)]
                    if bad:
                        st["non_finite_packets"] += 1
                        for i in bad:
                            st["non_finite_by_col"][names[i]] = st["non_finite_by_col"].get(names[i], 0) + 1
                        if 0 in bad or 2 in bad:
                            rl("nf", "training packet with non-finite time/counter dropped")
                            continue
                    c = int(row[2]) % WRAP
                    lc = st["last_counter"]
                    if lc is not None:
                        step = (c - lc) % WRAP
                        if step == 0 or step > WRAP // 2:
                            st["dup_or_reordered"] += 1
                            continue
                        if step > 1:
                            st["counter_gaps"] += 1
                            st["lost_packets"] += step - 1
                    st["last_counter"] = c
                    st["packets_ok"] += 1
                    st["last_rx"] = time.time()
                    vals = {names[i]: (row[i] if math.isfinite(row[i]) else None) for i in range(n)}
                    with lock:
                        latest.clear()
                        latest.update(vals)
                        hist_t.append(row[0])
                        hist.append(np.array(row, dtype=np.float64))
                        while hist_t and hist_t[-1] - hist_t[0] > KEEP_S:
                            hist_t.popleft()
                            hist.popleft()
                        if hist_t and hist_t[-1] < hist_t[0]:   # model restarted: start over
                            hist_t.clear()
                            hist.clear()
            except Exception:
                log.exception("training receiver error; rebuilding socket")
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
                        t = arr[:, 0]
                        newest = t[-1]
                        m = t >= newest - float(args[1])
                        window = float(args[1])
                        max_points = int(args[2]) if len(args) > 2 else 1500
                        # min/max bins anchored to absolute model time (like the Live page):
                        # completed bins are identical between requests, peaks never vanish
                        bw = max(window / (max_points / 2.0), 0.01)
                        tt_all = t[m]
                        bins = np.floor(tt_all / bw).astype(np.int64)
                        starts = np.flatnonzero(np.concatenate(([True], bins[1:] != bins[:-1]))) if len(bins) else np.array([], dtype=np.int64)
                        out = {"t_latest": float(newest), "bin_width": bw, "series": {}}
                        for nm in args[0]:
                            if nm not in names:
                                continue
                            y = arr[m, names.index(nm)]
                            if len(starts) == 0:
                                continue
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
    last_ok, last_t = 0, time.monotonic()
    while not stop_evt.is_set():
        time.sleep(0.5)
        if parent is not None and not parent.is_alive():
            break
        now = time.monotonic()
        rate = (st["packets_ok"] - last_ok) / max(1e-3, now - last_t)
        last_ok, last_t = st["packets_ok"], now
        with lock:
            snap = dict(latest)
        status = {k: v for k, v in st.items()}
        status.update(rate_hz=round(rate, 1), age_s=round(time.time() - st["last_rx"], 2) if st["last_rx"] else None,
                      latest=snap, port=port, layout_version=int(version), pid=os.getpid())
        try:
            out_q.put_nowait(("hb", status))
        except Full:
            pass
    log.info("training worker stopping")
