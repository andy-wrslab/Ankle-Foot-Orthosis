"""Design v18 end-to-end UI test (localhost only; nothing goes to the Speedgoat).

App on 127.0.0.1:18050 with the replay senders (main bus -> :15432, console
packet -> :15433) and UDP listeners standing in for the target's control
(:15990) and parameter (:15991) ports. Target writes stay disabled.

1. States: no participant -> Confirm (banner); S47 + LEFT confirmed + console
   side 0 -> OK; console side 1 -> Mismatch. Screenshots of each.
2. Screenshots at 1920x1080 and 1280x800: Live Gait / Sensors / Training,
   Trials, Signals, Teensy, status popover, Advanced popover.
3. Layout: every plot tick label inside its card (all Live sub-pages, both
   sizes), top bar not wider than the window, status button inside the gutter,
   no horizontal scroll.
4. Hover hold on Torque: card gets "holding", Torque frozen, Stride velocity keeps
   drawing; released on leave.
5. Commands: 0 control packets from page loads; Assist OFF->ON press = exactly
   one packet with only assist changed; Motor ON blocked during a side mismatch
   (0 packets) while Motor OFF stays possible.
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
                  "send_port": 15990, "param_port": 15991}
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
            nav(c, "signals", 3.0); res["shots"][f"{tag}_signals"] = shot(c, f"{tag}_signals")
            nav(c, "teensy", 3.0); res["shots"][f"{tag}_teensy"] = shot(c, f"{tag}_teensy")
            nav(c, "live", 3.0)
            if w == 1920:
                # ---- hover hold on Torque
                box = c.js("(function(){var r=document.querySelector('#torque .nsewdrag').getBoundingClientRect();return [r.left+r.width*0.6, r.top+r.height*0.5];})()")
                rev = "(function(){var o={};['torque','gait'].forEach(function(id){var g=document.getElementById(id);g=g&&(g.querySelector('.js-plotly-plot')||g);o[id]=g&&g.layout?g.layout.datarevision:null;});o.holding=!!document.querySelector('.plot-card.holding');return o;})()"
                c.call("Input.dispatchMouseEvent", type="mouseMoved", x=box[0], y=box[1]); c.pump(0.6)
                h0 = c.js(rev); c.call("Input.dispatchMouseEvent", type="mouseMoved", x=box[0] + 3, y=box[1]); c.pump(2.0)
                h1 = c.js(rev)
                res["shots"]["hover_hold"] = shot(c, f"{tag}_hover_hold")
                c.call("Input.dispatchMouseEvent", type="mouseMoved", x=5, y=b.h - 5); c.pump(2.0)
                h2 = c.js(rev)
                res["hover"] = {"held": h1, "after": h2, "frozen": h0["torque"] == h1["torque"],
                                "gait_moving": (h1["gait"] or 0) > (h0["gait"] or 0),
                                "resumed": (h2["torque"] or 0) > (h1["torque"] or 0), "holding_class": h1["holding"],
                                "released": not h2["holding"]}
                # ---- commands: page loads sent nothing; Assist press = 1 packet
                n0 = len(ctl.pkts)
                res["toggle_state_before"] = api("/api/console/state")["commands"]["toggles"]
                c.js("document.getElementById('bAssist').click(); 1"); c.pump(1.5)
                res["assist_press_packets"] = [struct.unpack("<6f", p) for _, p in ctl.pkts[n0:]]
                # ---- mismatch: console side becomes RIGHT
                senders.set()
                senders = replay_senders.start(15432, 15433, side=1.0)
                c.pump(3.0)
                st = api("/api/console/state")
                res["state_mismatch"] = {"status": st["status"]["text"], "side": st["side"]["state"], "chip": st["side"]["chip"]}
                res["shots"]["state_mismatch"] = shot(c, f"{tag}_state_mismatch")
                n2 = len(ctl.pkts)
                r2 = api("/api/console/toggle", {"name": "motor"})         # model echo motor OFF: press = ON -> blocked
                time.sleep(0.5)
                res["mismatch_motor_on"] = {"ok": r2.get("ok"), "msg": r2.get("msg"), "packets": len(ctl.pkts) - n2}
                # model reports Motor ON during the mismatch: switching it OFF must still work
                senders.set()
                senders = replay_senders.start(15432, 15433, side=1.0, cmds={"cmd_motor": 1.0})
                c.pump(2.0)
                n1 = len(ctl.pkts)
                r_off = api("/api/console/toggle", {"name": "motor"})
                time.sleep(0.5)
                res["mismatch_motor_off"] = {"ok": r_off.get("ok"), "msg": r_off.get("msg"),
                                             "packets": [struct.unpack("<6f", p) for _, p in ctl.pkts[n1:]]}
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
    if not (hv.get("frozen") and hv.get("gait_moving") and hv.get("resumed") and hv.get("holding_class") and hv.get("released")):
        res["fail"].append("hover hold")
    ap = res.get("assist_press_packets") or []
    if len(ap) != 1:
        res["fail"].append(f"assist press sent {len(ap)} packets")
    if (res.get("state_confirm") or {}).get("side") != "confirm" or (res.get("state_ok") or {}).get("side") != "ok" \
            or (res.get("state_mismatch") or {}).get("side") != "mismatch":
        res["fail"].append("side states")
    if (res.get("mismatch_motor_on") or {}).get("packets") != 0:
        res["fail"].append("motor ON not blocked during mismatch")
    if len((res.get("mismatch_motor_off") or {}).get("packets") or []) != 1:
        res["fail"].append("motor OFF not possible during mismatch")
    if res.get("param_packets"):
        res["fail"].append("parameter packets sent")
    json.dump(res, open(os.path.join(OUT, "results.json"), "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))
    sys.exit(1 if res["fail"] else 0)


if __name__ == "__main__":
    main()
