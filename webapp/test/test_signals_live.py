"""Signals page live test (read-only on the target: connect, recording on if off,
stream, drain; no stop/start/load/setparam). App on 127.0.0.1:18062, live UDP
replay on 15434 so the Live page rate can be measured at the same time."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from test_app import Replay, SSE, packets  # noqa: E402
import test_app  # noqa: E402

PORT = 18062
BASE = f"http://127.0.0.1:{PORT}"
test_app.LOCAL = BASE
OUT = os.path.join(HERE, "e2e")
os.makedirs(OUT, exist_ok=True)


def get(path, timeout=5):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        return {"_err": repr(exc)}


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def main():
    res = {}
    base = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    base["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15434, "send_host": "127.0.0.1",
                   "send_port": 15990, "param_port": 15991}
    base["dash"] = {"host": "127.0.0.1", "port": PORT}
    cfgp = os.path.join(tempfile.mkdtemp(), "sig.yaml")
    yaml.safe_dump(base, open(cfgp, "w"), sort_keys=False)
    log = open(os.path.join(OUT, "server_signals.log"), "w")
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=log, stderr=subprocess.STDOUT,
                           env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    rep = Replay(packets())
    sse = SSE()
    try:
        for _ in range(80):
            if "_err" not in get("/api/status"):
                break
            time.sleep(0.5)
        rep.start()
        sse.start()
        t0 = time.time()
        res["stream_on"] = post("/api/signals/stream", {"on": True})
        ready = None
        for _ in range(120):
            st = get("/api/signals/status")
            if st and st.get("channels") and st.get("state") == "streaming":
                ready = round(time.time() - t0, 1)
                break
            time.sleep(1)
        res["seconds_to_first_data"] = ready
        st = get("/api/signals/status") or {}
        res["n_channels"] = len(st.get("channels") or [])
        res["mode"] = st.get("mode")
        names = [c["name"] for c in st.get("channels") or []]
        res["sample_channels"] = names[:80]
        pick = [n for n in ("Uc", "assistance", "SV_target", "Total Desired torque") if n in names] or names[:3]
        # 60 s of steady streaming: freshness + live page rate at the same time
        ages, gaps = [], 0
        t_a = time.time()
        prev = None
        while time.time() - t_a < 60:
            d = get("/api/signals/data?" + urllib.parse.urlencode({"names": ",".join(pick), "window": 10}))
            st = get("/api/signals/status") or {}
            ages.append(st.get("silent_s"))
            tl = d.get("t_latest") if isinstance(d, dict) else None
            if prev is not None and tl is not None and tl <= prev:
                gaps += 1
            prev = tl if tl is not None else prev
            time.sleep(1)
        t_b = time.time()
        res["data_age_s_median"] = sorted(a for a in ages if a is not None)[len([a for a in ages if a is not None]) // 2] if any(a is not None for a in ages) else None
        res["data_age_s_max"] = max((a for a in ages if a is not None), default=None)
        res["polls_without_new_data"] = gaps
        res["live_rate_during_signals"] = sse.rate(t_a, t_b)
        d = get("/api/signals/data?" + urllib.parse.urlencode({"names": ",".join(pick), "window": 10}))
        res["points_per_signal_10s"] = {k: len(v["t"]) for k, v in (d.get("series") or {}).items()}
        # kill the MATLAB worker process: must come back by itself
        ms = get("/api/status")["matlab"]
        res["killed_worker_pid"] = ms.get("worker_pid")
        subprocess.run(["taskkill", "/PID", str(ms.get("worker_pid")), "/T", "/F"], capture_output=True)
        t_k = time.time()
        back = None
        for _ in range(150):
            st = get("/api/signals/status") or {}
            if st and st.get("state") == "streaming" and (st.get("silent_s") or 99) < 3:
                back = round(time.time() - t_k, 1)
                break
            time.sleep(1)
        res["seconds_to_recover_after_kill"] = back
        res["live_rate_during_recovery"] = sse.rate(t_k, time.time())
        res["matlab_status_after"] = get("/api/status")["matlab"]
        res["stream_off"] = post("/api/signals/stream", {"on": False})
        time.sleep(3)
    finally:
        rep.stop.set()
        sse.stop.set()
        subprocess.run(["taskkill", "/PID", str(srv.pid), "/T", "/F"], capture_output=True)
        log.close()
    json.dump(res, open(os.path.join(OUT, "signals_results.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
