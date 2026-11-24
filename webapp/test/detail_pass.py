"""Detail pass of the page (round 2): every page / popover at several window sizes.

App on 127.0.0.1:18050 (test ports only, target writes disabled, config model
AFO_r1), replay senders on :15432/:15433 (1 kHz bus, 100 Hz console), UDP
listeners on :15990/:15991. Never presses Connect / Start / Stop / Build / Flash
(those would start MATLAB or arduino-cli); presses only page controls.

Per size (1280x800, 1920x1080, 2560x1440, 1920x1080 at 125 %):
  views: Live Gait / Sensors / Training, Trials, Signals, Teensy, Advanced popover,
  status popover, side popover. Checks per view: no horizontal scroll, nothing
  past the right edge, no clipped text (scrollWidth > clientWidth on text nodes
  with overflow hidden), tick labels inside their cards, no console errors,
  no layout jump between first paint and 3 s of data (card rects within 1 px).
Feedback latency: click -> first DOM change (MutationObserver) for sub-tab,
  window, Advanced, status, side chip, legend chip, Motor / Assist / K.
Writes test/e2e/round2/results.json and screenshots (1920 at deviceScaleFactor 2).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _lowprio  # noqa: E402,F401
import replay_senders  # noqa: E402
from test_ui_v18 import BASE, Browser, Listener, api  # noqa: E402

OUT = os.path.join(HERE, "e2e", "round2")

PROBE = r"""
JSON.stringify((function(){
  var vw = innerWidth, out = {hscroll: document.documentElement.scrollWidth > vw, past_edge: [], clipped: [], ticks_out: []};
  document.querySelectorAll('body *').forEach(function(e){
    if (e.offsetParent === null && getComputedStyle(e).position !== 'fixed') return;
    var r = e.getBoundingClientRect(); if (r.width === 0 || r.height === 0) return;
    if (r.right > vw + 1 && !e.closest('.uplot')) {
      if (!e.parentElement || e.parentElement.getBoundingClientRect().right <= vw + 1) out.past_edge.push((e.id || e.className || e.tagName) + ' ' + Math.round(r.right));
    }
    var cs = getComputedStyle(e);
    if ((cs.overflow === 'hidden' || cs.textOverflow === 'ellipsis' || cs.whiteSpace === 'nowrap') && e.children.length === 0 &&
        e.textContent.trim() && e.scrollWidth > e.clientWidth + 1 && !e.closest('.uplot') && !e.closest('pre') &&
        !(e.classList && e.classList.contains('sb-txt')))      /* status text: ellipsis on purpose, full text in title */
      out.clipped.push((e.id || e.className || e.tagName) + ': ' + e.textContent.trim().slice(0, 40));
  });
  document.querySelectorAll('.card').forEach(function(card){
    if (card.offsetParent === null) return;
    var cb = card.getBoundingClientRect();
    card.querySelectorAll('.xtick text, .ytick text').forEach(function(t){
      var b = t.getBoundingClientRect(); if (b.width === 0) return;
      if (b.left < cb.left - 0.5 || b.right > cb.right + 0.5 || b.top < cb.top - 0.5 || b.bottom > cb.bottom + 0.5) out.ticks_out.push(t.textContent);
    });
  });
  var vis = [].slice.call(document.querySelectorAll('.card')).filter(function(c){ return c.offsetParent !== null; });
  out.overlap = [];
  for (var i = 0; i < vis.length; i++) for (var j = i + 1; j < vis.length; j++) {
    if (vis[i].contains(vis[j]) || vis[j].contains(vis[i])) continue;
    var a = vis[i].getBoundingClientRect(), b = vis[j].getBoundingClientRect();
    if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1)
      out.overlap.push(((vis[i].querySelector('.card-title') || {}).textContent || i) + ' x ' + ((vis[j].querySelector('.card-title') || {}).textContent || j));
  }
  out.overlap = out.overlap.slice(0, 4);
  out.cards = vis
    .map(function(c){ var r = c.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; });
  out.fonts = Array.from(new Set([].slice.call(document.querySelectorAll('body, button, .card-title, .tb-field, .input'))
    .map(function(e){ return getComputedStyle(e).fontFamily.split(',')[0]; })));
  out.past_edge = out.past_edge.slice(0, 6); out.clipped = out.clipped.slice(0, 8); out.ticks_out = out.ticks_out.slice(0, 6);
  return out;
})())
"""

LATENCY = r"""
(function(sel){
  window._lat = null;
  var el = document.querySelector(sel); if (!el) { window._lat = {err: 'missing ' + sel}; return 0; }
  var t0 = performance.now(), done = false;
  var mo = new MutationObserver(function(){ if (done) return; done = true; window._lat = {ms: Math.round(performance.now() - t0)}; mo.disconnect(); });
  mo.observe(document.body, {subtree: true, childList: true, attributes: true, characterData: true});
  el.click();
  setTimeout(function(){ if (!done) { done = true; mo.disconnect(); window._lat = {ms: null}; } }, 1500);
  return 1;
})('%s')
"""

VIEWS = [
    ("live_gait", "/live", "document.getElementById('pgGait').click()"),
    ("live_sensors", "/live", "document.getElementById('pgSensors').click()"),
    ("live_training", "/live", "document.getElementById('pgTraining').click()"),
    ("trials", "/trials", None),
    ("daq", "/daq", None),
    ("advanced_popover", "/live", "document.getElementById('advBtn').click()"),
    ("status_popover", "/live", "document.getElementById('statusBtn').click()"),
    ("side_popover", "/live", "document.getElementById('sideChip').click()"),
]
CLICKS = [("sub-tab Sensors", "#pgSensors"), ("sub-tab Gait", "#pgGait"), ("window 2 s", "#w2"), ("window 10 s", "#w10"),
          ("Advanced", "#advBtn"), ("status button", "#statusBtn"), ("side chip", "#sideChip"),
          ("Motor", "#bMotor"), ("Assist", "#bAssist"), ("K", "#bK")]


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="afo_round2_")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15432, "send_host": "127.0.0.1",
                  "send_port": 15990}
    cfg["dash"] = {"host": "127.0.0.1", "port": 18050}
    cfg["paths"]["log_dir"] = os.path.join(tmp, "logs")
    cfg["target"] = {"model": "AFO_r1"}
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    lay["port"] = 15433
    json.dump(lay, open(os.path.join(tmp, "lay.json"), "w"))
    cfg["training"] = {"enabled": True, "listen_host": "127.0.0.1", "layout": os.path.join(tmp, "lay.json")}
    cfgp = os.path.join(tmp, "r2.yaml")
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    prof = os.path.join(APP, "data", "session_profiles.json")
    backup = None
    if os.path.exists(prof):
        backup = prof + ".r2.bak"
        shutil.copy2(prof, backup)
        os.remove(prof)
    ctl, prm = Listener(15990), Listener(15991)
    ctl.start(); prm.start()
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=open(os.path.join(tmp, "server.log"), "w"),
                           stderr=subprocess.STDOUT, env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    senders = replay_senders.start(15432, 15433, side=0.0)
    res = {"sizes": {}, "latency": {}}
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(3)
        api("/api/console/sid", {"sid": "S99"})
        api("/api/console/side", {"side": "LEFT"})
        sizes = [("820x1000", 820, 1000, 1), ("1024x768", 1024, 768, 1), ("1280x800", 1280, 800, 1),
                 ("1920x1080", 1920, 1080, 1), ("2560x1440", 2560, 1440, 1), ("1920x1080@125", 1920, 1080, 1.25)]
        port = 19431
        for tag, w, h, z in sizes:
            b = Browser(port, w, h)
            port += 1
            c = b.c
            c.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=z, mobile=False)
            res["sizes"][tag] = {}
            for name, path, act in VIEWS:
                c.call("Page.navigate", url=BASE + path)
                c.pump(4)
                if act:
                    c.js(act + "; 1")
                first = json.loads(c.js(PROBE))
                c.pump(3)
                later = json.loads(c.js(PROBE))
                jump = [(a, b2) for a, b2 in zip(first["cards"], later["cards"])
                        if any(abs(x - y) > 1 for x, y in zip(a, b2))]
                later["layout_jump"] = jump[:4]
                later["console_errors"] = c.console[:4]
                c.console.clear()
                res["sizes"][tag][name] = {k: later[k] for k in ("hscroll", "past_edge", "clipped", "ticks_out", "overlap",
                                                                 "layout_jump", "console_errors", "fonts")}
                if tag == "1920x1080":
                    c.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2, mobile=False)
                    c.pump(0.8)
                    c.shot(os.path.join(OUT, f"{name}_1920.png"))
                    c.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
                elif tag in ("1280x800", "2560x1440"):
                    c.shot(os.path.join(OUT, f"{name}_{tag}.png"))
            if tag == "1920x1080":
                c.call("Page.navigate", url=BASE + "/live")
                c.pump(5)
                for label, sel in CLICKS + [("legend chip", '.lg[data-g="press"][data-k="0"]')]:
                    if label == "legend chip":
                        c.js("document.getElementById('pgSensors').click(); 1")
                        c.pump(1.0)
                    c.js(LATENCY % sel.replace("'", "\\'"))
                    c.pump(1.6)
                    res["latency"][label] = c.js("window._lat")
                    c.js("document.body.click(); 1")       # close popovers
                    c.pump(0.4)
            b.close()
        res["udp_sent"] = {"control": len(ctl.pkts), "param": len(prm.pkts)}
    finally:
        senders.set()
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()
        if os.path.exists(prof):
            os.remove(prof)
        if backup:
            shutil.move(backup, prof)
    json.dump(res, open(os.path.join(OUT, "results.json"), "w"), indent=1)
    # short summary
    for tag, views in res["sizes"].items():
        for name, r in views.items():
            bad = {k: v for k, v in r.items() if k != "fonts" and v}
            if bad:
                print(tag, name, json.dumps(bad)[:400])
    print("latency", json.dumps(res["latency"]))
    print("fonts", sorted({f for v in res["sizes"].values() for r in v.values() for f in r["fonts"]}))
    print("udp", res.get("udp_sent"))


if __name__ == "__main__":
    main()
