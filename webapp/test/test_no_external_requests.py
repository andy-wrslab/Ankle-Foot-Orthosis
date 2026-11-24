"""No request leaves the PC: every page, tab and popover loads only from 127.0.0.1 / localhost.

App on 127.0.0.1:18050 (test ports, replay senders so the plots draw), the installed
Chrome headless with the CDP Network domain on. Visits Live (Gait, Sensors, Training),
Trials, DAQ (each of its tabs) and the status / Advanced / side popovers,
and lists every request whose host is not 127.0.0.1 / localhost (fails on any).
Also checks that the bundled fonts load from /assets/fonts/ (Inter, JetBrains Mono)
and that nothing 404s.

    python test/test_no_external_requests.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import replay_senders  # noqa: E402  (also lowers this process's priority)
from test_ui_v18 import BASE, Browser, Listener, api  # noqa: E402

FAILS = []
LOCAL = {"127.0.0.1", "localhost", "[::1]", "::1"}


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


class Rec:
    """Records every CDP event (the shared helper keeps only console errors)."""
    def __init__(self, c):
        self.c, self.req, self.resp = c, [], {}

    def _take(self, msg):
        m = msg.get("method")
        if m == "Network.requestWillBeSent":
            p = msg["params"]
            self.req.append((p["requestId"], p["request"]["url"]))
        elif m == "Network.responseReceived":
            p = msg["params"]
            self.resp[p["requestId"]] = p["response"]["status"]
        elif m in ("Runtime.exceptionThrown",):
            self.c.console.append("exception: " + str(msg["params"]["exceptionDetails"].get("text"))[:200])

    def call(self, method, **params):
        c = self.c
        c.n += 1
        my = c.n
        c.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            msg = json.loads(c.ws.recv())
            self._take(msg)
            if msg.get("id") == my:
                return msg.get("result", {})

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def pump(self, seconds):
        c = self.c
        end = time.time() + seconds
        c.ws.settimeout(0.3)
        while time.time() < end:
            try:
                self._take(json.loads(c.ws.recv()))
            except Exception:
                continue
        c.ws.settimeout(20)


def host(url):
    if url.startswith(("data:", "blob:", "about:", "chrome-extension:", "devtools:")):
        return None
    return urllib.parse.urlsplit(url).hostname


def main():
    tmp = tempfile.mkdtemp(prefix="afo_noext_")
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
    cp = os.path.join(tmp, "ne.yaml")
    yaml.safe_dump(cfg, open(cp, "w"), sort_keys=False)
    prof = os.path.join(APP, "data", "session_profiles.json")
    backup = None
    if os.path.exists(prof):
        backup = prof + ".ne.bak"
        shutil.copy2(prof, backup)
        os.remove(prof)
    ctl, prm = Listener(15990), Listener(15991)
    ctl.start(); prm.start()
    srv = subprocess.Popen([sys.executable, "-u", "app.py"], cwd=APP, stdout=open(os.path.join(tmp, "s.log"), "w"),
                           stderr=subprocess.STDOUT, env=dict(os.environ, AFO_GUI_CONFIG=cp))
    senders = replay_senders.start(15432, 15433, side=0.0)
    b = None
    try:
        for _ in range(90):
            try:
                urllib.request.urlopen(BASE + "/", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(2)
        api("/api/console/sid", {"sid": "S96"})
        b = Browser(19476, 1600, 1000)
        r = Rec(b.c)
        r.call("Network.enable")
        r.call("Network.setCacheDisabled", cacheDisabled=True)
        visited = []

        def go(path, *clicks, wait=3.0):
            r.call("Page.navigate", url=BASE + path)
            r.pump(4.0)
            for sel in clicks:
                r.js("(function(){var e=document.querySelector(%s); if(e){e.click();} return 1;})()" % json.dumps(sel))
                r.pump(wait)
                r.js("document.body.click(); 1")
            visited.append(path + (" " + " ".join(clicks) if clicks else ""))

        go("/live", "#pgGait", "#pgSensors", "#pgTraining", "#statusBtn", "#advBtn", "#sideChip")
        go("/trials")
        go("/daq", '[id*="ty-tab-btn"][id*="code"]', '[id*="ty-tab-btn"][id*="changes"]',
           '[id*="ty-tab-btn"][id*="serial"]', '[id*="ty-tab-btn"][id*="build"]')
        fonts = r.js("document.fonts.ready.then(function(){var o=[]; document.fonts.forEach(function(f){"
                     "o.push([f.family.replace(/\"/g,''), f.weight, f.status]);}); return o;})")
        ext = sorted({u for _, u in r.req if host(u) not in LOCAL and host(u) is not None})
        print(f"requests: {len(r.req)} total, {len(ext)} external", flush=True)
        for u in ext:
            print("   external:", u)
        check("no request to a host other than 127.0.0.1 / localhost", not ext, ext[:10])
        font_reqs = [(u, r.resp.get(i)) for i, u in r.req if "/assets/fonts/" in u]
        check("bundled fonts requested from /assets/fonts/ and served (200)",
              font_reqs and all(s == 200 for _, s in font_reqs), font_reqs)
        loaded = {(f, w) for f, w, s in (fonts or []) if s == "loaded"}
        check("Inter loaded", any(f == "Inter" for f, _ in loaded), fonts)
        check("JetBrains Mono loaded", any(f == "JetBrains Mono" for f, _ in loaded), fonts)
        bad = sorted({(u, r.resp.get(i)) for i, u in r.req if (r.resp.get(i) or 200) >= 400})
        check("no 4xx / 5xx responses", not bad, bad[:6])
        check("no browser exceptions", not b.c.console, b.c.console[:4])
        print("visited:", visited)
    finally:
        senders.set()
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
