"""Teensy bench helpers: firmware repo, build, guarded flash, serial monitor.

Nothing here runs on its own: every action is started by a click on the
Teensy page (OMEN only). Flashing is refused while the Speedgoat stream is
live, without a Teensy on USB, without a build of the current commit, or
without the branch name typed as confirmation; every attempt is logged.
"""
from __future__ import annotations

import csv
import os
import re
import subprocess
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
FQBN = "teensy:avr:teensy41"


def _git(cfg, *args, timeout=20) -> str:
    repo = cfg["paths"]["firmware_repo"]
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git {' '.join(args)} failed")
    return r.stdout


def repo_summary(cfg) -> Dict[str, Any]:
    branch = _git(cfg, "branch", "--show-current").strip()
    head = _git(cfg, "log", "-1", "--format=%h %s (%cr)").strip()
    dirty = [l for l in _git(cfg, "status", "--porcelain").splitlines() if l.strip()]
    return {"branch": branch, "head": head, "dirty": dirty, "repo": cfg["paths"]["firmware_repo"]}


def repo_details(cfg) -> Dict[str, Any]:
    s = repo_summary(cfg)
    s["log"] = _git(cfg, "log", "-8", "--format=%h  %ad  %s", "--date=short").strip()
    local = [b.strip() for b in _git(cfg, "branch", "--format=%(refname:short)").splitlines() if b.strip()]
    remote = [b.strip()[len("origin/"):] for b in _git(cfg, "branch", "-r", "--format=%(refname:short)").splitlines()
              if b.strip().startswith("origin/") and not b.strip().endswith("/HEAD")]
    s["branches"] = sorted(set(local) | set(remote), key=lambda b: (b != "main", b))
    return s


def branch_diff(cfg, branch: str) -> str:
    """What checking out *branch* would change in DAQ/ compared with main."""
    ref = branch if _ref_exists(cfg, branch) else f"origin/{branch}"
    stat = _git(cfg, "diff", "--stat", f"main...{ref}", "--", "DAQ")
    body = _git(cfg, "diff", f"main...{ref}", "--", "DAQ")
    commits = _git(cfg, "log", "--format=%h %s", f"main..{ref}")
    return (f"Commits on {branch} not on main:\n{commits or '(none)'}\n\n{stat}\n{body}")[:200000]


def _ref_exists(cfg, ref: str) -> bool:
    try:
        _git(cfg, "rev-parse", "--verify", "--quiet", ref)
        return True
    except RuntimeError:
        return False


def checkout(cfg, branch: str) -> str:
    """Switch the firmware repo to *branch* (only with a clean working tree)."""
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch or ""):
        raise ValueError("invalid branch name")
    dirty = [l for l in _git(cfg, "status", "--porcelain").splitlines() if l.strip()]
    if dirty:
        raise RuntimeError("the repo has uncommitted changes; not switching:\n" + "\n".join(dirty[:20]))
    if _ref_exists(cfg, branch):
        _git(cfg, "switch", branch)
    else:
        _git(cfg, "fetch", "origin", branch, timeout=60)
        _git(cfg, "switch", "--track", f"origin/{branch}")
    return repo_summary(cfg)["branch"]


def daq_files(cfg) -> List[str]:
    d = os.path.join(cfg["paths"]["firmware_repo"], "DAQ")
    return sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))


def read_daq_file(cfg, name: str) -> str:
    if name not in daq_files(cfg):
        raise ValueError("unknown file")
    with open(os.path.join(cfg["paths"]["firmware_repo"], "DAQ", name), encoding="utf-8", errors="replace") as fp:
        return fp.read()


def list_teensy_ports(cfg) -> List[Dict[str, str]]:
    """Teensy USB devices (VID 16C0) with a COM port, via Windows PnP."""
    ps = ("Get-CimInstance Win32_PnPEntity | Where-Object { $_.DeviceID -like '*VID_16C0*' } | "
          "ForEach-Object { $_.Name + '|' + $_.DeviceID }")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                       text=True, timeout=20, creationflags=CREATE_NO_WINDOW)
    ports = []
    for line in r.stdout.splitlines():
        if "|" not in line:
            continue
        name, dev = line.split("|", 1)
        m = re.search(r"\((COM\d+)\)", name)
        ports.append({"name": name.strip(), "port": m.group(1) if m else "", "device": dev.strip()})
    return ports


def build_dir(cfg, commit: str) -> str:
    return os.path.join(cfg["paths"]["cache_dir"], "teensy_build", commit)


def parse_memory(text: str) -> Dict[str, str]:
    out = {}
    for key in ("FLASH", "RAM1", "RAM2"):
        m = re.search(rf"{key}:\s*(.+)", text)
        if m:
            out[key] = m.group(1).strip()
    return out


def compile_job(cfg, job, run_process) -> Dict[str, Any]:
    from workers import Job  # noqa: F401  (type only)
    info = repo_summary(cfg)
    commit = _git(cfg, "rev-parse", "--short", "HEAD").strip()
    if info["dirty"]:
        job.add("Note: uncommitted changes in the repo are included in this build:")
        for l in info["dirty"]:
            job.add("  " + l)
    out_dir = build_dir(cfg, commit + ("-dirty" if info["dirty"] else ""))
    os.makedirs(out_dir, exist_ok=True)
    sketch = os.path.join(cfg["paths"]["firmware_repo"], "DAQ")
    rc = run_process(job, [cfg["paths"]["arduino_cli"], "compile", "--fqbn", FQBN, "--warnings", "default",
                           "--build-path", out_dir, sketch], timeout=900)
    text = "\n".join(job.lines)
    res = {"ok": rc == 0, "branch": info["branch"], "commit": commit, "dirty": bool(info["dirty"]),
           "build_dir": out_dir, "memory": parse_memory(text), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    job.add("BUILD OK" if rc == 0 else f"BUILD FAILED (exit {rc})")
    return res


def flash_job(cfg, job, run_process, port: str, build: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    cmd = [cfg["paths"]["arduino_cli"], "upload", "--fqbn", FQBN, "-p", port, "--input-dir", build["build_dir"]]
    result = "dry-run"
    rc = 0
    if dry_run:
        job.add("DRY RUN - the loader is NOT called. Would run:")
        job.add("  " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    else:
        rc = run_process(job, cmd, timeout=180)
        result = "ok" if rc == 0 else f"failed (exit {rc})"
    log_path = os.path.join(cfg["paths"]["log_dir"], "flash_log.csv")
    new = not os.path.exists(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        if new:
            w.writerow(["time", "branch", "commit", "port", "dry_run", "result", "build_dir"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), build["branch"], build["commit"], port, dry_run, result,
                    build["build_dir"]])
    job.add(f"logged to {log_path}")
    return {"ok": rc == 0, "result": result, "dry_run": dry_run}


class SerialMonitor:
    """Teensy serial monitor through `arduino-cli monitor` (no pyserial needed)."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.proc: Optional[subprocess.Popen] = None
        self.lines: deque = deque(maxlen=5000)
        self.port = None
        self.log_path = None
        self.error = None
        self._lock = threading.Lock()

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, port: str, baud: int = 921600) -> None:
        self.stop()
        os.makedirs(self.cfg["paths"]["log_dir"], exist_ok=True)
        self.log_path = os.path.join(self.cfg["paths"]["log_dir"], time.strftime(f"serial_{port}_%Y%m%d_%H%M%S.log"))
        self.port = port
        self.error = None
        self.proc = subprocess.Popen(
            [self.cfg["paths"]["arduino_cli"], "monitor", "-p", port, "--fqbn", FQBN, "--config", f"baudrate={baud}",
             "--quiet"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        proc = self.proc
        with open(self.log_path, "a", encoding="utf-8") as log:
            for line in proc.stdout:
                stamped = time.strftime("%H:%M:%S ") + line.rstrip("\r\n")
                with self._lock:
                    self.lines.append(stamped)
                log.write(stamped + "\n")
                log.flush()
        if proc.returncode not in (0, None):
            self.error = f"monitor exited ({proc.returncode})"

    def stop(self) -> None:
        if self.running():
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        self.proc = None

    def clear(self) -> None:
        with self._lock:
            self.lines.clear()

    def text(self, filt: str = "", n: int = 400) -> str:
        with self._lock:
            lines = list(self.lines)
        if filt:
            lines = [l for l in lines if filt.lower() in l.lower()]
        return "\n".join(lines[-n:])
