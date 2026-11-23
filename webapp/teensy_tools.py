"""Teensy bench helpers: firmware source, build, guarded flash, port detection, serial monitor.

Nothing here runs on its own except the USB port scan: every action is started
by a click on the Teensy page (OMEN only).

Firmware source (2026-11-19): the page never checks out a branch. It fetches
origin, resolves each branch to its newest commit, and reads files, diffs and
builds straight from that commit (git show / git archive into cache/), so the
firmware repo's working tree is never touched and every tab shows the same
commit. Flashing is refused while the Speedgoat stream is live, without a
Teensy on USB, or without a clean, successful build of the selected commit
with the pinned board settings; every attempt is logged.
"""
from __future__ import annotations

import atexit
import csv
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import threading
import time
import zlib
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


_kill_job = None


def die_with_this_process(proc) -> bool:
    """Windows: put *proc* (and every process it starts) in a job object that is closed,
    and so killed, when this Python process ends - also on taskkill / TerminateProcess,
    where atexit does not run. Used for the long-lived `board list --watch`, which would
    otherwise be left running after each app restart. False if not available."""
    global _kill_job
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        if _kill_job is None:
            class IO(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

            class BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class EXT(ctypes.Structure):
                _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]
            job = k32.CreateJobObjectW(None, None)
            if not job:
                return False
            info = EXT()
            info.Basic.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):  # Extended
                return False
            _kill_job = job                          # kept open for the life of this process
        return bool(k32.AssignProcessToJobObject(_kill_job, wintypes.HANDLE(int(proc._handle))))
    except Exception:
        return False
BOARD = "teensy:avr:teensy41"
WORKTREE = "@worktree"          # pseudo-source: the repo's working copy (uncommitted edits)
SERIAL_BAUD = 921600            # DAQ.ino: Serial.begin(921600)

# Arduino IDE Tools-menu names for the Teensy 4.1 board options (teensy:avr boards.txt).
OPTION_NAMES = {"usb": "USB Type", "speed": "CPU Speed", "opt": "Optimize", "keys": "Keyboard Layout"}
OPTION_LABELS = {
    "usb": {"serial": "Serial", "serial2": "Dual Serial", "serial3": "Triple Serial", "keyboard": "Keyboard",
            "touch": "Keyboard + Touch Screen", "hidtouch": "Keyboard + Mouse + Touch Screen",
            "hid": "Keyboard + Mouse + Joystick", "serialhid": "Serial + Keyboard + Mouse + Joystick",
            "mtp": "MTP Disk (Experimental)", "serialmtp": "Serial + MTP Disk (Experimental)",
            "audio": "Audio", "serialmidiaudio": "Serial + MIDI + Audio", "midi": "MIDI",
            "serialmidi": "Serial + MIDI", "rawhid": "Raw HID", "everything": "All of the Above"},
    "speed": {s: f"{s} MHz" for s in ("1008", "960", "912", "816", "720", "600", "528", "450", "396", "150", "24")},
    "opt": {"o2std": "Faster", "o2lto": "Faster with LTO", "o1std": "Fast", "o1lto": "Fast with LTO",
            "o3std": "Fastest", "o3purestd": "Fastest + pure-code", "o3lto": "Fastest with LTO",
            "o3purelto": "Fastest + pure-code with LTO", "ogstd": "Debug", "oglto": "Debug with LTO",
            "osstd": "Smallest Code", "oslto": "Smallest Code with LTO"},
    "keys": {"en-us": "US English"},
}
DEFAULT_OPTIONS = {"usb": "serial", "speed": "600", "opt": "o2std", "keys": "en-us"}


# ---------------------------------------------------------------- small helpers
def _run(cmd: List[str], timeout: float = 20, binary: bool = False, cwd: Optional[str] = None):
    return subprocess.run(cmd, capture_output=True, text=not binary, timeout=timeout, cwd=cwd,
                          **({} if binary else {"encoding": "utf-8", "errors": "replace"}),
                          creationflags=CREATE_NO_WINDOW, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))


def _repo(cfg) -> str:
    return cfg["paths"]["firmware_repo"]


def _git(cfg, *args, timeout=20, binary=False):
    r = _run(["git", "-C", _repo(cfg), *args], timeout=timeout, binary=binary)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace") if binary else r.stderr
        out = r.stdout.decode("utf-8", "replace") if binary else r.stdout
        raise RuntimeError((err or out).strip() or f"git {' '.join(args)} failed")
    return r.stdout


def _ref_sha(cfg, ref: str) -> Optional[str]:
    try:
        return _git(cfg, "rev-parse", "--verify", "--quiet", ref + "^{commit}").strip() or None
    except RuntimeError:
        return None


def _is_ancestor(cfg, a: str, b: str) -> bool:
    return _run(["git", "-C", _repo(cfg), "merge-base", "--is-ancestor", a, b]).returncode == 0


def _cache(cfg, *parts) -> str:
    base = cfg["paths"].get("cache_dir", "cache")
    if not os.path.isabs(base):
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), base)
    return os.path.join(base, *parts)


def _log_dir(cfg) -> str:
    d = cfg["paths"].get("log_dir", "logs")
    if not os.path.isabs(d):
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), d)
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------- board settings
def board_settings(cfg) -> Dict[str, Any]:
    """The FQBN every build uses. Pinned in config.yaml `teensy.fqbn` (Andy's Arduino IDE
    Tools-menu choices); without it the build uses the board defaults and says so."""
    t = cfg.get("teensy") or {}
    fqbn = (t.get("fqbn") or "").strip()
    pinned = bool(fqbn)
    if not fqbn:
        fqbn = BOARD + ":" + ",".join(f"{k}={v}" for k, v in DEFAULT_OPTIONS.items())
    parts = fqbn.split(":")
    base = ":".join(parts[:3])
    opts = dict(DEFAULT_OPTIONS)
    if len(parts) > 3 and parts[3]:
        for kv in parts[3].split(","):
            if "=" in kv:
                k, v = kv.split("=", 1)
                opts[k.strip()] = v.strip()
    fqbn = base + ":" + ",".join(f"{k}={opts[k]}" for k in opts)
    labels = {OPTION_NAMES.get(k, k): OPTION_LABELS.get(k, {}).get(v, v) for k, v in opts.items()}
    return {"fqbn": fqbn, "board": base, "options": opts, "labels": labels, "pinned": pinned,
            "source": (t.get("fqbn_source") or "config.yaml") if pinned else "board defaults (not confirmed)",
            "summary": ", ".join(f"{k} {v}" for k, v in labels.items())}


# ---------------------------------------------------------------- firmware source
_fetch_state = {"time": None, "error": None}
_fetch_lock = threading.Lock()


def fetch(cfg) -> Dict[str, Any]:
    """git fetch origin --prune. Only moves origin/* refs; never touches the working tree."""
    with _fetch_lock:
        try:
            _git(cfg, "fetch", "origin", "--prune", "--quiet", timeout=60)
            _fetch_state.update(time=time.time(), error=None)
        except Exception as exc:  # offline lab network: keep going with what we have
            _fetch_state.update(error=str(exc).splitlines()[-1][:200] if str(exc) else "fetch failed")
        return dict(_fetch_state)


_fetch_thread: Optional[threading.Thread] = None


def fetch_state() -> Dict[str, Any]:
    running = _fetch_lock.locked() or (_fetch_thread is not None and _fetch_thread.is_alive())
    return dict(_fetch_state, running=running)


def fetch_in_background(cfg, min_age_s: float = 60.0) -> bool:
    """Start a fetch unless one ran in the last *min_age_s* seconds or is running."""
    global _fetch_thread
    last = _fetch_state.get("time") or 0
    if fetch_state()["running"] or time.time() - last < min_age_s:
        return False

    def _go():
        fetch(cfg)
        _refresh_sources(cfg)       # rebuilt here, so the page never waits for a cold read
    _fetch_thread = threading.Thread(target=_go, name="teensy-fetch", daemon=True)
    _fetch_thread.start()       # fetch_state() says running from here on, no gap
    return True


_sources_cache: Dict[str, Any] = {}


_sources_refresh = threading.Lock()


def _refresh_sources(cfg) -> Optional[Dict[str, Any]]:
    """Rebuild the branch list (~20 git calls, ~2 s cold). One rebuild at a time."""
    if not _sources_refresh.acquire(blocking=False):
        return None
    try:
        v = sources(cfg)
        _sources_cache.update(v=v, t=time.monotonic())
        return v
    finally:
        _sources_refresh.release()


def sources_cached(cfg, max_age_s: float = 10.0) -> Dict[str, Any]:
    """sources() is ~20 git calls; the page asks every few seconds. Stale-while-revalidate:
    any cached list is returned at once and refreshed in the background when older than
    *max_age_s*; only the very first call (cache empty) waits for git."""
    hit = _sources_cache.get("v")
    if hit:
        if time.monotonic() - _sources_cache.get("t", 0) >= max_age_s and not _sources_refresh.locked():
            threading.Thread(target=_refresh_sources, args=(cfg,), name="teensy-sources", daemon=True).start()
        return hit
    v = _refresh_sources(cfg)
    if v is None:                  # another thread is building it: wait for that one
        with _sources_refresh:
            pass
        v = _sources_cache.get("v")
    if v is None:
        v = sources(cfg)
        _sources_cache.update(v=v, t=time.monotonic())
    return v


def sources_peek() -> Optional[Dict[str, Any]]:
    """The cached branch list without any git call (None before the first read)."""
    return _sources_cache.get("v")


def warm_sources(cfg) -> None:
    """Read the branch list in the background at app start, so the Teensy page opens filled."""
    threading.Thread(target=lambda: sources_cached(cfg), name="teensy-sources-warm", daemon=True).start()


def _main_ref(cfg) -> str:
    return "origin/main" if _ref_sha(cfg, "origin/main") else "main"


def _commit_info(cfg, sha: str) -> Dict[str, Any]:
    out = _git(cfg, "log", "-1", "--format=%H%x1f%h%x1f%ct%x1f%an%x1f%s", sha).strip()
    full, short, ct, author, subject = out.split("\x1f", 4)
    daq = _git(cfg, "log", "-1", "--format=%ct%x1f%h", sha, "--", "DAQ").strip()
    daq_ct, daq_short = (daq.split("\x1f") + [""])[:2] if daq else ("0", "")
    return {"sha": full, "short": short, "time": int(ct), "author": author, "subject": subject,
            "daq_time": int(daq_ct or 0), "daq_short": daq_short}


def _resolve_branch(cfg, name: str) -> Optional[Dict[str, Any]]:
    """Newest commit of *name*: origin/<name> unless the local branch has unpushed commits."""
    local, remote = _ref_sha(cfg, f"refs/heads/{name}"), _ref_sha(cfg, f"refs/remotes/origin/{name}")
    note = ""
    if local and remote:
        if local == remote or _is_ancestor(cfg, local, remote):
            sha = remote
        elif _is_ancestor(cfg, remote, local):
            sha = local
            n = _git(cfg, "rev-list", "--count", f"{remote}..{local}").strip()
            note = f"{n} local commit(s) not pushed to GitHub"
        else:
            sha = remote
            note = "local branch differs from GitHub; showing GitHub"
    elif remote:
        sha = remote
    elif local:
        sha = local
        note = "local only, not on GitHub"
    else:
        return None
    info = _commit_info(cfg, sha)
    info.update(name=name, note=note, has_daq=_has_daq(cfg, sha))
    return info


def _has_daq(cfg, sha: str) -> bool:
    return _run(["git", "-C", _repo(cfg), "cat-file", "-e", f"{sha}:DAQ/DAQ.ino"]).returncode == 0


def worktree_status(cfg) -> Dict[str, Any]:
    branch = _git(cfg, "branch", "--show-current").strip() or "(detached)"
    dirty = [l for l in _git(cfg, "status", "--porcelain", "--", "DAQ").splitlines() if l.strip()]
    return {"branch": branch, "dirty": dirty}


def sources(cfg) -> Dict[str, Any]:
    """Every branch with firmware, newest commit first, plus the working copy if it has edits."""
    names = set()
    for line in _git(cfg, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes/origin").splitlines():
        line = line.strip()
        if line.startswith("refs/heads/"):
            names.add(line[len("refs/heads/"):])
        elif line.startswith("refs/remotes/origin/") and not line.endswith("/HEAD"):
            names.add(line[len("refs/remotes/origin/"):])
    branches = [b for b in (_resolve_branch(cfg, n) for n in sorted(names)) if b and b["has_daq"]]
    branches.sort(key=lambda b: (b["daq_time"], b["time"]), reverse=True)
    newest = branches[0]["name"] if branches else None
    main_ref = _main_ref(cfg)
    for b in branches:
        b["newest"] = b["name"] == newest
        try:
            b["ahead_of_main"] = int(_git(cfg, "rev-list", "--count", f"{main_ref}..{b['sha']}", "--", "DAQ").strip())
        except RuntimeError:
            b["ahead_of_main"] = None
    wt = worktree_status(cfg)
    return {"branches": branches, "newest": newest, "worktree": wt, "main_ref": main_ref,
            "fetch": fetch_state()}


def resolve(cfg, source: str) -> Dict[str, Any]:
    """Source -> {kind: commit|worktree, sha, short, name, ...}."""
    if source == WORKTREE:
        wt = worktree_status(cfg)
        head = _commit_info(cfg, "HEAD")
        return {"kind": "worktree", "name": f"{wt['branch']} (working copy)", "sha": head["sha"],
                "short": head["short"], "subject": head["subject"], "time": head["time"], "dirty": wt["dirty"],
                "note": "uncommitted edits: build only, commit and push before flashing"}
    info = _resolve_branch(cfg, source)
    if not info:
        raise ValueError(f"unknown branch {source!r}")
    info["kind"] = "commit"
    return info


def source_label(b: Dict[str, Any], now: Optional[float] = None) -> str:
    age = _age(b["time"], now)
    tags = []
    if b.get("newest"):
        tags.append("newest firmware")
    if b.get("note"):
        tags.append(b["note"])
    return f"{b['name']} · {b['short']} · {age}" + (f" · {', '.join(tags)}" if tags else "")


def _age(t: float, now: Optional[float] = None) -> str:
    d = (now or time.time()) - t
    if d < 3600:
        return f"{max(1, int(d // 60))} min ago"
    if d < 86400:
        return f"{int(d // 3600)} h ago"
    return time.strftime("%Y-%m-%d", time.localtime(t))


def daq_files(cfg, source: str) -> List[str]:
    if source == WORKTREE:
        d = os.path.join(_repo(cfg), "DAQ")
        return sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))
    sha = resolve(cfg, source)["sha"]
    out = _git(cfg, "ls-tree", "--name-only", f"{sha}:DAQ")
    return sorted(l.strip() for l in out.splitlines() if l.strip())


def read_daq_file(cfg, source: str, name: str) -> str:
    if name not in daq_files(cfg, source):
        raise ValueError("unknown file")
    if source == WORKTREE:
        with open(os.path.join(_repo(cfg), "DAQ", name), encoding="utf-8", errors="replace") as fp:
            return fp.read()
    sha = resolve(cfg, source)["sha"]
    return _git(cfg, "show", f"{sha}:DAQ/{name}", binary=True).decode("utf-8", "replace")


def changes_vs_main(cfg, source: str) -> str:
    """Commits and DAQ/ diff of the source compared with main (GitHub's main after a fetch)."""
    main_ref = _main_ref(cfg)
    if source == WORKTREE:
        stat = _git(cfg, "diff", "--stat", main_ref, "--", "DAQ")
        body = _git(cfg, "diff", main_ref, "--", "DAQ")
        return f"Working copy compared with {main_ref} (DAQ/):\n\n{stat}\n{body}"[:200000]
    sha = resolve(cfg, source)["sha"]
    commits = _git(cfg, "log", "--format=%h  %ad  %s", "--date=short", f"{main_ref}..{sha}", "--", "DAQ")
    stat = _git(cfg, "diff", "--stat", f"{main_ref}...{sha}", "--", "DAQ")
    body = _git(cfg, "diff", f"{main_ref}...{sha}", "--", "DAQ")
    if not commits.strip() and not body.strip():
        return f"{source} has the same firmware as {main_ref}."
    return (f"Firmware commits on {source} not on {main_ref}:\n{commits or '(none)'}\n\n{stat}\n{body}")[:200000]


def export_source(cfg, src: Dict[str, Any]) -> str:
    """Sketch folder (…/DAQ) for *src* without touching the repo's working tree."""
    if src["kind"] == "worktree":
        dest = _cache(cfg, "teensy_src", "worktree", "DAQ")
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(os.path.join(_repo(cfg), "DAQ"), dest)
        return dest
    root = _cache(cfg, "teensy_src", src["sha"][:12])
    dest = os.path.join(root, "DAQ")
    if os.path.isfile(os.path.join(dest, "DAQ.ino")):
        return dest
    tmp = root + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    data = _git(cfg, "archive", "--format=tar", src["sha"], "DAQ", binary=True, timeout=60)
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        try:
            tf.extractall(tmp, filter="data")
        except TypeError:  # Python < 3.12
            tf.extractall(tmp)
    shutil.rmtree(root, ignore_errors=True)
    os.replace(tmp, root)
    return dest


# ---------------------------------------------------------------- build / flash
def build_dir(cfg, src: Dict[str, Any], fqbn: str) -> str:
    tag = "worktree" if src["kind"] == "worktree" else src["sha"][:12]
    return _cache(cfg, "teensy_build", f"{tag}_{zlib.crc32(fqbn.encode()):08x}")


def parse_memory(text: str) -> Dict[str, str]:
    out = {}
    for key in ("FLASH", "RAM1", "RAM2"):
        m = re.search(rf"{key}:\s*(.+)", text)
        if m:
            out[key] = m.group(1).strip()
    return out


class _CompileLog:
    """Job proxy for a --verbose compile: keeps short lines (stage markers, warnings,
    errors, memory report), counts compiler calls instead of logging each long command
    line, and keeps job.meta["stage"] current."""

    def __init__(self, job):
        self.job = job
        self.lines = job.lines
        job.meta.update(stage="Compiling", compiled=0, reused=0)

    def add(self, line: str) -> None:
        s, m = line.strip(), self.job.meta
        low = s.lower()
        if "arm-none-eabi-g" in s and " -c " in s:
            m["compiled"] += 1
            return
        if low.startswith("using previously compiled file") or low.startswith("using precompiled"):
            m["reused"] += 1
            return
        if low.startswith("linking everything"):
            m["stage"] = "Linking"
        elif low.startswith("memory usage"):
            m["stage"] = "Memory report"
        if len(s) > 240 and ("arm-none-eabi" in s or "\\tools\\" in s or "/tools/" in s) and "error" not in low:
            return                      # other long tool command lines
        self.job.add(line)


def compile_job(cfg, job, run_process, source: Optional[str] = None) -> Dict[str, Any]:
    """Build *source* (a branch name or WORKTREE) with the pinned board settings.
    source=None keeps the old behaviour of building the newest firmware branch."""
    job.meta["stage"] = "Preparing"
    if source is None:
        source = sources(cfg)["newest"] or WORKTREE
    src = resolve(cfg, source)
    board = board_settings(cfg)
    job.add(f"Source: {src['name']} @ {src['short']}  {src.get('subject', '')}")
    job.add(f"Board:  {board['fqbn']}  ({board['source']})")
    if src["kind"] == "worktree":
        job.add("Note: building the working copy with uncommitted edits (cannot be flashed).")
    sketch = export_source(cfg, src)
    out_dir = build_dir(cfg, src, board["fqbn"])
    os.makedirs(out_dir, exist_ok=True)
    rc = run_process(_CompileLog(job), [cfg["paths"]["arduino_cli"], "compile", "--verbose", "--fqbn", board["fqbn"],
                                        "--warnings", "default", "--build-path", out_dir, sketch], timeout=900)
    text = "\n".join(job.lines)
    res = {"ok": rc == 0, "source": source, "branch": src["name"], "commit": src["short"], "sha": src["sha"],
           "kind": src["kind"], "dirty": src["kind"] == "worktree", "fqbn": board["fqbn"],
           "build_dir": out_dir, "memory": parse_memory(text), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    job.add("BUILD OK" if rc == 0 else f"BUILD FAILED (exit {rc})")
    job.meta["stage"] = "Done" if rc == 0 else "Failed"
    return res


def flash_block_reason(build: Optional[Dict[str, Any]], src: Dict[str, Any], board: Dict[str, Any]) -> str:
    """Why the selected source cannot be flashed with *build* ('' when it can)."""
    if src["kind"] == "worktree":
        return "The working copy has uncommitted edits. Commit and push them, then pick the branch."
    if not build or build.get("sha") != src["sha"] or build.get("fqbn") != board["fqbn"]:
        return f"Build {src['name']} @ {src['short']} first."
    if not build.get("ok"):
        return "The last build failed."
    return ""


# ---------------------------------------------------------------- "Reboot OK" from USB
TEENSY_VID, PID_SERIAL, PID_BOOT = "16C0", "0483", "0478"
BOOT_APPEAR_S = 8.0       # after the loader returns, the bootloader must have shown up by now
REBOOT_TIMEOUT_S = 15.0   # ... and the board must be back on its serial port within this


def usb_ids(vid: str = TEENSY_VID):
    """Instance IDs of PRESENT USB devices with this VID (Windows cfgmgr32, ~2 ms), or None if
    the query is not available (then flash_job falls back to watching the COM port list)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        cm = ctypes.WinDLL("cfgmgr32")
        flt, n, flags = ctypes.c_wchar_p("USB"), wintypes.ULONG(0), 0x1 | 0x100   # ENUMERATOR | PRESENT
        if cm.CM_Get_Device_ID_List_SizeW(ctypes.byref(n), flt, flags) != 0:
            return None
        buf = ctypes.create_unicode_buffer(n.value)
        if cm.CM_Get_Device_ID_ListW(flt, buf, n, flags) != 0:
            return None
        ids = ctypes.wstring_at(ctypes.addressof(buf), n.value).split("\x00")
        v = "VID_" + vid.upper()
        return {i for i in ids if v in i.upper()}
    except Exception:
        return None


class UsbWatch(threading.Thread):
    """Follows the Teensy through a flash the way the Teensy Loader does: the HalfKay
    bootloader (PID 0478) appears = programming; after it, the serial device (PID 0483)
    appears again = "Reboot OK". Polls every 0.1 s."""

    def __init__(self, ids_fn=None, period: float = 0.1) -> None:
        super().__init__(daemon=True, name="teensy-usb-watch")
        self.ids_fn = ids_fn or usb_ids
        self.period = period
        self.t0 = time.time()
        self.available = True
        self.boot_at: Optional[float] = None
        self.boot_gone_at: Optional[float] = None
        self.back_at: Optional[float] = None
        self._halt = threading.Event()

    @staticmethod
    def _has(ids, pid):
        return any(f"PID_{pid}" in i.upper() and "&MI_" not in i.upper() for i in ids)

    def run(self) -> None:
        while not self._halt.is_set():
            ids = self.ids_fn()
            now = time.time()
            if ids is None:
                self.available = False
                return
            boot, ser = self._has(ids, PID_BOOT), self._has(ids, PID_SERIAL)
            if boot and self.boot_at is None:
                self.boot_at = now
            if self.boot_at is not None and not boot and self.boot_gone_at is None:
                self.boot_gone_at = now
            if self.boot_at is not None and ser and not boot and self.back_at is None:
                self.back_at = now
                return
            self._halt.wait(self.period)

    def stop(self) -> None:
        self._halt.set()


FLASHING = threading.Event()   # set while flash_job runs: the port scanner starts nothing new then


def flash_job(cfg, job, run_process, port: Dict[str, str], build: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    FLASHING.set()
    try:
        return _flash_job(cfg, job, run_process, port, build, dry_run)
    finally:
        FLASHING.clear()


def _flash_job(cfg, job, run_process, port: Dict[str, str], build: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    addr, proto = port.get("upload_address") or port.get("port"), port.get("upload_protocol") or "serial"
    cmd = [cfg["paths"]["arduino_cli"], "upload", "--fqbn", build["fqbn"], "-p", addr, "-l", proto,
           "--input-dir", build["build_dir"]]
    result, rc = "dry-run", 0
    job.meta.update(stage="Uploading", port_back=None, back_after_s=None)
    job.add(f"Flash {build['branch']} @ {build['commit']} with {build['fqbn']} to {port.get('label') or addr}"
            f" (upload via {proto} {addr})")
    if dry_run:
        job.add("DRY RUN - the loader is NOT called. Would run:")
        job.add("  " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
        job.meta["stage"] = "Done (dry run)"
    else:
        job.add("The Teensy Loader window may open in the background; no action is needed there.")
        watch = UsbWatch()
        watch.start()
        n0 = len(job.lines)
        rc = run_process(job, cmd, timeout=180)
        out = "\n".join(list(job.lines)[n0:]).lower()
        bad = [w for w in ("error", "failed", "not found", "unable", "timeout", "timed out") if w in out]
        if rc != 0 or bad:
            watch.stop()
            job.meta["stage"] = "Failed"
            reason = f"loader exit {rc}" + (f"; it said: {', '.join(bad)}" if bad else "")
            job.add(f"FLASH FAILED ({reason})")
            job.meta["reason"] = reason
            result, rc = f"failed: {reason}", rc or 1
        else:
            t_exit = time.time()
            while watch.is_alive():
                now = time.time()
                if watch.boot_at is None:
                    job.meta["stage"] = "Waiting for bootloader"
                    if now - t_exit > BOOT_APPEAR_S:
                        break
                else:
                    job.meta["stage"] = "Programming" if watch.boot_gone_at is None else "Rebooting"
                    if now - max(t_exit, watch.boot_at) > REBOOT_TIMEOUT_S:
                        break
                time.sleep(0.1)
            watch.stop()
            if not watch.available:
                job.add("USB watch not available here: checking the COM port list instead.")
                back = _port_back_fallback(cfg)
                ok = back is not None
                reason = "" if ok else "no reboot (serial port not back)"
            elif watch.back_at is not None:
                back = _port_back_fallback(cfg, wait_s=5) or "its USB serial port"
                ok, reason = True, ""
            else:
                back, ok = None, False
                reason = "board never entered bootloader" if watch.boot_at is None else "no reboot"
            if ok:
                secs = round((watch.back_at or time.time()) - (watch.boot_at or t_exit), 1) if watch.available else None
                job.meta.update(stage="Reboot OK", port_back=back, back_after_s=secs)
                job.add(f"Reboot OK - bootloader seen, board back on {back}" + (f" after {secs} s" if secs is not None else ""))
                job.add("FLASH OK")
                result = "ok"
            else:
                job.meta.update(stage="Failed", reason=reason)
                job.add(f"FLASH FAILED - {reason}")
                result, rc = f"failed: {reason}", 1
    log_path = os.path.join(_log_dir(cfg), "flash_log.csv")
    new = not os.path.exists(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        if new:
            w.writerow(["time", "branch", "commit", "port", "dry_run", "result", "build_dir", "fqbn"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), build["branch"], build["commit"], port.get("label") or addr,
                    dry_run, result, build["build_dir"], build["fqbn"]])
    job.add(f"logged to {log_path}")
    return {"ok": rc == 0, "result": result, "reason": job.meta.get("reason", ""), "dry_run": dry_run, "commit": build["commit"],
            "branch": build["branch"], "port": job.meta.get("port_back") or addr,
            "back_after_s": job.meta.get("back_after_s"), "time": time.strftime("%Y-%m-%d %H:%M:%S")}


def _port_back_fallback(cfg, wait_s: float = 25.0) -> Optional[str]:
    """COM name of the Teensy once it is listed again (not in bootloader), or None."""
    t0 = time.time()
    sc = scanner(cfg)
    while time.time() - t0 < wait_s:
        sc.rescan()
        time.sleep(1.0)
        ports = [q for q in sc.get().get("ports", []) if q.get("teensy") and q.get("mode") != "Bootloader"
                 and re.fullmatch(r"COM\d+|/dev/\S+", q.get("port") or "")]
        if ports:
            return ports[0]["port"]
    return None


def last_flash_any(cfg) -> Optional[Dict[str, str]]:
    """Newest real (not dry-run) flash from logs/flash_log.csv, whatever its result."""
    path = os.path.join(_log_dir(cfg), "flash_log.csv")
    if not os.path.exists(path):
        return None
    last = None
    with open(path, newline="", encoding="utf-8") as fp:
        for row in csv.reader(fp):
            if len(row) >= 6 and row[0] != "time" and row[4] == "False":
                last = {"time": row[0], "branch": row[1], "commit": row[2], "port": row[3], "result": row[5]}
    return last


def last_flash(cfg) -> Optional[Dict[str, str]]:
    """Newest real (not dry-run) successful flash from logs/flash_log.csv."""
    path = os.path.join(_log_dir(cfg), "flash_log.csv")
    if not os.path.exists(path):
        return None
    last = None
    with open(path, newline="", encoding="utf-8") as fp:
        for row in csv.reader(fp):
            if len(row) >= 6 and row[0] != "time" and row[4] == "False" and row[5] == "ok":
                last = {"time": row[0], "branch": row[1], "commit": row[2], "port": row[3],
                        "fqbn": row[7] if len(row) > 7 else ""}
    return last


# ---------------------------------------------------------------- USB port detection
def parse_board_list(text: str) -> List[Dict[str, Any]]:
    """`arduino-cli board list --format json` (0.x list or 1.x {"detected_ports": [...]})
    -> one entry per device, Teensys first. A Teensy in Serial mode is reported twice
    (serial COMx + teensy usb:...); they are merged: monitor on COMx, upload via teensy."""
    data = json.loads(text or "[]")
    items = data.get("detected_ports", []) if isinstance(data, dict) else data
    devices: Dict[str, Dict[str, Any]] = {}
    for it in items or []:
        p = it.get("port") or it
        addr, proto = p.get("address", ""), p.get("protocol", "")
        props = p.get("properties") or {}
        boards = it.get("matching_boards") or it.get("boards") or []
        vid = (props.get("vid") or "").lower().replace("0x", "")
        label = p.get("label") or addr
        is_teensy = vid == "16c0" or proto == "teensy" or any("teensy" in (b.get("fqbn") or "") for b in boards)
        com = addr if re.fullmatch(r"COM\d+|/dev/\S+", addr or "") else ""
        m = re.match(r"(COM\d+|/dev/\S+)", label or "")
        if not com and m:
            com = m.group(1)
        serial_no = props.get("serialNumber") or props.get("serial") or ""
        # One row per board: key by COM port first, then serial number, then address. A Teensy
        # shows up twice (COMx serial + teensy-protocol port) with different serial numbers
        # (1608535 vs 16085350: Teensyduino appends a 0 on the USB side), and the serial entry
        # may carry no VID / board, so COM alone decides; COM-less rows are merged below.
        key = com or serial_no or addr
        d = devices.setdefault(key, {"port": "", "label": "", "board": "", "serial_number": serial_no,
                                     "teensy": False, "mode": "", "monitor_address": "", "monitor_protocol": "",
                                     "upload_address": "", "upload_protocol": "", "_serials": set()})
        d["teensy"] |= is_teensy
        if serial_no:
            d["_serials"].add(serial_no)
            d["serial_number"] = d["serial_number"] or serial_no
        if boards and not d["board"]:
            d["board"] = boards[0].get("name") or boards[0].get("fqbn") or ""
        if com:
            d["port"] = com
        if proto == "serial" and com:
            d["monitor_address"], d["monitor_protocol"] = com, "serial"
            if not d["upload_address"]:
                d["upload_address"], d["upload_protocol"] = com, "serial"
        if proto == "teensy":
            d["upload_address"], d["upload_protocol"] = addr, "teensy"
            if not d["monitor_address"]:
                d["monitor_address"], d["monitor_protocol"] = addr, "teensy"
            low = (label or "").lower()
            d["mode"] = "Bootloader" if ("bootloader" in low or "halfkay" in low) else (
                label.split(")")[-1].strip() if ")" in label else "")
        d["label"] = d["label"] or label
    # a row without COM (teensy-protocol entry whose label has no COMx) belongs to the COM row
    # of the same board: serial numbers equal, or equal up to Teensyduino's trailing 0
    def _same(a: set, b: set) -> bool:
        return any(x == y or x == y + "0" or y == x + "0" for x in a for y in b)
    for k in [k for k, d in devices.items() if not re.fullmatch(r"COM\d+|/dev/\S+", k)]:
        d = devices[k]
        host = next((h for hk, h in devices.items() if hk != k and re.fullmatch(r"COM\d+|/dev/\S+", hk)
                     and d["_serials"] and _same(d["_serials"], h["_serials"])), None)
        if host is None:
            continue
        host["teensy"] |= d["teensy"]
        host["board"] = host["board"] or d["board"]
        if d["upload_protocol"] == "teensy":
            host["upload_address"], host["upload_protocol"] = d["upload_address"], "teensy"
            host["mode"] = host["mode"] or d["mode"]
        host["_serials"] |= d["_serials"]
        del devices[k]
    out = list(devices.values())
    for d in out:
        d.pop("_serials", None)
        if not d["port"]:
            d["port"] = d["upload_address"] or d["monitor_address"]
        name = d["board"] or ("Teensy" if d["teensy"] else "Serial device")
        where = d["port"] if re.fullmatch(r"COM\d+|/dev/\S+", d["port"] or "") else "USB, no COM port"
        d["label"] = f"{where} · {name}" + (f" · {d['mode']}" if d["mode"] else "")
    out.sort(key=lambda d: (not d["teensy"], d["port"]))
    return out


def _pnp_ports() -> List[Dict[str, Any]]:
    """Fallback when arduino-cli is unavailable: Teensy (VID 16C0) COM ports via Windows PnP."""
    if os.name != "nt":
        return []
    ps = ("Get-CimInstance Win32_PnPEntity | Where-Object { $_.DeviceID -like '*VID_16C0*' } | "
          "ForEach-Object { $_.Name + '|' + $_.DeviceID }")
    r = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=20)
    out = []
    for line in r.stdout.splitlines():
        if "|" not in line:
            continue
        name, dev = line.split("|", 1)
        m = re.search(r"\((COM\d+)\)", name)
        com = m.group(1) if m else ""
        out.append({"port": com or "Teensy (no COM port)", "label": f"{com or 'no COM'} · {name.strip()}",
                    "board": "Teensy", "serial_number": "", "teensy": True, "mode": "",
                    "monitor_address": com, "monitor_protocol": "serial" if com else "",
                    "upload_address": com, "upload_protocol": "serial" if com else ""})
    return out


class PortScanner:
    """USB port list for the Teensy page; get() never blocks.

    Preferred (2026-11-23): one long-lived `arduino-cli board list --watch --format jsonmini`,
    the same discovery the Arduino IDE uses. It reports every plug/unplug within about
    a second, so no new arduino-cli process (1-5 s each on Windows) starts per scan.
    Fallback when the watcher cannot run (older arduino-cli, crash 3x in a row): one
    `board list` every 3 s while the Teensy page is open (touched in the last 20 s),
    otherwise every 15 s. Rescan restarts the watcher (fresh list) or scans now.
    status() tells the page whether a (re)scan is still running and when it finished.
    """

    FAST_S, SLOW_S, ACTIVE_S = 3.0, 15.0, 20.0
    SETTLE_S = 3.0          # watcher (re)started: list is complete after this long without news ...
    QUIET_S = 0.6           # ... or this long after the last add/remove event
    WATCH_FAILS = 3

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._raw: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._ports: List[Dict[str, Any]] = []
        self._error: Optional[str] = None
        self._scanned: Optional[float] = None
        self._touched = 0.0
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None
        self.mode = "watch"                 # "watch" | "poll"
        self._scan_started: Optional[float] = time.time()   # first list pending
        self._last_event = 0.0
        self._rescan_at: Optional[float] = None     # last Rescan press (for "Rescanned hh:mm:ss")
        self._restarting = False
        self._closed = False                # close(): the threads end, no new arduino-cli starts
        atexit.register(self.close)

    # ---- thread management
    def _ensure(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="teensy-ports", daemon=True)
            self._thread.start()

    def _cli(self) -> str:
        return self.cfg["paths"].get("arduino_cli") or ""

    def _run(self) -> None:
        if self.mode == "watch" and self._cli() and os.path.exists(self._cli()):
            self._watch_loop()
        if self._closed:
            return
        self.mode = "poll"
        self._poll_loop()

    def close(self) -> None:
        self._closed = True
        self._wake.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    # ---- watch mode
    def _watch_loop(self) -> None:
        fails = 0
        while fails < self.WATCH_FAILS and not self._closed:
            t0 = time.time()
            with self._lock:
                self._raw.clear()
                self._scan_started = t0
                self._restarting = False
            try:
                proc = subprocess.Popen(
                    [self._cli(), "board", "list", "--watch", "--format", "jsonmini"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                    encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
            except Exception as exc:
                with self._lock:
                    self._error = f"arduino-cli board list --watch failed ({exc})"
                return
            self._proc = proc
            die_with_this_process(proc)       # no orphan watcher after an app restart
            junk: List[str] = []
            for line in proc.stdout:
                line = line.strip()
                try:
                    ev = json.loads(line) if line.startswith("{") else None
                except ValueError:
                    ev = None
                if not isinstance(ev, dict):
                    if line:
                        junk.append(line)
                    continue
                self._on_event(ev)
            proc.wait()
            if self._closed:
                return
            with self._lock:
                restarting = self._restarting
            if restarting:
                fails = 0
                continue
            fails = fails + 1 if time.time() - t0 < 30 else 1
            with self._lock:
                self._error = ("USB watch stopped (arduino-cli exit %s%s); restarting"
                               % (proc.returncode, (": " + junk[-1][:120]) if junk else ""))
            time.sleep(1.0)
        with self._lock:
            self._error = None      # poll mode explains itself if it fails too

    def _on_event(self, ev: Dict[str, Any]) -> None:
        typ = ev.get("eventType") or ev.get("type") or ""
        if typ == "error" or ev.get("error"):
            with self._lock:
                self._error = f"USB watch: {ev.get('error') or 'error'}"
            return
        port = ev.get("port") or {}
        key = (port.get("address", ""), port.get("protocol", ""))
        with self._lock:
            if typ == "add":
                self._raw[key] = {"port": port, "matching_boards": ev.get("matching_boards") or []}
            elif typ == "remove":
                self._raw.pop(key, None)
            else:
                return
            self._ports = parse_board_list(json.dumps(list(self._raw.values())))
            self._last_event = time.time()
            self._error = None

    # ---- poll mode (fallback)
    def _poll_loop(self) -> None:
        while not self._closed:
            if FLASHING.is_set():               # the loader owns the USB port: start nothing new
                self._wake.wait(0.5)
                self._wake.clear()
                continue
            try:
                self.scan_once()
            except Exception as exc:  # never let the scanner die
                with self._lock:
                    self._error = str(exc)
                    self._scan_started = None
            active = time.monotonic() - self._touched < self.ACTIVE_S
            self._wake.wait(self.FAST_S if active else self.SLOW_S)
            self._wake.clear()

    def scan_once(self) -> List[Dict[str, Any]]:
        cli = self._cli()
        try:
            if not cli or not os.path.exists(cli):
                raise FileNotFoundError(f"arduino-cli not found at {cli}")
            r = _run([cli, "board", "list", "--format", "json"], timeout=20)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or r.stdout).strip()[:200])
            ports, err = parse_board_list(r.stdout), None
        except Exception as exc:
            ports, err = _pnp_ports(), f"arduino-cli board list failed ({exc}); used Windows device list"
        with self._lock:
            self._ports, self._error, self._scanned, self._scan_started = ports, err, time.time(), None
        return ports

    # ---- page API
    def touch(self) -> None:
        self._touched = time.monotonic()
        self._ensure()

    def rescan(self) -> None:
        """Fresh list now. While a (re)scan is still running (no double scans) or a flash
        runs (the loader owns the USB port then) no new scan starts, but the press is still
        recorded, so the page shows "Rescanned … · N Teensy found" once the list settles."""
        self.touch()
        with self._lock:
            self._rescan_at = time.time()
            if FLASHING.is_set() or self._busy_locked():
                return
            self._scan_started = time.time()
            proc = self._proc if self.mode == "watch" else None
            if proc is not None and proc.poll() is None:
                self._restarting = True
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        else:
            self._wake.set()

    def _busy_locked(self) -> bool:
        if self._scan_started is None:
            return False
        if self.mode == "watch":
            now = time.time()
            settled = (now - self._scan_started > self.SETTLE_S or
                       (self._last_event > self._scan_started and now - self._last_event > self.QUIET_S))
            if settled:
                self._scanned = max(self._last_event, self._scan_started) if self._last_event > self._scan_started \
                    else self._scan_started + self.SETTLE_S
                self._scan_started = None
                return False
        return True

    def status(self) -> Dict[str, Any]:
        """{'scanning', 'scanned' (epoch of the last finished list), 'rescan_at', 'mode', 'error'}."""
        self._ensure()
        with self._lock:
            busy = self._busy_locked()
            return {"scanning": busy, "scanned": self._scanned, "rescan_at": self._rescan_at,
                    "mode": self.mode, "error": self._error}

    def get(self) -> Dict[str, Any]:
        self._ensure()
        with self._lock:
            self._busy_locked()
            return {"ports": [dict(p) for p in self._ports], "error": self._error, "scanned": self._scanned}


_scanner: Optional[PortScanner] = None


def scanner(cfg) -> PortScanner:
    global _scanner
    if _scanner is None:
        _scanner = PortScanner(cfg)
    return _scanner


def list_teensy_ports(cfg) -> List[Dict[str, Any]]:
    """Teensy devices from the background scan (kept for the status poller / Home)."""
    return [p for p in scanner(cfg).get()["ports"] if p.get("teensy")]


def repo_summary(cfg) -> Dict[str, Any]:
    """Short status for Home: newest firmware branch + working copy state."""
    try:
        s = sources(cfg)
    except Exception as exc:
        return {"error": str(exc), "branch": "?", "head": "?", "dirty": [], "repo": _repo(cfg)}
    newest = next((b for b in s["branches"] if b["newest"]), None)
    head = f"{newest['short']} {newest['subject']} ({_age(newest['time'])})" if newest else "?"
    return {"branch": newest["name"] if newest else "?", "head": head, "dirty": s["worktree"]["dirty"],
            "repo": _repo(cfg), "checked_out": s["worktree"]["branch"]}


# ---------------------------------------------------------------- serial monitor
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

    def start(self, port, baud: int = SERIAL_BAUD) -> None:
        """*port* is a scanner entry (dict) or a plain address such as 'COM5'."""
        if isinstance(port, dict):
            addr = port.get("monitor_address") or port.get("port")
            proto = port.get("monitor_protocol") or "serial"
        else:
            addr, proto = port, "serial"
        self.stop()
        safe = re.sub(r"[^A-Za-z0-9]+", "_", addr).strip("_") or "port"
        self.log_path = os.path.join(_log_dir(self.cfg), time.strftime(f"serial_{safe}_%Y%m%d_%H%M%S.log"))
        self.port = addr
        self.error = None
        self.proc = subprocess.Popen(
            [self.cfg["paths"]["arduino_cli"], "monitor", "-p", addr, "-l", proto, "--fqbn", BOARD,
             "--config", f"baudrate={baud}", "--quiet"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def _reader(self, proc) -> None:
        with open(self.log_path, "a", encoding="utf-8") as log:
            for line in proc.stdout:
                stamped = time.strftime("%H:%M:%S ") + line.rstrip("\r\n")
                with self._lock:
                    self.lines.append(stamped)
                log.write(stamped + "\n")
                log.flush()
        proc.wait()
        if proc.returncode not in (0, None) and proc is self.proc:
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


# ---------------------------------------------------------------- IMU data (from the live bus health)
class ImuWatch:
    """Remembers IMU state changes seen in the live stream's health snapshot."""

    def __init__(self) -> None:
        self.state = None
        self.since = None
        self.events: deque = deque(maxlen=50)
        self.invalid_spells = 0

    def update(self, health: Dict[str, Any]) -> Dict[str, Any]:
        g = ((health or {}).get("groups") or {}).get("imu") or {}
        st = g.get("state", "idle")
        now = time.time()
        if st != self.state:
            if self.state is not None:
                self.events.appendleft((now, self.state, st))
            if st == "bad":
                self.invalid_spells += 1
            self.state, self.since = st, now
        return {"state": st, "since": self.since, "recent_bad": g.get("recent_bad", 0),
                "recent_total": g.get("recent_total", 0), "bad_total": g.get("bad_total", 0),
                "total": g.get("total", 0), "invalid_spells": self.invalid_spells, "events": list(self.events)}
