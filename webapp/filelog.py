"""Speedgoat file-log runs for the Trials page (design v17).

* list(): every run in the target's file log (afo_rc('list') via the app's
  MATLAB), cached; refreshed on demand and after a successful Stop. Only
  when this app's MATLAB is connected (it never connects by itself).
* Each run: id, start, duration, size, app, participant (from our export
  .json, else from the session log), exported (a .mat + .json in afo_mat
  whose json names this run's id / start time), recording (the newest run of
  the running app: not exportable until Stop), split_of (looks like the
  continuation of the previous run after a recording restart: same app, the
  older one ends < 60 s before this one starts).
* export(run_id, name, replace, join): import only that run (plus, when
  join, the earlier runs of the same app session; MATLAB checks model-time
  continuity) into afo_mat/{S-ID}_{YYYYMMDD}/{name}.mat + .json. Default name
  {S-ID}_{YYYYMMDD}_{HHMM}_T{nn} from the run's start time. An existing
  export is replaced only with replace=True; the old files are renamed to
  <file>.bak-<timestamp>, never deleted.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

ID_COLS = ("Id", "RunId", "RunID", "ID", "RunName", "Name")
START_COLS = ("StartDate", "StartTime", "Start", "Date", "Created", "CreationDate")
DUR_COLS = ("Duration", "Length", "DurationSec")
SIZE_COLS = ("Size", "Bytes", "FileSize", "SizeBytes")
APP_COLS = ("Application", "ApplicationName", "App")
SPLIT_GAP_S = 60.0


def _pick(cols, cands):
    return next((c for c in cands if c in cols), None)


def _parse_time(v) -> Optional[dt.datetime]:
    if not isinstance(v, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(v.strip()[:19], fmt)
        except ValueError:
            pass
    return None


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class FileLogRuns:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.lock = threading.Lock()
        self.cache: Dict[str, Any] = {"rows": [], "columns": [], "at": None, "err": None}

    # ------------------------------------------------------------ listing
    def keycol(self) -> Optional[str]:
        cols = self.cache["columns"]
        return _pick(cols, ID_COLS) or _pick(cols, START_COLS)

    def refresh_job(self, job) -> Dict[str, Any]:
        """Run inside a run-control job (one MATLAB engine, serialised with Stop/Save)."""
        res = self.ctx.runctl.call(job, "list")
        with self.lock:
            if res.get("ok"):
                rows = res.get("rows") or []
                if isinstance(rows, dict):
                    rows = [rows]
                mr = res.get("max_runs")
                self.cache = {"rows": rows, "columns": list(res.get("columns") or []), "at": time.time(), "err": None,
                              "max_runs": int(mr) if isinstance(mr, (int, float)) and mr > 0 else None}
            else:
                self.cache = dict(self.cache, err=res.get("err"), at=time.time())
        return res

    def refresh(self):
        rc = self.ctx.runctl
        if not (rc.status or {}).get("connected"):
            return None, "Not connected: connect on Run control first (the run list is read from the target)."
        if self.ctx.jobs.running("rc"):
            return None, "Another run-control action is running."
        return self.ctx.jobs.start("rc", "run control: list file log", self.refresh_job), "Reading the file log…"

    def _export_index(self) -> Tuple[Dict[str, dict], Dict[str, dict]]:
        by_id, by_start = {}, {}
        root = os.path.join(self.ctx.cfg["paths"]["afo_root"], "afo_mat")
        for jp in glob.glob(os.path.join(root, "*", "*.json")):
            try:
                meta = json.load(open(jp, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            run = meta.get("file_log_run") or {}
            mat = os.path.splitext(jp)[0] + ".mat"
            if not run or not os.path.exists(mat):
                continue
            info = {"mat": mat, "json": jp, "sid": meta.get("sid"), "exported_at": meta.get("exported_at")}
            if run.get("id") not in (None, ""):
                by_id[str(run["id"])] = info
            if run.get("start"):
                by_start[str(run["start"])] = info
        return by_id, by_start

    def _participant_at(self, when: Optional[dt.datetime]) -> Optional[str]:
        """S-ID active at that time according to logs/session_setup.csv (OMEN clock)."""
        if when is None:
            return None
        p = os.path.join(self.ctx.cfg["paths"]["log_dir"], "session_setup.csv")
        sid = None
        try:
            with open(p, encoding="utf-8") as fp:
                for r in csv.DictReader(fp):
                    t = _parse_time(r.get("time"))
                    if t is None or t > when:
                        break
                    if r.get("action") == "participant":
                        sid = r.get("detail")
        except OSError:
            return None
        return sid

    def runs(self) -> Dict[str, Any]:
        with self.lock:
            cache = dict(self.cache)
        cols = cache["columns"]
        idc, stc, duc, szc, apc = (_pick(cols, ID_COLS), _pick(cols, START_COLS), _pick(cols, DUR_COLS),
                                   _pick(cols, SIZE_COLS), _pick(cols, APP_COLS))
        key = idc or stc
        by_id, by_start = self._export_index()
        st = self.ctx.runctl.status or {}
        out = []
        for r in cache["rows"]:
            g = lambda c: r.get(re.sub(r"\W", "_", c)) if c else None  # noqa: E731 (makeValidName for plain names)
            start = g(stc)
            t0 = _parse_time(start)
            dur = _num(g(duc))
            run_id = str(g(key)) if key else f"#{r.get('row')}"
            hit = (by_id.get(str(g(idc))) if idc else None) or (by_start.get(str(start)) if start else None)
            out.append({"id": run_id, "row": r.get("row"), "start": start, "duration_s": dur, "size": g(szc),
                        "app": g(apc), "exported": bool(hit), "export": hit,
                        "participant": (hit or {}).get("sid") or self._participant_at(t0),
                        "participant_source": "export" if hit and hit.get("sid") else "session log",
                        "recording": False, "split_of": None, "_t0": t0})
        # recording: newest run of the running app; split: continuation of the previous run
        if out and st.get("running"):
            newest = max(out, key=lambda x: x["row"] or 0)
            if not st.get("app") or not newest["app"] or newest["app"] == st.get("app"):
                newest["recording"] = True
        ordered = sorted(out, key=lambda x: x["row"] or 0)
        for prev, cur in zip(ordered, ordered[1:]):
            if prev["app"] != cur["app"] or prev["_t0"] is None or cur["_t0"] is None or prev["duration_s"] is None:
                continue
            gap = (cur["_t0"] - prev["_t0"]).total_seconds() - prev["duration_s"]
            if -5.0 <= gap < SPLIT_GAP_S:
                cur["split_of"] = prev["id"]
        for x in out:
            x.pop("_t0", None)
        out.sort(key=lambda x: x["row"] or 0, reverse=True)      # newest first
        # the target keeps FileLogMaxRuns runs (read from the target when possible, else
        # config trials.file_log_max_runs, default 20) and deletes the oldest beyond that
        max_runs = cache.get("max_runs") or int(((self.ctx.cfg.get("trials") or {}).get("file_log_max_runs") or 20))
        n = len(out)
        unexported = sum(1 for x in out if not x["exported"] and not x["recording"])
        return {"runs": out, "at": cache["at"], "err": cache["err"], "key_column": key,
                "connected": bool(st.get("connected")), "n_runs": n, "max_runs": max_runs,
                "unexported": unexported, "near_limit": bool(n >= max_runs - 2 and unexported > 0),
                "max_runs_source": "target" if cache.get("max_runs") else "config"}

    # ------------------------------------------------------------ export
    def default_name(self, run: Dict[str, Any]) -> Dict[str, Any]:
        sid = run.get("participant") or self.ctx.session.sid
        if not sid:
            return {"ok": False, "err": "Unknown participant: set the S-ID first."}
        t0 = _parse_time(run.get("start")) or dt.datetime.now()
        day = t0.strftime("%Y%m%d")
        folder = os.path.join(self.ctx.cfg["paths"]["afo_root"], "afo_mat", f"{sid}_{day}")
        used = set()
        if os.path.isdir(folder):
            for f in os.listdir(folder):
                m = re.match(rf"^{re.escape(sid)}_{day}_\d{{4}}_T(\d+)", f)
                if m:
                    used.add(int(m.group(1)))
        nn = max(used) + 1 if used else 1
        return {"ok": True, "sid": sid, "folder": folder, "name": f"{sid}_{day}_{t0.strftime('%H%M')}_T{nn:02d}"}

    def find(self, run_id: str) -> Optional[Dict[str, Any]]:
        return next((r for r in self.runs()["runs"] if r["id"] == str(run_id)), None)

    def export(self, run_id: str, name: str = "", replace: bool = False, join: bool = True):
        """-> (job or None, message, http status)."""
        run = self.find(run_id)
        if run is None:
            return None, "Unknown run: refresh the run list.", 404
        if run["recording"]:
            return None, "This run is still recording: stop the app before exporting it.", 409
        if self.ctx.jobs.running("rc"):
            return None, "Another run-control action is running.", 409
        d = self.default_name(run)
        if not d["ok"]:
            return None, d["err"], 400
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip())[:80].strip("_") or d["name"]
        folder = d["folder"]
        if run["exported"] and run["export"]:
            folder = os.path.dirname(run["export"]["mat"])
            if not name:
                base = os.path.splitext(os.path.basename(run["export"]["mat"]))[0]
        mat, js = os.path.join(folder, base + ".mat"), os.path.join(folder, base + ".json")
        exists = [p for p in (mat, js) if os.path.exists(p)]
        if run["exported"] and not replace:
            return None, (f"Run already exported as {os.path.basename(run['export']['mat'])}; "
                          "export again with replace=true."), 409
        if exists and not replace:
            return None, f"{os.path.basename(mat)} exists; choose another name or replace=true.", 409
        backups = []
        if replace:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            olds = exists + ([run["export"]["mat"], run["export"]["json"]] if run.get("export") else [])
            for p in dict.fromkeys(olds):
                if os.path.exists(p):
                    bak = f"{p}.bak-{stamp}"
                    os.replace(p, bak)
                    backups.append(bak)
        os.makedirs(folder, exist_ok=True)
        meta = self.ctx.session.settings_record()
        meta.update({"sid": d["sid"], "file": mat, "json_path": js, "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "file_log_run": {k: run.get(k) for k in ("id", "row", "start", "duration_s", "size", "app")},
                     "replaced": backups or None, "join_requested": bool(join)})
        key = self.runs()["key_column"] or "#row"
        keyval = run["row"] if key == "#row" else run["id"]
        job = self.ctx.runctl.run_action("save", mat, run.get("app") or "", key, keyval, bool(join), _meta=meta)
        return job, f"Exporting {os.path.basename(mat)}" + (" (old files kept as .bak)" if backups else ""), 200
