"""Assist fade-in rule (Andy Nov 24 16:00-16:04), offline. The cases are also written to
test/fixtures/assist_ramp_cases.json as test vectors for the model (16g).

    python test/test_assist_ramp.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
from assist_ramp_ref import AssistRamp  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def run(step, events):
    """events: ('on'|'off') or ('hs', level); returns the applied level after each event."""
    r, out = AssistRamp(step), []
    for e in events:
        out.append(r.set_assist(e == "on") if e in ("on", "off") else r.heel_strike(e[1]))
    return out


CASES = [
    # name, step, events, expected applied after each event
    ("RL starts high and stays at 8, step 1: 1..8, done at stride 8, then 8",
     1.0, ["on"] + [("hs", 8)] * 9, [0, 1, 2, 3, 4, 5, 6, 7, 8, 8]),
    ("RL starts at 8 and drops to 4 by stride 4: 1, 2, 3, 4, done (live level, not the start level)",
     1.0, ["on", ("hs", 8), ("hs", 7), ("hs", 5), ("hs", 4), ("hs", 6), ("hs", 9)], [0, 1, 2, 3, 4, 6, 9]),
    ("after the ramp, an RL jump goes straight through (3 -> 9)",
     1.0, ["on", ("hs", 3), ("hs", 3), ("hs", 3), ("hs", 9)], [0, 1, 2, 3, 9]),
    ("Fixed K 5, step 0.5: 0.5 ... 5 over 10 strides",
     0.5, ["on"] + [("hs", 5)] * 11, [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5]),
    ("Assist off mid-ramp: 0 at once; on again restarts from the first step",
     1.0, ["on", ("hs", 8), ("hs", 8), ("hs", 8), "off", ("hs", 8), "on", ("hs", 8), ("hs", 8)], [0, 1, 2, 3, 0, 0, 0, 1, 2]),
    ("Assist off after the ramp, then on: a new ramp",
     1.0, ["on", ("hs", 2), ("hs", 2), ("hs", 5), "off", "on", ("hs", 5), ("hs", 5)], [0, 1, 2, 5, 0, 0, 1, 2]),
    ("step 0 = ramp off: the level at the first heel strike",
     0.0, ["on", ("hs", 8), ("hs", 6)], [0, 8, 6]),
    ("level 0 at the start (RL 0): done at the first stride, applied 0, then follows RL",
     1.0, ["on", ("hs", 0), ("hs", 7)], [0, 0, 7]),
    ("level below the step (K 0.5, step 1): 0.5 at the first stride, done",
     1.0, ["on", ("hs", 0.5), ("hs", 0.5)], [0, 0.5, 0.5]),
    ("mode switch mid-ramp (RL 8 -> Fixed K 2): min with the new level, done when the cap meets it",
     1.0, ["on", ("hs", 8), ("hs", 2), ("hs", 2)], [0, 1, 2, 2]),
    ("heel strikes while Assist is off: always 0",
     1.0, [("hs", 8), ("hs", 8)], [0, 0]),
]


def main():
    for name, step, ev, want in CASES:
        got = run(step, ev)
        check(name, [round(x, 6) for x in got] == [float(w) for w in want], (got, want))
    # never a rise of more than one step per stride during a ramp
    import random
    rnd = random.Random(7)
    worst = 0.0
    for _ in range(300):
        step = rnd.choice([0.5, 1.0])
        r, prev = AssistRamp(step), 0.0
        r.set_assist(True)
        for _k in range(25):
            was_ramping = r.active
            a = r.heel_strike(rnd.choice([0, 1, 2.5, 4, 6, 8, 10]))
            if was_ramping and a > prev:
                worst = max(worst, (a - prev) / step)
            prev = a
    check("random RL levels: during a ramp the applied level never rises by more than one step per stride", worst <= 1.0 + 1e-9, worst)
    fx = os.path.join(HERE, "fixtures", "assist_ramp_cases.json")
    os.makedirs(os.path.dirname(fx), exist_ok=True)
    with open(fx, "w", encoding="utf-8") as f:
        json.dump([{"name": n, "step": s, "events": [e if isinstance(e, str) else ["hs", e[1]] for e in ev], "applied": w}
                   for n, s, ev, w in CASES], f, indent=1)
    check("test vectors written for the model (test/fixtures/assist_ramp_cases.json)", os.path.isfile(fx))


main()
print("\nFAILS:", FAILS)
sys.exit(1 if FAILS else 0)
