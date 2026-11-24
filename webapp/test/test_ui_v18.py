"""Design v18 end-to-end UI test (localhost only; nothing goes to the Speedgoat).

App on 127.0.0.1:18050 with the replay senders (main bus -> :15432, console
packet -> :15433) and UDP listeners standing in for the target's control
(:15990) and parameter (:15991) ports. Target writes stay disabled.

1. States (44-float device, run 16): S47 + LEFT -> OK; the device side changes to 1 -> the
   page shows the device's RIGHT (adopted, no mismatch). Screenshots of each.
2. Screenshots at 1920x1080 and 1280x800: Live Gait / Sensors / Training,
   Trials, DAQ, status popover, Advanced popover.
3. Layout: every plot tick label inside its card (all Live sub-pages, both
   sizes), top bar not wider than the window, status button inside the gutter,
   no horizontal scroll.
4. (uPlot) no hover hold: pointer on Torque, both plots keep scrolling on one clock.
5. Commands: 0 control packets from page loads; Assist OFF->ON press = exactly
   one packet with only assist changed; after a device side change a Motor press is one
   UDP packet (no MATLAB, no mismatch lock).
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
import replay_senders  # noqa: E402

OUT = os.path.join(HERE, "e2e", "v18")
BASE = "http://127.0.0.1:18050"


class Listener(threading.Thread):
    def __init__(self, port):
        super().__init__(daemon=True)
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.bind(("127.0.0.1", port))
        self.s.settimeout(0.5)
        self.pkts = []
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            try:
                d, _ = self.s.recvfrom(1024)
                self.pkts.append((time.time(), d))
            except socket.timeout:
                pass


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
        self.w, self.h = w, h

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


BOUNDS_JS = """
(function(){
  var bad = [], n = 0;
  document.querySelectorAll('.plot-card').forEach(function(card){
    if (card.offsetParent === null) return;
    var cb = card.getBoundingClientRect();
    card.querySelectorAll('.xtick text, .ytick text').forEach(function(t){
      var b = t.getBoundingClientRect(); if (!b.width) return; n++;
      if (b.left < cb.left - .5 || b.right > cb.right + .5 || b.top < cb.top - .5 || b.bottom > cb.bottom + .5)
        bad.push({card: (card.querySelector('.card-title')||{}).textContent, label: t.textContent});
    });
  });
  var tb = document.getElementById('topbar').getBoundingClientRect();
  var sb = document.getElementById('statusBtn').getBoundingClientRect();
  return {tick_overflow: bad.slice(0, 5), n_ticks: n, topbar_w: Math.round(tb.width), window_w: window.innerWidth,
          status_right: Math.round(sb.right), hscroll: document.documentElement.scrollWidth > window.innerWidth,
          plot_h: Array.from(document.querySelectorAll('.plot-card')).filter(function(c){return c.offsetParent;})
                   .map(function(c){return Math.round(c.querySelector('.plot-body').getBoundingClientRect().height);})};
})()
"""


def nav(c, page, wait=2.5):
    c.js(f"document.querySelector('#nav a[data-nav=\"{page}\"]').click(); 1")
    c.pump(wait)


def sub(c, name, wait=3.0):
    c.js(f"document.getElementById('pg{name}').click(); 1")
    c.pump(wait)


def shot(c, name):
    p = os.path.join(OUT, name + ".png")
    c.shot(p)
    return p


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="afo_v18_")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15432, "send_host": "127.0.0.1",
                  "send_port": 15990}
    cfg["dash"] = {"host": "127.0.0.1", "port": 18050}
    cfg["paths"]["log_dir"] = os.path.join(tmp, "logs")
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    lay["port"] = 15433
    json.dump(lay, open(os.path.join(tmp, "lay.json"), "w"))
    cfg["training"] = {"enabled": True, "listen_host": "127.0.0.1", "layout": os.path.join(tmp, "lay.json")}
    cfgp = os.path.join(tmp, "v18.yaml")
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    # session profiles live in data/: start from a clean copy so the test never touches real profiles
    data_dir = os.path.join(APP, "data")
    backup = None
    prof = os.path.join(data_dir, "session_profiles.json")
    if os.path.exists(prof):
        backup = prof + ".v18test.bak"
        shutil.copy2(prof, backup)
        os.remove(prof)
    ctl, prm = Listener(15990), Listener(15991)
    ctl.start(); prm.start()
    log = open(os.path.join(tmp, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=log, stderr=subprocess.STDOUT,
                           env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    senders = replay_senders.start(15432, 15433, side=0.0)
    res = {"shots": {}, "bounds": [], "fail": []}
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(4)
        for (w, h) in ((1920, 1080), (1280, 800)):
            b = Browser(19301, w, h)
            c = b.c
            tag = f"{w}x{h}"
            c.call("Page.navigate", url=BASE + "/live")
            c.pump(7)
            if w == 1920:
                res["pkts_after_load"] = len(ctl.pkts)
                st = api("/api/console/state")
                res["state_no_sid"] = {"status": st["status"]["text"], "side": st["side"]["state"], "chip": st["side"]["chip"]}
                res["shots"]["state_no_participant"] = shot(c, f"{tag}_state_no_participant")
                api("/api/console/sid", {"sid": "S47"})
                api("/api/console/value", {"key": "weight", "value": 55})
                c.pump(2)
                res["shots"]["state_confirm"] = shot(c, f"{tag}_state_confirm")
                st = api("/api/console/state")
                res["state_confirm"] = {"status": st["status"]["text"], "side": st["side"]["state"],
                                        "chip": st["side"]["chip"], "start_disabled": c.js("document.getElementById('tStart').disabled")}
                # confirm LEFT through the side popover (two clicks)
                c.js("document.getElementById('sideChip').click(); 1"); c.pump(0.6)
                res["shots"]["side_popover"] = shot(c, f"{tag}_side_popover")
                c.js("document.querySelector('.side-opt[data-side=\"LEFT\"]').click(); 1"); c.pump(0.4)
                c.js("document.getElementById('scOk').click(); 1"); c.pump(2.5)
                st = api("/api/console/state")
                res["state_ok"] = {"status": st["status"]["text"], "side": st["side"]["state"], "chip": st["side"]["chip"],
                                   "rows": [(r["label"], r["entered"], r["target"], r["state"]) for r in st["settings"]["rows"]]}
            # ---- pages
            sub(c, "Gait"); res["shots"][f"{tag}_live_gait"] = shot(c, f"{tag}_live_gait")
            res["bounds"].append(dict(view=f"{tag}_gait", **c.js(BOUNDS_JS)))
            sub(c, "Sensors"); res["shots"][f"{tag}_live_sensors"] = shot(c, f"{tag}_live_sensors")
            res["bounds"].append(dict(view=f"{tag}_sensors", **c.js(BOUNDS_JS)))
            sub(c, "Training", 4.0); res["shots"][f"{tag}_live_training"] = shot(c, f"{tag}_live_training")
            res["bounds"].append(dict(view=f"{tag}_training", **c.js(BOUNDS_JS)))
            sub(c, "Gait", 2.0)
            c.js("document.getElementById('statusBtn').click(); 1"); c.pump(1.0)
            res["shots"][f"{tag}_status_popover"] = shot(c, f"{tag}_status_popover")
            c.js("document.body.click(); 1"); c.pump(0.3)
            c.js("document.getElementById('advBtn').click(); 1"); c.pump(1.0)
            res["shots"][f"{tag}_advanced"] = shot(c, f"{tag}_advanced")
            c.js("document.body.click(); 1"); c.pump(0.3)
            nav(c, "trials", 3.0); res["shots"][f"{tag}_trials"] = shot(c, f"{tag}_trials")
            nav(c, "daq", 3.0); res["shots"][f"{tag}_daq"] = shot(c, f"{tag}_daq")
            nav(c, "live", 3.0)
            if w == 1920:
                # ---- no hover hold any more (uPlot, Andy 14:55): pointer on Torque, both plots keep
                # scrolling on the one shared model-time clock (window._afoPlots.state())
                box = c.js("(function(){var r=document.getElementById('torque').getBoundingClientRect();return [r.left+r.width*0.6, r.top+r.height*0.5];})()")
                rev = "(function(){var s=window._afoPlots.state();return {clock:s.clock, held:s.held, tq:(s.plots.torque||{}).xmax, gt:(s.plots.gait||{}).xmax};})()"
                c.call("Input.dispatchMouseEvent", type="mouseMoved", x=box[0], y=box[1]); c.pump(0.6)
                h0 = c.js(rev); c.call("Input.dispatchMouseEvent", type="mouseMoved", x=box[0] + 3, y=box[1]); c.pump(2.0)
                h1 = c.js(rev)
                res["shots"]["hover_no_hold"] = shot(c, f"{tag}_hover_no_hold")
                res["hover"] = {"before": h0, "after": h1, "not_held": h1["held"] is False,
                                "torque_moving": (h1["tq"] or 0) > (h0["tq"] or 0),
                                "same_window": h1["tq"] is not None and abs((h1["tq"] or 0) - (h1["gt"] or 0)) < 1e-6}
                # ---- commands: page loads sent nothing; Assist press = 1 packet
                n0 = len(ctl.pkts)
                res["toggle_state_before"] = api("/api/console/state")["commands"]["toggles"]
                c.js("document.getElementById('bAssist').click(); 1"); c.pump(1.5)
                res["assist_press_packets"] = [struct.unpack("<6f", p) for _, p in ctl.pkts[n0:]]
                # ---- the device's side changes to RIGHT (another console): the page shows the device's
                # value (Andy 16:15, run 14+ adopts it), no mismatch; Motor stays usable over UDP
                senders.set()
                senders = replay_senders.start(15432, 15433, side=1.0)
                c.pump(3.0)
                st = api("/api/console/state")
                res["state_device_side"] = {"status": st["status"]["text"], "side": st["side"]["state"], "chip": st["side"]["chip"]}
                res["shots"]["state_device_side"] = shot(c, f"{tag}_state_device_side")
                n2 = len(ctl.pkts)
                r2 = api("/api/console/toggle", {"name": "motor"})
                time.sleep(0.5)
                res["device_side_motor"] = {"ok": r2.get("ok"), "msg": r2.get("msg"), "packets": len(ctl.pkts) - n2}
                senders.set()
                senders = replay_senders.start(15432, 15433, side=0.0)
                c.pump(2.0)
            res[f"console_errors_{tag}"] = c.console[:6]
            b.close()
        res["param_packets"] = len(prm.pkts)
    finally:
        senders.set()
        subprocess.run(["taskkill", "/PID", str(srv.pid), "/T", "/F"], capture_output=True)
        ctl.stop.set(); prm.stop.set()
        log.close()
        try:
            res["server_errors"] = [ln.strip() for ln in open(os.path.join(tmp, "server.log"), encoding="utf-8",
                                                                errors="replace") if "Traceback" in ln or " ERROR " in ln][:8]
        except OSError:
            pass
        if os.path.exists(prof):
            os.remove(prof)
        if backup:
            shutil.move(backup, prof)
    # verdicts
    for bd in res["bounds"]:
        if bd["tick_overflow"] or bd["hscroll"] or bd["topbar_w"] > bd["window_w"] or bd["status_right"] > bd["window_w"] - 8 or not bd["n_ticks"]:
            res["fail"].append(f"layout {bd['view']}")
    if res.get("pkts_after_load"):
        res["fail"].append("packets sent on page load")
    hv = res.get("hover") or {}
    if not (hv.get("not_held") and hv.get("torque_moving") and hv.get("same_window")):
        res["fail"].append("no hold / shared window")
    ap = res.get("assist_press_packets") or []
    if len(ap) != 1:
        res["fail"].append(f"assist press sent {len(ap)} packets")
    # run 14+ (44-float device): the side is the device's (adopted from the echo), never 'differs'
    if (res.get("state_ok") or {}).get("side") != "ok" or (res.get("state_device_side") or {}).get("side") != "ok" \
            or "RIGHT" not in str((res.get("state_device_side") or {}).get("chip", "")).upper():
        res["fail"].append("side states (device side adopted)")
    if (res.get("device_side_motor") or {}).get("packets") != 1:
        res["fail"].append("motor press after a device side change: not exactly one UDP packet")
    if any("differs" in str(r[3]) for r in (res.get("state_ok") or {}).get("rows") or []):
        res["fail"].append("a 'differs' row in the popover")
    if res.get("param_packets"):
        res["fail"].append("parameter packets sent")
    json.dump(res, open(os.path.join(OUT, "results.json"), "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))
    sys.exit(1 if res["fail"] else 0)


if __name__ == "__main__":
    main()
