"""Trials: runs-on-target limit (FileLogMaxRuns) from a fake run list (no MATLAB, no target).

    python test/test_filelog_limit.py
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)
import _lowprio  # noqa: E402,F401
from filelog import FileLogRuns  # noqa: E402
from test_round5 import make_ctx  # noqa: E402

FAILS = []


def check(name, cond, got=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"   got: {got!r}"), flush=True)
    if not cond:
        FAILS.append(name)


def rows(n):
    return [{"row": i + 1, "Application": "AFO_r1", "StartDate": f"2026-11-23 {8 + i // 6:02d}:{(i % 6) * 10:02d}:00",
             "Duration": 300, "Size": 1e7} for i in range(n)]


def main():
    tmp = tempfile.mkdtemp(prefix="afo_fl_")
    c = make_ctx({"connected": True, "running": False, "app": "AFO_r1"}, tmp=tmp)
    fl = FileLogRuns(c)
    fl.cache = {"columns": ["Application", "StartDate", "Duration", "Size"], "at": time.time(), "err": None, "rows": rows(15)}
    d = fl.runs()
    check("15 runs: 15/20 from config default", d["n_runs"] == 15 and d["max_runs"] == 20 and d["max_runs_source"] == "config", d)
    check("15 runs: no warning", d["near_limit"] is False, d)
    fl.cache["rows"] = rows(18)
    d = fl.runs()
    check("18 runs, none exported: warning", d["near_limit"] is True and d["unexported"] == 18, d)
    fl.cache["max_runs"] = 30
    d = fl.runs()
    check("limit read from the target wins", d["max_runs"] == 30 and d["max_runs_source"] == "target" and not d["near_limit"], d)
    fl.cache["max_runs"] = None
    fl._export_index = lambda: ({}, {r["StartDate"]: {"mat": "x.mat", "sid": "S1"} for r in rows(18)})
    d = fl.runs()
    check("18 runs, all exported: no warning", d["near_limit"] is False and d["unexported"] == 0, d)
    c.cfg["trials"] = {"file_log_max_runs": 25}
    d = fl.runs()
    check("config trials.file_log_max_runs used", d["max_runs"] == 25, d)
    js = open(os.path.join(APP, "assets", "afo_console.js"), encoding="utf-8").read()
    check("page: runs-on-target line + warning", "runs on target · the oldest is deleted at" in js and
          "Export before the next run: the oldest unexported run will be deleted" in js)
    print("\nFAILS:", FAILS)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
