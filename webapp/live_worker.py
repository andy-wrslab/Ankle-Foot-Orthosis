"""Live data worker process: UDP receive, validation, history and encoding.

Runs in its own process (started and supervised by workers.LiveSupervisor), so
nothing the other pages do (compiles, trial loading, MATLAB calls) can stall
the live stream, and a crash here is restarted without taking the web app down.
Sends ("snap", json_text) for every snapshot and ("hb", status) once a second
over a multiprocessing queue.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from queue import Full


def _put(q, item) -> None:
    try:
        q.put_nowait(item)
    except Full:
        pass  # the main process is behind: drop this frame, the next one is newer


def worker_main(cfg, out_q, stop_evt, log_dir, req_q=None, resp_q=None) -> None:
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.FileHandler(os.path.join(log_dir, time.strftime("live_worker_%Y%m%d_%H%M%S.log")),
                                      encoding="utf-8")],
    )
    log = logging.getLogger("afo.live_worker")
    from utils import raise_priority
    raise_priority(log)
    import encoding
    import network
    from utils import is_host_reachable

    def hook(snapshot):
        text = encoding.encode_snapshot(snapshot)
        if text is not None:
            _put(out_q, ("snap", text))

    network.set_publish_hook(hook)
    stop = network.get_stop_event()

    def supervised(name, target):
        while not stop.is_set():
            try:
                target(cfg, stop)
                return
            except Exception:
                log.exception("%s failed; restarting in 1 s", name)
                stop.wait(1.0)

    threading.Thread(target=supervised, args=("udp-listener", network.start_udp_listener),
                     name="udp-listener", daemon=True).start()
    live_cfg = cfg.get("live") or {}
    if live_cfg.get("fake_data_when_offline", True) and not is_host_reachable(cfg["udp"]["send_host"]):
        log.warning("target unreachable; fake data until it sends")
        threading.Thread(target=supervised, args=("fake-data", network.start_fake_data),
                         name="fake-data", daemon=True).start()

    def req_loop():
        # Live > Training data (5431 at ~100 Hz, up to 330 s), on its own queue
        import json
        from queue import Empty
        while not stop.is_set():
            try:
                rid, kind, args = req_q.get(timeout=0.5)
            except Empty:
                continue
            except (EOFError, OSError):
                return
            try:
                out = network.slow_data(args[0], float(args[1]), int(args[2]))
            except Exception as exc:
                out = {"err": repr(exc)}
            try:
                resp_q.put((rid, json.dumps(out)))
            except Exception:
                pass

    if req_q is not None:
        threading.Thread(target=req_loop, name="slow-req", daemon=True).start()

    last_ok = 0
    last_t = time.monotonic()
    log.info("live worker running (pid %d)", os.getpid())
    import multiprocessing
    parent = multiprocessing.parent_process()
    while not stop_evt.is_set():
        time.sleep(1.0)
        if parent is not None and not parent.is_alive():
            log.warning("web app process is gone; live worker exits")
            break
        now = time.monotonic()
        health = network.get_health()
        ok = health["packets"].get("ok", 0)
        rate = (ok - last_ok) / max(1e-3, now - last_t)
        last_ok, last_t = ok, now
        link = network.get_link_status()
        _put(out_q, ("hb", {"pid": os.getpid(), "rate_hz": round(rate, 1), "health": health,
                            "connected": link["connected"], "age_s": None if link["age"] == float("inf") else round(link["age"], 2),
                            "session": link["session"], "live_seen": network.live_data_seen(),
                            "readback": network.get_readback()}))
    network.request_shutdown()
    log.info("live worker stopping")
