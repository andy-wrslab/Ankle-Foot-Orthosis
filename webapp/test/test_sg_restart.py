"""Speedgoat restarted into its startup app (Nov 23, 15:24 power loss, 15:32 boot into the old
AFO): 5431 flows again with model time restarted near 0 and the AFO_r1 console echo (5433)
stays silent. Fake streams only, no sockets, no browser.

- 5431 model time jumps back near 0 and no r1 echo within 3 s -> amber "Speedgoat restarted:
  AFO_r1 not running (startup app)" with the restart time, last app AFO_r1 and the time the
  echo stopped in the popover detail; no red "No data" for the console;
- 5431 flowing, 5433 absent for > 3 s while the profile was r1 (after a server restart too);
- one WARNING line per detection; the 5434 / 5435 links stay frozen (nothing sent);
- any console echo (12 / 15 / 18 / 31 floats, run 12 included) clears or prevents it; a normal Start (echo back within 3 s) never flags.

    python test/test_sg_restart.py
"""
import logging
import os
import sys
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


class Cap(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, rec):
        if rec.levelno >= logging.WARNING:
            self.lines.append(rec.getMessage())


def streams(ctx, t_model, echo_cols, echo_age=0.05):
    """5431 flowing at model time t_model; 5433 with echo_cols floats (None = silent)."""
    ctx.live.st = {"live_seen": True, "age_s": 0.05}
    ctx.live.last_hb = time.monotonic()
    ctx.live.readback = lambda: {"t_model": t_model, "statusword": 0x0237}
    if echo_cols is None:
        ctx.training.st = {"packets_ok": 100, "age_s": 30.0, "columns": 18}
    else:
        ctx.training.st = {"packets_ok": 100, "age_s": echo_age, "columns": echo_cols}
    ctx.training.last_hb = time.monotonic()


def keys(st):
    return [i["key"] for i in st["issues"]]


def main():
    import status as ST
    from status import top_status
    from test_round5 import make_ctx
    cap = Cap()
    logging.getLogger("afo.status").addHandler(cap)
    ctx = make_ctx({"connected": True, "running": True, "app": "AFO_r1"})
    ST.RESTART_ECHO_WAIT_S = 0.3                 # test speed (live: 3 s)

    # normal running on run 14: 18-float echo, model time 500 s
    streams(ctx, 500.0, 18)
    st = top_status(ctx)
    check("running AFO_r1 with the echo: no restart issue", "speedgoat-restarted" not in keys(st), keys(st))

    # power loss: both silent (5431 stale -> readback empty)
    ctx.live.st = {"live_seen": True, "age_s": 60.0}
    ctx.live.readback = lambda: {}
    ctx.training.st = {"packets_ok": 100, "age_s": 60.0, "columns": 18}
    st = top_status(ctx)
    check("both silent (power off): not the startup-app issue", "speedgoat-restarted" not in keys(st), keys(st))

    # boot into the startup app: 5431 back at model time 2 s, no 5433
    streams(ctx, 2.0, None)
    st = top_status(ctx)
    check("right after the restart (< 3 s): not flagged yet", "speedgoat-restarted" not in keys(st), keys(st))
    time.sleep(0.4)
    streams(ctx, 2.4, None)
    st = top_status(ctx)
    iss = next((i for i in st["issues"] if i["key"] == "speedgoat-restarted"), None)
    check("restart + no r1 echo: amber 'Speedgoat restarted: AFO_r1 not running (startup app)' on the button",
          st["text"] == "Speedgoat restarted: AFO_r1 not running (startup app)" and st["level"] == "amber", (st["text"], keys(st)))
    check("no red 'No data' for the console while flagged", not any(i["key"] == "no-data" and i.get("stream") == "console"
                                                                   for i in st["issues"]), keys(st))
    check("popover detail: restart time, last app AFO_r1, echo stopped at",
          iss and "restarted near 0 at" in iss["detail"] and "last known app AFO_r1" in iss["detail"]
          and "console echo stopped at" in iss["detail"] and iss["restart_at"] and iss["echo_stopped_at"], iss)
    warns = [l for l in cap.lines if "startup app" in l]
    check("one WARNING line on detection", len(warns) == 1, cap.lines)
    top_status(ctx)
    top_status(ctx)
    check("no repeated WARNING while it stays", len([l for l in cap.lines if "startup app" in l]) == 1, cap.lines)

    # settings links frozen: nothing sent
    import udp_settings as U
    sent = []
    lk = U.SettingsLink({"udp": {"send_host": "127.0.0.1", "session_port": 15434}},
                        lambda: ({"side": 0.0, "settings_seq": 1.0, "gyro_cal_request": 0.0}, 30.0, 18),
                        sender=lambda d, a: sent.append(d), start_thread=False)
    lk.state = {"side": 0.0}
    lk.tick()
    r = lk.press("side", 1.0)
    check("5434 link frozen while the echo is gone: press refused, nothing sent", lk.frozen and not r["ok"] and not sent, (r, sent))

    # AFO_r1 loaded and started: the 31-float echo comes back -> cleared
    streams(ctx, 0.5, 31)
    st = top_status(ctx)
    check("r1 echo back (31 floats): cleared", "speedgoat-restarted" not in keys(st), keys(st))
    streams(ctx, 3.0, 31)
    st = top_status(ctx)
    check("stays cleared while the echo runs", "speedgoat-restarted" not in keys(st), keys(st))

    # run 12 (12-float echo): an echo too, so never "Speedgoat restarted", and it clears the flag
    ctx12 = make_ctx({"connected": True, "running": True, "app": "AFO_r1"})
    streams(ctx12, 300.0, 18)
    top_status(ctx12)
    streams(ctx12, 1.0, 12)
    top_status(ctx12)
    time.sleep(0.4)
    streams(ctx12, 1.4, 12)
    st = top_status(ctx12)
    check("run 12 (12-float echo) after a restart: not flagged", "speedgoat-restarted" not in keys(st), keys(st))
    ctx12.session.last_model = "AFO_r1"
    streams(ctx12, 2.0, None)
    top_status(ctx12)
    time.sleep(0.4)
    streams(ctx12, 2.4, None)
    st = top_status(ctx12)
    check("echo gone > 3 s: flagged", "speedgoat-restarted" in keys(st), keys(st))
    streams(ctx12, 2.6, 12)
    st = top_status(ctx12)
    check("a 12-float echo clears it", "speedgoat-restarted" not in keys(st), keys(st))

    # a normal page Start: model time back to 0 and the echo returns within the wait -> never flagged
    streams(ctx, 400.0, 18)
    top_status(ctx)
    streams(ctx, 0.1, None)
    top_status(ctx)
    streams(ctx, 0.2, 18)
    st = top_status(ctx)
    time.sleep(0.4)
    streams(ctx, 0.7, 18)
    st = top_status(ctx)
    check("normal Start (echo back at once): never flagged", "speedgoat-restarted" not in keys(st), keys(st))

    # after a server restart: no history, last connect was AFO_r1, 5431 flowing, 5433 absent > 3 s
    ctx2 = make_ctx({"connected": False, "running": False})
    ctx2.session.last_model = "AFO_r1"
    streams(ctx2, 50.0, None)
    st = top_status(ctx2)
    check("server restart, 5433 absent just now: not yet", "speedgoat-restarted" not in keys(st), keys(st))
    time.sleep(0.4)
    streams(ctx2, 50.4, None)
    st = top_status(ctx2)
    check("5431 flowing + 5433 absent > 3 s, last app AFO_r1: flagged (not connected too)",
          "speedgoat-restarted" in keys(st), (st["text"], keys(st)))
    # never for a model that is not r1
    ctx3 = make_ctx({"connected": False, "running": False})
    ctx3.session.last_model = None
    streams(ctx3, 50.0, None)
    top_status(ctx3)
    time.sleep(0.4)
    streams(ctx3, 50.4, None)
    st = top_status(ctx3)
    check("old AFO only (never r1): no startup-app issue", "speedgoat-restarted" not in keys(st), keys(st))
    net = open(os.path.join(APP, "network.py"), encoding="utf-8").read()
    check("5431 readback carries the model time", '_readback["t_model"] = t_val' in net)


if __name__ == "__main__":
    main()
    print("FAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
