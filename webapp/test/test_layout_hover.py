"""Live page layout bounds + no hover hold + top status (localhost only, port 18050).

1. Layout bounds (uPlot page): every plot canvas inside its card, no legend readout
   overflow, equal drawing areas, at 1920x1080 and 1280x800, 2 s and 10 s windows, Gait and
   Sensors, with extreme / NaN / sign-flipping values. Fails on any overflow.
2. No hover hold (Andy 14:55): the pointer on the Torque plot holds nothing, Torque and
   Stride velocity keep scrolling on one shared clock (window._afoPlots.state()).
3. /api/status/top and /api/session/target answer (no MATLAB, no target).
Nothing is sent anywhere but 127.0.0.1 test ports.
"""
import json
import os
import shutil
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
sys.path.insert(0, HERE)
from cdp_capture import CHROME, _CDP  # noqa: E402

OUT = os.path.join(HERE, "e2e")
BASE = "http://127.0.0.1:18050"


class Browser:
    def __init__(self, port, w, h):
        self.prof = tempfile.mkdtemp(prefix="afo_cdp_")
        self.proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}",
                                      f"--user-data-dir={self.prof}", "--no-first-run", "--disable-extensions",
                                      "--hide-scrollbars", f"--window-size={w},{h}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tg = []
        for _ in range(40):
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

    def close(self):
        try:
            self.c.ws.close()
        except Exception:
            pass
        self.proc.terminate()


def sender(stop):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    t0, k = time.perf_counter(), 0
    while not stop.is_set():
        while time.perf_counter() - t0 < k / 1024.0:
            time.sleep(0.0005)
        ph = (k // 2048) % 4
        sign = -1.0 if (k // 64) % 2 else 1.0
        row = [0.0] * 31
        row[0] = 1.0 + k / 1024.0
        row[1] = [4.99, float("nan"), 0.0, 2.5][ph]
        row[3:11] = [[4999.0] * 8, [float("nan")] * 8, [0.0] * 8, [999.99] * 8][ph]
        row[11:14] = [[sign * 15.999] * 3, [float("nan")] * 3, [sign * 0.001] * 3, [sign * 999.99] * 3][ph]
        row[25] = [sign * 199.99, float("nan"), sign * 0.01, sign * 999.99][ph]
        row[28] = row[25]
        row[2] = [-179.9, 179.9, 0.0, float("nan")][ph]
        row[29] = 0x228
        s.sendto(struct.pack("<31f", *row), ("127.0.0.1", 15432))
        k += 1


# uPlot page (canvas): bounds of every plot canvas and legend readout inside its card, the
# equal drawing areas from window._afoPlots.state(), plus whether the plots draw at all
CHECK_JS = """
(function(){
  var bad = [], ro = [];
  document.querySelectorAll('#page-live .card').forEach(function(card){
    var cb = card.getBoundingClientRect();
    if (cb.width === 0 || card.offsetParent === null) return;
    card.querySelectorAll('.uplot canvas').forEach(function(t){
      var b = t.getBoundingClientRect();
      if (b.width === 0) return;
      if (b.left < cb.left - 0.5 || b.right > cb.right + 0.5 || b.top < cb.top - 0.5 || b.bottom > cb.bottom + 0.5)
        bad.push({card: (card.querySelector('.uplot') || {parentElement: {}}).parentElement.id,
                  over: [Math.round(cb.left-b.left), Math.round(b.right-cb.right), Math.round(cb.top-b.top), Math.round(b.bottom-cb.bottom)]});
    });
  });
  document.querySelectorAll('.lg-v').forEach(function(e){
    if (e.offsetParent === null) return;
    if (e.scrollWidth > e.clientWidth + 0.5) ro.push({text: e.textContent, sw: e.scrollWidth, cw: e.clientWidth});
  });
  var st = window._afoPlots.state(), vis = Object.keys(st.plots).filter(function(id){ return st.plots[id].visible; });
  var areas = vis.map(function(id){ return st.plots[id].area_h; });
  return {tick_overflow: bad, readout_overflow: ro, n_ticks: vis.length,
          n_readouts: document.querySelectorAll('.lg-v').length,
          equal_areas: areas.length ? Math.max.apply(null, areas) - Math.min.apply(null, areas) <= 1 : false, areas: areas};
})()
"""

REV_JS = """(function(){var s=window._afoPlots.state();
return {held: s.held, tq: (s.plots.torque||{}).xmax, gt: (s.plots.gait||{}).xmax, drawn: s.drawn};})()"""


def mouse(c, x, y):
    c.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="afo_r5_")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15432, "send_host": "127.0.0.1",
                  "send_port": 15990, "param_port": 15991}
    cfg["dash"] = {"host": "127.0.0.1", "port": 18050}
    cfg.setdefault("paths", {})["log_dir"] = os.path.join(tmp, "logs")
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    lay["port"] = 15433
    lp = os.path.join(tmp, "layout.json")
    json.dump(lay, open(lp, "w"))
    cfg["training"] = {"enabled": True, "listen_host": "127.0.0.1", "layout": lp}
    cfgp = os.path.join(tmp, "r5.yaml")
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    log = open(os.path.join(tmp, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=log, stderr=subprocess.STDOUT,
                           env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    stop = threading.Event()
    threading.Thread(target=sender, args=(stop,), daemon=True).start()
    res = {"cases": [], "fail": False}
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(3)
        # ---- 1 layout bounds
        for w, h in ((1920, 1080), (1280, 800)):
            b = Browser(19293, w, h)
            c = b.c
            c.call("Page.navigate", url=BASE + "/live")
            c.pump(6)
            for win_btn in ("w10", "w2"):
                c.js(f"document.getElementById('{win_btn}').click(); 1")
                for page in (0, 1):
                    c.js("document.getElementById('%s').click(); 1" % ("pgGait", "pgSensors")[page])
                    worst = {"tick_overflow": [], "readout_overflow": [], "equal_areas": True}
                    for _ in range(16):
                        c.pump(0.5)
                        r = c.js(CHECK_JS)
                        worst["tick_overflow"] += r["tick_overflow"]
                        worst["readout_overflow"] += r["readout_overflow"]
                        worst["n_ticks"], worst["n_readouts"] = r["n_ticks"], r["n_readouts"]
                        worst["equal_areas"] = worst["equal_areas"] and r["equal_areas"]
                    name = f"{w}x{h}_{win_btn[1:]}s_page{page + 1}"
                    shot = os.path.join(OUT, f"r5_bounds_{name}.png")
                    c.shot(shot)
                    case = {"case": name, "tick_overflows": len(worst["tick_overflow"]),
                            "readout_overflows": len(worst["readout_overflow"]),
                            "examples": (worst["tick_overflow"] + worst["readout_overflow"])[:4],
                            "ticks_checked": worst.get("n_ticks"), "readouts_checked": worst.get("n_readouts"),
                            "equal_areas": worst["equal_areas"]}
                    res["cases"].append(case)
                    if case["tick_overflows"] or case["readout_overflows"] or not worst.get("n_ticks") or not worst["equal_areas"]:
                        res["fail"] = True
            if (w, h) == (1280, 800):
                # ---- 2 no hover hold any more (uPlot, Andy 14:55): pointer on Torque, both plots
                # keep scrolling on ONE shared clock, nothing is held
                c.js("document.getElementById('w10').click(); document.getElementById('pgGait').click(); 1")
                c.pump(2)
                box = c.js("(function(){var r=document.getElementById('torque').getBoundingClientRect();return [r.left+r.width*0.6, r.top+r.height*0.5];})()")
                before = c.js(REV_JS)
                mouse(c, box[0], box[1])
                c.pump(0.8)
                h0 = c.js(REV_JS)
                mouse(c, box[0] + 2, box[1])
                c.pump(2.0)
                h1 = c.js(REV_JS)
                c.shot(os.path.join(OUT, "r5_no_hold.png"))
                hv = {"before": before, "start": h0, "after_2s": h1}
                hv["not_held"] = h1["held"] is False
                hv["torque_kept_scrolling"] = (h1["tq"] or 0) > (h0["tq"] or 0)
                hv["one_clock"] = h1["tq"] is not None and h1["tq"] == h1["gt"]
                res["hover"] = hv
                if not all(hv[k] for k in ("not_held", "torque_kept_scrolling", "one_clock")):
                    res["fail"] = True
                res["console_errors"] = c.console[:6]
            b.close()
        # ---- 3 APIs
        top = json.loads(urllib.request.urlopen(BASE + "/api/status/top", timeout=5).read())
        res["status_top"] = {k: top[k] for k in ("state", "text", "level", "base_state", "streams")}
        res["status_top"]["issues"] = [i["text"] for i in top["issues"]]
        tgt = json.loads(urllib.request.urlopen(BASE + "/api/session/target", timeout=5).read())
        res["session_target_rows"] = [r["name"] for r in tgt["rows"]]
        res["training_plots"] = [(p["title"], p["columns"], [round(v, 2) for v in p["y_range"]])
                                 for p in json.loads(urllib.request.urlopen(BASE + "/api/training/plots").read())["plots"]]
        runs = json.loads(urllib.request.urlopen(BASE + "/api/trials/runs", timeout=5).read())
        res["trials_runs"] = {"n": len(runs["runs"]), "connected": runs["connected"]}
    finally:
        stop.set()
        subprocess.run(["taskkill", "/PID", str(srv.pid), "/T", "/F"], capture_output=True)
        log.close()
        try:
            res["server_errors"] = [ln.strip() for ln in open(os.path.join(tmp, "server.log"), encoding="utf-8",
                                                                errors="replace") if "Traceback" in ln or " ERROR " in ln][:8]
        except OSError:
            pass
    json.dump(res, open(os.path.join(OUT, "r5_layout_hover_results.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1 if res["fail"] else 0)


if __name__ == "__main__":
    main()
