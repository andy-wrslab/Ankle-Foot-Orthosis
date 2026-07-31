#!/usr/bin/env python3
"""
AFO Rig Console backend.

Data plane: instrument push over XCP, with SDI-run polling as fallback.
    A single long-lived slrealtime.Instrument (created once per MATLAB
    session, never removed — churn wedges XCP; see afo_stream_setup.m)
    receives every SDI-instrumented (blue badge) signal by push callback
    at the full ~1 kHz stream rate into an accumulator, which the server
    drains about once per second (afo_stream_drain.m). If the instrument
    plane cannot be established, the server falls back to incrementally
    reading the live SDI run that startRecording creates. Either way,
    vector signals expand into per-element channels (name(1..w)), rows
    re-emit on a uniform 100 Hz grid, and the dashboard receives them
    over WebSocket. The discovered channel set is cached
    (signals_cache.json) and adopted by the dashboard automatically.

Recording:
    While the model runs, the target records all instrumented signals
    (SDI + File Log on the target SSD). When the model stops, the server
    imports the newest file log and exports a full-rate wide CSV
    (target_<stamp>.csv). Independently, the live stream is mirrored to
    a host-side CSV (runNNN_*.csv) as a belt-and-braces copy.

Control plane: MATLAB engine (shared desktop session first, headless
    fallback) -> slrealtime start / stop / setparam. CONNECT in the UI
    means the Speedgoat target; the engine is background plumbing.

Run:  python server.py        then open http://localhost:8321.
"""

import argparse
import array
import asyncio
import contextlib
import json
import re
import struct
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
MATLAB_DIR = HERE / "matlab"
CACHE_FILE = HERE / "signals_cache.json"

ap = argparse.ArgumentParser(description="AFO Rig Console backend")
ap.add_argument("--http-host", default="127.0.0.1", help="bind for the web UI (0.0.0.0 to reach it from other lab PCs)")
ap.add_argument("--http-port", type=int, default=8321)
ap.add_argument("--logs-dir", default=str(HERE / "trial_logs"))
ap.add_argument("--mldatx", default="", help="path of the built real-time application for LOAD")
ap.add_argument("--target", default="TargetPC1", help="Speedgoat target name for slrealtime()")
ap.add_argument("--target-ip", default="192.168.7.5", help="Speedgoat IP for the fast reachability probe (ping)")
ap.add_argument("--gp-mat", default=str(HERE / "gp" / "best_gp_Haoran_synced_.mat"),
                help="subject GP ensemble MAT-file the model requires; loaded into the base "
                     "workspace on every CONNECT (empty string disables)")
ap.add_argument("--own-engine", action="store_true",
                help="always start a private headless MATLAB engine (ignore shared sessions) — "
                     "no manually-opened MATLAB needed")
ap.add_argument("--no-matlab", action="store_true", help="disable the MATLAB engine entirely")
ap.add_argument("--no-spawn", action="store_true", help="attach to a shared MATLAB session only; never start a headless one")
ARGS = ap.parse_args()

ENGINE_GAP_S = 6.0    # stream gap threshold (drain slices arrive every ~1 s)
AUTOREC_STOP_S = 15.0 # close the host CSV after this much stream silence
FREEZE_AFTER_S = 2.0  # a lively channel unchanged this long -> frozen
LIVELY_N = 20         # channel must change this many times...
LIVELY_WIN_S = 5.0    # ...within this window to be freeze-eligible
BATCH_S = 0.05        # WebSocket flush interval
STATUS_S = 0.5        # status broadcast interval
BACKFILL_S = 10.0     # history replayed to a newly connected client
GRID_DT = 0.001       # stream is re-emitted on this uniform grid (ZOH) —
                      # 1 kHz, matching the model base rate, so the console
                      # records and shows full-resolution data like the SDI
DRAIN_S = 0.4         # SDI-run drain interval
                      # (its cost grows with run length; the model's own File
                      # Log blocks record continuously regardless)


def _san(name):
    return re.sub(r"[^0-9A-Za-z_()\[\] .:/#-]", "_", str(name)).strip() or "signal"


# --------------------------------------------------------------------------
# channel set — discovered from the live SDI run, cached across sessions
# --------------------------------------------------------------------------
class ChannelSet:
    def __init__(self):
        self.defs = []
        self.groups = []
        self.names = []
        self.flat_excluded = set()
        cached = self._load_cache()
        if cached:
            self.defs, self.groups = cached
        self._finish()

    def _finish(self):
        self.names = [d["name"] for d in self.defs]
        self.flat_excluded = {d["name"] for d in self.defs if d.get("step") or d.get("hold")}

    def _load_cache(self):
        try:
            j = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if j.get("defs"):
                return j["defs"], j.get("groups") or [{"id": "signals", "label": "SIGNALS"}]
        except Exception:
            pass
        return None

    def save_cache(self):
        with contextlib.suppress(Exception):
            CACHE_FILE.write_text(json.dumps({"defs": self.defs, "groups": self.groups}, indent=1),
                                  encoding="utf-8")

    def adopt_discovered(self, sig_list):
        """sig_list: [(name, width)] in stable order. Returns True if changed."""
        defs, groups, seen_groups = [], [], []
        for name, w in sig_list:
            base = _san(name)
            if w <= 1:
                defs.append({"id": base, "name": base, "group": "signals", "units": "—", "prec": 3})
                if "signals" not in seen_groups:
                    seen_groups.append("signals")
            else:
                gid = base
                if gid not in seen_groups:
                    seen_groups.append(gid)
                for k in range(1, w + 1):
                    nm = f"{base}({k})"
                    defs.append({"id": nm, "name": nm, "group": gid, "units": "—", "prec": 3})
        for gid in seen_groups:
            groups.append({"id": gid, "label": gid.upper() if gid != "signals" else "SIGNALS"})
        if [d["name"] for d in defs] == self.names:
            return False
        self.defs, self.groups = defs, groups
        self._finish()
        self.save_cache()
        return True

CH = ChannelSet()

# --------------------------------------------------------------------------
# stream state (rows of float values on the model clock)
# --------------------------------------------------------------------------
class Stream:
    def __init__(self):
        self.reset()
        self.gaps = 0
        self.src = None
        self.mode = "none"          # engine | none
        self.gap_window = ENGINE_GAP_S

    def reset(self):
        self.ring = deque(maxlen=20000)      # (t, tuple of floats)
        self.batch = []
        self.n_rows = 0
        self.last_t = 0.0
        self.last_wall = 0.0
        self.was_active = False
        self.rate_win = deque(maxlen=4000)
        self.last_vals = {}
        self.last_change = {}
        self.change_hist = {}       # name -> deque of recent change times

    def alive(self):
        return self.last_wall and (time.monotonic() - self.last_wall) < self.gap_window

    def rate(self):
        cut = time.monotonic() - 1.0
        while self.rate_win and self.rate_win[0] < cut:
            self.rate_win.popleft()
        return len(self.rate_win)

    def push(self, t, vals, wall=None):
        wall = wall or time.monotonic()
        if self.was_active and self.last_wall and (wall - self.last_wall) > self.gap_window:
            self.gaps += 1
            note("error", "data stream gap recovered", f"gap={round((wall-self.last_wall)*1000)} ms")
        if not self.was_active:
            note("ok", "data stream active", f"{len(CH.names)} channels")
            self.was_active = True
        for name, v in zip(CH.names, vals):
            lv = self.last_vals.get(name)
            if lv is None or abs(v - lv) > 1e-9:
                self.last_change[name] = t
                h = self.change_hist.get(name)
                if h is None:
                    h = self.change_hist[name] = deque(maxlen=LIVELY_N)
                h.append(t)
            self.last_vals[name] = v
        self.n_rows += 1
        self.last_t = t
        self.last_wall = wall
        self.rate_win.append(wall)
        row = (t, tuple(vals))
        self.ring.append(row)
        self.batch.append(row)
        REC.write(t, vals)

    def flat_channels(self):
        """Frozen channels: only channels that were recently lively (>=LIVELY_N
        changes within LIVELY_WIN_S — i.e. noisy analog signals) can be flagged.
        Constants, status codes and step signals are never eligible."""
        if not self.alive():
            return []
        t = self.last_t
        out = []
        for n in CH.names:
            h = self.change_hist.get(n)
            if not h or len(h) < LIVELY_N:
                continue
            lc = self.last_change.get(n, 0.0)
            if t - lc <= FREEZE_AFTER_S:
                continue
            if (h[-1] - h[0]) <= LIVELY_WIN_S:      # it WAS changing fast, then stopped
                out.append(n)
        return out

STREAM = Stream()
EVENTS = asyncio.Queue()


def note(sev, msg, raw=""):
    print(f"[{sev}] {msg}" + (f" | {raw}" if raw else ""), flush=True)
    with contextlib.suppress(Exception):
        EVENTS.put_nowait({"type": "event", "sev": sev, "msg": msg, "raw": raw})


# --------------------------------------------------------------------------
# host-side CSV recorder (live-stream copy; the authoritative full-rate
# record is the imported target file log -> target_<stamp>.csv)
# --------------------------------------------------------------------------
class Recorder:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.f = None
        self.path = None
        self.rows = 0
        self.started = None
        self.gaps_at_start = 0

    def next_run_no(self):
        best = 0
        for p in self.root.glob("run*.csv"):
            m = re.match(r"run(\d+)", p.stem)
            if m:
                best = max(best, int(m.group(1)))
        return best + 1

    @property
    def on(self):
        return self.f is not None

    def start(self):
        if self.on:
            return self.path.name
        if not CH.names:
            return None
        n = self.next_run_no()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = self.root / f"run{n:03d}_{stamp}.csv"
        self.f = open(self.path, "w", buffering=1 << 16, encoding="utf-8")
        self.f.write("time_s," + ",".join(CH.names) + "\n")
        self.rows = 0
        self.started = datetime.now().isoformat(timespec="seconds")
        self.gaps_at_start = STREAM.gaps
        note("ok", f"recording started · {self.path.name}", str(self.root))
        return self.path.name

    def write(self, t, values):
        if self.f:
            self.f.write(f"{t:.4f}," + ",".join(f"{v:.6g}" for v in values) + "\n")
            self.rows += 1

    def stop(self, reason=""):
        if not self.on:
            return None
        self.f.close()
        self.f = None
        meta = {
            "file": self.path.name,
            "rows": self.rows,
            "started": self.started,
            "stopped": datetime.now().isoformat(timespec="seconds"),
            "stream_gaps_during_run": STREAM.gaps - self.gaps_at_start,
            "channels": CH.names,
            "source": STREAM.src,
            "note": reason or "host-side live copy; full-rate record is the imported target file log",
        }
        self.path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        note("ok", f"recording stopped · {self.path.name}",
             f"{self.rows} rows · gaps={meta['stream_gaps_during_run']}")
        name = self.path.name
        self.path = None
        return name

REC = Recorder(Path(ARGS.logs_dir))


# --------------------------------------------------------------------------
# MATLAB engine (control plane + SDI data plane)
# --------------------------------------------------------------------------
class MatlabRT:
    def __init__(self):
        self.eng = None
        self.mode = None
        self.available = None
        self.err = ""

    def _import(self):
        if self.available is not None:
            return self.available
        if ARGS.no_matlab:
            self.available, self.err = False, "disabled with --no-matlab"
            return False
        try:
            import matlab.engine  # noqa: F401
            self.available = True
        except Exception as e:
            self.available, self.err = False, f"matlabengine not installed ({e})"
        return self.available

    # blocking; call via asyncio.to_thread.
    # The engine is plumbing: ensure_engine attaches it quietly; CONNECT in
    # the UI means connecting to the Speedgoat target itself.
    def ensure_engine(self, allow_spawn=True):
        if not self._import():
            return {"ok": False, "err": self.err}
        if self.eng:
            return {"ok": True, "mode": self.mode}
        import matlab.engine
        try:
            names = [] if ARGS.own_engine else matlab.engine.find_matlab()
            if names:
                self.eng = matlab.engine.connect_matlab(names[0])
                self.mode = f"shared:{names[0]}"
            elif ARGS.no_spawn or not allow_spawn:
                return {"ok": False, "err": "no shared MATLAB session found (run matlab.engine.shareEngine('AFO') in MATLAB)"}
            else:
                self.eng = matlab.engine.start_matlab()
                self.mode = "headless"
            mdir = str(MATLAB_DIR).replace("\\", "/").replace("'", "''")
            self.eng.eval(f"addpath('{mdir}');", nargout=0)
            tgt = f"'{ARGS.target}'" if ARGS.target else ""
            self.eng.eval(f"tg = slrealtime({tgt});", nargout=0)
            return {"ok": True, "mode": self.mode}
        except Exception as e:
            self.eng = None
            return {"ok": False, "err": str(e)}

    def connect_target(self):
        # fast reachability probe first (ICMP ping — the QNX target answers no
        # fixed TCP port we can rely on): an off-network rig must fail in ~2 s,
        # not block the (single-threaded) engine — and every status poll behind
        # it — on a long tg.connect timeout
        import subprocess
        try:
            p = subprocess.run(["ping", "-n", "1", "-w", "2000", ARGS.target_ip],
                               capture_output=True, timeout=6)
            reachable = p.returncode == 0
        except Exception:
            reachable = True          # probe itself failed — let tg.connect decide
        if not reachable:
            return {"ok": False,
                    "err": f"{ARGS.target} ({ARGS.target_ip}) not reachable — is this PC on the rig network?"}
        r = self.ensure_engine(True)
        if not r.get("ok"):
            return r
        # the model requires the subject GP ensemble in the base workspace —
        # load it before anything touches the target (or the model)
        gp = {"ok": True, "skipped": True}
        if ARGS.gp_mat:
            gp = self.call_json("afo_load_gp('%s')" % ARGS.gp_mat.replace("'", "''"))
        rr = self._eval("tg.connect;")
        chk = self._eval("jsonencode(logical(isConnected(tg)))", nargout=1)
        conn = False
        if chk.get("ok"):
            with contextlib.suppress(Exception):
                conn = bool(json.loads(chk["out"]))
        if conn:
            return {"ok": True, "target": ARGS.target, "gp": gp}
        return {"ok": False, "err": rr.get("err") or f"{ARGS.target} not reachable", "gp": gp}

    def disconnect_target(self):
        if self.eng:
            self._eval("tg.disconnect;")
        return {"ok": True}

    def disconnect(self):
        if self.eng:
            with contextlib.suppress(Exception):
                if self.mode == "headless":
                    self.eng.quit()
            self.eng = None
            self.mode = None
        return {"ok": True}

    def _eval(self, code, nargout=0):
        if not self.eng:
            return {"ok": False, "err": "MATLAB not connected"}
        try:
            out = self.eng.eval(code, nargout=nargout)
            return {"ok": True, "out": out}
        except Exception as e:
            return {"ok": False, "err": str(e)}

    def call_json(self, expr):
        """Evaluate an expression returning a JSON string; parse it."""
        r = self._eval(expr, nargout=1)
        if not r["ok"]:
            return {"ok": False, "err": r["err"]}
        try:
            return json.loads(r["out"])
        except Exception as e:
            return {"ok": False, "err": f"bad JSON from MATLAB: {e}"}

    def load(self):
        if not ARGS.mldatx:
            return {"ok": False, "err": "no --mldatx configured on the server"}
        p = str(Path(ARGS.mldatx)).replace("'", "''")
        return self._eval(f"tg.load('{p}');")

    def start(self):
        return self._eval("tg.start;")

    def stop(self):
        return self._eval("tg.stop;")

    def setparam(self, block, param, value):
        blk = str(block).replace("'", "''")
        prm = str(param).replace("'", "''")
        try:
            val = float(value)
        except (TypeError, ValueError):
            return {"ok": False, "err": f"non-numeric value {value!r}"}
        mdl = "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo"
        return self._eval(f"setparam(tg, '{mdl}/{blk}', '{prm}', {val});")

    def status(self):
        if not self.eng:
            return {"connected": False, "available": bool(self._import()), "err": self.err}
        self._eval(
            "slrt_s=struct('ok',true);"
            "try, slrt_s.target_conn=isConnected(tg); catch slrt_e, slrt_s.ok=false; slrt_s.err=slrt_e.message; end;"
            "try, slrt_s.loaded=isLoaded(tg); catch, end;"
            "try, slrt_s.running=isRunning(tg); catch, end;"
            "try, slrt_s.app=char(getLastApplication(tg)); catch, end;"
            "try, slrt_s.target_status=char(string(tg.TargetStatus)); catch, end;")
        r = self._eval("jsonencode(slrt_s)", nargout=1)
        out = {"connected": True, "available": True, "mode": self.mode}
        if r["ok"]:
            with contextlib.suppress(Exception):
                out.update(json.loads(r["out"]))
        return out

ML = MatlabRT()
ML._import()   # heavy DLL import on the MAIN thread — importing matlab.engine
               # inside a worker thread can hang indefinitely
ML_STATUS_CACHE = {"connected": False, "available": None}


# --------------------------------------------------------------------------
# data plane: incremental reads of the live SDI run -> uniform-grid rows
# --------------------------------------------------------------------------
class EngineStream:
    def __init__(self):
        self.setup_ok = False
        self.next_setup_wall = 0.0    # backoff: retry setup at most every 5 s
        self.last_setup_err = ""
        self.next_rec_wall = 0.0      # backoff for recording start attempts
        self.last_rec_err = ""
        self.last_diag = ""
        self.extra_sleep = 0.0        # adaptive cadence: drains slow as runs grow
        self.last_rows_wall = 0.0     # when the live stream last produced samples
        self.restart_tried = False    # escalation 1: recording restart
        self.flush_tried = False      # escalation 2: full recovery (afo_recover)
        self.next_guidance_wall = 0.0
        self.run_pinned_wall = 0.0    # when the current SDI run was pinned (diagnostic)
        self.last_sig_t = {}      # raw signal name -> newest timestamp ingested
        self.adv_wall = {}        # raw signal name -> wall time it last advanced
        self.pend = {}            # raw signal name -> deque[(t, [element values])]
        self.chan_map = {}        # raw signal name -> expanded channel ids
        self.lastv = {}           # expanded channel name -> last value (ZOH)
        self.known = {}           # persistent discovered set: name -> width
        self.grid_t = None
        self.sdi_recording = False
        self.plane = "none"       # active data plane: instrument push / run polling
        self.setup_fail_wall = 0.0    # when setup started failing with the model running
        self.slow = set()         # polled stragglers: never gate the watermark

    def reset(self):
        self.setup_ok = False
        self.next_setup_wall = 0.0
        self.last_sig_t = {}
        self.adv_wall = {}
        self.pend = {}
        self.chan_map = {}
        self.lastv = {}
        self.known = {}
        self.grid_t = None
        self.last_rows_wall = 0.0
        self.restart_tried = False
        self.flush_tried = False
        self.next_guidance_wall = 0.0
        self.setup_fail_wall = 0.0
        self.slow = set()

    def ingest(self, signals, binpath=None):
        """Returns (changed, rows). Samples arrive via a binary side file
        (drain manifest {name,w,n,slow} + per-signal [t f64][v f32] blocks
        in `binpath` — multi-MB payloads must not cross the engine as
        strings) or as legacy JSON arrays ({name,w,t,v}). Drains may
        deliver subsets, so discovery merges into a persistent set — the
        channel manifest only changes when a genuinely new signal appears.
        Signals flagged slow=1 (polled stragglers) never gate the
        watermark; they zero-order hold like any sparse signal."""
        blob = b""
        if binpath and signals:
            try:
                with open(binpath, "rb") as f:
                    blob = f.read()
            except Exception as ex:
                note("warn", "drain binary unreadable — batch dropped", str(ex))
                return False, 0
        norm = []
        off = 0
        for s in signals:
            nm = s.get("name", "?")
            w = int(s.get("w", 1) or 1)
            if "n" in s and binpath:
                n = int(s.get("n", 0) or 0)
                tb, vb = 8 * n, 4 * n * w
                if off + tb + vb > len(blob):
                    break                     # truncated file: keep what parsed
                ts = array.array("d")
                ts.frombytes(blob[off:off + tb])
                vs = array.array("f")
                vs.frombytes(blob[off + tb:off + tb + vb])
                off += tb + vb
            else:
                ts = s.get("t") or []
                vs = s.get("v") or []
                if isinstance(ts, (int, float)):
                    ts = [ts]
                if isinstance(vs, (int, float)):
                    vs = [vs]
            if s.get("slow"):
                self.slow.add(nm)
            norm.append((nm, w, ts, vs))
        # model time jumped backward (target reboot or model restart): every
        # per-signal last-t and the watermark are ahead of the new epoch, so
        # nothing would ever count as advancing again — start over. Seen
        # live 2026-07-31 (second Speedgoat reboot of the day).
        newest = None
        for nm, w, ts, vs in norm:
            if len(ts) and (newest is None or float(ts[-1]) > newest):
                newest = float(ts[-1])
        if newest is not None and self.grid_t is not None and newest < self.grid_t - 60.0:
            note("warn", "model time jumped backward — resetting stream state",
                 f"{self.grid_t:.1f} s -> {newest:.1f} s (target reboot / model restart)")
            self.reset()
        for nm, w, ts, vs in norm:
            if self.known.get(nm) != w:
                self.known[nm] = w
                base = _san(nm)
                self.chan_map[nm] = [base] if w <= 1 else [f"{base}({k})" for k in range(1, w + 1)]
        sig_list = sorted(self.known.items())
        changed = CH.adopt_discovered(sig_list) if sig_list else False
        if changed:
            self.lastv = {}
        # buffer fresh samples per signal — different signals may lag each
        # other by a drain or two; the watermark below keeps rows honest
        noww = time.monotonic()
        for name, w, ts, vs in norm:
            q = self.pend.setdefault(name, deque())
            newest = self.last_sig_t.get(name, -1.0)
            for i, t in enumerate(ts):
                if t <= newest:
                    continue
                row = vs[i * w:(i + 1) * w]
                if len(row) != w:
                    continue
                q.append((float(t), [float(x) for x in row]))
            if len(ts) and float(ts[-1]) > newest:
                self.last_sig_t[name] = float(ts[-1])
                self.adv_wall[name] = noww
            while len(q) > 60000:
                q.popleft()
        # watermark: only emit rows where EVERY actively-advancing signal has
        # delivered its samples, so no channel is ever fabricated as flat.
        # Sparse/triggered signals (not advancing for >15 s) are excluded from
        # the watermark and simply zero-order hold — correct for them anyway.
        active = [n for n in self.known
                  if n in self.last_sig_t and n not in self.slow
                  and (noww - self.adv_wall.get(n, 0.0)) < 15.0]
        if not active:
            return changed, 0
        wm = min(self.last_sig_t[n] for n in active)
        if self.grid_t is None:
            self.grid_t = wm - GRID_DT
        rows = 0
        while self.grid_t + GRID_DT <= wm and rows < 6000:
            self.grid_t += GRID_DT
            for name, q in self.pend.items():
                chans = self.chan_map.get(name)
                if not chans:
                    continue
                while q and q[0][0] <= self.grid_t:
                    _, valsrow = q.popleft()
                    for c, vv in zip(chans, valsrow):
                        self.lastv[c] = vv
            STREAM.push(self.grid_t, [self.lastv.get(n, 0.0) for n in CH.names])
            rows += 1
        return changed, rows

ES = EngineStream()


async def _setup_fail_escalate(running):
    """Post-reboot deadlock breaker. After a Speedgoat reboot the host XCP
    session is stale: every new recording run stays empty, so stream setup
    can never succeed and the silent-stream watchdog (which requires
    setup_ok) never arms. Seen live 2026-07-31 — recovery had to be run by
    hand. If setup keeps failing for >25 s while the model runs, fire one
    full recovery from here as well."""
    if not running:
        ES.setup_fail_wall = 0.0
        return
    noww = time.monotonic()
    if not ES.setup_fail_wall:
        ES.setup_fail_wall = noww
        return
    if noww - ES.setup_fail_wall < 25 or ES.flush_tried:
        return
    ES.flush_tried = True
    ES.setup_fail_wall = 0.0
    note("warn", "setup keeps failing with the model running — full recovery",
         "stale host XCP session suspected (target reboot?) · afo_recover")
    rr = await asyncio.to_thread(ML.call_json, f"afo_recover('{ARGS.target}')")
    if rr.get("ok"):
        note("ok", "recovery sequence completed — retrying stream setup", "")
    else:
        note("warn", "recovery sequence failed", rr.get("err", ""))
    ES.sdi_recording = True
    ES.next_setup_wall = 0.0


async def engine_loop():
    while True:
        await asyncio.sleep(DRAIN_S + ES.extra_sleep)
        m = ML_STATUS_CACHE
        if not (ML.eng and m.get("connected") and m.get("target_conn")):
            if ES.setup_ok:
                ES.reset()
            continue
        # target-side SDI/FileLog recording follows the model state — and must
        # run BEFORE stream setup, whose live SDI run only exists once
        # recording is active. afo_recording is tolerant: "already recording"
        # (startup app or Explorer-initiated) counts as success.
        running = bool(m.get("running"))
        if running and not ES.sdi_recording:
            noww = time.monotonic()
            if noww >= ES.next_rec_wall:
                ES.next_rec_wall = noww + 5.0
                rr = await asyncio.to_thread(ML.call_json, "afo_recording('start')")
                if rr.get("ok"):
                    ES.sdi_recording = True
                    ES.last_rec_err = ""
                    note("ok", "target recording active",
                         "was already recording" if rr.get("state") == "already"
                         else "SDI + File Log on target")
                else:
                    err = rr.get("err", "")
                    if err != ES.last_rec_err:
                        note("warn", "target recording start failed", err)
                        ES.last_rec_err = err
        elif not running and ES.sdi_recording:
            await asyncio.to_thread(ML.call_json, "afo_recording('stop')")
            ES.sdi_recording = False
            note("info", "target recording stopped — importing file log…", "")
            asyncio.create_task(_import_filelog())
        if not ES.setup_ok:
            noww = time.monotonic()
            if noww < ES.next_setup_wall:
                continue
            ES.next_setup_wall = noww + 5.0     # gentle retry — never hammer the engine
            r = await asyncio.to_thread(ML.call_json, "afo_stream_setup()")
            if r.get("ok") and not r.get("nsignames"):
                err = "live SDI run has no signals yet (model running & recording?)"
                if err != ES.last_setup_err:
                    note("warn", "stream setup incomplete — will retry", err)
                    ES.last_setup_err = err
                await _setup_fail_escalate(running)
                continue
            if r.get("ok"):
                ES.setup_ok = True
                ES.last_setup_err = ""
                ES.setup_fail_wall = 0.0
                ES.plane = r.get("mode", "run")
                STREAM.mode = "engine"
                STREAM.src = ("instrument push (XCP)" if ES.plane == "instrument"
                              else "SDI run polling (XCP)")
                STREAM.gap_window = ENGINE_GAP_S
                ES.last_rows_wall = time.monotonic()   # grace period starts now
                ES.run_pinned_wall = time.monotonic()
                note("ok", f"live data plane ready · {ES.plane}",
                     f"{r.get('app','?')} · {r.get('nsignames')} signals")
                notes = (r.get("notes") or "").strip()
                if notes:
                    note("info", "instrumentation notes", notes[:300])
            else:
                err = r.get("err", "")
                if err != ES.last_setup_err:    # log each distinct failure once
                    note("warn", "stream setup failed", err)
                    ES.last_setup_err = err
                await _setup_fail_escalate(running)
                continue
        t0 = time.monotonic()
        r = await asyncio.to_thread(ML.call_json, "afo_stream_drain()")
        dur = time.monotonic() - t0
        # keep the shared MATLAB responsive: engine duty <= ~50%
        # smoothed pacing: a single slow call (usually engine-lock contention
        # with the status poll) must not stretch the whole cadence — average
        # it out; sustained slowness still backs the loop off
        ES.extra_sleep = max(0.0, min(2.0, 0.6 * ES.extra_sleep
                                          + 0.4 * max(0.0, dur - DRAIN_S)))
        if not r.get("ok"):
            if "re-setup" in str(r.get("err", "")):
                ES.setup_ok = False          # a new recording run started
                ES.next_setup_wall = 0.0
            continue
        # drain diagnostics — surface each distinct message once
        diag = " · ".join(r.get("diag") or [])
        if diag and diag != ES.last_diag:
            note("info", "live stream diagnostic", diag)
            ES.last_diag = diag
        # an ingest bug must never silently kill the engine loop (a TypeError
        # here did exactly that on 2026-07-31 — the server became a zombie)
        try:
            changed, _rows = ES.ingest(r.get("signals") or [], r.get("bin"))
        except Exception as ex:
            err = f"{type(ex).__name__}: {ex}"
            if err != ES.last_diag:
                note("error", "stream ingest failed — dropping this batch", err)
                ES.last_diag = err
            continue
        if _rows > 0:
            ES.last_rows_wall = time.monotonic()
        # stale-stream watchdog: model runs but no samples arrive — the app's
        # XCP live-streaming link is likely down. Try one recording restart
        # (re-establishes streaming for soft wedges), then tell the user the
        # app itself needs a reload.
        if ES.setup_ok and running and ES.last_rows_wall:
            silent = time.monotonic() - ES.last_rows_wall
            if silent > 15:
                if not ES.restart_tried:
                    ES.restart_tried = True
                    note("warn", "live stream silent — restarting target recording",
                         f"{int(silent)} s without samples · trying to re-establish streaming")
                    await asyncio.to_thread(ML.call_json, "afo_recording('stop')")
                    await asyncio.sleep(1.0)
                    await asyncio.to_thread(ML.call_json, "afo_recording('start')")
                    ES.sdi_recording = True
                    ES.setup_ok = False           # re-pin the (hopefully new) run
                    ES.next_setup_wall = 0.0
                    ES.last_rows_wall = time.monotonic()
                elif not ES.flush_tried:
                    ES.flush_tried = True
                    note("warn", "live stream still silent — running full recovery",
                         "flush stale instruments · reconnect target · restart recording")
                    rr = await asyncio.to_thread(ML.call_json, f"afo_recover('{ARGS.target}')")
                    if rr.get("ok"):
                        note("ok", "recovery sequence completed — waiting for the stream", "")
                    else:
                        note("warn", "recovery sequence failed", rr.get("err", ""))
                    ES.sdi_recording = True
                    ES.setup_ok = False
                    ES.next_setup_wall = 0.0
                    ES.last_rows_wall = time.monotonic()
                elif time.monotonic() >= ES.next_guidance_wall:
                    ES.next_guidance_wall = time.monotonic() + 120
                    note("error", "live streaming is down — the app's XCP link appears broken",
                         "stop the model and RELOAD the application on the Speedgoat "
                         "(rebooting the Speedgoat does this), then reconnect")
        if changed:
            note("ok", "signal set discovered", f"{len(CH.names)} channels (cached)")
            STREAM.reset()
            if REC.on:
                REC.stop("channel set changed")
            await _broadcast(json.dumps({"type": "hello", "channels": CH.defs, "groups": CH.groups}),
                             binary=False)
        # runs are TRIAL-ALIGNED (user request 2026-07-31): one SDI run per
        # device run, like the Data Inspector — no time-based rotation. A
        # model restart creates a fresh run naturally; the drain's run-change
        # re-pin and the backward-time reset in ingest() handle the boundary.
        # Cost: the polling fallback's sg.Values reads slow down over very
        # long trials (the 10 s tail cap keeps them correct); the push plane,
        # once its extraction is fixed, is insensitive to run length.


async def _import_filelog():
    outdir = str(REC.root).replace("\\", "/").replace("'", "''")
    r = await asyncio.to_thread(ML.call_json, f"afo_record_import('{outdir}')")
    if r.get("ok"):
        note("ok", f"target file log imported · {Path(r.get('file','?')).name}",
             f"{r.get('rows','?')} rows · {r.get('nsignals','?')} signals (full rate)")
    else:
        note("error", "file log import failed", r.get("err", ""))


# --------------------------------------------------------------------------
# web app
# --------------------------------------------------------------------------
app = FastAPI(title="AFO Rig Console backend")
CLIENTS: set[WebSocket] = set()


@app.get("/")
def index():
    return FileResponse(HERE / "dashboard.html")


@app.get("/api/config")
def config():
    return {"channel_defs": CH.defs, "groups": CH.groups, "logs_dir": str(REC.root)}


def _stream_status():
    now = time.monotonic()
    return {
        "type": "status",
        "stream": {
            "running": STREAM.alive(),
            "mode": STREAM.mode,
            "rate": STREAM.rate(),
            "age_ms": round((now - STREAM.last_wall) * 1000) if STREAM.last_wall else None,
            "gaps": STREAM.gaps,
            "rows": STREAM.n_rows,
            "flat": STREAM.flat_channels(),
            "t": STREAM.last_t,
            "source": STREAM.src,
            "stall_ms": int(STREAM.gap_window * 1000),
            "nch": len(CH.names),
        },
        "rec": {"on": REC.on, "file": REC.path.name if REC.on else None,
                "rows": REC.rows if REC.on else 0,
                "sdi": ES.sdi_recording},
        "matlab": ML_STATUS_CACHE,
        "cfg": {"mldatx": bool(ARGS.mldatx)},
    }


@app.get("/api/status")
def status():
    return _stream_status()


@app.get("/api/debug/es")
def debug_es():
    """Internal state of the stream assembler (diagnostics)."""
    noww = time.monotonic()
    lag = sorted(ES.last_sig_t.items(), key=lambda kv: kv[1])
    return {
        "plane": ES.plane,
        "grid_t": ES.grid_t,
        "n_known": len(ES.known),
        "n_with_t": len(ES.last_sig_t),
        "n_active": len([n for n in ES.known
                         if n in ES.last_sig_t and (noww - ES.adv_wall.get(n, 0.0)) < 15.0]),
        "watermark_laggards": [{"name": n, "t": round(t, 3),
                                "adv_age_s": round(noww - ES.adv_wall.get(n, 0.0), 1)}
                               for n, t in lag[:8]],
        "newest": [{"name": n, "t": round(t, 3)} for n, t in lag[-3:]],
        "pend_backlogs": [{"name": n, "qlen": len(q)}
                          for n, q in sorted(ES.pend.items(), key=lambda kv: -len(kv[1]))[:8]],
    }


@app.post("/api/rt/connect")
async def rt_connect():
    r = await asyncio.to_thread(ML.connect_target)
    gp = r.get("gp") or {}
    if gp.get("ok") and not gp.get("skipped"):
        note("ok", "subject GP model loaded", Path(str(gp.get("file", ""))).name)
    elif not gp.get("ok"):
        note("error", "subject GP model load FAILED — model variables missing",
             gp.get("err", ""))
    if r.get("ok"):
        note("ok", f"target connected · {ARGS.target}", f"{ARGS.target_ip} · signal discovery follows")
    else:
        note("warn", f"target not reachable · {ARGS.target}", r.get("err", ""))
    return JSONResponse(r, status_code=200 if r.get("ok") else 503)


@app.post("/api/rt/disconnect")
async def rt_disconnect():
    ES.reset()
    r = await asyncio.to_thread(ML.disconnect_target)
    note("info", f"target disconnected · {ARGS.target}", "")
    return r


@app.post("/api/rt/load")
async def rt_load():
    r = await asyncio.to_thread(ML.load)
    note("ok" if r.get("ok") else "error",
         "application load requested" if r.get("ok") else "load failed", r.get("err", ARGS.mldatx))
    return JSONResponse(r, status_code=200 if r.get("ok") else 503)


@app.post("/api/rt/start")
async def rt_start():
    r = await asyncio.to_thread(ML.start)
    if r.get("ok"):
        note("ok", "model start requested", "target recording follows automatically")
    else:
        note("warn", "model start not sent", r.get("err", ""))
    return {"ok": True, "matlab": r}


@app.post("/api/rt/stop")
async def rt_stop():
    r = await asyncio.to_thread(ML.stop)
    if r.get("ok"):
        note("info", "model stop requested", "file log import follows automatically")
    else:
        note("warn", "model stop not sent", r.get("err", ""))
    return {"ok": True, "matlab": r}


@app.post("/api/import")
async def api_import():
    """Manually import the newest target file log (e.g., from a previous session)."""
    if not ML.eng:
        return JSONResponse({"ok": False, "err": "MATLAB not connected"}, status_code=503)
    await _import_filelog()
    return {"ok": True}


@app.post("/api/param")
async def set_param(body: dict):
    block, param, value = body.get("block"), body.get("param", "Value"), body.get("value")
    if not block:
        return JSONResponse({"ok": False, "err": "missing block"}, status_code=400)
    r = await asyncio.to_thread(ML.setparam, block, param, value)
    if r.get("ok"):
        note("info", f"param applied · {block}", f"{param} = {value}")
    else:
        note("error", f"param NOT applied · {block}", r.get("err", ""))
    return JSONResponse(r, status_code=200 if r.get("ok") else 503)


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    CLIENTS.add(sock)
    try:
        await sock.send_text(json.dumps({"type": "hello", "channels": CH.defs, "groups": CH.groups}))
        t_min = STREAM.last_t - BACKFILL_S
        back = [r for r in STREAM.ring if r[0] >= t_min]
        for i in range(0, len(back), 400):
            await sock.send_bytes(_pack_batch(back[i:i + 400]))
        await sock.send_text(json.dumps(_stream_status()))
        while True:
            await sock.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        CLIENTS.discard(sock)


def _pack_batch(items):
    n = len(CH.names)
    out = bytearray(struct.pack("<BI", 1, len(items)))
    for t, vals in items:
        if len(vals) != n:
            continue
        out += struct.pack("<d", t)
        out += struct.pack(f"<{n}f", *vals)
    return bytes(out)


async def _broadcast(payload, binary):
    dead = []
    for c in list(CLIENTS):
        try:
            if binary:
                await c.send_bytes(payload)
            else:
                await c.send_text(payload)
        except Exception:
            dead.append(c)
    for c in dead:
        CLIENTS.discard(c)


async def batch_loop():
    while True:
        await asyncio.sleep(BATCH_S)
        if STREAM.batch and CLIENTS:
            items, STREAM.batch = STREAM.batch, []
            await _broadcast(_pack_batch(items), binary=True)
        else:
            STREAM.batch.clear()


async def status_loop():
    global ML_STATUS_CACHE
    tick = 0
    while True:
        await asyncio.sleep(STATUS_S)
        tick += 1
        # host CSV auto-record follows the live stream
        if CH.names and STREAM.alive() and not REC.on:
            REC.start()
        if REC.on and STREAM.last_wall and (time.monotonic() - STREAM.last_wall) > AUTOREC_STOP_S:
            REC.stop()
        if tick % 8 == 0:
            # engine status polls serialize with drains on the engine lock —
            # keep them rare so the 1 kHz cadence stays tight
            ML_STATUS_CACHE = await asyncio.to_thread(ML.status)
        if CLIENTS:
            await _broadcast(json.dumps(_stream_status()), binary=False)


async def event_loop():
    while True:
        e = await EVENTS.get()
        if CLIENTS:
            await _broadcast(json.dumps(e), binary=False)


async def _quiet_engine_attach():
    """Attach a shared MATLAB session in the background (plumbing only —
    never spawns a headless MATLAB; CONNECT is about the target)."""
    if ARGS.no_matlab:
        return
    r = await asyncio.to_thread(ML.ensure_engine, False)
    if r.get("ok"):
        note("info", "MATLAB engine attached (background)", r.get("mode", ""))


@app.on_event("startup")
async def startup():
    asyncio.create_task(batch_loop())
    asyncio.create_task(status_loop())
    asyncio.create_task(event_loop())
    asyncio.create_task(engine_loop())
    asyncio.create_task(_quiet_engine_attach())
    print("Data plane    : live SDI run via the MATLAB engine", flush=True)
    print(f"Dashboard     : http://{ARGS.http_host}:{ARGS.http_port}/", flush=True)
    print(f"Trial logs    : {REC.root}", flush=True)


if __name__ == "__main__":
    uvicorn.run(app, host=ARGS.http_host, port=ARGS.http_port, log_level="warning")
