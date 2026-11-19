"""MATLAB engine worker check: start, call afo_rc('status') (does NOT connect to the
target), check the timeout/restart path, shut down. Run: python test_matlab_worker.py"""
import json
import os
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
os.chdir(APP)

from workers import MatlabWorker  # noqa: E402


def main():
    w = MatlabWorker([os.path.join(APP, "matlab")], os.path.join(APP, "logs"))
    out = {}
    t0 = time.time()
    try:
        s = w.call("afo_rc", "status", timeout=60)
        out["first_call_s"] = round(time.time() - t0, 1)
        out["status"] = json.loads(s)
        t1 = time.time()
        w.call("afo_rc", "status", timeout=30)
        out["second_call_s"] = round(time.time() - t1, 2)
        # a call that cannot finish in time must kill and restart the engine
        try:
            w.call("afo_sleep", 8.0, timeout=2)
            out["timeout_path"] = "no timeout?!"
        except TimeoutError as exc:
            out["timeout_path"] = str(exc)
        t2 = time.time()
        s = w.call("afo_rc", "status", timeout=180)
        out["after_restart_call_s"] = round(time.time() - t2, 1)
        out["after_restart_ok"] = json.loads(s).get("ok")
    except Exception as exc:
        out["error"] = repr(exc)
    finally:
        w.shutdown()
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
