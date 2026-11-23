"""A new run / restart clears every live buffer at once, without a reconnect or reload (Andy
16:08: after the Speedgoat reboot the page kept the old run's plots around 1000 s).

Fake streams only (no target; one short UDP burst on a test port for the 5433 worker):
- the live receiver (network): model time 990..1000 s, then a restart at t = 0 -> the display
  history and the SSE snapshots hold only the new run, with a new stream session;
- the main-process SSE window (state.DisplayWindow): the same with an unchanged session
  (live worker restarted too) -> no stale point in the 'full' message a new page gets;
- the training history (5433 worker): back by more than 1 s clears it;
- the browser engine: test/test_live_uplot_unit.py case 'restart' (plots emptied at once,
  the x range back to [0, 10]).

    python test/test_live_restart.py
"""
import json
import os
import queue as Q
import socket
import struct
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def receiver():
    import network as N
    snaps = []
    N.set_publish_hook(lambda s: snaps.append(json.loads(json.dumps(s, default=lambda o: None))))

    def feed(t0, n):
        for k in range(n):
            N._publish_sample({}, {"t": round(t0 + k * 0.01, 4), "torque": 1.0, "gait": 1.0}, live=True)
            if k % 10 == 0:
                N._last_emit_ts = 0.0          # let a snapshot out every 10 samples (no 20 Hz wait)
    feed(990.0, 1000)
    s_old = N.get_link_status()["session"]
    told = list(N._display.t)
    check("old run: display up to ~1000 s", told and told[-1] > 999, told[-1:])
    feed(0.0, 200)                              # restart at t = 0
    t = list(N._display.t)
    check("restart: the display history holds only the new run (< 3 s)", t and max(t) < 3 and min(t) >= 0, (t[:2], t[-2:]))
    check("restart: a new stream session", N.get_link_status()["session"] == s_old + 1, (s_old, N.get_link_status()["session"]))
    last = snaps[-1]
    check("restart: the next SSE snapshot carries only new points and the new session",
          last["t"] and max(last["t"]) < 3 and last["meta"]["session"] == s_old + 1, (last["t"][-2:], last["meta"]))


def sse_window():
    from state import DisplayWindow
    w = DisplayWindow()

    def delta(t0, n, sess):
        t = [round(t0 + k * 0.01, 4) for k in range(n)]
        return {"kind": "delta", "t": t, "torque": [1.0] * n, "meta": {"session": sess}}
    for k in range(20):
        w.apply(delta(990.0 + k * 0.5, 50, 1))
    check("SSE window: old run ~1000 s", w.t[-1] > 999, w.t[-1])
    w.apply(delta(0.0, 50, 1))                  # same session number (the live worker restarted)
    full = json.loads(w.full_text())
    check("SSE window: model time back > 1 s resets it (same session): no stale point for a new page",
          max(full["t"]) < 1 and min(full["t"]) >= 0, (full["t"][:2], full["t"][-2:]))


def training():
    import training_worker as TW
    check("training: a jump back of more than 1 s is a restart", TW.RESTART_JUMP_S == 1.0, TW.RESTART_JUMP_S)
    lay = json.load(open(os.path.join(HERE, "fixtures", "run12_console_udp_layout.json"), encoding="utf-8"))
    tmp = tempfile.mkdtemp(prefix="afo_trr_")
    lp = os.path.join(tmp, "lay.json")
    json.dump(dict(lay, port=15443), open(lp, "w"))
    out_q, req_q, resp_q, stop = Q.Queue(), Q.Queue(), Q.Queue(), threading.Event()
    threading.Thread(target=TW.worker_main, args=(lp, "127.0.0.1", out_q, req_q, resp_q, stop, tmp), daemon=True).start()
    time.sleep(0.5)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(t0, n):
        for k in range(n):
            row = [t0 + k * 0.01, 1.0, 70.0, 3.0, 5.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0]
            s.sendto(struct.pack("<12f", *row), ("127.0.0.1", 15443))
            time.sleep(0.005)
    send(1000.0, 30)
    time.sleep(0.15)
    send(0.5, 30)                               # restart: back by ~999.8 s
    time.sleep(0.2)
    req_q.put((1, "data", [["side"], 300.0, 1500]))
    rid, txt = resp_q.get(timeout=3)
    d = json.loads(txt)
    stop.set()
    check("training: history cleared on the restart (t_latest < 2 s, no point of the old run)",
          d.get("t_latest") is not None and d["t_latest"] < 2 and all(d["t_latest"] + x < 2 for x in d["series"]["side"]["t"]), d)


if __name__ == "__main__":
    receiver()
    sse_window()
    training()
    print("FAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
