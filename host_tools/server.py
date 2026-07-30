#!/usr/bin/env python3
"""
AFO Rig Console backend.

Data plane (primary): MATLAB engine + slrealtime Instrument streaming.
    After CONNECT, the server attaches an slrealtime.Instrument with
    addInstrumentedSignals() — every SDI-instrumented (blue badge) signal
    in the running app — and drains its buffer a few times per second.
    Vector signals are expanded into per-element channels (name(1..w)).
    The discovered channel set is cached (signals_cache.json) and pushed
    to the dashboard, which adopts it automatically.

Recording:
    While the model runs, the target records everything instrumented
    (tg.startRecording -> SDI + File Log on the target SSD). When the
    model stops, the server imports the newest file log and exports a
    full-rate wide CSV (target_<stamp>.csv). Independently, the live
    stream is also written to a host-side CSV (runNNN_*.csv, zero-order
    hold on a uniform grid) as a belt-and-braces copy.

Data plane (optional, for demos): UDP packets from the model's UDP Send
    blocks. Disabled by default; enable with --udp-port 5432. Real
    Speedgoat data cannot be contaminated by the demo sender (loopback
    is locked out once a non-loopback source appears).

Control plane: MATLAB engine (shared desktop session first, headless
    fallback) -> slrealtime start / stop / setparam. Without the
    matlabengine package the endpoints return errors the dashboard
    shows as toasts.

Run:
    python server.py                  # engine data plane (normal)
    python server.py --udp-port 5432  # + UDP listener (demo / legacy)
Then open http://localhost:8321.
"""

import argparse
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
ap.add_argument("--udp-bind", default="0.0.0.0", help="bind address for the optional UDP listener")
ap.add_argument("--udp-port", type=int, default=0, help="0 = UDP disabled (default); 5432/5431 = listen to the model's UDP Send stream (demo/legacy)")
ap.add_argument("--logs-dir", default=str(HERE / "trial_logs"))
ap.add_argument("--mldatx", default="", help="path of the built real-time application for LOAD")
ap.add_argument("--target", default="", help="Speedgoat target name for slrealtime(); empty = default target")
ap.add_argument("--no-matlab", action="store_true", help="disable the MATLAB engine entirely")
ap.add_argument("--no-spawn", action="store_true", help="attach to a shared MATLAB session only; never start a headless one")
ap.add_argument("--record-demo", action="store_true", help="also auto-record demo (loopback UDP) data")
ARGS = ap.parse_args()

GAP_S = 0.25          # UDP: no packets for this long while active -> gap
ENGINE_GAP_S = 1.5    # engine stream: drain cadence is ~0.4 s, so be lenient
AUTOREC_STOP_S = 5.0  # close the host CSV after this much stream silence
FLAT_S = 0.10         # channel unchanged this long while stream alive -> flat
BATCH_S = 0.05        # WebSocket flush interval
STATUS_S = 0.5        # status broadcast interval
BACKFILL_S = 10.0     # history replayed to a newly connected client
GRID_DT = 0.01        # engine stream is re-emitted on this uniform grid (ZOH)
DRAIN_S = 0.4         # instrument buffer drain interval

# --------------------------------------------------------------------------
# channel set (dynamic — discovered from the instrumented signals)
# --------------------------------------------------------------------------
# Static fallback manifest: matches the model's 31-channel UDP payload.
# Used for the optional UDP mode and as the boot default until discovery.
STATIC_DEFS = [
    {"id": "ankle_angle", "name": "ankle_angle", "group": "ankle",    "units": "deg",   "prec": 2},
    {"id": "pot_raw",     "name": "pot_raw",     "group": "ankle",    "units": "deg",   "prec": 2},
    {"id": "torque_cmd",  "name": "torque_cmd",  "group": "actuator", "units": "N·m",   "prec": 2},
    {"id": "ins_p1", "name": "insole_p1", "group": "pressure", "units": "kPa", "prec": 0},
    {"id": "ins_p2", "name": "insole_p2", "group": "pressure", "units": "kPa", "prec": 0},
    {"id": "ins_p3", "name": "insole_p3", "group": "pressure", "units": "kPa", "prec": 0},
    {"id": "ins_p4", "name": "insole_p4", "group": "pressure", "units": "kPa", "prec": 0},
    {"id": "ins_p5", "name": "insole_p5", "group": "pressure", "units": "kPa", "prec": 0},
    {"id": "ins_p6", "name": "insole_p6", "group": "pressure", "units": "kPa", "prec": 0},
    {"id": "ins_p7", "name": "insole_p7", "group": "pressure", "units": "kPa", "prec": 0},
    {"id": "ins_p8", "name": "insole_p8", "group": "pressure", "units": "kPa", "prec": 0},
    {"id": "heel_press", "name": "heel_agg", "group": "pressure", "units": "kPa", "prec": 0},
    {"id": "toe_press",  "name": "toe_agg",  "group": "pressure", "units": "kPa", "prec": 0},
    {"id": "imu_yaw",   "name": "imu_yaw",   "group": "imu", "units": "deg",   "prec": 1},
    {"id": "imu_pitch", "name": "imu_pitch", "group": "imu", "units": "deg",   "prec": 1},
    {"id": "imu_roll",  "name": "imu_roll",  "group": "imu", "units": "deg",   "prec": 1},
    {"id": "imu_ax", "name": "imu_ax", "group": "imu", "units": "m/s²",  "prec": 2},
    {"id": "imu_ay", "name": "imu_ay", "group": "imu", "units": "m/s²",  "prec": 2},
    {"id": "imu_az", "name": "imu_az", "group": "imu", "units": "m/s²",  "prec": 2},
    {"id": "imu_gx", "name": "imu_gx", "group": "imu", "units": "deg/s", "prec": 1},
    {"id": "imu_gy", "name": "imu_gy", "group": "imu", "units": "deg/s", "prec": 1},
    {"id": "imu_gz", "name": "imu_gz", "group": "imu", "units": "deg/s", "prec": 1},
    {"id": "gait_phase", "name": "gait_phase", "group": "gait", "units": "—",   "prec": 0, "step": True},
    {"id": "stride_vel", "name": "stride_vel", "group": "gait", "units": "m/s", "prec": 2, "step": True},
    {"id": "stride_len", "name": "stride_len", "group": "gait", "units": "m",   "prec": 2, "step": True},
    {"id": "assist_uc",  "name": "assist_Uc",  "group": "gait", "units": "N·m", "prec": 2},
    {"id": "sync_led",   "name": "sync_led",   "group": "gait", "units": "—",   "prec": 0, "step": True},
    {"id": "motor_current", "name": "motor_current", "group": "actuator", "units": "A",     "prec": 2},
    {"id": "motor_vel",     "name": "motor_vel",     "group": "actuator", "units": "rad/s", "prec": 2},
    {"id": "ctrl_dt",       "name": "ctrl_loop_dt",  "group": "actuator", "units": "ms",    "prec": 3, "hold": True},
    {"id": "spare_31",      "name": "spare_31",      "group": "actuator", "units": "—",     "prec": 0, "step": True},
]
STATIC_GROUPS = [
    {"id": "ankle",    "label": "ANKLE / ENCODER"},
    {"id": "pressure", "label": "INSOLE PRESSURE"},
    {"id": "imu",      "label": "IMU"},
    {"id": "gait",     "label": "GAIT / RL ASSIST"},
    {"id": "actuator", "label": "ACTUATOR / LOOP"},
]


def _san(name):
    return re.sub(r"[^0-9A-Za-z_()\[\] .:/-]", "_", str(name)).strip() or "signal"


class ChannelSet:
    def __init__(self):
        self.defs = []
        self.groups = []
        self.names = []
        self.flat_excluded = set()
        cached = self._load_cache()
        if cached:
            self.defs, self.groups = cached
        else:
            self.defs, self.groups = STATIC_DEFS, STATIC_GROUPS
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
# stream state (rows of float values on a shared clock)
# --------------------------------------------------------------------------
class Stream:
    def __init__(self):
        self.t0 = time.monotonic()
        self.reset()
        self.gaps = 0
        self.bad_packets = 0
        self.src = None
        self.demo = False
        self.real_seen = False
        self.ignored_demo = 0
        self.mode = "none"          # engine | udp | none
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

    def now(self):
        return time.monotonic() - self.t0

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
            note("ok", "data stream active", f"{self.mode} · {len(CH.names)} channels")
            self.was_active = True
        for name, v in zip(CH.names, vals):
            lv = self.last_vals.get(name)
            if lv is None or abs(v - lv) > 1e-9:
                self.last_change[name] = t
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
        if not self.alive():
            return []
        t = self.now() if self.mode == "udp" else self.last_t
        out = [n for n in CH.names
               if n not in CH.flat_excluded and t - self.last_change.get(n, 0.0) > FLAT_S]
        return out if len(out) < max(1, len(CH.names) - len(CH.flat_excluded)) else []

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
            "mode": STREAM.mode,
            "demo_data": STREAM.demo,
            "note": reason or ("host-side live copy; full-rate record is the imported target file log"
                               if STREAM.mode == "engine" else ""),
        }
        self.path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        note("ok", f"recording stopped · {self.path.name}",
             f"{self.rows} rows · gaps={meta['stream_gaps_during_run']}")
        name = self.path.name
        self.path = None
        return name

REC = Recorder(Path(ARGS.logs_dir))


# --------------------------------------------------------------------------
# optional UDP listener (demo / legacy)
# --------------------------------------------------------------------------
class UdpProto(asyncio.DatagramProtocol):
    def datagram_received(self, data, addr):
        n = len(CH.names)
        if len(data) != 4 * n:
            STREAM.bad_packets += 1
            return
        ip = addr[0]
        is_demo = ip.startswith("127.")
        if is_demo and STREAM.real_seen:
            STREAM.ignored_demo += 1
            if STREAM.ignored_demo == 1:
                note("warn", "demo sender ignored — real data has priority",
                     "close the demo_data window; its packets are being dropped")
            return
        if not is_demo and not STREAM.real_seen:
            STREAM.real_seen = True
            if STREAM.demo:
                note("warn", "real Speedgoat stream detected — demo sender now ignored", ip)
        if STREAM.src != ip:
            STREAM.src = ip
            STREAM.demo = is_demo
            STREAM.mode = "udp"
            STREAM.gap_window = GAP_S
        vals = struct.unpack(f"<{n}f", data)
        STREAM.push(STREAM.now(), vals)


# --------------------------------------------------------------------------
# MATLAB engine (control plane + instrument data plane)
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

    # blocking; call via asyncio.to_thread
    def connect(self):
        if not self._import():
            return {"ok": False, "err": self.err}
        if self.eng:
            return {"ok": True, "mode": self.mode}
        import matlab.engine
        try:
            names = matlab.engine.find_matlab()
            if names:
                self.eng = matlab.engine.connect_matlab(names[0])
                self.mode = f"shared:{names[0]}"
            elif ARGS.no_spawn:
                return {"ok": False, "err": "no shared MATLAB session found (run matlab.engine.shareEngine in MATLAB)"}
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
ML_STATUS_CACHE = {"connected": False, "available": None}


# --------------------------------------------------------------------------
# engine data plane: instrument drains -> dedup -> uniform-grid rows
# --------------------------------------------------------------------------
class EngineStream:
    def __init__(self):
        self.setup_ok = False
        self.setup_err_noted = False
        self.last_sig_t = {}      # raw signal name -> newest timestamp ingested
        self.lastv = {}           # expanded channel name -> last value (ZOH)
        self.grid_t = None
        self.sdi_recording = False

    def reset(self):
        self.setup_ok = False
        self.last_sig_t = {}
        self.lastv = {}
        self.grid_t = None

    def ingest(self, signals):
        """Returns (changed, rows). signals: [{name,w,t:[...],v:[flat]}]."""
        sig_list = [(s.get("name", "?"), int(s.get("w", 1) or 1)) for s in signals]
        sig_list.sort(key=lambda x: x[0])
        changed = CH.adopt_discovered(sig_list) if sig_list else False
        if changed:
            self.lastv = {}
            self.grid_t = None
        # collect fresh samples as (t, {channel: value})
        events = []
        for s in signals:
            name = s.get("name", "?")
            w = int(s.get("w", 1) or 1)
            ts = s.get("t") or []
            vs = s.get("v") or []
            if isinstance(ts, (int, float)):
                ts = [ts]
            if isinstance(vs, (int, float)):
                vs = [vs]
            base = _san(name)
            chans = [base] if w <= 1 else [f"{base}({k})" for k in range(1, w + 1)]
            newest = self.last_sig_t.get(name, -1.0)
            for i, t in enumerate(ts):
                if t <= newest:
                    continue
                row = vs[i * w:(i + 1) * w]
                if len(row) != w:
                    continue
                events.append((float(t), dict(zip(chans, [float(x) for x in row]))))
            if ts:
                self.last_sig_t[name] = max(newest, float(ts[-1]))
        if not events:
            return changed, 0
        events.sort(key=lambda e: e[0])
        rows = 0
        if self.grid_t is None:
            self.grid_t = events[0][0]
        for t, upd in events:
            while self.grid_t + GRID_DT <= t:
                self.grid_t += GRID_DT
                STREAM.push(self.grid_t, [self.lastv.get(n, 0.0) for n in CH.names])
                rows += 1
            self.lastv.update(upd)
        # emit the final instant so the newest values are visible immediately
        if events[-1][0] >= self.grid_t + GRID_DT:
            self.grid_t = events[-1][0]
            STREAM.push(self.grid_t, [self.lastv.get(n, 0.0) for n in CH.names])
            rows += 1
        return changed, rows

ES = EngineStream()


async def engine_loop():
    while True:
        await asyncio.sleep(DRAIN_S)
        if ARGS.udp_port:                       # UDP mode owns the stream
            continue
        m = ML_STATUS_CACHE
        if not (ML.eng and m.get("connected") and m.get("target_conn")):
            if ES.setup_ok:
                ES.reset()
            continue
        if not ES.setup_ok:
            r = await asyncio.to_thread(ML.call_json, "afo_stream_setup()")
            if r.get("ok"):
                ES.setup_ok = True
                ES.setup_err_noted = False
                STREAM.mode = "engine"
                STREAM.src = "slrealtime instrument"
                STREAM.demo = False
                STREAM.gap_window = ENGINE_GAP_S
                note("ok", "instrument stream attached", "all SDI-instrumented signals")
            else:
                if not ES.setup_err_noted:
                    note("warn", "instrument stream setup failed", r.get("err", ""))
                    ES.setup_err_noted = True
                continue
        r = await asyncio.to_thread(ML.call_json, "afo_stream_drain()")
        if not r.get("ok"):
            continue
        changed, _rows = ES.ingest(r.get("signals") or [])
        if changed:
            note("ok", "signal set discovered", f"{len(CH.names)} channels (cached)")
            STREAM.reset()
            if REC.on:
                REC.stop("channel set changed")
            await _broadcast(json.dumps({"type": "hello", "channels": CH.defs, "groups": CH.groups}),
                             binary=False)
        # target-side SDI/FileLog recording follows the model state
        running = bool(m.get("running"))
        if running and not ES.sdi_recording:
            rr = await asyncio.to_thread(ML._eval, "startRecording(tg);")
            if rr.get("ok"):
                ES.sdi_recording = True
                note("ok", "target recording started", "SDI + File Log on target")
        elif not running and ES.sdi_recording:
            await asyncio.to_thread(ML._eval, "stopRecording(tg);")
            ES.sdi_recording = False
            note("info", "target recording stopped — importing file log…", "")
            asyncio.create_task(_import_filelog())


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
    return {"channel_defs": CH.defs, "groups": CH.groups,
            "udp_port": ARGS.udp_port, "logs_dir": str(REC.root)}


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
            "bad": STREAM.bad_packets,
            "flat": STREAM.flat_channels(),
            "t": STREAM.last_t,
            "source": STREAM.src,
            "demo": STREAM.demo,
            "ignored_demo": STREAM.ignored_demo,
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


@app.post("/api/rt/connect")
async def rt_connect():
    r = await asyncio.to_thread(ML.connect)
    if r.get("ok"):
        note("ok", f"MATLAB engine connected ({r.get('mode')})", "slrealtime tg ready")
    else:
        note("warn", "MATLAB engine unavailable", r.get("err", ""))
    return JSONResponse(r, status_code=200 if r.get("ok") else 503)


@app.post("/api/rt/disconnect")
async def rt_disconnect():
    ES.reset()
    return await asyncio.to_thread(ML.disconnect)


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
        if STREAM.alive() and not REC.on and (not STREAM.demo or ARGS.record_demo):
            REC.start()
        if REC.on and STREAM.last_wall and (time.monotonic() - STREAM.last_wall) > AUTOREC_STOP_S:
            REC.stop()
        if tick % 4 == 0:
            ML_STATUS_CACHE = await asyncio.to_thread(ML.status)
        if CLIENTS:
            await _broadcast(json.dumps(_stream_status()), binary=False)


async def event_loop():
    while True:
        e = await EVENTS.get()
        if CLIENTS:
            await _broadcast(json.dumps(e), binary=False)


@app.on_event("startup")
async def startup():
    loop = asyncio.get_running_loop()
    if ARGS.udp_port:
        await loop.create_datagram_endpoint(UdpProto, local_addr=(ARGS.udp_bind, ARGS.udp_port))
        STREAM.mode = "udp"
        STREAM.gap_window = GAP_S
        print(f"UDP listener  : {ARGS.udp_bind}:{ARGS.udp_port}  ({len(CH.names)} x float32)", flush=True)
    else:
        print("Data plane    : MATLAB engine instrument stream (UDP disabled)", flush=True)
    asyncio.create_task(batch_loop())
    asyncio.create_task(status_loop())
    asyncio.create_task(event_loop())
    asyncio.create_task(engine_loop())
    print(f"Dashboard     : http://{ARGS.http_host}:{ARGS.http_port}/", flush=True)
    print(f"Trial logs    : {REC.root}", flush=True)


if __name__ == "__main__":
    uvicorn.run(app, host=ARGS.http_host, port=ARGS.http_port, log_level="warning")
