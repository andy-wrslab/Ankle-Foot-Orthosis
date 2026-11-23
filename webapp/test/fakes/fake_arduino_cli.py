#!/usr/bin/env python3
"""Fake arduino-cli for the port-scanner tests: `board list [--watch] --format json|jsonmini`.
Ports come from the JSON file in $FAKE_PORTS (a list of board-list items); the watch
mode re-reads it every 0.1 s and prints add/remove events like arduino-cli 1.x.
$FAKE_NOWATCH=1 makes --watch fail like an old arduino-cli; $FAKE_DELAY adds start-up time;
the watch mode ends after $FAKE_MAX_S (default 120 s) so it never outlives a test run."""
import json, os, sys, time

args = sys.argv[1:]
time.sleep(float(os.environ.get("FAKE_DELAY", "0")))


def load():
    try:
        return json.load(open(os.environ["FAKE_PORTS"]))
    except Exception:
        return []


if args[:2] != ["board", "list"]:
    sys.exit(2)
if "--watch" not in args:
    print(json.dumps({"detected_ports": load()}))
    sys.exit(0)
if os.environ.get("FAKE_NOWATCH"):
    print("Error: unknown flag: --watch", file=sys.stderr)
    sys.exit(1)
seen = {}
t_end = time.time() + float(os.environ.get("FAKE_MAX_S", "120"))   # never outlive a test run
while time.time() < t_end:
    now = {(it["port"]["address"], it["port"]["protocol"]): it for it in load()}
    for k in [k for k in seen if k not in now]:
        print(json.dumps({"eventType": "remove", "port": seen.pop(k)["port"]}), flush=True)
    for k, it in now.items():
        if k not in seen:
            seen[k] = it
            print(json.dumps({"eventType": "add", **it}), flush=True)
    time.sleep(0.1)
