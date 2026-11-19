"""MATLAB Engine worker process (started by workers.MatlabWorker).

One hidden MATLAB R2024b session serves two clients, never at the same time
(an engine lock serialises every MATLAB call):

* run control: (request_id, function, args) messages -> (request_id, ok, result)
* signal streaming: when enabled, a thread keeps the target's instrumented
  signals flowing with the proven host_tools helpers (afo_recording,
  afo_stream_setup, afo_stream_drain) and buffers the last 120 s of every
  signal here, in the worker. The web app asks for plot data through a separate
  queue that never waits for MATLAB.
"""
from __future__ import annotations

import json
import logging
import os
import queue as _queue
import threading
import time

import numpy as np

KEEP_S = 120.0
DRAIN_S = 0.25


class SignalBuffer:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.chunks = {}      # channel -> list of (t array, v array)
        self.widths = {}
        self.count = {}
        self.first_t = {}
        self.last_t = {}
        self.last_wall = {}

    def reset(self) -> None:
        with self.lock:
            self.chunks.clear()
            self.count.clear()
            self.first_t.clear()
            self.last_t.clear()

    def ingest(self, manifest, binpath) -> int:
        blob = b""
        if binpath:
            with open(binpath, "rb") as fp:
                blob = fp.read()
        off = 0
        rows = 0
        now = time.time()
        with self.lock:
            for s in manifest:
                name = s.get("name", "?")
                w = int(s.get("w", 1) or 1)
                n = int(s.get("n", 0) or 0)
                tb, vb = 8 * n, 4 * n * w
                if off + tb + vb > len(blob):
                    break
                t = np.frombuffer(blob, dtype="<f8", count=n, offset=off)
                v = np.frombuffer(blob, dtype="<f4", count=n * w, offset=off + tb).reshape(n, w) if n else None
                off += tb + vb
                self.widths[name] = w
                if not n:
                    continue
                chans = [name] if w == 1 else [f"{name}({k + 1})" for k in range(w)]
                for k, ch in enumerate(chans):
                    last = self.last_t.get(ch)
                    if last is not None and t[-1] < last - 60.0:   # model restarted
                        self.chunks[ch] = []
                        self.count[ch] = 0
                        self.first_t.pop(ch, None)
                        last = None
                    keep = t > last if last is not None else np.ones(n, dtype=bool)
                    if not keep.any():
                        continue
                    tt = t[keep].copy()
                    vv = v[keep, k].astype(np.float64)
                    lst = self.chunks.setdefault(ch, [])
                    lst.append((tt, vv))
                    self.count[ch] = self.count.get(ch, 0) + len(tt)
                    self.first_t.setdefault(ch, float(tt[0]))
                    self.last_t[ch] = float(tt[-1])
                    self.last_wall[ch] = now
                    rows += len(tt)
                    cutoff = self.last_t[ch] - KEEP_S
                    while lst and lst[0][0][-1] < cutoff:
                        lst.pop(0)
        return rows

    def channels(self):
        with self.lock:
            out = []
            now = time.time()
            for ch, lst in self.chunks.items():
                span = (self.last_t.get(ch, 0) - self.first_t.get(ch, 0)) or 0
                out.append({"name": ch, "n": self.count.get(ch, 0),
                            "rate_hz": round(self.count.get(ch, 0) / span, 1) if span > 0 else None,
                            "age_s": round(now - self.last_wall.get(ch, now), 1)})
            return sorted(out, key=lambda c: c["name"].lower())

    def data(self, names, window_s, max_points=1500):
        with self.lock:
            newest = max((self.last_t[n] for n in names if n in self.last_t), default=None)
            out = {"t_latest": newest, "series": {}}
            if newest is None:
                return out
            for n in names:
                lst = self.chunks.get(n)
                if not lst:
                    continue
                t = np.concatenate([c[0] for c in lst])
                v = np.concatenate([c[1] for c in lst])
                m = t >= newest - window_s
                t, v = t[m] - newest, v[m]
                if len(t) > max_points:  # min/max envelope keeps every peak
                    bins = max_points // 2
                    edges = np.linspace(0, len(t), bins + 1).astype(np.int64)[:-1]
                    with np.errstate(all="ignore"):
                        lo = np.fmin.reduceat(v, edges)
                        hi = np.fmax.reduceat(v, edges)
                    tx = np.repeat(t[edges], 2)
                    vy = np.empty(2 * bins)
                    vy[0::2], vy[1::2] = lo, hi
                    t, v = tx, vy
                v = np.where(np.isfinite(v) & (np.abs(v) < 1e30), v, np.nan)
                out["series"][n] = {"t": [round(float(x), 4) for x in t],
                                    "v": [None if x != x else float(f"{x:.6g}") for x in v]}
            return out


def worker_main(req_q, resp_q, paths, log_dir, snap_req_q=None, snap_resp_q=None) -> None:
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(os.path.join(log_dir, time.strftime("matlab_worker_%Y%m%d_%H%M%S.log")),
                                      encoding="utf-8")],
    )
    log = logging.getLogger("afo.matlab_worker")
    try:
        import matlab.engine
        eng = matlab.engine.start_matlab("-nodesktop -nosplash")
        for p in paths:
            if os.path.isdir(p):
                eng.addpath(p, nargout=0)
        pid = int(eng.feature("getpid"))
        log.info("MATLAB started (pid %d), paths %s", pid, paths)
        resp_q.put(("ready", pid))
    except Exception as exc:
        log.exception("MATLAB engine failed to start")
        resp_q.put(("fatal", f"MATLAB engine failed to start: {exc}"))
        return

    elock = threading.Lock()
    buf = SignalBuffer()
    st = {"on": False, "state": "off", "mode": None, "nsig": 0, "err": "", "drains": 0,
          "last_rows_wall": 0.0, "setup_ok": False, "recording": False, "restart_tried": False,
          "recover_tried": False, "notes": [], "auto_reconnects": 0, "offer_recover": False}
    MAX_AUTO_RECONNECTS = 3

    def note(msg):
        st["notes"] = (st["notes"] + [time.strftime("%H:%M:%S ") + msg])[-12:]
        log.info(msg)

    def ml_json(expr, timeout_note=""):
        with elock:
            out = eng.eval(expr, nargout=1)
        return json.loads(out)

    def stream_loop():
        next_setup = 0.0
        while True:
            time.sleep(DRAIN_S)
            if not st["on"]:
                continue
            try:
                if time.time() - st.get("status_wall", 0) > 3.0 or not st["setup_ok"]:
                    st["status"] = ml_json("afo_rc('status')")
                    st["status_wall"] = time.time()
                s = st["status"]
                if not s.get("connected"):
                    st["state"] = "connecting"
                    s = ml_json("afo_rc('connect')")
                    st["status"], st["status_wall"] = s, time.time()
                    if not s.get("connected"):
                        st["err"] = s.get("err", "cannot connect")
                        time.sleep(3)
                        continue
                    note("connected to the target")
                if not s.get("running"):
                    st["state"] = "model stopped"
                    st["setup_ok"] = False
                    st["recording"] = False
                    time.sleep(2)
                    continue
                if not st["recording"]:
                    r = ml_json("afo_recording('start')")
                    if r.get("ok"):
                        st["recording"] = True
                        note("target recording active" + (" (already on)" if r.get("state") == "already" else ""))
                if not st["setup_ok"]:
                    if time.time() < next_setup:
                        continue
                    next_setup = time.time() + 5.0
                    r = ml_json("afo_stream_setup()")
                    if r.get("ok") and r.get("nsignames"):
                        for k in ("setup_fail_since", "reconnect_wall"):
                            st.pop(k, None)
                        st.update(auto_reconnects=0, offer_recover=False)
                        st.update(setup_ok=True, mode=r.get("mode"), nsig=r.get("nsignames"), err="",
                                  last_rows_wall=time.time(), restart_tried=False, recover_tried=False)
                        note(f"stream ready: {r.get('nsignames')} signals, {r.get('mode')} mode")
                    else:
                        err = r.get("err") or "stream setup: no signals yet"
                        if err != st["err"]:
                            note("stream setup failed: " + err[:200])
                        st["err"] = err
                        # Automatic recovery is limited to a clean reconnect of THIS
                        # session (never touches target recording), at most 3 times.
                        # After that the page offers ONE manual "Reconnect Signals"
                        # (afo_recover). Never restarts recording by itself.
                        st.setdefault("setup_fail_since", time.time())
                        if time.time() - st["setup_fail_since"] > 15 and time.time() - st.get("reconnect_wall", 0) > 30:
                            if st["auto_reconnects"] >= MAX_AUTO_RECONNECTS:
                                if not st["offer_recover"]:
                                    st["offer_recover"] = True
                                    note(f"automatic reconnect failed {MAX_AUTO_RECONNECTS} times: "
                                         "Reconnect Signals (afo_recover) offered on the page")
                                continue
                            st["reconnect_wall"] = time.time()
                            st["auto_reconnects"] += 1
                            note(f"setup keeps failing: reconnecting this MATLAB session to the target "
                                 f"(automatic {st['auto_reconnects']}/{MAX_AUTO_RECONNECTS})")
                            ml_json("afo_rc('disconnect')")
                            time.sleep(3)
                            ml_json("afo_rc('connect')")
                            st["recording"] = False
                            next_setup = 0.0
                        continue
                st["state"] = "streaming"
                r = ml_json("afo_stream_drain()")
                st["drains"] += 1
                if not r.get("ok"):
                    if "re-setup" in str(r.get("err", "")):
                        st["setup_ok"] = False
                    st["err"] = r.get("err", "")
                    continue
                rows = buf.ingest(r.get("signals") or [], r.get("bin"))
                if rows:
                    st["last_rows_wall"] = time.time()
                # silent-stream watchdog: flag it and re-run setup once; never
                # restart target recording automatically (that splits the file log)
                silent = time.time() - st["last_rows_wall"]
                if silent > 15 and not st["restart_tried"]:
                    st["restart_tried"] = True
                    note("stream silent 15 s: re-running stream setup (target recording untouched)")
                    st["setup_ok"] = False
            except Exception as exc:  # never let the stream thread die
                st["err"] = f"{type(exc).__name__}: {exc}"
                log.exception("stream loop error")
                time.sleep(1)

    def snap_loop():
        while snap_req_q is not None:
            msg = snap_req_q.get()
            if msg is None:
                return
            rid, kind, args = msg
            try:
                if kind == "status":
                    out = {k: st[k] for k in ("on", "state", "mode", "nsig", "err", "drains", "notes",
                                              "auto_reconnects", "offer_recover")}
                    out["silent_s"] = round(time.time() - st["last_rows_wall"], 1) if st["last_rows_wall"] else None
                    out["channels"] = buf.channels()
                elif kind == "data":
                    out = buf.data(args[0], float(args[1]))
                else:
                    out = {"err": "unknown"}
                snap_resp_q.put((rid, json.dumps(out)))
            except Exception as exc:
                snap_resp_q.put((rid, json.dumps({"err": repr(exc)})))

    threading.Thread(target=stream_loop, name="stream", daemon=True).start()
    threading.Thread(target=snap_loop, name="snap", daemon=True).start()

    import multiprocessing
    parent = multiprocessing.parent_process()
    while True:
        try:
            msg = req_q.get(timeout=2.0)
        except _queue.Empty:
            if parent is not None and not parent.is_alive():
                log.warning("web app process is gone; MATLAB worker exits")
                break
            continue
        if msg is None:
            break
        rid, func, args = msg
        t0 = time.monotonic()
        try:
            if func == "__recover__":
                mode = args[0]
                # only afo_recover is offered in the UI ("Reconnect Signals");
                # restarting recording on its own was removed (it splits the file log)
                expr = {"reconnect": "afo_rc('disconnect')",
                        "afo_recover": "afo_recover('TargetPC1')"}.get(mode)
                if expr is None:
                    raise ValueError("unknown recovery mode")
                note(f"manual recovery requested: {mode}")
                res = {"mode": mode, "steps": []}
                res["steps"].append(ml_json(expr))
                if mode == "reconnect":
                    time.sleep(3)
                    res["steps"].append(ml_json("afo_rc('connect')"))
                st.update(setup_ok=False, recording=False, restart_tried=False, auto_reconnects=0,
                          offer_recover=False)
                st.pop("setup_fail_since", None)
                st.pop("reconnect_wall", None)
                resp_q.put((rid, True, json.dumps(res)))
                continue
            if func == "__stream__":
                st["on"] = bool(args[0])
                if not st["on"]:
                    st["state"] = "off"
                    st["setup_ok"] = False
                    note("streaming turned off")
                else:
                    note("streaming turned on")
                resp_q.put((rid, True, json.dumps({"ok": True, "on": st["on"]})))
                continue
            with elock:
                out = getattr(eng, func)(*args, nargout=1)
            resp_q.put((rid, True, out))
            log.info("%s%s ok in %.1f s", func, tuple(args), time.monotonic() - t0)
        except Exception as exc:
            resp_q.put((rid, False, f"{type(exc).__name__}: {exc}"))
            log.warning("%s%s failed: %s", func, tuple(args), exc)
    st["on"] = False
    try:  # leave the target clean: an unclean exit can wedge its XCP link
        with elock:
            eng.eval("try, tg = slrealtime(); if isConnected(tg), disconnect(tg); end, catch, end", nargout=0)
        log.info("disconnected from the target")
    except Exception:
        pass
    try:
        eng.quit()
    except Exception:
        pass
