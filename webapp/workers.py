"""Background workers managed by the web app.

* LiveSupervisor  - the UDP/live-data process (live_worker.py); restarted if it
                    dies or stops sending heartbeats. The Live page depends
                    only on this, never on the other workers.
* MatlabWorker    - one persistent MATLAB Engine in its own process
                    (matlab_worker.py); every call has a timeout, and a hung
                    engine is killed and restarted.
* JobManager      - long jobs (compile, flash, trial decoding, MATLAB actions)
                    run in threads that only wait on subprocesses / workers,
                    so web requests never block. Pages poll job status.
* StatusPoller    - cheap periodic checks for the Home page (target ping,
                    Teensy USB, firmware repo).
"""
from __future__ import annotations

import itertools
import json
import logging
import multiprocessing as mp
import os
import queue
import subprocess
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Dict, List, Optional

from state import snapshots

_log = logging.getLogger("afo.workers")
_SPAWN = mp.get_context("spawn")
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# ---------------------------------------------------------------- live data
class LiveSupervisor:
    HEARTBEAT_TIMEOUT_S = 5.0

    def __init__(self, cfg: Dict[str, Any], log_dir: str) -> None:
        self.cfg = cfg
        self.log_dir = log_dir
        self.proc = None
        self.q = None
        self.stop_evt = None
        self.status: Dict[str, Any] = {"state": "starting", "restarts": 0, "last_error": None}
        self.last_hb = 0.0
        self.last_snap = 0.0
        self._lock = threading.Lock()
        self._shutdown = threading.Event()

    def start(self) -> None:
        self._spawn()
        threading.Thread(target=self._bridge, name="live-bridge", daemon=True).start()
        threading.Thread(target=self._monitor, name="live-monitor", daemon=True).start()

    def _spawn(self) -> None:
        import live_worker
        self.q = _SPAWN.Queue(maxsize=16)
        self.req = _SPAWN.Queue()
        self.resp = _SPAWN.Queue()
        self.stop_evt = _SPAWN.Event()
        self.proc = _SPAWN.Process(target=live_worker.worker_main,
                                   args=(self.cfg, self.q, self.stop_evt, self.log_dir, self.req, self.resp),
                                   name="afo-live-worker", daemon=True)
        self.proc.start()
        self.last_hb = time.monotonic()
        with self._lock:
            self.status["state"] = "running"
            self.status["pid"] = self.proc.pid
        _log.info("live worker started (pid %s)", self.proc.pid)

    def _bridge(self) -> None:
        while not self._shutdown.is_set():
            q = self.q
            try:
                kind, payload = q.get(timeout=1.0)
            except queue.Empty:
                continue
            except (EOFError, OSError):
                time.sleep(0.2)
                continue
            if kind == "snap":
                self.last_snap = time.monotonic()
                snapshots.publish(payload)  # already strict-JSON text
            elif kind == "hb":
                self.last_hb = time.monotonic()
                with self._lock:
                    self.status.update(payload)
                    self.status["hb_at"] = time.time()

    def _monitor(self) -> None:
        while not self._shutdown.wait(1.0):
            dead = self.proc is None or not self.proc.is_alive()
            silent = time.monotonic() - self.last_hb > self.HEARTBEAT_TIMEOUT_S
            if dead or silent:
                reason = "exited" if dead else "stopped sending heartbeats"
                code = None if self.proc is None else self.proc.exitcode
                _log.error("live worker %s (exit code %s); restarting", reason, code)
                with self._lock:
                    self.status["restarts"] += 1
                    self.status["last_error"] = f"{time.strftime('%H:%M:%S')} live worker {reason} (code {code})"
                    self.status["state"] = "restarting"
                try:
                    if self.proc is not None and self.proc.is_alive():
                        self.proc.kill()
                except Exception:
                    pass
                time.sleep(1.0)
                self._spawn()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            s = dict(self.status)
        s["stream_live"] = bool(s.get("connected")) and (time.monotonic() - self.last_hb) < self.HEARTBEAT_TIMEOUT_S
        s["snap_age_s"] = round(time.monotonic() - self.last_snap, 1) if self.last_snap else None
        return s

    def stream_live(self) -> bool:
        """True if live packets arrived in the last ~5 s (used to lock flashing)."""
        s = self.get_status()
        age = s.get("age_s")
        return bool(s.get("live_seen")) and age is not None and age < 5.0

    def slow_data(self, names, window_s: float = 120.0, max_points: int = 1500, timeout: float = 1.0):
        """Live > Training data from the 5431 bus (~100 Hz, up to 330 s), min/max binned."""
        if self.proc is None or not self.proc.is_alive():
            return None
        if not hasattr(self, "_req_lock"):
            self._req_lock = threading.Lock()
            self._ids = itertools.count(1)
        with self._req_lock:
            rid = next(self._ids)
            self.req.put((rid, "slow", [list(names), float(window_s), int(max_points)]))
            t_end = time.monotonic() + timeout
            while time.monotonic() < t_end:
                try:
                    got = self.resp.get(timeout=0.2)
                except queue.Empty:
                    continue
                if got[0] == rid:
                    return json.loads(got[1])
        return None

    def readback(self) -> Dict[str, Any]:
        """Bus values for command readback (statusword, assistance_level, ...); {} if stale."""
        if time.monotonic() - self.last_hb > 3.0:
            return {}
        with self._lock:
            return dict(self.status.get("readback") or {})

    def shutdown(self) -> None:
        self._shutdown.set()
        try:
            if self.stop_evt is not None:
                self.stop_evt.set()
            if self.proc is not None:
                self.proc.join(timeout=3)
                if self.proc.is_alive():
                    self.proc.kill()
        except Exception:
            pass


# ---------------------------------------------------------------- MATLAB
class MatlabWorker:
    START_TIMEOUT_S = 180.0

    def __init__(self, paths: List[str], log_dir: str) -> None:
        self.paths = paths
        self.log_dir = log_dir
        self.proc = None
        self.req = None
        self.resp = None
        self.state = "stopped"          # stopped | starting | ready | busy | error
        self.error: Optional[str] = None
        self.matlab_pid: Optional[int] = None
        self._lock = threading.Lock()   # one MATLAB call at a time
        self._snap_lock = threading.Lock()
        self._ids = itertools.count(1)
        self.snap_req = None
        self.snap_resp = None
        self.stream_wanted = False
        self.restarts = 0
        threading.Thread(target=self._monitor, name="matlab-monitor", daemon=True).start()

    def _monitor(self) -> None:
        """If streaming is wanted and the worker died, bring it back (and the stream)."""
        while True:
            time.sleep(5.0)
            if not self.stream_wanted:
                continue
            if self.proc is None or not self.proc.is_alive():
                self.restarts += 1
                _log.warning("MATLAB worker not running while streaming is wanted; restarting (%d)", self.restarts)
                try:
                    self.call("__stream__", True, timeout=240)
                except Exception as exc:
                    _log.error("MATLAB worker restart failed: %s", exc)

    def set_stream(self, on: bool):
        self.stream_wanted = bool(on)
        return self.call("__stream__", bool(on), timeout=240)

    def _start(self) -> None:
        import matlab_worker
        self.req = _SPAWN.Queue()
        self.resp = _SPAWN.Queue()
        self.snap_req = _SPAWN.Queue()
        self.snap_resp = _SPAWN.Queue()
        self.proc = _SPAWN.Process(target=matlab_worker.worker_main,
                                   args=(self.req, self.resp, self.paths, self.log_dir,
                                         self.snap_req, self.snap_resp),
                                   name="afo-matlab-worker", daemon=True)
        self.state = "starting"
        self.error = None
        self.proc.start()
        t_end = time.monotonic() + self.START_TIMEOUT_S
        while time.monotonic() < t_end:
            try:
                kind, *rest = self.resp.get(timeout=1.0)
            except queue.Empty:
                if not self.proc.is_alive():
                    break
                continue
            if kind == "ready":
                self.matlab_pid = rest[0]
                self.state = "ready"
                _log.info("MATLAB engine ready (MATLAB pid %s)", self.matlab_pid)
                return
            if kind == "fatal":
                self.error = rest[0]
                break
        self.state = "error"
        self.error = self.error or "MATLAB engine did not start"
        self._kill()
        raise RuntimeError(self.error)

    def _kill(self) -> None:
        try:
            if self.proc is not None and self.proc.is_alive():
                self.proc.kill()
        except Exception:
            pass
        if self.matlab_pid:
            try:
                subprocess.run(["taskkill", "/PID", str(self.matlab_pid), "/T", "/F"],
                               capture_output=True, timeout=10, creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass
        self.matlab_pid = None
        self.proc = None

    def call(self, func: str, *args, timeout: float = 60.0) -> Any:
        """Call a MATLAB function (nargout=1). Raises on error or timeout."""
        with self._lock:
            if self.proc is None or not self.proc.is_alive() or self.state not in ("ready", "busy"):
                self._start()
            rid = next(self._ids)
            self.state = "busy"
            self.req.put((rid, func, list(args)))
            t_end = time.monotonic() + timeout
            while time.monotonic() < t_end:
                try:
                    got = self.resp.get(timeout=0.5)
                except queue.Empty:
                    if not self.proc.is_alive():
                        self.state = "error"
                        self.error = "MATLAB worker exited"
                        raise RuntimeError(self.error)
                    continue
                if got[0] == rid:
                    self.state = "ready"
                    ok, value = got[1], got[2]
                    if not ok:
                        raise RuntimeError(value)
                    return value
            # hung: kill the engine so the next call starts a fresh one
            self.state = "error"
            self.error = f"MATLAB call {func} timed out after {timeout:.0f} s; engine restarted"
            _log.error(self.error)
            self._kill()
            raise TimeoutError(self.error)

    def get_status(self) -> Dict[str, Any]:
        return {"state": self.state, "error": self.error, "matlab_pid": self.matlab_pid,
                "stream_wanted": self.stream_wanted, "restarts": self.restarts,
                "worker_pid": self.proc.pid if self.proc is not None else None}

    def snapshot(self, kind: str, *args, timeout: float = 1.0):
        """Ask the worker's signal buffer (never waits for MATLAB). None if not running."""
        if self.proc is None or not self.proc.is_alive():
            return None
        with self._snap_lock:
            rid = next(self._ids)
            self.snap_req.put((rid, kind, list(args)))
            t_end = time.monotonic() + timeout
            while time.monotonic() < t_end:
                try:
                    got = self.snap_resp.get(timeout=0.2)
                except queue.Empty:
                    continue
                if got[0] == rid:
                    return json.loads(got[1])
            return None

    def shutdown(self) -> None:
        try:
            if self.req is not None and self.proc is not None and self.proc.is_alive():
                self.req.put(None)
                self.proc.join(timeout=40)
        except Exception:
            pass
        self._kill()


# ---------------------------------------------------------------- jobs
class Job:
    def __init__(self, kind: str, title: str) -> None:
        self.id = uuid.uuid4().hex[:10]
        self.kind = kind
        self.title = title
        self.state = "running"          # running | done | failed
        self.lines: deque = deque(maxlen=4000)
        self.result: Any = None
        self.started = time.time()
        self.finished: Optional[float] = None

    def add(self, line: str) -> None:
        self.lines.append(line.rstrip("\r\n"))

    def view(self) -> Dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "title": self.title, "state": self.state,
                "started": self.started, "finished": self.finished, "result": self.result,
                "log": "\n".join(self.lines)}


class JobManager:
    def __init__(self) -> None:
        self.jobs: Dict[str, Job] = {}
        self.latest: Dict[str, str] = {}
        self._lock = threading.Lock()

    def running(self, kind: str) -> Optional[Job]:
        with self._lock:
            jid = self.latest.get(kind)
            job = self.jobs.get(jid) if jid else None
        return job if job and job.state == "running" else None

    def start(self, kind: str, title: str, fn: Callable[[Job], Any]) -> Job:
        job = Job(kind, title)
        with self._lock:
            self.jobs[job.id] = job
            self.latest[kind] = job.id
            if len(self.jobs) > 200:
                for old in sorted(self.jobs.values(), key=lambda j: j.started)[:50]:
                    self.jobs.pop(old.id, None)

        def run():
            try:
                job.result = fn(job)
                job.state = "done"
            except Exception as exc:  # report, never crash the app
                job.add(f"ERROR: {exc}")
                job.result = {"ok": False, "err": str(exc)}
                job.state = "failed"
                _log.exception("job %s (%s) failed", job.title, job.kind)
            finally:
                job.finished = time.time()

        threading.Thread(target=run, name=f"job-{kind}", daemon=True).start()
        return job

    def get(self, kind: str) -> Optional[Job]:
        with self._lock:
            jid = self.latest.get(kind)
            return self.jobs.get(jid) if jid else None


def run_process(job: Job, cmd: List[str], cwd: Optional[str] = None, timeout: float = 600.0,
                env: Optional[Dict[str, str]] = None) -> int:
    """Run *cmd*, streaming its output into the job log; kill it on timeout."""
    job.add("$ " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
    killer = threading.Timer(timeout, lambda: proc.kill())
    killer.start()
    try:
        for line in proc.stdout:
            job.add(line)
        proc.wait()
    finally:
        killer.cancel()
    if proc.returncode is None or proc.returncode < 0:
        job.add(f"(killed after {timeout:.0f} s)")
    return proc.returncode


# ---------------------------------------------------------------- status poller
class StatusPoller:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        self.status: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._loop, name="status-poller", daemon=True).start()

    def _set(self, **kw) -> None:
        with self._lock:
            self.status.update(kw)
            self.status["updated"] = time.time()

    def get(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.status)

    def _loop(self) -> None:
        import teensy_tools
        from utils import is_host_reachable
        n = 0
        while True:
            try:
                host = self.cfg["udp"]["send_host"]
                self._set(target_reachable=is_host_reachable(host), target_host=host)
            except Exception as exc:
                self._set(target_reachable=None, target_err=str(exc))
            if n % 3 == 0:
                try:
                    self._set(teensy_ports=teensy_tools.list_teensy_ports(self.cfg))
                except Exception as exc:
                    self._set(teensy_ports=[], teensy_err=str(exc))
                try:
                    self._set(repo=teensy_tools.repo_summary(self.cfg))
                except Exception as exc:
                    self._set(repo={"error": str(exc)})
            n += 1
            time.sleep(5.0)


# ---------------------------------------------------------------- training stream
class TrainingSupervisor:
    """Runs training_worker.py (UDP 5433) in its own process; restarts it if it dies."""

    def __init__(self, cfg: Dict[str, Any], app_dir: str, log_dir: str) -> None:
        tcfg = cfg.get("training") or {}
        self.enabled = bool(tcfg.get("enabled", False))
        lp = tcfg.get("layout", "config/console_udp_layout.json")
        self.layout_path = lp if os.path.isabs(lp) else os.path.join(app_dir, lp)
        self.host = tcfg.get("listen_host", "0.0.0.0")
        self.log_dir = log_dir
        self.proc = None
        self.status: Dict[str, Any] = {"state": "off" if not self.enabled else "starting", "restarts": 0}
        self.last_hb = 0.0
        self._lock = threading.Lock()
        self._req_lock = threading.Lock()
        self._ids = itertools.count(1)
        self._stop = threading.Event()

    def start(self) -> None:
        if not self.enabled:
            return
        self._spawn()
        threading.Thread(target=self._bridge, daemon=True, name="training-bridge").start()
        threading.Thread(target=self._monitor, daemon=True, name="training-monitor").start()

    def _spawn(self) -> None:
        import training_worker
        self.q = _SPAWN.Queue(maxsize=8)
        self.req = _SPAWN.Queue()
        self.resp = _SPAWN.Queue()
        self.stop_evt = _SPAWN.Event()
        self.proc = _SPAWN.Process(target=training_worker.worker_main,
                                   args=(self.layout_path, self.host, self.q, self.req, self.resp, self.stop_evt,
                                         self.log_dir), name="afo-training-worker", daemon=True)
        self.proc.start()
        self.last_hb = time.monotonic()
        with self._lock:
            self.status["state"] = "running"

    def _bridge(self) -> None:
        while not self._stop.is_set():
            try:
                kind, payload = self.q.get(timeout=1.0)
            except (queue.Empty, EOFError, OSError):
                continue
            if kind == "hb":
                self.last_hb = time.monotonic()
                with self._lock:
                    self.status.update(payload)

    def _monitor(self) -> None:
        while not self._stop.wait(1.0):
            if self.proc is None or not self.proc.is_alive() or time.monotonic() - self.last_hb > 5.0:
                with self._lock:
                    self.status["restarts"] = self.status.get("restarts", 0) + 1
                    self.status["state"] = "restarting"
                _log.error("training worker not alive/silent; restarting")
                try:
                    if self.proc is not None and self.proc.is_alive():
                        self.proc.kill()
                except Exception:
                    pass
                time.sleep(1.0)
                self._spawn()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            s = dict(self.status)
        s["fresh"] = bool(s.get("age_s") is not None and s["age_s"] < 1.0 and time.monotonic() - self.last_hb < 2.0)
        return s

    def latest(self, max_age_s: float = 1.0) -> Dict[str, Any]:
        s = self.get_status()
        if not s.get("latest") or s.get("age_s") is None or s["age_s"] > max_age_s:
            return {}
        return dict(s["latest"])

    def data(self, names, window_s: float = 10.0, timeout: float = 1.0, max_points: int = 1500):
        if self.proc is None or not self.proc.is_alive():
            return None
        with self._req_lock:
            rid = next(self._ids)
            self.req.put((rid, "data", [list(names), float(window_s), int(max_points)]))
            t_end = time.monotonic() + timeout
            while time.monotonic() < t_end:
                try:
                    got = self.resp.get(timeout=0.2)
                except queue.Empty:
                    continue
                if got[0] == rid:
                    return json.loads(got[1])
        return None

    def shutdown(self) -> None:
        self._stop.set()
        try:
            self.stop_evt.set()
            self.proc.join(timeout=3)
            if self.proc.is_alive():
                self.proc.kill()
        except Exception:
            pass
