"""PortScanner with a fake arduino-cli (watch mode, fallback poll mode, Rescan state).

Run: python test/test_port_scanner.py   (or python -m pytest test/test_port_scanner.py)

The fake CLI is a Python script; on Windows (OMEN) it cannot be started directly, so
the tests start it through this Python (subprocess.Popen shim, test only). Nothing
talks to a real board: no arduino-cli, no upload.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
try:
    import _lowprio  # noqa: E402,F401  (below normal priority)
except Exception:
    pass
import teensy_tools as tt  # noqa: E402

FAKE = os.path.join(HERE, "fakes", "fake_arduino_cli.py")
TEENSY = [
    {"port": {"address": "COM4", "label": "COM4", "protocol": "serial",
              "properties": {"pid": "0x0483", "vid": "0x16C0", "serialNumber": "16835980"}},
     "matching_boards": [{"name": "Teensy 4.1", "fqbn": "teensy:avr:teensy41"}]},
    {"port": {"address": "usb:0/140000/0/7", "label": "COM4 (Teensy 4.1) Serial", "protocol": "teensy",
              "properties": {"serialNumber": "1683598"}},
     "matching_boards": [{"name": "Teensy 4.1", "fqbn": "teensy:avr:teensy41"}]},
]


def wait(cond, timeout=8.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.05)
    return False


class _MP:
    """The part of pytest's monkeypatch these tests use (setenv / setattr, undone after)."""
    def __init__(self):
        self._undo = []

    def setenv(self, k, v):
        old = os.environ.get(k)
        os.environ[k] = v
        self._undo.append(lambda: os.environ.pop(k, None) if old is None else os.environ.__setitem__(k, old))

    def setattr(self, obj, name, val):
        old = getattr(obj, name)
        setattr(obj, name, val)
        self._undo.append(lambda: setattr(obj, name, old))

    def undo(self):
        while self._undo:
            self._undo.pop()()


def _shim_popen(mp):
    """Windows: start the fake CLI (a .py) through this Python."""
    if os.name != "nt":
        return
    real = subprocess.Popen

    class P(real):
        def __init__(self, args, *a, **k):
            if isinstance(args, (list, tuple)) and args and args[0] == FAKE:
                args = [sys.executable, FAKE] + list(args[1:])
            super().__init__(args, *a, **k)
    mp.setattr(subprocess, "Popen", P)


def _env(tmp, mp):
    ports = os.path.join(tmp, "ports.json")
    open(ports, "w").write("[]")
    mp.setenv("FAKE_PORTS", ports)
    _shim_popen(mp)
    made = []

    def make():
        sc = tt.PortScanner({"paths": {"arduino_cli": FAKE}})
        made.append(sc)
        return sc
    return ports, make, made


try:
    import pytest

    @pytest.fixture()
    def env(tmp_path, monkeypatch):
        mp = _MP()
        ports, make, made = _env(str(tmp_path), mp)
        yield _W(ports), make
        for sc in made:
            sc.close()
        mp.undo()

    @pytest.fixture()
    def mpatch():
        mp = _MP()
        yield mp
        mp.undo()
except ImportError:            # plain-script run (no pytest on the OMEN test Python)
    pytest = None


class _W:
    """ports.write_text like pathlib, on a plain path."""
    def __init__(self, path):
        self.path = path

    def write_text(self, t):
        open(self.path, "w").write(t)


def teensys(sc):
    return [p for p in sc.get()["ports"] if p.get("teensy")]


def test_watch_sees_plug_and_unplug_without_rescan(env):
    ports, make = env
    sc = make()
    assert sc.status()["scanning"]                      # first list pending
    assert wait(lambda: not sc.status()["scanning"])    # empty bus settles (<= SETTLE_S)
    assert sc.mode == "watch" and teensys(sc) == []
    t0 = time.time()
    ports.write_text(json.dumps(TEENSY))
    assert wait(lambda: teensys(sc), 3)
    assert time.time() - t0 < 2.0
    assert any(p.get("upload_protocol") == "teensy" for p in teensys(sc))
    assert len(teensys(sc)) == 1                        # serial + teensy-protocol entry: one row
    ports.write_text("[]")
    assert wait(lambda: not teensys(sc), 3)


def test_rescan_busy_then_done_and_no_double_scan(env):
    ports, make = env
    ports.write_text(json.dumps(TEENSY))
    sc = make()
    assert wait(lambda: not sc.status()["scanning"])
    first_proc = sc._proc
    sc.rescan()
    st = sc.status()
    assert st["scanning"] and st["rescan_at"]
    sc.rescan()                                         # second press while busy: ignored
    assert wait(lambda: not sc.status()["scanning"])
    st = sc.status()
    assert st["scanned"] >= st["rescan_at"] and teensys(sc)
    assert sc._proc is not first_proc                   # watcher was restarted once
    assert wait(lambda: sc._proc.poll() is None)
    assert first_proc.poll() is not None


def test_rescan_ignored_while_flashing(env):
    ports, make = env
    sc = make()
    assert wait(lambda: not sc.status()["scanning"])
    proc = sc._proc
    tt.FLASHING.set()
    try:
        sc.rescan()
        assert not sc.status()["scanning"] and sc._proc is proc and proc.poll() is None
    finally:
        tt.FLASHING.clear()


def test_falls_back_to_polling_when_watch_is_unsupported(env, mpatch):
    ports, make = env
    mpatch.setenv("FAKE_NOWATCH", "1")
    mpatch.setattr(tt.PortScanner, "FAST_S", 0.2)
    ports.write_text(json.dumps(TEENSY))
    sc = make()
    sc.touch()
    assert wait(lambda: sc.mode == "poll" and teensys(sc), 12)
    assert wait(lambda: not sc.status()["scanning"], 5)
    sc.rescan()
    assert sc.status()["scanning"]
    assert wait(lambda: not sc.status()["scanning"], 5)
    assert sc.status()["error"] is None


def test_scan_view_texts():
    from pages.teensy import _scan_view
    assert _scan_view({"scanning": True}, []) == ("Scanning…", True, "Scanning USB…")
    now = time.time()
    lbl, dis, txt = _scan_view({"scanning": False, "rescan_at": now, "scanned": now}, [{"teensy": True}])
    assert (lbl, dis) == ("Rescan", False) and txt.startswith("Rescanned ") and txt.endswith("1 Teensy found")
    assert _scan_view({"scanning": False, "rescan_at": now - 60, "scanned": now - 59}, [])[2] == ""


def test_board_list_one_row_per_board():
    """COM first, then serial number, then address: the teensy-protocol and serial entries of
    one board (serials 1608535 vs 16085350, or 1683598 vs 16835980) are one row."""
    devs = tt.parse_board_list(json.dumps({"detected_ports": TEENSY}))
    assert len(devs) == 1 and devs[0]["port"] == "COM4" and devs[0]["upload_protocol"] == "teensy", devs
    nov23 = [
        {"port": {"address": "Port_#0001.Hub_#0001", "label": "COM4 Serial", "protocol": "teensy",
                  "properties": {"modelID": "0x25", "name": "Teensy 4.1", "serialNumber": "1608535"}},
         "matching_boards": [{"name": "Teensy 4.1", "fqbn": "teensy:avr:teensy41"}]},
        {"port": {"address": "COM4", "label": "COM4", "protocol": "serial",
                  "properties": {"pid": "0x0483", "serialNumber": "16085350", "vid": "0x16C0"}}}]
    devs = tt.parse_board_list(json.dumps({"detected_ports": nov23}))
    assert len(devs) == 1 and devs[0]["port"] == "COM4", devs
    # serial entry reported first: same single row
    devs = tt.parse_board_list(json.dumps({"detected_ports": nov23[::-1]}))
    assert len(devs) == 1 and devs[0]["port"] == "COM4" and devs[0]["upload_protocol"] == "teensy", devs
    # the serial entry without VID / board (the duplicate COM4 row seen on Nov 23)
    novid = json.loads(json.dumps(nov23))
    novid[1]["port"]["properties"] = {"serialNumber": "16085350"}
    devs = tt.parse_board_list(json.dumps({"detected_ports": novid}))
    assert len(devs) == 1 and devs[0]["port"] == "COM4" and devs[0]["teensy"], devs
    # teensy-protocol entry whose label has no COM: merged by serial number (trailing 0)
    nocom = json.loads(json.dumps(novid))
    nocom[0]["port"]["label"] = "(Teensy 4.1) Serial"
    devs = tt.parse_board_list(json.dumps({"detected_ports": nocom}))
    assert len(devs) == 1 and devs[0]["port"] == "COM4" and devs[0]["upload_protocol"] == "teensy", devs
    # two boards stay two rows
    other = json.loads(json.dumps(TEENSY))
    other[0]["port"]["address"] = other[0]["port"]["label"] = "COM9"
    other[0]["port"]["properties"]["serialNumber"] = "17000010"
    other[1]["port"]["address"], other[1]["port"]["label"] = "usb:0/140000/0/9", "COM9 (Teensy 4.1) Serial"
    other[1]["port"]["properties"]["serialNumber"] = "1700001"
    devs = tt.parse_board_list(json.dumps({"detected_ports": TEENSY + other}))
    assert sorted(d["port"] for d in devs) == ["COM4", "COM9"], devs
    # bootloader (teensy protocol, no COM yet): keyed by serial number, one row
    boot = [{"port": {"address": "usb:0/140000/0/7", "label": "(Teensy 4.1) Bootloader", "protocol": "teensy",
                      "properties": {"serialNumber": "1683598"}},
             "matching_boards": [{"name": "Teensy 4.1", "fqbn": "teensy:avr:teensy41"}]}]
    devs = tt.parse_board_list(json.dumps({"detected_ports": boot}))
    assert len(devs) == 1 and devs[0].get("teensy"), devs


CHILD = r"""
import os, sys, time, subprocess
sys.path.insert(0, %(app)r); sys.path.insert(0, %(here)r)
import teensy_tools as tt
FAKE = %(fake)r
real = subprocess.Popen
class P(real):
    def __init__(self, args, *a, **k):
        if isinstance(args, (list, tuple)) and args and args[0] == FAKE:
            args = [sys.executable, FAKE] + list(args[1:])
        super().__init__(args, *a, **k)
subprocess.Popen = P
sc = tt.PortScanner({"paths": {"arduino_cli": FAKE}})
sc.touch()
t0 = time.time()
while sc._proc is None and time.time() - t0 < 10:
    time.sleep(0.05)
print(sc._proc.pid, flush=True)
time.sleep(60)
"""


def test_watcher_dies_with_the_app_on_hard_kill():
    """taskkill / TerminateProcess skips atexit: the watcher must still end (job object)."""
    if os.name != "nt":
        return
    import psutil
    tmp = tempfile.mkdtemp(prefix="afo_ps_kill_")
    ports = os.path.join(tmp, "ports.json")
    open(ports, "w").write("[]")
    code = CHILD % {"app": os.path.dirname(HERE), "here": HERE, "fake": FAKE}
    child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True,
                             env=dict(os.environ, FAKE_PORTS=ports, FAKE_MAX_S="90"))
    try:
        wpid = int(child.stdout.readline().strip())
        assert psutil.pid_exists(wpid) and "fake_arduino_cli" in " ".join(psutil.Process(wpid).cmdline())
    finally:
        child.kill()                                   # TerminateProcess: no atexit in the child
        child.wait(10)
    assert wait(lambda: not psutil.pid_exists(wpid), 5), f"watcher {wpid} outlived the app"


def _main():
    import inspect
    import traceback
    fails = []
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        mp, mp2 = _MP(), _MP()
        tmp = tempfile.mkdtemp(prefix="afo_ps_")
        made = []
        try:
            params = inspect.signature(fn).parameters
            kw = {}
            if "env" in params:
                ports, make, made = _env(tmp, mp)
                kw["env"] = (_W(ports), make)
            if "mpatch" in params:
                kw["mpatch"] = mp2
            fn(**kw)
            print("ok   " + name, flush=True)
        except Exception:
            print("FAIL " + name, flush=True)
            traceback.print_exc()
            fails.append(name)
        finally:
            for sc in made:
                sc.close()
            mp2.undo()
            mp.undo()
    print("\nFAILS:", fails)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    _main()
