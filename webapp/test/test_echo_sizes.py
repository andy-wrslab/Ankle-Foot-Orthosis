"""One shared set of 5433 echo lengths (echo_sizes.py) and the cloud-suite bug it fixes:
status.R1_ECHO_COLS lacked 44 / 45, so a healthy run-16b / 16c device read "Speedgoat
restarted: AFO_r1 not running (startup app)" ~3 s after load and after every Start, never
cleared, and hid IMU / STO / Ready. Fake streams only (one short UDP burst on a test port).

- echo_sizes: 12 / 15 / 18 / 31 / 44 / 45 from the column tails; every module uses it
  (no literal echo-length tuples left in status / session / udp_settings / console_api);
- the receiver accepts exactly those lengths;
- for EVERY length: a healthy device never shows the restart issue (also after a model-time
  restart = a Start), 'Ready' shows, and IMU fault / Drive fault (STO) still show when real;
- the status button text wraps instead of being cut (CSS), checked by size arithmetic.

    python test/test_echo_sizes.py
"""
import json
import os
import queue as Q
import re
import socket
import struct
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def shared():
    import echo_sizes as ES
    import status
    import training_worker as TW
    import udp_settings as U
    check("echo_sizes: 12 / 15 / 18 / 31 / 44 / 45 / 47 (run 16g)", ES.ECHO_SIZES == (12, 15, 18, 31, 44, 45, 47), ES.ECHO_SIZES)
    check("status uses the shared lengths (44 and 45 included)", status.R1_ECHO_COLS is ES.ECHO_SIZES
          and 44 in status.R1_ECHO_COLS and 45 in status.R1_ECHO_COLS, status.R1_ECHO_COLS)
    check("receiver tails = echo_sizes tails", TW.RUN16C_TAIL is ES.RUN16C_TAIL and TW.RUN14_TAIL is ES.RUN14_TAIL)
    check("links: 5434 / 5435 / 5436 active from 18 / 31 / 44 (echo_sizes)", (U.SettingsLink.ECHO_N, U.AdvLink.ECHO_N,
          U.GuardLink.ECHO_N) == (ES.UDP_SETTINGS_MIN, ES.ADV_UDP_MIN, ES.GUARD_UDP_MIN) == (18, 31, 44))
    lit = re.compile(r"\(12, 15, 18|\b(?:>=|==|<|>|!=) ?(?:15|18|31|44|45)\b")
    left = {}
    for f in ("status.py", "session.py", "udp_settings.py", os.path.join("pages", "console_api.py"), "training_worker.py"):
        src = open(os.path.join(APP, f), encoding="utf-8").read()
        hits = [m.group(0) for m in lit.finditer(src)]
        if hits:
            left[f] = hits
    check("no literal echo-length checks left outside echo_sizes.py", not left, left)


def receiver():
    import echo_sizes as ES
    import training_worker as TW
    lay = json.load(open(os.path.join(APP, "config", "console_udp_layout.json"), encoding="utf-8"))
    tmp = tempfile.mkdtemp(prefix="afo_es_")
    lp = os.path.join(tmp, "lay.json")
    json.dump(dict(lay, port=15462), open(lp, "w"))
    out_q, stop = Q.Queue(), threading.Event()
    threading.Thread(target=TW.worker_main, args=(lp, "127.0.0.1", out_q, Q.Queue(), Q.Queue(), stop, tmp), daemon=True).start()
    time.sleep(0.5)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    got = {}

    def last_hb():
        last = None
        while True:
            try:
                kind, pl = out_q.get_nowait()
            except Q.Empty:
                return last
            if kind == "hb":
                last = pl
    for n in ES.ECHO_SIZES + (13, 46):
        for k in range(8):
            row = ([500.0 + 10 * n + k * 0.01, 1.0, 70.0, 3.0, 5.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0] + [0.5] * 40)[:n]
            s.sendto(struct.pack(f"<{n}f", *row), ("127.0.0.1", 15462))
            time.sleep(0.01)
        time.sleep(0.12)
        hb = last_hb() or {}
        got[n] = (hb.get("columns"), hb.get("bad_length"))
    stop.set()
    check("receiver: every echo_sizes length accepted", all(got[n][0] == n for n in ES.ECHO_SIZES), got)
    check("receiver: other lengths (13, 46) dropped as bad length", got[46][1] and got[46][1] >= 8 and got[13][1] >= 8, got)


def streams(ctx, t_model, cols, sw=0x0237, imu_ok=1.0):
    ctx.live.st = {"live_seen": True, "age_s": 0.05}
    ctx.live.last_hb = time.monotonic()
    ctx.live.readback = lambda: {"t_model": t_model, "statusword": sw}
    if cols is None:
        ctx.training.st = {"packets_ok": 100, "age_s": 30.0, "columns": 45}
    else:
        ctx.training.st = {"packets_ok": 100, "age_s": 0.05, "columns": cols}
    ctx.training._latest["imu_ok"] = imu_ok
    ctx.training.last_hb = time.monotonic()


def status_every_size():
    import echo_sizes as ES
    import status as ST
    from status import top_status
    from test_round5 import confirm, make_ctx
    ST.RESTART_ECHO_WAIT_S = 0.3                    # test speed (live: 3 s)
    for n in ES.ECHO_SIZES:
        ctx = make_ctx({"connected": False, "running": False},
                       echo={"side": 1, "weight_kg": 72.5, "assist_mode": 1, "fixed_k_pct": 5, "cmd_motor": 0,
                             "cmd_assist": 0, "cmd_k": 1, "imu_ok": 1.0, "bif_mass_kg": 72.5})
        confirm(ctx)
        ctx.session.last_model = "AFO_r1"
        streams(ctx, 300.0, n)
        top_status(ctx)
        time.sleep(0.4)
        streams(ctx, 300.4, n)
        st = top_status(ctx)
        keys = [i["key"] for i in st["issues"]]
        check(f"{n} floats: healthy device, never 'Speedgoat restarted'", "speedgoat-restarted" not in keys, (st["text"], keys))
        check(f"{n} floats: the button shows 'Ready' (green)", st["text"] == "Ready" and st["level"] == "green", (st["text"], keys))
        # a Start: model time back to ~0, the same echo length keeps coming
        streams(ctx, 0.1, n)
        top_status(ctx)
        time.sleep(0.4)
        streams(ctx, 0.5, n)
        st = top_status(ctx)
        check(f"{n} floats: after a Start (model time back to 0) still no restart issue", "speedgoat-restarted"
              not in [i["key"] for i in st["issues"]], (st["text"], st["issues"]))
        # real problems still show (not hidden behind a false restart)
        streams(ctx, 1.0, n, sw=0x0628)
        st = top_status(ctx)
        check(f"{n} floats: STO / drive fault shows", st["text"] == "Drive fault (STO)" and st["level"] == "red", st["text"])
        streams(ctx, 1.2, n, imu_ok=0.0)
        top_status(ctx)
        ctx.session._imu_not_ok_since -= 0.3
        st = top_status(ctx)
        check(f"{n} floats: IMU fault shows", any(i["key"] == "imu-fault" for i in st["issues"]), st["issues"])
    # the startup app (5431 flowing, no echo at all) is still caught
    ctx = make_ctx({"connected": False, "running": False})
    ctx.session.last_model = "AFO_r1"
    streams(ctx, 50.0, None)
    top_status(ctx)
    time.sleep(0.4)
    streams(ctx, 50.4, None)
    st = top_status(ctx)
    check("no echo at all (startup app): still 'Speedgoat restarted'", st["text"] == ST.STARTUP_APP_TEXT, st["text"])
    streams(ctx, 50.6, 45)
    st = top_status(ctx)
    check("a 45-float echo clears it", st["text"] != ST.STARTUP_APP_TEXT, st["text"])


def css_wrap():
    """No browser: the status text must wrap (never ellipsis / clip) and two lines of the
    longest status text must fit the bar at 820 / 1024 / 1280 px. Arithmetic with a generous
    0.62 em average glyph width for Inter at 13 px."""
    import status as ST
    css = open(os.path.join(APP, "assets", "afo-ui.css"), encoding="utf-8").read()
    rule = re.findall(r"\.status-btn \.sb-txt \{([^}]*)\}", css)
    base = rule[0] if rule else ""
    check("status text wraps: white-space normal, no ellipsis / hidden overflow", "white-space: normal" in base
          and "ellipsis" not in base and "overflow: hidden" not in base, base)
    check("status button grows in height (height auto, min-height)", ".status-btn, .topbar .status-btn { height: auto; min-height: var(--btn-md);" in css)
    bar = int(re.search(r"--topbar-h: (\d+)px", css).group(1))
    longest = max([ST.STARTUP_APP_TEXT, "Cable jam: torque cut", "Drive fault (STO)", "Confirm foot side"], key=len)
    text_w = len(longest) * 13 * 0.62
    for vw, maxw in ((820, 240), (1024, 240), (1280, 240)):
        lines = -(-text_w // maxw)
        h = lines * 13 * 1.25 + 4
        check(f"{vw} px: '{longest[:28]}…' fits in {int(lines)} lines ({h:.0f} px <= {bar} px bar)", lines <= 2 and h <= bar,
              (text_w, maxw, lines, h))


if __name__ == "__main__":
    shared()
    receiver()
    status_every_size()
    css_wrap()
    print("FAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
