"""Teensy page with the target off: the selected branch's details fill from the local repo.

Part 1 (units): the branch list is stale-while-revalidate (a cached list is returned at
once and refreshed in the background), a fetch rebuilds it instead of clearing it.
Part 2 (browser, app on 127.0.0.1:18050, test ports only, no target, no Teensy needed):
- /teensy opened directly: a branch is selected at once (layout from the warm cache),
  Commit / Compared with main / Board settings are filled within 3 s, and the Flash
  hint never says "Pick a firmware branch." while a branch is selected;
- Live first, then the Teensy tab: the details are there within 1.5 s.
Only read-only git (and the page's usual `git fetch`) runs; nothing is built or flashed.

    python test/test_teensy_offline.py
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import _lowprio  # noqa: E402,F401  (below normal priority)
import teensy_tools as tt  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def units():
    calls = []
    real = tt.sources

    def slow(cfg):
        calls.append(time.time())
        time.sleep(0.5)
        return {"branches": [{"name": f"b{len(calls)}"}], "worktree": {"dirty": []}, "newest": f"b{len(calls)}"}
    tt.sources = slow
    tt._sources_cache.clear()
    try:
        t0 = time.time()
        v1 = tt.sources_cached({})
        check("first read waits for git", time.time() - t0 >= 0.45 and v1["newest"] == "b1", v1)
        tt._sources_cache["t"] -= 60                    # make it stale
        t0 = time.time()
        v2 = tt.sources_cached({})
        check("stale list returned at once (< 50 ms)", time.time() - t0 < 0.05 and v2["newest"] == "b1", time.time() - t0)
        time.sleep(0.8)
        check("... and refreshed in the background", tt.sources_peek()["newest"] == "b2" and len(calls) == 2, len(calls))
        tt._sources_cache["t"] -= 60
        for _ in range(5):
            tt.sources_cached({})                       # many readers: one rebuild
        time.sleep(0.8)
        check("one background rebuild for many readers", len(calls) == 3, len(calls))
        # a fetch rebuilds the list (the page never meets an empty cache afterwards)
        rf = tt.fetch
        tt.fetch = lambda cfg: {"ok": True}
        try:
            tt._fetch_state["time"] = 0
            tt.fetch_in_background({}, min_age_s=0)
            check("during the fetch the old list is still served", tt.sources_peek() is not None)
            time.sleep(1.0)
            check("after the fetch: list rebuilt, not cleared", tt.sources_peek()["newest"] == "b4", tt.sources_peek())
        finally:
            tt.fetch = rf
    finally:
        tt.sources = real
        tt._sources_cache.clear()


P = """JSON.stringify({src:(document.querySelector('#ty-source') || {}).textContent.slice(0, 60),
 commit:(document.getElementById('ty-commit')||{}).textContent, vs:(document.getElementById('ty-vsmain')||{}).textContent,
 board:(document.getElementById('ty-board')||{}).textContent, msg:(document.getElementById('ty-flash-msg')||{}).textContent})"""


def e2e():
    from test_ui_v18 import BASE, Browser
    tmp = tempfile.mkdtemp(prefix="afo_tyoff_")
    cfg = yaml.safe_load(open(os.path.join(APP, "config.yaml"), encoding="utf-8"))
    cfg["udp"] = {"listen_host": "127.0.0.1", "listen_port": 15432, "send_host": "127.0.0.1",
                  "send_port": 15990, "param_port": 15991}
    cfg["dash"] = {"host": "127.0.0.1", "port": 18050}
    cfg["paths"]["log_dir"] = os.path.join(tmp, "logs")
    cfg["training"] = {"enabled": False}
    cp = os.path.join(tmp, "ty.yaml")
    yaml.safe_dump(cfg, open(cp, "w"), sort_keys=False)
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=open(os.path.join(tmp, "s.log"), "w"),
                           stderr=subprocess.STDOUT, env=dict(os.environ, AFO_GUI_CONFIG=cp))
    b = None
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(3)                                   # warm-up read at app start
        b = Browser(19473, 1600, 1000)
        c = b.c
        c.call("Page.navigate", url=BASE + "/daq")
        t0, seen, filled_at, first_src = time.time(), [], None, None
        while time.time() - t0 < 6:
            c.pump(0.25)
            v = json.loads(c.js(P))
            seen.append((round(time.time() - t0, 2), v))
            if first_src is None and "·" in v["src"]:
                first_src = time.time() - t0
            if filled_at is None and v["commit"] not in ("", "–") and v["vs"] not in ("", "–") and v["board"] not in ("", "–"):
                filled_at = time.time() - t0
        check("direct /daq: branch selected within 1.5 s", first_src is not None and first_src < 1.5, (first_src, seen[:3]))
        check("direct /daq: Commit, Compared with main, Board settings within 3 s",
              filled_at is not None and filled_at < 3.0, (filled_at, seen[-1]))
        bad = [s for s in seen if "·" in s[1]["src"] and "Pick a firmware branch" in s[1]["msg"]]
        check("never 'Pick a firmware branch.' while a branch is selected", not bad, bad[:2])
        last = seen[-1][1]
        check("details: commit has the short sha, vs main and board text", len(last["commit"]) > 8
              and ("main" in last["vs"]) and ("USB" in last["board"] or "CPU" in last["board"]), last)

        # Live first, then the Teensy tab
        c.call("Page.navigate", url=BASE + "/live")
        c.pump(6)
        c.js("document.querySelector('a[data-nav=\"daq\"]').click(); 1")
        t0, filled_at = time.time(), None
        while time.time() - t0 < 4:
            c.pump(0.2)
            v = json.loads(c.js(P))
            if v["commit"] not in ("", "–") and v["board"] not in ("", "–"):
                filled_at = time.time() - t0
                break
        check("Live -> Teensy tab: details within 1.5 s", filled_at is not None and filled_at < 1.5, (filled_at, v))
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
    e2e()
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)
