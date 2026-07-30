#!/usr/bin/env python3
"""
AFO Rig Console backend.

Data plane   : UDP 124-byte packets (31 x float32 LE) from the Speedgoat
               -> ring buffer -> WebSocket relay to the dashboard
               -> optional per-trial CSV recording (+ .json sidecar).
Control plane: MATLAB Engine (shared desktop session first, headless
               fallback) -> slrealtime load / start / stop / setparam.
               Fully optional: without the matlabengine package the data
               plane still works and control endpoints return an error
               the dashboard shows as a toast.

Run:
    python server.py                      # defaults below
    python server.py --udp-port 5431      # listen on the 1 kHz stream instead
    python server.py --no-matlab          # never touch MATLAB

Then open http://localhost:8321 (the dashboard is served at /).
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

ap = argparse.ArgumentParser(description="AFO Rig Console backend")
ap.add_argument("--http-host", default="127.0.0.1", help="bind for the web UI (use 0.0.0.0 to reach it from other lab PCs)")
ap.add_argument("--http-port", type=int, default=8321)
ap.add_argument("--udp-bind", default="0.0.0.0", help="bind address for the UDP listener")
ap.add_argument("--udp-port", type=int, default=5432, help="5432 = 333 Hz stream, 5431 = ~1 kHz stream (model UDP Send blocks)")
ap.add_argument("--logs-dir", default=str(HERE / "trial_logs"))
ap.add_argument("--mldatx", default="", help="path of the built real-time application for LOAD")
ap.add_argument("--target", default="", help="Speedgoat target name for slrealtime(); empty = default target")
ap.add_argument("--no-matlab", action="store_true", help="disable the MATLAB engine control plane")
ap.add_argument("--record-demo", action="store_true", help="also auto-record demo (loopback) data")
ap.add_argument("--no-spawn", action="store_true", help="attach to a shared MATLAB session only; never start a headless one")
ARGS = ap.parse_args()

PACKET_BYTES = 124                      # 31 x float32, little-endian
N_CH = 31
UNPACK = struct.Struct("<31f")

# Channel order of the UDP payload. Placeholder names — fix once the Mux3
# wiring is confirmed (wiggle test); the dashboard adopts these at connect.
CHANNELS = [
    "ankle_angle", "pot_raw", "torque_cmd",
    "insole_p1", "insole_p2", "insole_p3", "insole_p4",
    "insole_p5", "insole_p6", "insole_p7", "insole_p8",
    "heel_agg", "toe_agg",
    "imu_yaw", "imu_pitch", "imu_roll",
    "imu_ax", "imu_ay", "imu_az",
    "imu_gx", "imu_gy", "imu_gz",
    "gait_phase", "stride_vel", "stride_len", "assist_Uc", "sync_led",
    "motor_current", "motor_vel", "ctrl_loop_dt", "spare_31",
]
assert len(CHANNELS) == N_CH

GAP_S = 0.25         # no packets for this long while active -> stream gap
AUTOREC_STOP_S = 5.0 # close the auto-recording after this much stream silence
FLAT_S = 0.10        # channel unchanged for this long while stream alive -> flat
# step/hold channels legitimately sit still between gait events — exclude
# them from the flat-freeze detector so it only flags true sensor freezes
STEP_CHANNELS = {"gait_phase", "stride_vel", "stride_len", "sync_led",
                 "ctrl_loop_dt", "spare_31"}
BATCH_S = 0.05       # WebSocket flush interval
STATUS_S = 0.5       # status broadcast interval
BACKFILL_S = 10.0    # history replayed to a newly connected client

# --------------------------------------------------------------------------
# stream state
# --------------------------------------------------------------------------
class Stream:
    def __init__(self):
        self.t0 = time.monotonic()
        self.ring = deque(maxlen=20000)          # (t, payload bytes)
        self.batch = []                          # packets since last WS flush
        self.n_packets = 0
        self.last_pkt_t = 0.0                    # stream time of last packet
        self.last_pkt_wall = 0.0                 # monotonic wall of last packet
        self.was_active = False
        self.gaps = 0
        self.rate_win = deque(maxlen=2000)       # arrival walls, last ~1 s
        self.last_vals = [None] * N_CH
        self.last_change = [0.0] * N_CH
        self.bad_packets = 0
        self.src = None           # ip of the accepted source
        self.demo = False         # accepted source is loopback (demo sender)
        self.real_seen = False    # once real (non-loopback) data arrives, demo is locked out
        self.ignored_demo = 0

    def now(self):
        return time.monotonic() - self.t0

    def alive(self):
        return self.last_pkt_wall and (time.monotonic() - self.last_pkt_wall) < GAP_S

    def rate(self):
        cut = time.monotonic() - 1.0
        while self.rate_win and self.rate_win[0] < cut:
            self.rate_win.popleft()
        return len(self.rate_win)

    def flat_channels(self):
        if not self.alive():
            return []
        t = self.now()
        out = [CHANNELS[i] for i in range(N_CH)
               if CHANNELS[i] not in STEP_CHANNELS and t - self.last_change[i] > FLAT_S]
        return out if len(out) < N_CH - len(STEP_CHANNELS) else []   # all-flat = stream problem

STREAM = Stream()
EVENTS = asyncio.Queue()                          # dicts forwarded to all WS clients


def note(sev, msg, raw=""):
    """Queue an event for the dashboard's log (and print it)."""
    print(f"[{sev}] {msg}" + (f" | {raw}" if raw else ""), flush=True)
    with contextlib.suppress(Exception):
        EVENTS.put_nowait({"type": "event", "sev": sev, "msg": msg, "raw": raw})


# --------------------------------------------------------------------------
# recorder
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
        self.f = open(self.path, "w", buffering=1 << 16)
        self.f.write("host_time_s," + ",".join(CHANNELS) + "\n")
        self.rows = 0
        self.started = datetime.now().isoformat(timespec="seconds")
        self.gaps_at_start = STREAM.gaps
        note("ok", f"recording started · {self.path.name}", str(self.root))
        return self.path.name

    def write(self, t, values):
        if self.f:
            self.f.write(f"{t:.4f}," + ",".join(f"{v:.6g}" for v in values) + "\n")
            self.rows += 1

    def stop(self):
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
            "channels": CHANNELS,
            "udp_port": ARGS.udp_port,
            "source": STREAM.src,
            "demo_data": STREAM.demo,
        }
        self.path.with_suffix(".json").write_text(json.dumps(meta, indent=2))
        note("ok", f"recording stopped · {self.path.name}",
             f"{self.rows} rows · gaps={meta['stream_gaps_during_run']}")
        name = self.path.name
        self.path = None
        return name

REC = Recorder(Path(ARGS.logs_dir))


# --------------------------------------------------------------------------
# UDP listener
# --------------------------------------------------------------------------
class UdpProto(asyncio.DatagramProtocol):
    def datagram_received(self, data, addr):
        if len(data) != PACKET_BYTES:
            STREAM.bad_packets += 1
            return
        # source priority: the real Speedgoat (non-loopback) always outranks the
        # demo sender (loopback). Once real data has been seen, demo packets are
        # dropped until the server restarts — a forgotten demo_data window can
        # never contaminate a trial.
        ip = addr[0]
        is_demo = ip.startswith("127.")
        if is_demo and STREAM.real_seen:
            STREAM.ignored_demo += 1
            if STREAM.ignored_demo == 1:
                note("warn", "demo sender ignored — real Speedgoat data has priority",
                     "close the demo_data window; its packets are being dropped")
            return
        if not is_demo and not STREAM.real_seen:
            STREAM.real_seen = True
            if STREAM.demo:
                note("warn", "real Speedgoat stream detected — demo sender now ignored", ip)
        if STREAM.src != ip:
            STREAM.src = ip
            STREAM.demo = is_demo
        wall = time.monotonic()
        t = STREAM.now()
        vals = UNPACK.unpack(data)

        if STREAM.was_active and STREAM.last_pkt_wall and (wall - STREAM.last_pkt_wall) > GAP_S:
            STREAM.gaps += 1
            gap_ms = round((wall - STREAM.last_pkt_wall) * 1000)
            note("error", "UDP stream gap recovered", f"gap={gap_ms} ms")
        if not STREAM.was_active:
            note("ok", "UDP stream active", f"{addr[0]}:{ARGS.udp_port} · {PACKET_BYTES} B packets")
            STREAM.was_active = True

        for i, v in enumerate(vals):
            lv = STREAM.last_vals[i]
            if lv is None or abs(v - lv) > 1e-9:
                STREAM.last_change[i] = t
            STREAM.last_vals[i] = v

        STREAM.n_packets += 1
        STREAM.last_pkt_t = t
        STREAM.last_pkt_wall = wall
        STREAM.rate_win.append(wall)
        STREAM.ring.append((t, data))
        STREAM.batch.append((t, data))
        REC.write(t, vals)


# --------------------------------------------------------------------------
# MATLAB engine control plane (optional, runs in worker threads)
# --------------------------------------------------------------------------
class MatlabRT:
    def __init__(self):
        self.eng = None
        self.mode = None            # 'shared' | 'headless'
        self.available = None       # matlabengine importable?
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

    # every method below is blocking; call via asyncio.to_thread
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
        # statements and value-returning expression must be separate evals
        # (multi-statement eval with nargout=1 is rejected by MATLAB).
        # R2024b slrealtime.Target API: isConnected/isLoaded/isRunning methods,
        # TargetStatus property, getLastApplication for the app name.
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
# web app
# --------------------------------------------------------------------------
app = FastAPI(title="AFO Rig Console backend")
CLIENTS: set[WebSocket] = set()


@app.get("/")
def index():
    return FileResponse(HERE / "dashboard.html")


@app.get("/api/config")
def config():
    return {"channels": CHANNELS, "packet_bytes": PACKET_BYTES,
            "udp_port": ARGS.udp_port, "logs_dir": str(REC.root)}


def _stream_status():
    now = time.monotonic()
    return {
        "type": "status",
        "stream": {
            "running": STREAM.alive(),
            "rate": STREAM.rate(),
            "age_ms": round((now - STREAM.last_pkt_wall) * 1000) if STREAM.last_pkt_wall else None,
            "gaps": STREAM.gaps,
            "packets": STREAM.n_packets,
            "bad": STREAM.bad_packets,
            "flat": STREAM.flat_channels(),
            "t": STREAM.last_pkt_t,
            "source": STREAM.src,
            "demo": STREAM.demo,
            "ignored_demo": STREAM.ignored_demo,
        },
        "rec": {"on": REC.on, "file": REC.path.name if REC.on else None, "rows": REC.rows if REC.on else 0},
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
        note("ok", "model start requested", "recording starts automatically with the stream")
    else:
        note("warn", "model start not sent", r.get("err", ""))
    return {"ok": True, "matlab": r}


@app.post("/api/rt/stop")
async def rt_stop():
    r = await asyncio.to_thread(ML.stop)
    if r.get("ok"):
        note("info", "model stop requested", "recording closes when the stream goes silent")
    else:
        note("warn", "model stop not sent", r.get("err", ""))
    return {"ok": True, "matlab": r}


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


@app.post("/api/zero")
def zero():
    return JSONResponse({"ok": False, "err": "sensor zeroing not wired yet (needs the zeroing switch mechanism)"},
                        status_code=501)


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    CLIENTS.add(sock)
    try:
        await sock.send_text(json.dumps({"type": "hello", "channels": CHANNELS}))
        # backfill recent history so charts fill instantly
        t_min = STREAM.now() - BACKFILL_S
        back = [(t, d) for (t, d) in STREAM.ring if t >= t_min]
        for i in range(0, len(back), 400):
            await sock.send_bytes(_pack_batch(back[i:i + 400]))
        await sock.send_text(json.dumps(_stream_status()))
        while True:                                   # inbound messages are ignored
            await sock.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        CLIENTS.discard(sock)


def _pack_batch(items):
    out = bytearray(struct.pack("<BI", 1, len(items)))
    for t, data in items:
        out += struct.pack("<d", t)
        out += data
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
        # auto-record: capture whenever Speedgoat data is streaming (demo data
        # only with --record-demo); close after AUTOREC_STOP_S of silence so
        # brief dropouts don't split a run into fragments
        if STREAM.alive() and not REC.on and (not STREAM.demo or ARGS.record_demo):
            REC.start()
        if REC.on and STREAM.last_pkt_wall and (time.monotonic() - STREAM.last_pkt_wall) > AUTOREC_STOP_S:
            REC.stop()
        if tick % 4 == 0:                                  # MATLAB poll every 2 s
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
    await loop.create_datagram_endpoint(UdpProto, local_addr=(ARGS.udp_bind, ARGS.udp_port))
    asyncio.create_task(batch_loop())
    asyncio.create_task(status_loop())
    asyncio.create_task(event_loop())
    print(f"UDP listener  : {ARGS.udp_bind}:{ARGS.udp_port}  ({PACKET_BYTES} B = {N_CH} x float32)", flush=True)
    print(f"Dashboard     : http://{ARGS.http_host}:{ARGS.http_port}/", flush=True)
    print(f"Trial logs    : {REC.root}", flush=True)


if __name__ == "__main__":
    uvicorn.run(app, host=ARGS.http_host, port=ARGS.http_port, log_level="warning")
