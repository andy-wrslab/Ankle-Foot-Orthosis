"""Training-stream receiver test (localhost only, test port 15433).

Replays layout-v1 packets (50 x float32) at 100 Hz with injected faults: wrong
length, wrong layout_version, NaN values, NaN counter, counter gaps, a duplicate
and a 24-bit counter wrap. Checks the receiver's counters and latest values,
then that commands.CommandState takes the model's latched commands (cmd_*) as
the authoritative toggle state and flags a mismatch with the last-sent state.
"""
import json
import math
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

PORT = 15433


def main():
    lay = json.load(open(os.path.join(APP, "config", "training_udp_layout.json")))
    lay["port"] = PORT
    tmpd = tempfile.mkdtemp(prefix="afo_train_")
    lp = os.path.join(tmpd, "layout.json")
    json.dump(lay, open(lp, "w"))
    names = [c["n"] for c in lay["columns"]]
    n = len(names)
    cfg = {"training": {"enabled": True, "listen_host": "127.0.0.1", "layout": lp}}
    sup = TrainingSupervisor(cfg, APP, tmpd)
    sup.start()
    time.sleep(3)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fmt = struct.Struct(lay["format"])

    def row(k, counter, **kw):
        r = [0.0] * n
        r[0] = 10.0 + k / 100.0
        r[1] = 1.0
        r[2] = float(counter)
        r[names.index("sv")] = 1.1
        r[names.index("side")] = 0.0
        r[names.index("weight_kg")] = 72.5
        r[names.index("assist_mode")] = 3.0
        r[names.index("fixed_k_pct")] = 5.0
        r[names.index("cmd_motor")] = 1.0
        r[names.index("cmd_assist")] = 0.0
        r[names.index("cmd_k")] = 1.0
        r[names.index("param_epsilon_up")] = 0.05
        for key, v in kw.items():
            r[names.index(key)] = v
        return r

    expect = {"bad_length": 0, "bad_version": 0, "non_finite_packets": 0, "counter_gaps": 0,
              "lost_packets": 0, "dup_or_reordered": 0, "valid": 0}
    counter = (1 << 24) - 250       # wraps during the run
    for k in range(600):
        counter = (counter + 1) % (1 << 24)
        if k == 100:
            s.sendto(b"\x00" * 100, ("127.0.0.1", PORT)); expect["bad_length"] += 1
        if k == 150:
            s.sendto(fmt.pack(*row(k, counter, layout_version=2.0)), ("127.0.0.1", PORT)); expect["bad_version"] += 1
            counter = (counter + 1) % (1 << 24)
            expect["counter_gaps"] += 1; expect["lost_packets"] += 1   # that counter value never arrives valid
        if k == 200:
            s.sendto(fmt.pack(*row(k, counter, sv=float("nan"))), ("127.0.0.1", PORT))
            expect["non_finite_packets"] += 1; expect["valid"] += 1    # kept (value -> None)
            counter = (counter + 1) % (1 << 24)
        if k == 250:
            s.sendto(fmt.pack(*row(k, float("nan"))), ("127.0.0.1", PORT))
            expect["non_finite_packets"] += 1                         # dropped (no counter)
        if k == 300:
            counter = (counter + 6) % (1 << 24)
            expect["counter_gaps"] += 1; expect["lost_packets"] += 6
        pkt = fmt.pack(*row(k, counter))
        s.sendto(pkt, ("127.0.0.1", PORT)); expect["valid"] += 1
        if k == 350:
            s.sendto(pkt, ("127.0.0.1", PORT)); expect["dup_or_reordered"] += 1
        time.sleep(0.01)
    time.sleep(1.5)
    st = sup.get_status()
    res = {"expected": expect,
           "got": {k: st.get(k) for k in ("packets_ok", "bad_length", "bad_version", "non_finite_packets",
                                         "counter_gaps", "lost_packets", "dup_or_reordered", "non_finite_by_col")},
           "rate_hz_while_sending": None, "latest_sample": {k: st.get("latest", {}).get(k) for k in
                                                           ("side", "weight_kg", "assist_mode", "fixed_k_pct",
                                                            "cmd_motor", "cmd_k", "sv")}}
    # keep streaming a little to measure rate and test command readback
    sent = []
    cs = CommandState({}, os.path.join(tmpd, "last_command.json"), lambda *a, **k: sent.append(a),
                      lambda *a, **k: None, lambda: sup.latest(max_age_s=2.0))
    cs.toggles.update({"motor": 1, "assist": 1, "k": 1})      # console thinks assist is ON
    t_end = time.time() + 3.0
    k = 600
    while time.time() < t_end:
        counter = (counter + 1) % (1 << 24)
        s.sendto(fmt.pack(*row(k, counter)), ("127.0.0.1", PORT))
        k += 1
        time.sleep(0.01)
        if abs(time.time() - (t_end - 1.5)) < 0.01:
            cs.mismatches()
    view = cs.view()
    res["rate_hz_while_sending"] = sup.get_status().get("rate_hz")
    res["toggles_from_model"] = view["toggles"]
    res["model_params"] = {k2: v for k2, v in view["model_params"].items() if v is not None}
    res["mismatch_after_1_5_s"] = view["mismatch"]
    d = sup.data(["sv", "cmd_motor"], 5.0)
    res["history_points_5s"] = {k2: len(v["t"]) for k2, v in (d or {}).get("series", {}).items()}
    sup.shutdown()
    print(json.dumps(res, indent=1, default=str))
    json.dump(res, open(os.path.join(APP, "test", "e2e", "training_results.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
