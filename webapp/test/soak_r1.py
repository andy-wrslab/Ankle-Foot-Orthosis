"""Soak test of the web app with the AFO_r1 profile (localhost test ports only).

    python test/soak_r1.py [minutes=30]

App on 127.0.0.1:18070 (config target.model AFO_r1, target writes disabled,
no MATLAB, no target). A separate sender process replays the main bus (5431
layout, '<31f' at 1000 Hz) to :15442 and the AFO_r1 console packet ('<15f' at
100 Hz: 12 layout columns + bif_valid, bif_cal_progress, bif_bias_ready) to
:15443: side -1 for the first 60 s then 0; Bi-LSTM cycling every 120 s (5 s
bias not ready, 35 s calibration walk 0->100 %, 70 s valid, 10 s invalid).
The harness sets S-ID / body mass (t=30 s), confirms LEFT (t=70 s) and sets
the mass with gear 75 kg (t=90 s); writes are disabled, so nothing is sent.
UDP listeners stand in for the target's control (:15992) and parameter
(:15993) ports and must receive 0 packets.

Four headless Chrome windows: Live/Gait, Live/Training, Trials, Signals. Each minute:
app RSS/CPU (app + its worker processes), packets/s and dropped/bad packet
deltas (main bus + console), UI update count per page (Plotly datarevision),
max fetch latency per page (Dash callbacks and API polls), new browser console
errors, new server errors (log lines and HTTP 5xx), UDP packets sent, new
/events connections (server log) and 503s, open SSE slots (/api/sse/clients).
Writes test/e2e/soak/minutes.jsonl and summary.json. Exit 1 on fail:
RSS growth > 10 % (minute 3 -> last), any server/browser error, any UDP sent,
any bad/dropped packet, packets/s below 95 % of nominal, or a page's UI update
rate below 80 % of its median in any minute after warm-up, any /events 503, or
more than 1 new /events connection in any minute after the first.
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _lowprio  # noqa: E402,F401  (below normal priority)
import json
import math
import multiprocessing as mp
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import psutil
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from cdp_capture import CHROME, _CDP  # noqa: E402

PORT_APP, PORT_BUS, PORT_CON, PORT_CTL, PORT_PRM = 18070, 15442, 15443, 15992, 15993
BASE = f"http://127.0.0.1:{PORT_APP}"
OUT = os.path.join(HERE, "e2e", "soak")
BUS_HZ, CON_HZ = 1000.0, 100.0

LAT_JS = r"""
(function(){
  if (window._soak) return;
  window._soak = {n: 0, max: 0, maxUrl: '', errs: 0, draws: {}, es_open: 0, es_msg: 0};
  // UI updates: count Plotly draws per graph (dcc.Graph and clientside both end in Plotly.react / extendTraces)
  (function hook(){
    var P = window.Plotly;
    if (!P || !P.react) { setTimeout(hook, 200); return; }
    if (P._soakHooked) return; P._soakHooked = true;
    ['react', 'newPlot', 'extendTraces'].forEach(function(fn){
      var orig = P[fn]; if (!orig) return;
      P[fn] = function(gd){
        try { var el = (typeof gd === 'string') ? document.getElementById(gd) : gd;
              var host = el && el.parentElement && el.parentElement.closest('[id]');
              var id = (el && el.id) || (host && host.id) || '?';
              window._soak.draws[id] = (window._soak.draws[id] || 0) + 1; } catch (e) {}
        return orig.apply(this, arguments);
      };
    });
  })();
  // live stream: count EventSource connections and messages
  var ES = window.EventSource;
  window.EventSource = function(u, o){
    var es = new ES(u, o); window._soak.es_open++;
    es.addEventListener('message', function(){ window._soak.es_msg++; });
    return es;
  };
  window.EventSource.prototype = ES.prototype;
  ['CONNECTING', 'OPEN', 'CLOSED'].forEach(function(k){ window.EventSource[k] = ES[k]; });
  var f = window.fetch;
  window.fetch = function(u, o){
    var t0 = performance.now(), url = (typeof u === 'string') ? u : (u && u.url) || '';
    return f.apply(this, arguments).then(function(r){
      var dt = performance.now() - t0; var s = window._soak; s.n++;
      if (dt > s.max) { s.max = dt; s.maxUrl = url.replace(/^https?:\/\/[^\/]+/, ''); }
      if (!r.ok) { s.errs++; }
      return r;
    }, function(e){ window._soak.errs++; throw e; });
  };
})();
"""
SAMPLE_JS = r"""
(function(){
  var s = window._soak || {n: 0, max: 0, maxUrl: '', errs: 0, draws: {}, es_open: 0, es_msg: 0};
  var o = {revs: JSON.parse(JSON.stringify(s.draws || {})), es_open: s.es_open, es_msg: s.es_msg};
  o.fetch_n = s.n; o.fetch_max_ms = Math.round(s.max); o.fetch_max_url = s.maxUrl; o.fetch_errs = s.errs;
  if (window._soak) { window._soak.max = 0; window._soak.maxUrl = ''; }
  o.page = location.pathname;
  return o;
})()
"""


# ------------------------------------------------------------------ senders (own process)
def senders(stop, t_start):
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    names = [c.get("name", c.get("n")) for c in sorted(lay["columns"], key=lambda c: c.get("column", c.get("i")))]
    f15 = struct.Struct("<%df" % (len(names) + 3))

    def bus():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        t0, k, level = time.perf_counter(), 0, 4.0
        while not stop.is_set():
            while time.perf_counter() - t0 < k / BUS_HZ:
                time.sleep(0.0005)
            t = 20.0 + k / BUS_HZ
            ph = (t % 1.1) / 1.1
            if k and k % 1100 == 0:
                level = 3.0 + 3.0 * math.sin(k / 9000.0)
            prof = max(0.0, math.sin((ph - 0.35) / 0.3 * math.pi)) if 0.35 < ph < 0.65 else 0.0
            cmd = 1.2 * level * prof
            r = [0.0] * 31
            r[0], r[1], r[2] = t, 1.1 + 0.1 * math.sin(t / 7.0), 12.0 * math.sin(2 * math.pi * ph)
            for i in range(8):
                r[3 + i] = 900.0 * max(0.0, math.sin(min(1.0, max(0.0, (ph - 0.05 * i) / 0.55)) * math.pi)) if ph < 0.65 else 3.0
            r[11], r[12], r[13] = 0.2 * math.sin(4 * math.pi * ph), 0.1 * math.cos(2 * math.pi * ph), 1.0
            r[23], r[24], r[25] = 1.1, float((k // 5500) % 2), 0.93 * cmd + 0.15 * math.sin(t * 40)
            r[26], r[27], r[28], r[29], r[30] = (1.0 if ph < 0.02 else 0.0), level, cmd, float(0x0637), float(k % 1000)
            s.sendto(struct.pack("<31f", *r), ("127.0.0.1", PORT_BUS))
            k += 1

    def console():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        t0, k = time.perf_counter(), 0
        while not stop.is_set():
            while time.perf_counter() - t0 < k / CON_HZ:
                time.sleep(0.001)
            el = time.time() - t_start
            c = el % 120.0
            if c < 5:
                ready, prog, valid = 0.0, 0.0, 0.0
            elif c < 40:
                ready, prog, valid = 1.0, (c - 5) / 35.0, 0.0
            elif c < 110:
                ready, prog, valid = 1.0, 1.0, 1.0
            else:
                ready, prog, valid = 1.0, 1.0, 0.0
            v = dict(t_model=20.0 + k / CON_HZ, side=-1.0 if el < 60 else 0.0, weight_kg=55.0, assist_mode=3.0,
                     fixed_k_pct=5.0, cmd_motor=0.0, cmd_assist=0.0, cmd_k=0.0, cmd_calibrate_pressure=0.0,
                     cmd_reset_sv=0.0, imu_ok=1.0, imu_bad_count=0.0)
            s.sendto(f15.pack(*[v[n] for n in names], valid, prog, ready), ("127.0.0.1", PORT_CON))
            k += 1

    th = [threading.Thread(target=bus, daemon=True), threading.Thread(target=console, daemon=True)]
    for x in th:
        x.start()
    while not stop.is_set():
        time.sleep(0.2)


class Listener(threading.Thread):
    def __init__(self, port):
        super().__init__(daemon=True)
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.bind(("127.0.0.1", port))
        self.s.settimeout(0.5)
        self.n = 0
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            try:
                self.s.recvfrom(2048)
                self.n += 1
            except socket.timeout:
                pass


class Browser:
    def __init__(self, port, w=1280, h=800):
        self.prof = tempfile.mkdtemp(prefix="afo_soak_cdp_")
        self.proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}",
                                      f"--user-data-dir={self.prof}", "--no-first-run", "--disable-extensions",
                                      "--hide-scrollbars", f"--window-size={w},{h}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tg = []
        for _ in range(60):
            try:
                tg = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2))
                if any(t.get("type") == "page" for t in tg):
                    break
            except Exception:
                pass
            time.sleep(0.25)
        self.c = _CDP(next(t for t in tg if t.get("type") == "page")["webSocketDebuggerUrl"])
        self.c.call("Runtime.enable")
        self.c.call("Page.enable")
        self.c.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        self.c.call("Page.addScriptToEvaluateOnNewDocument", source=LAT_JS)
        self.lock = threading.Lock()

    def js(self, expr):
        with self.lock:
            return self.c.js(expr)

    def pump(self, s):
        with self.lock:
            self.c.pump(s)

    def close(self):
        try:
            self.c.ws.close()
        except Exception:
            pass
        self.proc.terminate()


def api(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


ERR_RE = re.compile(r"Traceback|\bERROR\b|Exception|\" 5\d\d ")
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def events_counts(path):
    try:
        txt = ANSI.sub("", open(path, encoding="utf-8", errors="replace").read())
    except OSError:
        return 0, 0
    return (len(re.findall(r'"GET /events HTTP/1\.1" 200', txt)),
            len(re.findall(r'"GET /events HTTP/1\.1" 503', txt)))


def count_errors(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fp:
            lines = [ln.rstrip() for ln in fp if ERR_RE.search(ln)]
        return lines
    except OSError:
        return []


def main():
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="afo_soak_")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": PORT_BUS, "send_host": "127.0.0.1",
                  "send_port": PORT_CTL, "param_port": PORT_PRM}
    cfg["dash"] = {"host": "127.0.0.1", "port": PORT_APP}
    cfg["paths"]["log_dir"] = os.path.join(tmp, "logs")
    cfg["target"] = {"model": "AFO_r1"}
    cfg.setdefault("session", {})["target_writes_enabled"] = False
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    lay["port"] = PORT_CON
    json.dump(lay, open(os.path.join(tmp, "lay.json"), "w"))
    cfg["training"] = {"enabled": True, "listen_host": "127.0.0.1", "layout": os.path.join(tmp, "lay.json")}
    cfgp = os.path.join(tmp, "soak.yaml")
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    prof = os.path.join(APP, "data", "session_profiles.json")
    backup = None
    if os.path.exists(prof):
        backup = prof + ".soak.bak"
        shutil.copy2(prof, backup)
        os.remove(prof)

    ctl, prm = Listener(PORT_CTL), Listener(PORT_PRM)
    ctl.start(); prm.start()
    srv_log = os.path.join(tmp, "server.log")
    log = open(srv_log, "w")
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=log, stderr=subprocess.STDOUT,
                           env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    t_start = time.time()
    stop = mp.Event()
    sp = mp.Process(target=senders, args=(stop, t_start), daemon=True)
    sp.start()
    browsers, rows, fails = [], [], []
    rows_path = os.path.join(OUT, "minutes.jsonl")
    open(rows_path, "w").close()
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(4)
        pages = [("live_gait", "/live", None), ("live_training", "/live", "training"), ("trials", "/trials", None),
                 ("signals", "/signals", None)]
        for i, (name, path, sub) in enumerate(pages):
            b = Browser(19331 + i)
            b.name = name
            b.c.call("Page.navigate", url=BASE + path)
            b.pump(6)
            if sub:
                b.js("(function(){var x=document.getElementById('pgTraining'); if(x){x.click();} return !!x;})()")
                b.pump(2)
            browsers.append(b)
        proc = psutil.Process(srv.pid)
        procs = {}

        def proc_stats():
            rss, cpu = 0, 0.0
            alive = [proc] + proc.children(recursive=True)
            for p in alive:
                if p.pid not in procs:
                    procs[p.pid] = p
                    p.cpu_percent(None)
                try:
                    rss += p.memory_info().rss
                    cpu += procs[p.pid].cpu_percent(None)
                except psutil.Error:
                    pass
            return rss / 1e6, cpu, len(alive)

        proc_stats()
        last = {"st": api("/api/console/state"), "t": time.time(), "errs": 0, "ev": events_counts(srv_log),
                "samples": {b.name: b.js(SAMPLE_JS) for b in browsers}, "console": {b.name: 0 for b in browsers}}
        done = {"sid": False, "side": False, "mass": False}
        t_end = t_start + minutes * 60.0
        minute = 0
        next_t = time.time() + 60.0
        while time.time() < t_end:
            el = time.time() - t_start
            if el > 30 and not done["sid"]:
                api("/api/console/sid", {"sid": "S95"}); api("/api/console/value", {"key": "weight", "value": 55})
                done["sid"] = True
            if el > 70 and not done["side"]:
                api("/api/console/side", {"side": "LEFT"}); done["side"] = True
            if el > 90 and not done["mass"]:
                api("/api/console/value", {"key": "bif_mass", "value": 75}); done["mass"] = True
            for b in browsers:
                b.pump(0.3)        # keep reading console events
            if time.time() < next_t:
                continue
            next_t += 60.0
            minute += 1
            now = time.time()
            st = api("/api/console/state")
            rss, cpu, nproc = proc_stats()
            R, R0 = st["rig"], last["st"]["rig"]
            row = {"minute": minute, "rss_mb": round(rss, 1), "cpu_pct": round(cpu, 1), "procs": nproc,
                   "main_pps": R["main_udp"]["rate"], "main_bad_delta": (R["main_udp"]["bad"] or 0) - (R0["main_udp"]["bad"] or 0),
                   "console_pps": R["console_udp"]["rate"], "console_cols": R["console_udp"].get("columns"),
                   "console_lost_delta": (R["console_udp"]["lost"] or 0) - (R0["console_udp"]["lost"] or 0),
                   "console_rejected_delta": (R["console_udp"].get("rejected") or 0) - (R0["console_udp"].get("rejected") or 0),
                   "status": st["status"]["text"], "bif": (st.get("bif") or {}).get("text"),
                   "checklist_done": (st.get("checklist") or {}).get("all_done"),
                   "udp_sent": ctl.n + prm.n}
            errs = count_errors(srv_log)
            logs_dir = os.path.join(tmp, "logs")
            for fn in sorted(os.listdir(logs_dir)) if os.path.isdir(logs_dir) else []:
                if fn.endswith(".log"):
                    errs += count_errors(os.path.join(logs_dir, fn))
            ev = events_counts(srv_log)
            row["events_connects_new"], row["events_503_new"] = ev[0] - last["ev"][0], ev[1] - last["ev"][1]
            last["ev"] = ev
            try:
                row["sse_clients"] = api("/api/sse/clients").get("clients")
            except Exception:
                row["sse_clients"] = None
            row["server_err_new"] = len(errs) - last["errs"]
            if row["server_err_new"]:
                row["server_err_examples"] = errs[last["errs"]:][:3]
            last["errs"] = len(errs)
            for b in browsers:
                s = b.js(SAMPLE_JS)
                s0 = last["samples"][b.name]
                ids = ["torque", "gait"] if b.name == "live_gait" else ["tr-assist", "tr-uc"] if b.name == "live_training" else []
                ups = [(s["revs"].get(i) or 0) - (s0["revs"].get(i) or 0) for i in ids]
                row[f"{b.name}_updates_per_min"] = min(ups) if ups else None
                row[f"{b.name}_sse_connects"] = s["es_open"] - s0["es_open"]
                row[f"{b.name}_sse_msgs"] = s["es_msg"] - s0["es_msg"]
                row[f"{b.name}_fetch_n"] = s["fetch_n"] - s0["fetch_n"]
                row[f"{b.name}_fetch_max_ms"] = s["fetch_max_ms"]
                row[f"{b.name}_fetch_max_url"] = s["fetch_max_url"]
                row[f"{b.name}_fetch_errs_new"] = s["fetch_errs"] - s0["fetch_errs"]
                nc = len(b.c.console)
                row[f"{b.name}_console_err_new"] = nc - last["console"][b.name]
                if row[f"{b.name}_console_err_new"]:
                    row[f"{b.name}_console_examples"] = b.c.console[last["console"][b.name]:][:3]
                last["console"][b.name] = nc
                last["samples"][b.name] = s
            last["st"], last["t"] = st, now
            rows.append(row)
            with open(rows_path, "a") as fp:
                fp.write(json.dumps(row, default=str) + "\n")
            print(json.dumps(row, default=str), flush=True)
            if srv.poll() is not None:
                fails.append("app exited")
                break
        for b in browsers:
            try:
                b.c.call("Page.captureScreenshot", format="png")
            except Exception:
                pass
    finally:
        stop.set()
        for b in browsers:
            b.close()
        srv.terminate()
        try:
            srv.wait(15)
        except Exception:
            srv.kill()
        ctl.stop.set(); prm.stop.set()
        if os.path.exists(prof):
            os.remove(prof)
        if backup:
            shutil.move(backup, prof)

    # ---- verdict
    summ = {"minutes": len(rows), "fails": fails}
    if rows:
        warm = [r for r in rows if r["minute"] >= 3] or rows
        r0, rl = warm[0], rows[-1]
        growth = (rl["rss_mb"] - r0["rss_mb"]) / r0["rss_mb"] * 100.0
        summ.update(rss_mb_first=r0["rss_mb"], rss_mb_last=rl["rss_mb"], rss_mb_max=max(r["rss_mb"] for r in rows),
                    rss_growth_pct=round(growth, 1),
                    cpu_pct_mean=round(sum(r["cpu_pct"] for r in rows) / len(rows), 1),
                    main_pps_min=min(r["main_pps"] for r in warm), console_pps_min=min(r["console_pps"] for r in warm),
                    bad_or_dropped=sum(r["main_bad_delta"] + r["console_lost_delta"] + r["console_rejected_delta"] for r in rows),
                    server_errors=sum(r["server_err_new"] for r in rows),
                    browser_errors=sum(r.get(f"{n}_console_err_new", 0) + r.get(f"{n}_fetch_errs_new", 0)
                                       for r in rows for n in ("live_gait", "live_training", "trials", "signals")),
                    udp_sent=rows[-1]["udp_sent"])
        after1 = [r["events_connects_new"] for r in rows if r["minute"] > 1]
        summ["events_connects_after_min1"] = sum(after1)
        summ["events_connects_max_per_min_after_min1"] = max(after1 or [0])
        summ["events_503"] = sum(r["events_503_new"] for r in rows)
        summ["sse_clients_last"] = rows[-1].get("sse_clients")
        if summ["events_503"]:
            fails.append("/events 503")
        if summ["events_connects_max_per_min_after_min1"] > 1:
            fails.append("/events reconnect churn")
        for n in ("live_gait", "live_training", "trials", "signals"):
            ups = [r[f"{n}_updates_per_min"] for r in warm if r.get(f"{n}_updates_per_min") is not None]
            lat = [r[f"{n}_fetch_max_ms"] for r in rows]
            if ups:
                med = sorted(ups)[len(ups) // 2]
                summ[f"{n}_updates_per_min"] = {"min": min(ups), "median": med, "max": max(ups)}
                if med <= 0 or min(ups) < 0.8 * med:
                    fails.append(f"{n} update rate not steady")
            summ[f"{n}_fetch_max_ms"] = max(lat) if lat else None
        if growth > 10.0:
            fails.append(f"RSS grew {growth:.1f} %")
        if summ["server_errors"]:
            fails.append("server errors")
        if summ["browser_errors"]:
            fails.append("browser errors")
        if summ["udp_sent"]:
            fails.append("UDP sent")
        if summ["bad_or_dropped"]:
            fails.append("bad/dropped packets")
        if summ["main_pps_min"] < 0.95 * BUS_HZ:
            fails.append("main bus rate low")
        if summ["console_pps_min"] < 0.95 * CON_HZ:
            fails.append("console rate low")
    summ["PASS"] = not fails
    json.dump(summ, open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=str)
    print("SUMMARY " + json.dumps(summ, default=str), flush=True)
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
