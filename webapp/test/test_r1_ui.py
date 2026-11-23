"""AFO_r1 profile in the browser (localhost only, test ports: app 127.0.0.1:18050,
bus :15432, console :15433, control/param listeners :15990/:15991). No MATLAB,
no target; target writes stay disabled. config target.model = AFO_r1.

Checks at 1920x1080 and 1280x800: the "w/ gear" mass field is shown and the
top bar fits (no horizontal scroll), the side chip shows the built side -1 as
unset, the status popover lists the 4 after-Start items (no banners: Andy Nov 23), the gear mass is
validated (> 20 kg), and no UDP packet goes out on load. Screenshots in
test/e2e/r1/. Exit 1 on any failure.
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
import replay_senders  # noqa: E402
from test_ui_v18 import BASE, Browser, Listener, api  # noqa: E402

OUT = os.path.join(HERE, "e2e", "r1")

PROBE = r"""
(function(){
  var tb = document.getElementById('topbar').getBoundingClientRect();
  var sb = document.getElementById('statusBtn').getBoundingClientRect();
  var gw = document.getElementById('sGearWrap'), lst = document.getElementById('afterStart');
  return {topbar_w: Math.round(tb.width), topbar_h: Math.round(tb.height), window_w: window.innerWidth,
          status_right: Math.round(sb.right), hscroll: document.documentElement.scrollWidth > window.innerWidth,
          gear_shown: !!gw && !gw.hidden && gw.getBoundingClientRect().width > 0,
          chip: document.getElementById('sideChip').textContent,
          banners: !!(document.getElementById('bifBanner') || document.getElementById('sideBanner') ||
                      document.querySelector('.sys-banner:not([hidden])')),
          status_text: (document.getElementById('statusTxt') || {}).textContent,
          open_items: [].slice.call(document.querySelectorAll('#openItems li b')).map(function(b){ return b.textContent; }),
          checklist_items: lst ? lst.querySelectorAll('li').length : 0};
})()
"""


def shot(c, name):
    import base64
    os.makedirs(OUT, exist_ok=True)
    data = c.call("Page.captureScreenshot", format="png")["data"]
    p = os.path.join(OUT, name + ".png")
    open(p, "wb").write(base64.b64decode(data))
    return p


def main():
    tmp = tempfile.mkdtemp(prefix="afo_r1ui_")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15432, "send_host": "127.0.0.1",
                  "send_port": 15990, "param_port": 15991}
    cfg["dash"] = {"host": "127.0.0.1", "port": 18050}
    cfg["paths"]["log_dir"] = os.path.join(tmp, "logs")
    cfg["target"] = {"model": "AFO_r1"}
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    lay["port"] = 15433
    json.dump(lay, open(os.path.join(tmp, "lay.json"), "w"))
    cfg["training"] = {"enabled": True, "listen_host": "127.0.0.1", "layout": os.path.join(tmp, "lay.json")}
    cfgp = os.path.join(tmp, "r1.yaml")
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    prof = os.path.join(APP, "data", "session_profiles.json")
    backup = None
    if os.path.exists(prof):
        backup = prof + ".r1test.bak"
        shutil.copy2(prof, backup)
        os.remove(prof)
    ctl, prm = Listener(15990), Listener(15991)
    ctl.start(); prm.start()
    log = open(os.path.join(tmp, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=log, stderr=subprocess.STDOUT,
                           env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    senders = replay_senders.start(15432, 15433, side=-1.0)
    res, fail = {}, []
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(4)
        api("/api/console/sid", {"sid": "S93"})
        # one Mass field: body mass also sets the Bi-LSTM mass (BIF_mass_kg); > 20 kg
        r20 = api("/api/console/value", {"key": "weight", "value": 20})
        r75 = api("/api/console/value", {"key": "weight", "value": 75})
        rbif = api("/api/console/value", {"key": "bif_mass", "value": 60})
        res["mass_20"], res["mass_75"], res["bif_direct"] = r20.get("msg"), r75.get("msg"), rbif.get("msg")
        if r20.get("ok") or "more than 20" not in (r20.get("msg") or ""):
            fail.append("mass_20_not_rejected")
        if not r75.get("ok"):
            fail.append("mass_75_not_saved")
        if rbif.get("ok"):
            fail.append("bif_mass_settable_directly")
        time.sleep(1.5)
        vals = api("/api/console/state")["session"]["values"]
        res["values_after_75"] = {k: vals.get(k) for k in ("weight", "bif_mass")}
        if vals.get("weight") != 75 or vals.get("bif_mass") != 75:
            fail.append("bif_mass_not_following_body_mass")
        st = api("/api/console/state")
        res["state"] = {"model": st.get("model"), "bif": st.get("bif"), "checklist": st.get("checklist"),
                        "side": st["side"], "status": st["status"]["text"],
                        "issues": [i["key"] for i in st["status"]["issues"]],
                        "settings": [(r["key"], r["entered"], r["target"]) for r in st["settings"]["rows"]]}
        if (st.get("model") or {}).get("name") != "AFO_r1":
            fail.append("model_not_r1")
        keys = [r["key"] for r in st["settings"]["rows"]]
        wrow = next((r for r in st["settings"]["rows"] if r["key"] == "weight"), {})
        if "bif_mass" in keys or "BIF_mass_kg" not in (wrow.get("title") or ""):
            fail.append("one_body_mass_row")
        for (w, h) in ((1920, 1080), (1280, 800)):
            b = Browser(19311, w, h)
            c = b.c
            c.call("Page.navigate", url=BASE + "/live")
            c.pump(7)
            p = c.js(PROBE)
            res[f"probe_{w}x{h}"] = p
            res[f"shot_{w}x{h}"] = shot(c, f"{w}x{h}_r1_after_start")
            if p["hscroll"] or p["status_right"] > p["window_w"]:
                fail.append(f"topbar_overflow_{w}")
            if p["gear_shown"]:
                fail.append(f"gear_field_still_shown_{w}")
            if p["banners"]:
                fail.append(f"banner_present_{w}")
            if p["status_text"] != "Confirm foot side" or "Confirm foot side" not in p["open_items"]:
                fail.append(f"status_button_{w}")
            if p["checklist_items"] != 4:
                fail.append(f"checklist_{w}")
            if "CONFIRM" not in p["chip"].upper():
                fail.append(f"chip_{w}")
            c.call("Page.navigate", url=BASE + "/daq")
            c.pump(3)
            res[f"shot_daq_{w}x{h}"] = shot(c, f"{w}x{h}_r1_daq")
            b.close()
        res["udp_out_ctl"], res["udp_out_param"] = len(ctl.pkts), len(prm.pkts)
        if ctl.pkts or prm.pkts:
            fail.append("udp_sent")
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
    res["FAILS"] = fail
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "results.json"), "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
