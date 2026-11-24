"""Live > Sensors and the absolute-time x axis (localhost test ports only: app 127.0.0.1:18050,
bus :15432, console :15433, listeners :15990/:15991). No target, nothing pressed except
the sub-page buttons and one legend chip.

Checks at 1920x1080 and 1280x800 (uPlot: window._afoPlots.state()):
* x axis = model time: [max(0, t - 10), max(10, t)] on ONE shared clock, moving between reads;
  Gait, Sensors and Training use the same 2 s / 10 s window.
* Sensors: 'Pressure' (FSR1..8) and 'Acceleration' (x, y, z) with the spec's series labels;
  legend chips show numbers that change over time.
* Full width: right after switching to Sensors (fresh page load), every plot is as wide as
  its card body (+-2 px); same for Gait after switching back.
* A legend click hides that series (show == false) and shows it again.
* All canvases inside their cards, no h-scroll; no browser errors; no UDP sent.

    python test/test_sensors_tab.py
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
sys.path.insert(0, APP)
import replay_senders  # noqa: E402
from plot_style import SENSOR_CARDS  # noqa: E402
from test_ui_v18 import BASE, Browser, Listener  # noqa: E402
from pages.live import live_spec  # noqa: E402

LIVE_SPEC = live_spec()

FAILS = []
OUT = os.path.join(HERE, "e2e", "sensors")


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {str(got)[:400]}"), flush=True)
    if not cond:
        FAILS.append(name)


# uPlot (assets/live_uplot.js): plot state from window._afoPlots.state(); canvas, no DOM ticks
WIDTHS_JS = r"""
(function(sub){
  window._w = null;
  document.getElementById(sub === 'sensors' ? 'pgSensors' : 'pgGait').click();
  requestAnimationFrame(function(){ requestAnimationFrame(function(){
    var out = [];
    document.querySelectorAll('#page-live .plot-card').forEach(function(card){
      if (card.offsetParent === null) return;
      var body = card.querySelector('.plot-body'), up = card.querySelector('.uplot');
      if (!body || !up) return;
      var cs = getComputedStyle(body), inner = body.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      out.push({id: up.parentElement.id, body: Math.round(inner), svg: Math.round(up.getBoundingClientRect().width)});
    });
    window._w = out;
  }); });
  return 1;
})('%s')
"""

STATE_JS = r"""
JSON.stringify((function(){
  var st = window._afoPlots.state(), o = {cards: {}, legend: {}};
  Object.keys(st.plots).forEach(function(id){
    var p = st.plots[id];
    o.cards[id] = {names: p.labels, n: p.n, vis: p.shown, xr: [p.xmin, p.xmax], visible: p.visible};
  });
  document.querySelectorAll('.lg[data-g]').forEach(function(b){
    o.legend[b.getAttribute('data-g') + ':' + b.getAttribute('data-k')] = b.querySelector('.lg-v').textContent;
  });
  o.torque_xr = st.plots.torque ? [st.plots.torque.xmin, st.plots.torque.xmax] : null;
  var vw = window.innerWidth, bad = [];
  document.querySelectorAll('#page-live .card').forEach(function(card){
    if (card.offsetParent === null) return;
    var cb = card.getBoundingClientRect();
    card.querySelectorAll('.uplot canvas').forEach(function(cv){
      var b = cv.getBoundingClientRect(); if (b.width === 0) return;
      if (b.left < cb.left - 0.5 || b.right > cb.right + 0.5 || b.top < cb.top - 0.5 || b.bottom > cb.bottom + 0.5) bad.push('canvas outside its card');
    });
    if (cb.right > vw + 0.5) bad.push('card beyond viewport');
  });
  o.out_of_bounds = bad.slice(0, 6);
  o.hscroll = document.documentElement.scrollWidth > vw;
  return o;
})())
"""


ENDS_JS = r"""
JSON.stringify((function(){
  var st = window._afoPlots.state(), plots = [];
  Object.keys(st.plots).forEach(function(id){
    var p = st.plots[id]; if (!p.visible) return;
    plots.push([id, p.xmax, p.xmin]);
  });
  return {plots: plots, t_latest: st.t_latest, clock: st.clock};
})())
"""


def main():
    tmp = tempfile.mkdtemp(prefix="afo_sensors_")
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
    cfgp = os.path.join(tmp, "s.yaml")
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    prof = os.path.join(APP, "data", "session_profiles.json")
    backup = None
    if os.path.exists(prof):
        backup = prof + ".sensors.bak"
        shutil.copy2(prof, backup)
        os.remove(prof)
    ctl, prm = Listener(15990), Listener(15991)
    ctl.start(); prm.start()
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=open(os.path.join(tmp, "server.log"), "w"),
                           stderr=subprocess.STDOUT, env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    senders = replay_senders.start(15432, 15433, side=0.0)
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(3)
        for port, (w, h) in ((19411, (1920, 1080)), (19412, (1280, 800))):
            tag = f"{w}x{h}"
            b = Browser(port, w, h)
            c = b.c
            c.call("Page.navigate", url=BASE + "/live")
            c.pump(6)
            # half width: first frame after the first switch to Sensors on a fresh page
            c.js(WIDTHS_JS % "sensors")
            c.pump(0.4)
            wid = c.js("window._w") or []
            check(f"{tag} sensors: plots measured", len(wid) == len(SENSOR_CARDS), wid)
            off = [x for x in wid if x["svg"] is None or abs(x["svg"] - x["body"]) > 2]
            check(f"{tag} sensors: full width at the first frame", not off, off)
            c.pump(2.5)
            s1 = json.loads(c.js(STATE_JS))
            c.pump(1.5)
            s2 = json.loads(c.js(STATE_JS))
            for card in SENSOR_CARDS:
                got = (s1["cards"].get(card["id"]) or {})
                want_names = [x["label"] for x in LIVE_SPEC["plots"][card["id"]]["series"]]
                check(f"{tag} {card['id']}: named series (Pressure / Acceleration spec)", got.get("names") == want_names,
                      (got.get("names"), want_names))
                check(f"{tag} {card['id']}: has data", (got.get("n") or 0) > 50, got.get("n"))
            xr1, xr2 = s1["cards"]["press"]["xr"], s2["cards"]["press"]["xr"]
            check(f"{tag} x axis: model time, 10 s window (> 15 s model time)", abs((xr1[1] - xr1[0]) - 10) < 0.01 and xr1[1] > 15, xr1)
            check(f"{tag} x axis scrolls", xr2[1] > xr1[1], (xr1, xr2))
            vals = {k: v for k, v in s2["legend"].items()}
            check(f"{tag} legend values shown", all(v not in ("", "–") for k, v in vals.items() if not k.startswith("ankvel")), vals)
            changed = [k for k in vals if s1["legend"].get(k) != vals[k]]
            check(f"{tag} legend values update", len(changed) >= 5, changed)
            check(f"{tag} sensors: inside bounds, no h-scroll", not s2["out_of_bounds"] and not s2["hscroll"],
                  (s2["out_of_bounds"], s2["hscroll"]))
            # legend click hides / shows
            names = json.loads(c.js("JSON.stringify(Array.from(document.querySelectorAll('.lg[data-g=press] .lg-n'))"
                                    ".map(function(e){return e.textContent.trim();}))"))
            want = ["Hallux (FSR1)", "Heel medial (FSR2)", "Met 1 (FSR3)", "Met 5 (FSR4)", "Arch (FSR5)", "Toes (FSR6)",
                    "Heel lateral (FSR7)", "Met 3 (FSR8)"]
            check(f"{tag} pressure legend: FSR1..8 names (Heel medial / Heel lateral)",
                  [" ".join(n.split()) for n in names] == want, names)
            wrap = json.loads(c.js("JSON.stringify(Array.from(document.querySelectorAll('.lg[data-g=press]'))"
                                   ".filter(function(e){var r=e.getClientRects();return r.length>1 || e.scrollWidth>e.clientWidth+1;})"
                                   ".map(function(e){return e.textContent;}))"))
            check(f"{tag} pressure legend chips: no wrap / clip", not wrap, wrap)
            c.js("document.querySelector('.lg[data-g=\"press\"][data-k=\"1\"]').click(); 1")
            c.pump(1.0)
            v = json.loads(c.js(STATE_JS))["cards"]["press"]["vis"]
            check(f"{tag} legend click hides that series", v[1] is False and v[0] is True, v)
            c.js("document.querySelector('.lg[data-g=\"press\"][data-k=\"1\"]').click(); 1")
            c.pump(1.0)
            v = json.loads(c.js(STATE_JS))["cards"]["press"]["vis"]
            check(f"{tag} legend click shows it again", v[1] is True, v)
            os.makedirs(OUT, exist_ok=True)
            c.shot(os.path.join(OUT, f"{tag}_sensors.png"))
            # back to Gait: full width at once, absolute axis there too
            c.js(WIDTHS_JS % "gait")
            c.pump(0.4)
            wid = c.js("window._w") or []
            off = [x for x in wid if x["svg"] is None or abs(x["svg"] - x["body"]) > 2]
            check(f"{tag} gait: full width at the first frame", len(wid) == 2 and not off, wid)
            c.pump(1.0)
            txr = json.loads(c.js(STATE_JS))["torque_xr"]
            check(f"{tag} gait x axis: model time, 10 s window", txr and abs((txr[1] - txr[0]) - 10) < 0.01 and txr[1] > 15, txr)
            c.shot(os.path.join(OUT, f"{tag}_gait.png"))
            # same model time on every visible plot of each sub-tab (+-0.1 s), ticks in model seconds
            for sub, btn in (("gait", "pgGait"), ("sensors", "pgSensors"), ("training", "pgTraining")):
                c.js("document.getElementById('%s').click(); 1" % btn)
                c.pump(2.5 if sub == "training" else 1.2)
                r = json.loads(c.js(ENDS_JS))
                ends = [e for _, e, _ in r["plots"]]
                tl = r["t_latest"]
                # one shared model-time clock for every plot of every sub-tab (Andy 14:34: Training
                # uses the same 2 s / 10 s window as Gait and Sensors)
                check(f"{tag} {sub}: all plots end at one model time", ends and max(ends) - min(ends) <= 1e-6, r["plots"])
                check(f"{tag} {sub}: ends at the shared clock, near t_latest (+-0.3 s)", ends and tl is not None
                      and abs(max(ends) - max(10.0, tl)) <= 0.3, (tl, ends))
                wins = {round(e - s0, 2) for _, e, s0 in r["plots"]}
                check(f"{tag} {sub}: 10 s window, never negative", wins == {10.0}
                      and min(s0 for _, _, s0 in r["plots"]) >= 0, (wins, r["plots"]))
            c.js("document.getElementById('pgGait').click(); 1")
            c.pump(0.5)
            check(f"{tag} no browser errors", not c.console, c.console[:4])
            b.close()
        # top bar: 56 px (Andy: "slightly thicker"), one row at >= 1280, fits 360..1920, no banners
        b = Browser(19413, 1920, 1080)
        c = b.c
        c.call("Page.navigate", url=BASE + "/live")
        c.pump(5)
        for w in (1920, 1280, 1024, 980, 820, 600, 360):
            c.call("Emulation.setDeviceMetricsOverride", width=w, height=800, deviceScaleFactor=1, mobile=False)
            c.pump(0.8)
            r = c.js("JSON.stringify((function(){var tb=document.getElementById('topbar').getBoundingClientRect(),"
                     "sb=document.getElementById('statusBtn').getBoundingClientRect();"
                     "return {h:Math.round(tb.height), w:Math.round(tb.width), right:Math.round(sb.right), vw:innerWidth,"
                     "hs:document.documentElement.scrollWidth>innerWidth, banners:document.querySelectorAll('.sys-banner').length};})())")
            r = json.loads(r)
            check(f"top bar {w}: fits, no h-scroll", not r["hs"] and r["w"] <= r["vw"] and r["right"] <= r["vw"], r)
            if w >= 1280:
                check(f"top bar {w}: 56 px, one row", r["h"] == 56, r)
            check(f"top bar {w}: no banners", r["banners"] == 0, r)
        b.close()
        check("no UDP sent", not ctl.pkts and not prm.pkts)
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
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
