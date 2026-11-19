"""Run-control live test (approved by Andy with STO engaged; no torque/assist/motor).

connect -> status -> save the current file log -> stop (verify) -> [save again if
the first save failed] -> start (verify running, EtherCAT OP, UDP back ~1 kHz)
-> disconnect. Stops and reports at the first failure of stop/start/EtherCAT.
Uses the app's MatlabWorker + matlab/afo_rc.m, and the tee summary for UDP.
"""
import json
import os
import sys
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
os.chdir(APP)
from workers import MatlabWorker  # noqa: E402

TEE_SUMMARY = r"C:\Users\Andy\Desktop\AFO\_claude_live\tee_summary.txt"
OUTDIR = r"C:\Users\Andy\Desktop\AFO\_claude_live"
log = []


def step(name, res):
    log.append({"t": time.strftime("%H:%M:%S"), "step": name, "res": res})
    print(time.strftime("%H:%M:%S"), name, json.dumps(res)[:600], flush=True)


def udp_rate():
    try:
        last = open(TEE_SUMMARY, encoding="utf-8").read().strip().splitlines()[-1]
        return last[:60]
    except Exception as exc:
        return repr(exc)


def call(w, *args, timeout=120):
    return json.loads(w.call("afo_rc", *args, timeout=timeout))


def main():
    w = MatlabWorker([os.path.join(APP, "matlab")], os.path.join(APP, "logs"))
    try:
        r = call(w, "connect")
        step("connect", r)
        if not r.get("connected"):
            return
        step("status", call(w, "status"))
        step("udp before", udp_rate())
        f1 = os.path.join(OUTDIR, time.strftime("runcontrol_test_%H%M%S.mat"))
        saved = call(w, "save", f1, timeout=600)
        step("save (running)", saved)
        r = call(w, "stop", timeout=120)
        step("stop", r)
        if not r.get("ok") or r.get("running"):
            step("ABORT", "failed to stop - not continuing")
            return
        time.sleep(3)
        step("udp while stopped", udp_rate())
        if not saved.get("ok"):
            f2 = os.path.join(OUTDIR, time.strftime("runcontrol_test_%H%M%S.mat"))
            step("save (stopped)", call(w, "save", f2, timeout=600))
        r = call(w, "start", timeout=120)
        step("start", r)
        if not r.get("ok") or not r.get("running"):
            step("ABORT", "start did not verify")
            return
        ok_ecat = False
        for _ in range(10):
            time.sleep(2)
            s = call(w, "status")
            if s.get("ethercat_state") == 8:
                ok_ecat = True
                break
        step("status after start", s)
        step("ethercat OP", ok_ecat)
        time.sleep(11)
        step("udp after start", udp_rate())
    finally:
        try:
            step("disconnect", call(w, "disconnect"))
        except Exception as exc:
            step("disconnect error", repr(exc))
        w.shutdown()
        json.dump(log, open(os.path.join(OUTDIR, time.strftime("runcontrol_test_log_%H%M%S.json")), "w"), indent=1)


if __name__ == "__main__":
    main()
