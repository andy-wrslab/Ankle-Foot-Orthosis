"""Headless Chrome capture through the DevTools protocol (localhost only).

Starts a throw-away headless Chrome (own profile folder, own debug port), opens
the dashboard, and after it has rendered live data saves screenshots of both
swipe pages and returns the lamp texts, parse-failure count and every console
error the page logged. Never touches the user's own Chrome.
"""
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class _CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=20, suppress_origin=True)
        self.n = 0
        self.console = []

    def call(self, method, **params):
        self.n += 1
        my = self.n
        self.ws.send(json.dumps({"id": my, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Runtime.consoleAPICalled":
                p = msg["params"]
                if p.get("type") in ("error", "warning"):
                    txt = " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", []))
                    self.console.append(f"{p['type']}: {txt[:200]}")
            elif msg.get("method") == "Runtime.exceptionThrown":
                d = msg["params"]["exceptionDetails"]
                self.console.append("exception: " + str(d.get("exception", {}).get("description", d.get("text")))[:200])
            if msg.get("id") == my:
                return msg.get("result", {})

    def pump(self, seconds):
        """Keep reading events (console errors) for a while."""
        end = time.time() + seconds
        self.ws.settimeout(0.5)
        while time.time() < end:
            try:
                msg = json.loads(self.ws.recv())
            except Exception:
                continue
            if msg.get("method") == "Runtime.consoleAPICalled":
                p = msg["params"]
                if p.get("type") in ("error", "warning"):
                    txt = " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", []))
                    self.console.append(f"{p['type']}: {txt[:200]}")
            elif msg.get("method") == "Runtime.exceptionThrown":
                d = msg["params"]["exceptionDetails"]
                self.console.append("exception: " + str(d.get("exception", {}).get("description", d.get("text")))[:200])
        self.ws.settimeout(20)

    def shot(self, path):
        r = self.call("Page.captureScreenshot", format="png")
        with open(path, "wb") as fp:
            fp.write(base64.b64decode(r["data"]))

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True)
        return r.get("result", {}).get("value")


def capture(url, out_prefix, debug_port=19222, settle_s=6.0, width=1600, height=1300):
    prof = tempfile.mkdtemp(prefix="afo_cdp_")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={debug_port}", f"--user-data-dir={prof}",
         "--no-first-run", "--disable-extensions", "--hide-scrollbars", f"--window-size={width},{height}",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    result = {"url": url}
    try:
        targets = None
        for _ in range(40):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json", timeout=2))
                if any(t.get("type") == "page" for t in targets):
                    break
            except Exception:
                pass
            time.sleep(0.25)
        page = next(t for t in targets if t.get("type") == "page")
        cdp = _CDP(page["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.call("Page.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=url)
        cdp.pump(settle_s)
        p1 = out_prefix + "_page1.png"
        cdp.shot(p1)
        cdp.js("var s=document.querySelector('.swipe-container'); if(s){s.scrollLeft=s.clientWidth;} 1")
        cdp.pump(1.5)
        p2 = out_prefix + "_page2.png"
        cdp.shot(p2)
        result["screenshots"] = [p1, p2]
        result["lamps"] = cdp.js(
            "Array.from(document.querySelectorAll('.health-lamp')).map(e=>e.className.replace('health-lamp ','')+' | '+e.textContent)"
        )
        result["parse_failures"] = cdp.js("window._afoParseFailures === undefined ? null : window._afoParseFailures")
        result["imu_trace_points"] = cdp.js(
            "(function(){var g=document.getElementById('imu'); if(!g||!g.querySelector('.js-plotly-plot')) return null;"
            "var d=g.querySelector('.js-plotly-plot').data; return d ? d.map(t=>t.y?t.y.length:0) : null;})()"
        )
        result["console_errors"] = cdp.console[:20]
        result["console_error_count"] = len(cdp.console)
        cdp.ws.close()
    except Exception as exc:
        result["error"] = repr(exc)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    return result


if __name__ == "__main__":
    import sys
    print(json.dumps(capture(sys.argv[1], sys.argv[2]), indent=1))
