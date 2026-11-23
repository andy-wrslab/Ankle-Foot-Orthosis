"""Motor button with a latched drive fault (statusword 0x0628) on AFO_r1 (localhost test ports only).

App on 127.0.0.1:18050 (config target.model AFO_r1, target writes disabled), main bus
'<31f' at 1 kHz to :15432 with statusword 0x0628 (fault bit set) and the console
packet to :15433 with side 0. Checks: before the side is confirmed Motor is disabled
("Confirm the foot side first"); after confirming LEFT (side reads back 0 from the
console echo) Motor is clickable, neutral grey, with the fault-reset hint; with
Assist ON the hint says to switch Assist off. Nothing is pressed except the side.

    python test/test_motor_fault.py
"""
import json
import math
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
import replay_senders  # noqa: E402
from test_ui_v18 import BASE, Browser, Listener, api  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


SW = [0x0628]


def bus(stop):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    t0, k = time.perf_counter(), 0
    while not stop.is_set():
        while time.perf_counter() - t0 < k / 1000.0:
            time.sleep(0.0005)
        r = [0.0] * 31
        r[0] = 20.0 + k / 1000.0
        r[1], r[23], r[29] = 0.0, 0.5, float(SW[0])
        s.sendto(struct.pack("<31f", *r), ("127.0.0.1", 15432))
        k += 1


def main():
    tmp = tempfile.mkdtemp(prefix="afo_motorfault_")
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
    cfgp = os.path.join(tmp, "mf.yaml")
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    prof = os.path.join(APP, "data", "session_profiles.json")
    backup = None
    if os.path.exists(prof):
        backup = prof + ".mf.bak"
        shutil.copy2(prof, backup)
        os.remove(prof)
    ctl, prm = Listener(15990), Listener(15991)
    ctl.start(); prm.start()
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=open(os.path.join(tmp, "s.log"), "w"),
                           stderr=subprocess.STDOUT, env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    stop = threading.Event()
    threading.Thread(target=bus, args=(stop,), daemon=True).start()
    con = replay_senders.start(0, 15433, side=0.0)          # console only (side 0 echo), no bus
    b = None
    rd = ("JSON.stringify((function(){var m=document.getElementById('bMotor');"
          "return {dis:m.disabled, drive:m.getAttribute('data-drive'), bg:m.style.background, title:m.title};})())")
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(3)
        b = Browser(19401, 1600, 1000)
        c = b.c
        c.call("Page.navigate", url=BASE + "/live")
        c.pump(6)
        api("/api/console/sid", {"sid": "S98"})
        c.pump(1.5)
        m0 = json.loads(c.js(rd))
        check("fault, side not confirmed: Motor disabled", m0["dis"] and m0["drive"] == "fault", m0)
        api("/api/console/side", {"side": "LEFT"})
        c.pump(2.5)
        m1 = json.loads(c.js(rd))
        check("fault, side confirmed, Assist off: Motor clickable", m1["dis"] is False, m1)
        check("fault-reset: stays red (fault colour) + hint", m1["drive"] == "fault" and not (m1["bg"] or "") and "release STO, then press Motor" in m1["title"], m1)
        # drive colour from the CiA-402 state mask (bit 10 ignored)
        for sw, want in ((0x0660, "disabled"), (0x0260, "disabled"), (0x0237, "on"), (0x0637, "on"),
                         (0x0221, "ready"), (0x0623, "ready"), (0x0228, "fault")):
            SW[0] = sw
            c.pump(0.8)
            got = json.loads(c.js(rd))["drive"]
            check(f"statusword {sw:#06x} -> {want}", got == want, got)
        check("no UDP sent", not ctl.pkts and not prm.pkts)
        check("no browser errors", not c.console, c.console[:4])
    finally:
        stop.set(); con.set()
        if b:
            b.close()
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
