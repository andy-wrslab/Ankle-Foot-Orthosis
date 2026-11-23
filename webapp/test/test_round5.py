"""Offline tests (no MATLAB, no target): top-bar status, settings-on-target table,
file-log run list / default names / export guards (design round 5 + v17).

    python test/test_round5.py
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _lowprio  # noqa: E402,F401  (below normal priority)
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

import session as S   # noqa: E402
from status import top_status   # noqa: E402
from filelog import FileLogRuns  # noqa: E402


class Sup:
    def __init__(self, st, latest=None):
        self.st, self.last_hb = st, time.monotonic()
        self._latest = latest or {}

    def get_status(self):
        return dict(self.st)

    def latest(self, max_age_s=1.0):
        a = self.st.get("age_s")
        return dict(self._latest) if a is not None and a <= max_age_s else {}


class Jobs:
    def __init__(self):
        self.busy = {}
        self.started = []

    def running(self, kind):
        return self.busy.get(kind)

    def start(self, kind, title, fn):
        self.started.append((kind, title))
        return type("J", (), {"id": len(self.started), "title": title})()


class Job:
    def __init__(self, title):
        self.title = title


class Cmd:
    def __init__(self):
        self.toggles = {"motor": 1, "assist": 1, "k": 1}
        self.params = {"epsilon_up": 0.05}
        self.param_echo = {"epsilon_up": "param_epsilon_up"}

    def view(self):
        return {"toggles": {"motor": {"value": 1}}}


class RC:
    def __init__(self, status):
        self.status = status
        self.calls = []

    def run_action(self, *a, _meta=None):
        self.calls.append((a, _meta))
        return type("J", (), {"id": 99})()


def make_ctx(rc_status, live_age=0.05, tr_age=0.05, echo=None, tmp=None, bif=True):
    tmp = tmp or tempfile.mkdtemp()
    ctx = type("Ctx", (), {})()
    ctx.app_dir = tmp
    ctx.cfg = {"paths": {"log_dir": tmp, "afo_root": tmp}, "session": {}}
    ctx.runctl = RC(rc_status)
    ctx.jobs = Jobs()
    ctx.live = Sup({"live_seen": live_age is not None, "age_s": live_age})
    ctx.training = Sup({"packets_ok": 100 if tr_age is not None else 0, "age_s": tr_age}, echo)
    ctx.commands = Cmd()
    # Bi-LSTM state from a fake Signals stream: IMU ready + valid (so "Ready" means nothing open);
    # bif=None leaves it unknown
    vals = {"bif_bias_ready": 1.0, "bif_valid": 1.0} if bif else {}
    ctx.matlab = type("ML", (), {"snapshot": lambda self, kind, names, *a, **k: {"values": vals}})()
    ctx.session = S.SessionSetup(ctx)
    return ctx


def confirm(ctx, side=1, weight=72.5):
    ctx.session.set_sid("S90")
    ctx.session.adopted_echo = True          # operator values entered after the device state was adopted
    ctx.session.values.update(side=side, weight=weight, mode=1, k_percent=5)
    ctx.session.side_confirmed = {"sid": "S90", "side": side, "at": time.time()}


ECHO = {"side": 1, "weight_kg": 72.5, "assist_mode": 1, "fixed_k_pct": 5, "cmd_motor": 1, "cmd_assist": 1, "cmd_k": 1,
        "param_epsilon_up": 0.05}


def main():
    r = {}
    run = {"connected": True, "running": True, "app": "AFO_r1"}
    # 1 Ready: AFO_r1 running, both streams, echo matches
    c = make_ctx(run, echo=ECHO); confirm(c); c.session.refresh_readback()
    r["1_ready"] = top_status(c)["text"]
    # 1b same, but no Bi-LSTM state (no Signals, 12-float console): still Ready (green),
    # the unknown state is only a grey note in the popover
    c = make_ctx(run, echo=ECHO, bif=False); confirm(c); c.session.refresh_readback()
    s = top_status(c); r["1b_bif_unknown"] = (s["text"], s["level"], s.get("notes"))
    # 2 mass differs (amber)
    c = make_ctx(run, echo=dict(ECHO, weight_kg=55.0)); confirm(c); c.session.refresh_readback()
    s = top_status(c); r["2_mass"] = (s["text"], s["level"])
    # 2b server (re)start onto a 15-float echo: side adopted from the device; col 2 weight (55,
    # possibly the build default) is NOT adopted as a mass (14:26 live); nothing is sent
    c = make_ctx(run, echo=dict(ECHO, weight_kg=55.0)); c.session.set_sid("S90")
    c.session.values.update(side=1, weight=72.5, mode=1, k_percent=5)
    n0 = len(c.jobs.started)
    c.session.refresh_readback()
    sets = [t for _, t in c.jobs.started[n0:] if t.startswith("set ")]
    r["2b_adopt"] = (c.session.values.get("weight"), c.session.values.get("side"), len(sets))
    # 3 side differs (red) beats mass (amber)
    c = make_ctx(run, echo=dict(ECHO, side=0, weight_kg=55.0)); confirm(c); c.session.refresh_readback()
    s = top_status(c); r["3_side"] = (s["text"], s["level"], [i["text"] for i in s["issues"]])
    # 4 no data on the training stream (red), with age
    c = make_ctx(run, tr_age=3.3, echo=ECHO); confirm(c); c.session.refresh_readback()
    s = top_status(c); r["4_nodata"] = (s["text"], s["level"])
    # 5 confirm foot side (amber): side not confirmed
    c = make_ctx(run, echo=ECHO); c.session.set_sid("S90"); c.session.adopted_echo = True; c.session.refresh_readback()
    s = top_status(c); r["5_confirm"] = (s["text"], s["level"])
    # 5b server (re)start with the device on RIGHT: the page inherits it (Andy 14:01), no "Confirm"
    c = make_ctx(run, echo=ECHO); c.session.set_sid("S90"); c.session.refresh_readback()
    s = top_status(c); r["5b_adopt_side"] = (s["text"], c.session.side_chip()["text"])
    # 6 connected, app stopped
    c = make_ctx({"connected": True, "running": False, "app": "AFO_r1"}, live_age=None, tr_age=None); confirm(c)
    c.session.readback.update(side=1); c.session.readback_src.update(side="getparam")
    r["6_connected"] = top_status(c)["text"]
    # 7 not connected, no data
    c = make_ctx({}, live_age=None, tr_age=None)
    r["7_not_connected"] = top_status(c)["text"]
    # 8 busy verb wins over red
    c = make_ctx(run, tr_age=5.0, echo=ECHO); confirm(c); c.jobs.busy["rc"] = Job("run control: start")
    r["8_busy"] = top_status(c)["text"]
    # 9 old model AFO: echo ignored (getparam for all); training stream not required if never seen
    c = make_ctx({"connected": True, "running": True, "app": "AFO"}, tr_age=None, echo=ECHO); confirm(c)
    c.session.refresh_readback()
    r["9_afo_echo_sources"] = {k: c.session.readback_src.get(k) for k in ("side", "weight")}
    r["9_afo_getparam_job"] = c.jobs.started[-1][1] if c.jobs.started else None
    c.session.readback.update(side=1, weight=72.5); c.session.readback_src.update(side="getparam", weight="getparam")
    r["9_afo_status"] = top_status(c)["text"]
    # 10 settings table (AFO_r1)
    c = make_ctx(run, echo=dict(ECHO, cmd_assist=0)); confirm(c); c.session.refresh_readback()
    r["10_table"] = [(x["name"], x["entered"], x["target"], x["source"], x["match"]) for x in c.session.target_table()]
    r["10_status"] = top_status(c)["text"]
    # 11 echo stops -> echo values dropped (not kept as stale confirmation)
    c.training.st["age_s"] = 9.0
    c.session.refresh_readback()
    r["11_after_echo_lost"] = {k: c.session.readback.get(k) for k in ("side", "weight")}

    # ---- file-log runs
    tmp = tempfile.mkdtemp()
    c = make_ctx({"connected": True, "running": True, "app": "AFO_r1"}, tmp=tmp)
    with open(os.path.join(tmp, "session_setup.csv"), "w", encoding="utf-8") as fp:
        fp.write("time,sid,action,detail\n2026-11-19 09:00:00,,participant,S47\n2026-11-19 13:00:00,S47,participant,S48\n")
    fl = FileLogRuns(c)
    fl.cache = {"columns": ["Application", "StartDate", "Duration", "Size"], "at": time.time(), "err": None,
                "rows": [{"row": 1, "Application": "AFO_r1", "StartDate": "2026-11-19 10:00:00", "Duration": 600, "Size": 1e8},
                         {"row": 2, "Application": "AFO_r1", "StartDate": "2026-11-19 10:10:05", "Duration": 300, "Size": 5e7},
                         {"row": 3, "Application": "AFO_r1", "StartDate": "2026-11-19 14:00:00", "Duration": 60, "Size": 1e7}]}
    d = fl.runs()
    r["12_runs"] = [(x["id"], x["participant"], x["recording"], x["split_of"], x["exported"]) for x in d["runs"]]
    r["12_key"] = d["key_column"]
    r["13_default_name"] = fl.default_name(d["runs"][2])
    r["14_export_recording"] = fl.export(d["runs"][0]["id"])[1:]
    # mark run 1 exported -> needs replace
    folder = os.path.join(tmp, "afo_mat", "S47_20261119")
    os.makedirs(folder)
    open(os.path.join(folder, "S47_20261119_1000_T01.mat"), "w").write("x")
    json.dump({"sid": "S47", "file_log_run": {"id": "2026-11-19 10:00:00", "start": "2026-11-19 10:00:00"}},
              open(os.path.join(folder, "S47_20261119_1000_T01.json"), "w"))
    r["15_exported_flag"] = [x["exported"] for x in fl.runs()["runs"]]
    r["16_export_again_no_replace"] = fl.export("2026-11-19 10:00:00")[1:]
    job, msg, code = fl.export("2026-11-19 10:00:00", replace=True)
    r["17_replace"] = (msg, code, sorted(os.listdir(folder)))
    r["17_save_args"] = c.runctl.calls[-1][0]
    r["17_meta_run"] = c.runctl.calls[-1][1]["file_log_run"]

    # Andy 16:11-16:15: the status button is live / device only (no MATLAB link or run-control
    # states, never 'X differs': the page shows the device's values)
    expect = {
        "1_ready": "Ready", "1b_bif_unknown": ("Ready", "green", ["Bi-LSTM state unknown: needs the 15-float console packet"]), "2_mass": ("Ready", "green"), "2b_adopt": (72.5, 1, 0), "4_nodata": ("No data 3.3 s", "red"),
        "5_confirm": ("Confirm foot side", "amber"), "5b_adopt_side": ("Ready", "Side: RIGHT"), "6_connected": "No data", "7_not_connected": "No data",
        "8_busy": "No data 5.0 s", "9_afo_status": "Ready", "10_status": "Ready",
        "11_after_echo_lost": {"side": None, "weight": None}, "12_key": "StartDate",
    }
    fails = {k: (r.get(k), v) for k, v in expect.items() if (tuple(r[k]) if isinstance(r.get(k), list) else r.get(k)) != v}
    if r["3_side"][:2] != ("Foot side differs", "red"):
        fails["3_side"] = r["3_side"]
    if [x[3] for x in r["12_runs"]] != [None, "2026-11-19 10:00:00", None] or r["12_runs"][0][2] is not True:
        fails["12_runs"] = r["12_runs"]
    if [x[1] for x in r["12_runs"]] != ["S48", "S47", "S47"]:
        fails["12_participants"] = r["12_runs"]
    if r["14_export_recording"][1] != 409 or r["16_export_again_no_replace"][1] != 409 or r["17_replace"][1] != 200:
        fails["export_guards"] = (r["14_export_recording"], r["16_export_again_no_replace"], r["17_replace"])
    if not any(".bak-" in f for f in r["17_replace"][2]):
        fails["17_bak"] = r["17_replace"][2]
    r["FAILS"] = fails
    print(json.dumps(r, indent=1, default=str))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
