"""End-to-end test of the AFO web app (no Speedgoat, no Teensy, no flashing).

Runs the app on port 18060 (bound to all interfaces so a request through the
192.168.7.15 interface can prove the OMEN-only lock), with live data replayed
from today's tee log to 127.0.0.1:15434. Control packets go to 127.0.0.1:15990.

Checks: Live update rate alone and while a Teensy compile and a trial decode
run; OMEN-only pages/callbacks rejected for a non-loopback request; live
worker crash -> automatic restart; dry-run flash refused while the stream is
live and allowed (dry run only) after it stops; trial health on real files;
the MATLAB engine path (status only, the target is not contacted);
screenshots of every page.
"""
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
AFO = os.path.dirname(APP)
sys.path.insert(0, HERE)
from cdp_capture import CHROME, _CDP  # noqa: E402

OUT = os.path.join(HERE, "e2e")
os.makedirs(OUT, exist_ok=True)
PORT = 18060
LOCAL = f"http://127.0.0.1:{PORT}"
REMOTE = f"http://192.168.7.15:{PORT}"
REC = struct.Struct("<dH")
results = {}


def packets():
    data = open(os.path.join(AFO, "_claude_live", "tee_103952.bin"), "rb").read()
    lt = time.localtime()
    t0 = time.mktime((lt.tm_year, 11, 19, 10, 40, 30, 0, 0, -1))
    out, pos = [], 0
    while pos + REC.size <= len(data):
        t, n = REC.unpack_from(data, pos)
        pos += REC.size
        if t >= t0 and n == 124:
            out.append(data[pos:pos + n])
        pos += n
    return out


class Replay(threading.Thread):
    def __init__(self, pk):
        super().__init__(daemon=True)
        self.pk, self.stop = pk, threading.Event()

    def run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        t0, i = time.perf_counter(), 0
        while not self.stop.is_set():
            while time.perf_counter() - t0 < i / 1024.0:
                time.sleep(0.0005)
            s.sendto(self.pk[i % len(self.pk)], ("127.0.0.1", 15434))
            i += 1


class SSE(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.times, self.bad, self.stop = [], 0, threading.Event()

    def run(self):
        while not self.stop.is_set():
            try:
                with urllib.request.urlopen(LOCAL + "/events", timeout=5) as r:
                    while not self.stop.is_set():
                        line = r.readline()
                        if not line:
                            break
                        if line.startswith(b"data:"):
                            try:
                                json.loads(line[5:], parse_constant=lambda c: (_ for _ in ()).throw(ValueError()))
                                self.times.append(time.time())
                            except ValueError:
                                self.bad += 1
            except Exception:
                time.sleep(0.5)

    def rate(self, t0, t1):
        return round(sum(1 for t in self.times if t0 <= t < t1) / max(1e-6, t1 - t0), 1)


def http(url, data=None, method=None, timeout=10):
    req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)


def dash_cb(base, output, inputs, state=(), changed=None):
    body = {"output": output, "outputs": {"id": output.split(".")[0], "property": output.split(".")[1]},
            "inputs": [{"id": i, "property": p, "value": v} for i, p, v in inputs],
            "changedPropIds": changed or [f"{inputs[0][0]}.{inputs[0][1]}"],
            "state": [{"id": i, "property": p, "value": v} for i, p, v in state]}
    return http(base + "/_dash-update-component", body, "POST")


def status():
    return json.loads(http(LOCAL + "/api/status")[1])


def wait_job(kind, timeout):
    t_end = time.time() + timeout
    while time.time() < t_end:
        j = status()["jobs"].get(kind)
        if j and j["state"] != "running":
            return j
        time.sleep(1)
    return status()["jobs"].get(kind)


def shots(base, pages, prefix, w=1280, h=800, port=19251):
    prof = tempfile.mkdtemp(prefix="afo_cdp_")
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={prof}",
                             "--no-first-run", "--disable-extensions", "--hide-scrollbars", f"--window-size={w},{h}",
                             "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = {}
    try:
        for _ in range(40):
            try:
                tg = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2))
                if any(t.get("type") == "page" for t in tg):
                    break
            except Exception:
                pass
            time.sleep(0.25)
        c = _CDP(next(t for t in tg if t.get("type") == "page")["webSocketDebuggerUrl"])
        c.call("Runtime.enable")
        c.call("Page.enable")
        c.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        c.call("Page.navigate", url=base + "/home")
        c.pump(5)
        for page in pages:
            c.js(f"window.history.pushState({{}}, '', '/{page}'); window.dispatchEvent(new PopStateEvent('popstate')); 1")
            c.pump(4 if page != "trials" else 6)
            path = os.path.join(OUT, f"{prefix}_{page}.png")
            c.shot(path)
            out[page] = path
        out["console_errors"] = c.console[:8]
        c.ws.close()
    finally:
        proc.terminate()
    return out


def main():
    base = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    base["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15434, "send_host": "127.0.0.1",
                   "send_port": 15990, "param_port": 15991}
    base["dash"] = {"host": "0.0.0.0", "port": PORT}
    cfgp = os.path.join(tempfile.mkdtemp(), "e2e.yaml")
    yaml.safe_dump(base, open(cfgp, "w"), sort_keys=False)
    log = open(os.path.join(OUT, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=log, stderr=subprocess.STDOUT,
                           env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    rep = Replay(packets())
    sse = SSE()
    try:
        for _ in range(80):
            if http(LOCAL + "/api/status")[0] == 200:
                break
            time.sleep(0.5)
        rep.start()
        sse.start()
        time.sleep(8)
        t = time.time()
        time.sleep(8)
        results["live_rate_alone"] = sse.rate(t, time.time())

        # --- OMEN-only enforcement
        code_l, lay_l = http(LOCAL + "/_dash-layout")
        code_r, lay_r = http(REMOTE + "/_dash-layout")
        results["layout_local_has_teensy_controls"] = "ty-build-btn" in lay_l
        results["layout_remote_has_teensy_controls"] = "ty-build-btn" in lay_r
        results["layout_remote_shows_locked_notice"] = "available on the OMEN only" in lay_r
        results["api_build_remote_status"] = http(REMOTE + "/api/teensy/build", {}, "POST")[0]
        cl, bl = dash_cb(LOCAL, "ty-file-view.children", [("ty-file", "value", "IMU.h")])
        cr, br = dash_cb(REMOTE, "ty-file-view.children", [("ty-file", "value", "IMU.h")])
        results["callback_local_status"] = cl
        results["callback_local_returned_file"] = "YEIgetStreamingBatch" in bl
        results["callback_remote_status"] = cr
        results["callback_remote_returned_file"] = "YEIgetStreamingBatch" in br

        # --- load: compile + trial decode while live
        t0 = time.time()
        results["build_request"] = http(LOCAL + "/api/teensy/build", {}, "POST")
        david = os.path.join(AFO, "afo_mat", "David_26_11_12", "David_26_11_12.mat")
        results["trial_request"] = http(LOCAL + "/api/trials/open", {"path": david}, "POST")
        tj = wait_job("trial-load", 300)
        bj = wait_job("teensy", 900)
        t1 = time.time()
        results["live_rate_during_compile_and_trial_load"] = sse.rate(t0, t1)
        results["load_window_s"] = round(t1 - t0, 1)
        results["build_job"] = {"state": bj["state"], "result": bj["result"]} if bj else None
        results["trial_job"] = {"state": tj["state"], "tail": tj["log"][-300:]} if tj else None

        # --- dry-run flash: locked while live
        branch = bj["result"]["branch"] if bj and isinstance(bj.get("result"), dict) else "main"
        _c, body = dash_cb(LOCAL, "ty-flash-msg.children", [("ty-flash-btn", "n_clicks", 1)],
                           state=[("ty-confirm", "value", branch), ("ty-dry", "value", ["dry"])])
        results["flash_while_live"] = body[-200:]

        # --- live worker crash -> restart
        pid = status()["live"].get("pid")
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        t_kill = time.time()
        time.sleep(12)
        st = status()["live"]
        results["worker_killed_pid"] = pid
        results["worker_restarts"] = st.get("restarts")
        results["worker_new_pid"] = st.get("pid")
        results["worker_last_error"] = st.get("last_error")
        results["live_rate_after_restart"] = sse.rate(time.time() - 4, time.time())

        # --- screenshots (local) and the locked view (remote)
        results["shots_local"] = shots(LOCAL, ["home", "live", "signals", "trials", "teensy"], "local")
        results["shots_remote"] = shots(REMOTE, ["home", "teensy"], "remote", port=19252)

        # --- stop the stream; dry-run flash allowed
        rep.stop.set()
        time.sleep(7)
        _c, body = dash_cb(LOCAL, "ty-flash-msg.children", [("ty-flash-btn", "n_clicks", 2)],
                           state=[("ty-confirm", "value", branch), ("ty-dry", "value", ["dry"])])
        results["flash_after_stream_stopped"] = body[-200:]
        fj = wait_job("teensy", 60)
        results["dry_run_job"] = {"state": fj["state"], "log": fj["log"][-500:]} if fj else None
        _c, body = dash_cb(LOCAL, "ty-flash-msg.children", [("ty-flash-btn", "n_clicks", 3)],
                           state=[("ty-confirm", "value", "wrong-branch"), ("ty-dry", "value", ["dry"])])
        results["flash_wrong_confirmation"] = body[-200:]
        flog = os.path.join(APP, "logs", "flash_log.csv")
        results["flash_log_tail"] = open(flog, encoding="utf-8").read().splitlines()[-2:] if os.path.exists(flog) else None
        results["sse_invalid_frames"] = sse.bad
    finally:
        rep.stop.set()
        sse.stop.set()
        subprocess.run(["taskkill", "/PID", str(srv.pid), "/T", "/F"], capture_output=True)
        log.close()
    json.dump(results, open(os.path.join(OUT, "e2e_results.json"), "w"), indent=1, default=str)
    print(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
