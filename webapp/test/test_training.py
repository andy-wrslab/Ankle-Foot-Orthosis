"""Console-packet receiver test (UDP 5433 '<12f', localhost only, test port 15433).

Replays console packets at 100 Hz with injected faults: wrong length, NaN,
side = 2, assist_mode = 5, a repeated model time, a 60 ms time gap and a model
restart (time jumps back). Checks the receiver's counters and latest values,
then that commands.CommandState takes the model's latched commands (cmd_*) as
the authoritative toggle state and flags a mismatch with the last-sent state.
Exit code 1 on any unexpected count.
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _lowprio  # noqa: E402,F401  (below normal priority)
import json
import os
import socket
import struct
import sys
import tempfile
import time

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
os.chdir(APP)

from workers import TrainingSupervisor  # noqa: E402
from commands import CommandState  # noqa: E402
from training_worker import load_layout  # noqa: E402

PORT = 15433


def main():
    # the 12-float run-12 layout, pinned (config/ moved on to 18, then 31 floats)
    lay, names = load_layout(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "run12_console_udp_layout.json"))
    lay["port"] = PORT
    tmpd = tempfile.mkdtemp(prefix="afo_console_")
    lp = os.path.join(tmpd, "layout.json")
    json.dump(lay, open(lp, "w"))
    cfg = {"training": {"enabled": True, "listen_host": "127.0.0.1", "layout": lp}}
    sup = TrainingSupervisor(cfg, APP, tmpd)
    sup.start()
    time.sleep(3)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fmt = struct.Struct(lay["format"])
    assert fmt.size == 48, fmt.size

    def row(t, **kw):
        r = dict(t_model=t, side=0.0, weight_kg=72.5, assist_mode=3.0, fixed_k_pct=5.0, cmd_motor=1.0,
                 cmd_assist=0.0, cmd_k=1.0, cmd_calibrate_pressure=0.0, cmd_reset_sv=0.0, imu_ok=1.0,
                 imu_bad_count=3.0)
        r.update(kw)
        return fmt.pack(*[r[n] for n in names])

    def send(b):
        s.sendto(b, ("127.0.0.1", PORT))

    expect = {"bad_length": 0, "non_finite_packets": 0, "bad_value": 0, "counter_gaps": 0, "lost_packets": 0,
              "dup_or_reordered": 0, "model_restarts": 0, "valid": 0}
    t = 100.0
    for k in range(600):
        t = round(t + 0.01, 4)
        if k == 100:
            send(b"\x00" * 50); expect["bad_length"] += 1
        if k == 150:
            send(row(t, weight_kg=float("nan"))); expect["non_finite_packets"] += 1
        if k == 200:
            send(row(t, side=2.0)); expect["bad_value"] += 1
        if k == 250:
            send(row(t, assist_mode=5.0)); expect["bad_value"] += 1
        if k == 300:
            t = round(t + 0.05, 4)                     # 5 packets never sent
            expect["counter_gaps"] += 1; expect["lost_packets"] += 5
        if k == 400:
            t = 3.0                                    # model restarted
            expect["model_restarts"] += 1
        send(row(t, side=-1.0 if k < 50 else 0.0)); expect["valid"] += 1
        if k == 350:
            send(row(t)); expect["dup_or_reordered"] += 1
        time.sleep(0.01)
    time.sleep(1.5)
    st = sup.get_status()
    got = {k: st.get(k) for k in expect if k != "valid"}
    got["valid"] = st.get("packets_ok")
    res = {"expected": expect, "got": got, "bad_value_by_col": st.get("bad_value_by_col"),
           "latest": st.get("latest")}

    sent = []
    cs = CommandState({}, os.path.join(tmpd, "last_command.json"), lambda *a, **k: sent.append(a),
                      lambda *a, **k: None, lambda: sup.latest(max_age_s=0.5))
    cs.toggles.update({"motor": 1, "assist": 1, "k": 1})      # console thinks assist is ON; model has OFF
    t_end = time.time() + 3.0
    while time.time() < t_end:
        t = round(t + 0.01, 4)
        send(row(t))
        time.sleep(0.01)
        cs.mismatches()
    view = cs.view()
    res["rate_hz_while_sending"] = sup.get_status().get("rate_hz")
    res["toggles_from_model"] = view["toggles"]
    res["mismatch_after_3_s"] = view["mismatch"]
    res["model_params_echo"] = {k2: v for k2, v in view["model_params"].items() if v is not None}
    time.sleep(1.0)
    res["latest_after_silence_0_5"] = sup.latest(max_age_s=0.5)
    sup.shutdown()
    fails = [k for k in expect if res["got"].get(k) != expect[k]]
    if [m["name"] for m in res["mismatch_after_3_s"]] != ["assist"]:
        fails.append("mismatch")
    if res["toggles_from_model"]["assist"] != {"value": 0, "source": "model"}:
        fails.append("toggle_source")
    if res["latest_after_silence_0_5"]:
        fails.append("stale_not_dropped")
    if res["model_params_echo"]:
        fails.append("param_echo_should_be_empty")
    res["FAILS"] = fails
    os.makedirs(os.path.join(APP, "test", "e2e"), exist_ok=True)
    json.dump(res, open(os.path.join(APP, "test", "e2e", "console_results.json"), "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
