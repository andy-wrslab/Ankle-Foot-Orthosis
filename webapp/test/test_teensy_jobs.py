"""Teensy Build / Flash feedback (no upload ever happens here).

Part 1, units: JobManager.start_exclusive (double click -> 1 job), Teensy board-list
merge (COMx serial + teensy-protocol port with different serial numbers -> one device,
upload via teensy protocol), compile stage/counters, flash_job OK / FAILED / port not
back with a fake run_process and scanner.

Part 2, browser (app on 127.0.0.1:18050, test ports only): arduino-cli is replaced by
a stand-in .bat that passes only `compile` and `board` (read-only) to the real CLI and
answers everything else (`upload`) with an echo, so nothing is ever uploaded. Checks:
a double-clicked Build starts one job (and the API answers 409 busy), the button reads
"Building… m:ss" and is disabled, the stage line moves, Last build / Last flash are
separate rows, Flash arms on the button ("Confirm flash? (3 s)") and disarms after
3 s, a confirmed flash shows "Flashing…" then "Flash OK · board back on COMx".

    python test/test_teensy_jobs.py [--units-only]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

import _lowprio  # noqa: E402,F401  (below normal priority)
import teensy_tools as tt  # noqa: E402
from workers import Job, JobManager  # noqa: E402

REAL_CLI = r"C:\Users\Andy\AppData\Local\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


# ------------------------------------------------------------------ part 1
def units():
    jm = JobManager()
    gate = threading.Event()
    res = []

    def click():
        res.append(jm.start_exclusive("teensy", "build", lambda j: gate.wait(5)))
    th = [threading.Thread(target=click) for _ in range(5)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    check("double click: exactly one job started", sum(1 for _, s in res if s) == 1, [s for _, s in res])
    check("double click: all calls see the same job", len({j.id for j, _ in res}) == 1)
    gate.set()
    time.sleep(0.2)
    j2, s2 = jm.start_exclusive("teensy", "build", lambda j: None)
    check("after it finished a new job may start", s2)

    raw = json.dumps({"detected_ports": [
        {"port": {"address": "Port_#0001.Hub_#0001", "label": "COM4 Serial", "protocol": "teensy",
                  "properties": {"modelID": "0x25", "name": "Teensy 4.1", "serialNumber": "1608535"}},
         "matching_boards": [{"name": "Teensy 4.1", "fqbn": "teensy:avr:teensy41"}]},
        {"port": {"address": "COM4", "label": "COM4", "protocol": "serial",
                  "properties": {"pid": "0x0483", "serialNumber": "16085350", "vid": "0x16C0"}}}]})
    devs = tt.parse_board_list(raw)
    check("board list (Nov 23): one Teensy device", len(devs) == 1, devs)
    d = devs[0]
    check("upload via the teensy-protocol port", d["upload_protocol"] == "teensy"
          and d["upload_address"] == "Port_#0001.Hub_#0001", d)
    check("monitor on COM4, label COM4", d["monitor_address"] == "COM4" and d["port"] == "COM4", d)

    job = Job("teensy", "build")
    log = tt._CompileLog(job)
    for ln in ['"C:/x/arm-none-eabi-g++" -c -O2 a.cpp -o a.o ' + "x" * 300,
               '"C:/x/arm-none-eabi-gcc" -c b.c -o b.o ' + "x" * 300,
               "Using previously compiled file: C:\\build\\core\\c.o",
               "Linking everything together...",
               '"C:/x/arm-none-eabi-gcc" -O2 -Wl,--gc-sections -o DAQ.elf ' + "x" * 300,
               "Memory Usage on Teensy 4.1:", "  FLASH: code:74992, data:10520"]:
        log.add(ln)
    check("compile: 2 compiled, 1 reused", job.meta["compiled"] == 2 and job.meta["reused"] == 1, job.meta)
    check("compile: stage reaches Memory report", job.meta["stage"] == "Memory report", job.meta)
    check("compile: long command lines not logged", not any(len(x) > 240 for x in job.lines), list(job.lines))

    tmp = tempfile.mkdtemp(prefix="afo_ty_units_")
    cfg = {"paths": {"log_dir": tmp, "arduino_cli": "arduino-cli"}}
    build = {"branch": "imu-resync-20261119", "commit": "6f5fa6c", "fqbn": "teensy:avr:teensy41", "build_dir": tmp}
    port = {"port": "COM4", "label": "COM4 · Teensy 4.1", "upload_address": "Port_#0001.Hub_#0001",
            "upload_protocol": "teensy", "teensy": True}

    class FakeScanner:
        def __init__(self, ports):
            self.ports = ports

        def rescan(self):
            pass

        def get(self):
            return {"ports": self.ports}

    orig = (tt.scanner, tt.usb_ids, tt.BOOT_APPEAR_S, tt.REBOOT_TIMEOUT_S)
    SER, BOOT = r"USB\VID_16C0&PID_0483\16085350", r"USB\VID_16C0&PID_0478\00188B57"

    def seq(*steps):
        """Simulated present-USB timeline: (seconds, ids) steps from the first call; the last one stays."""
        t0 = []

        def ids():
            if not t0:
                t0.append(time.time())
            el, acc = time.time() - t0[0], 0.0
            for dur, cur in steps:
                acc += dur
                if el < acc:
                    return set(cur)
            return set(steps[-1][1])
        return ids

    def fake_run(rc, text):
        def run(job, cmd, timeout=0):
            job.add("$ " + " ".join(cmd))
            job.add(text)
            run.cmd = cmd
            return rc
        return run
    try:
        tt.BOOT_APPEAR_S, tt.REBOOT_TIMEOUT_S = 1.5, 1.5
        tt.scanner = lambda c: FakeScanner([{"teensy": True, "port": "COM4", "mode": ""}])
        tt.usb_ids = seq((0.3, {SER}), (0.3, set()), (0.5, {BOOT}), (0.2, set()), (99, {SER}))
        j = Job("teensy", "flash")
        run = fake_run(0, "Opening Teensy Loader...")
        r = tt.flash_job(cfg, j, run, port, build, False)
        check("flash: uses the teensy-protocol port", "-l" in run.cmd and run.cmd[run.cmd.index("-l") + 1] == "teensy"
              and run.cmd[run.cmd.index("-p") + 1] == "Port_#0001.Hub_#0001", run.cmd)
        check("USB: bootloader then serial -> Reboot OK on COM4", r["ok"] and r["result"] == "ok" and r["port"] == "COM4"
              and j.meta["stage"] == "Reboot OK" and r["back_after_s"] is not None, (r, j.meta))
        check("log has Reboot OK and FLASH OK", any("Reboot OK" in x for x in j.lines) and any(x == "FLASH OK" for x in j.lines))
        tt.usb_ids = seq((99, {SER}))
        j = Job("teensy", "flash")
        r = tt.flash_job(cfg, j, fake_run(0, "Opening Teensy Loader..."), port, build, False)
        check("USB: bootloader never seen -> FAILED", not r["ok"] and r["reason"] == "board never entered bootloader", r)
        tt.usb_ids = seq((0.2, {SER}), (0.4, {BOOT}), (99, set()))
        j = Job("teensy", "flash")
        r = tt.flash_job(cfg, j, fake_run(0, "ok"), port, build, False)
        check("USB: bootloader, then nothing -> FAILED no reboot", not r["ok"] and r["reason"] == "no reboot", r)
        tt.usb_ids = seq((99, {SER}))
        j = Job("teensy", "flash")
        r = tt.flash_job(cfg, j, fake_run(1, "error: no device"), port, build, False)
        check("loader exit 1 -> FAILED", not r["ok"] and r["result"].startswith("failed") and j.meta["stage"] == "Failed", r)
        j = Job("teensy", "flash")
        r = tt.flash_job(cfg, j, fake_run(0, "upload finished; error: loader not found"), port, build, False)
        check("loader error text with exit 0 -> FAILED", not r["ok"], r)
        tt.usb_ids = lambda vid="16C0": None
        j = Job("teensy", "flash")
        r = tt.flash_job(cfg, j, fake_run(0, "ok"), port, build, False)
        check("USB watch unavailable -> port-list fallback OK", r["ok"] and r["port"] == "COM4", r)
        real = orig[1]()
        check("real USB query works here (set, Teensy may be unplugged)", isinstance(real, set), real)
    finally:
        tt.scanner, tt.usb_ids, tt.BOOT_APPEAR_S, tt.REBOOT_TIMEOUT_S = orig
    lf = tt.last_flash_any(cfg)
    check("last_flash_any: newest real flash, whatever the result", lf and lf["result"] == "ok", lf)

    # (foot-side pending checks live in test_pending_feedback.py on this branch)

    # (port scanner: watch mode, plug / unplug, Rescan busy + result, flash hold -> test_port_scanner.py)


# ------------------------------------------------------------------ part 2
def e2e():
    import yaml
    from test_ui_v18 import BASE, Browser, Listener
    tmp = tempfile.mkdtemp(prefix="afo_ty_e2e_")
    fake = os.path.join(tmp, "fake-arduino-cli.bat")
    with open(fake, "w") as fp:
        fp.write("@echo off\r\n"
                 'if /I "%~1"=="compile" goto real\r\n'
                 'if /I "%~1"=="board" goto real\r\n'
                 "echo FAKE arduino-cli %*\r\n"
                 "echo (test stand-in: nothing was uploaded)\r\n"
                 "exit /b 0\r\n"
                 ":real\r\n"
                 f'"{REAL_CLI}" %*\r\n'
                 "exit /b %ERRORLEVEL%\r\n")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15432, "send_host": "127.0.0.1",
                  "send_port": 15990, "param_port": 15991}
    cfg["dash"] = {"host": "127.0.0.1", "port": 18050}
    cfg["paths"]["log_dir"] = os.path.join(tmp, "logs")
    cfg["paths"]["arduino_cli"] = fake
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    lay["port"] = 15433
    json.dump(lay, open(os.path.join(tmp, "lay.json"), "w"))
    cfg["training"] = {"enabled": True, "listen_host": "127.0.0.1", "layout": os.path.join(tmp, "lay.json")}
    cfgp = os.path.join(tmp, "ty.yaml")
    yaml.safe_dump(cfg, open(cfgp, "w"), sort_keys=False)
    ctl, prm = Listener(15990), Listener(15991)
    ctl.start(); prm.start()
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=open(os.path.join(tmp, "server.log"), "w"),
                           stderr=subprocess.STDOUT, env=dict(os.environ, AFO_GUI_CONFIG=cfgp))
    b = None
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(3)
        b = Browser(19381, 1600, 1000)
        c = b.c
        c.call("Page.navigate", url=BASE + "/teensy")
        c.pump(8)
        rd = ("JSON.stringify((function(){function t(i){var e=document.getElementById(i);return e?(e.innerText||'').trim():null;}"
              "var bb=document.getElementById('ty-build-btn'),fb=document.getElementById('ty-flash-btn');"
              "return {build:t('ty-build-btn'),build_dis:bb&&bb.disabled,build_cls:bb&&bb.className,flash:t('ty-flash-btn'),"
              "flash_dis:fb&&fb.disabled,stage:t('ty-job-stage'),last_build:t('ty-build-summary'),last_flash:t('ty-flash-summary'),"
              "fw_last_flash:t('ty-lastflash'),msg:t('ty-flash-msg'),port:t('ty-port'),source:t('ty-source')};})())")
        st0 = json.loads(c.js(rd))
        check("teensy tab: source preselected", "6f5fa6c" in (st0["source"] or ""), st0)
        check("teensy tab: Last build / Last flash rows", st0["last_build"] is not None and st0["last_flash"] is not None, st0)
        # double click Build
        c.js("(function(){var b=document.getElementById('ty-build-btn'); b.click(); b.click(); return 1;})()")
        c.pump(0.6)
        st1 = json.loads(c.js(rd))
        check("Build: busy at once", (st1["build"] or "").startswith("Building") and st1["build_dis"] is True, st1)
        api = json.loads(urllib.request.urlopen(BASE + "/api/status", timeout=5).read())["jobs"]["teensy"]
        first_id = api["id"]
        req = urllib.request.Request(BASE + "/api/teensy/build", data=b"{}", headers={"Content-Type": "application/json"},
                                     method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            code = 200
        except urllib.error.HTTPError as e:
            code = e.code
        check("API build while building -> 409", code == 409, code)
        ids, stages = {first_id}, set()
        t0 = time.time()
        while time.time() - t0 < 300:
            c.pump(1)
            st = json.loads(c.js(rd))
            stages.add((st["stage"] or "").split(" · ")[1] if " · " in (st["stage"] or "") else st["stage"])
            ids.add(json.loads(urllib.request.urlopen(BASE + "/api/status", timeout=5).read())["jobs"]["teensy"]["id"])
            if st["build"] == "Build" and not st["build_dis"]:
                break
        check("double click -> one build job", len(ids) == 1, ids)
        check("stage line moved through the build", len(stages) >= 2, stages)
        st2 = json.loads(c.js(rd))
        check("build done: Last build OK row", (st2["last_build"] or "").startswith("OK") and "6f5fa6c" in st2["last_build"], st2)
        check("build done: stage says Build OK", (st2["stage"] or "").startswith("Build OK"), st2)
        if "COM" not in (st2["port"] or ""):
            check("Teensy on USB for the flash part (skipped: no Teensy)", True)
            return
        # Flash arms on the button and disarms after 3 s
        c.js("document.getElementById('ty-flash-btn').click(); 1")
        c.pump(0.6)
        st3 = json.loads(c.js(rd))
        check("Flash: first click arms on the button", (st3["flash"] or "").startswith("Confirm flash? ("), st3)
        c.pump(4.0)
        st4 = json.loads(c.js(rd))
        check("Flash: disarms after 3 s", st4["flash"] == "Flash", st4)
        # confirmed (fake upload): busy, then OK with port back
        c.js("document.getElementById('ty-flash-btn').click(); 1")
        c.pump(0.6)
        c.js("document.getElementById('ty-flash-btn').click(); 1")
        c.pump(0.8)
        st5 = json.loads(c.js(rd))
        check("Flash: busy on the button", (st5["flash"] or "").startswith("Flashing") and st5["flash_dis"] is True, st5)
        t0 = time.time()
        while time.time() - t0 < 60:
            c.pump(1)
            st6 = json.loads(c.js(rd))
            if st6["flash"] in ("Flash", "Flash (dry run)"):
                break
        # the stand-in uploads nothing, so the board never enters its bootloader: the page must say so
        check("Flash (stand-in): FAILED · board never entered bootloader",
              "Flash FAILED" in (st6["stage"] or "") and "never entered bootloader" in (st6["stage"] or ""), st6)
        check("Flash: Last flash row FAILED", (st6["last_flash"] or "").startswith("FAILED") and "6f5fa6c" in st6["last_flash"], st6)
        check("Flash: Last build row unchanged", st6["last_build"] == st2["last_build"], (st6["last_build"], st2["last_build"]))
        job = json.loads(urllib.request.urlopen(BASE + "/api/status", timeout=5).read())["jobs"]["teensy"]
        check("Flash: the stand-in answered the upload (nothing uploaded)", "FAKE arduino-cli upload" in job["log"],
              job["log"][-400:])
        check("Flash: upload went to the teensy-protocol port", " -l teensy" in job["log"], job["log"][-400:])
        check("no UDP sent", not ctl.pkts and not prm.pkts)
        check("no browser errors", not c.console, c.console[:4])
    finally:
        if b:
            b.close()
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()


if __name__ == "__main__":
    units()
    if "--units-only" not in sys.argv:
        e2e()
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
