# AFO Rig Console (host tools)

Web console for running AFO trials without the Simulink UI: live plots of
every instrumented signal, automatic full-set recording, and model
start/stop + parameter tuning through the MATLAB engine.

## Quick start

Double-click **`start_console.bat`** — it sets up the Python environment on
first run, starts the server, and opens http://localhost:8321. Click
CONNECT (connects to TargetPC1); with the rig on, signals and recording
follow by themselves.

Manual equivalent:

```
cd host_tools
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python server.py            # console at http://localhost:8321
```

Opening `dashboard.html` directly as a file runs the standalone mock demo
instead (press `d` for the scenario panel).

## Data path (live SDI run via the MATLAB engine)

- While the model runs with recording active, every SDI-instrumented
  signal (the blue badges) streams into a live Simulation Data Inspector
  run in the shared MATLAB session. The server reads that run
  incrementally a few times per second. Nothing to configure: the signal
  set is discovered, vector signals are expanded into per-element
  channels (`name(1)…name(w)`), and the discovered set is cached in
  `signals_cache.json` and adopted by the dashboard automatically.
- **Recording is two-layer and automatic.** While the model runs, the
  target records all instrumented signals (`startRecording` → SDI + File
  Log on the target SSD). When the model stops, the server imports the
  newest file log and writes a full-rate wide CSV
  (`trial_logs/target_<stamp>.csv`, vectors expanded to `name_1…name_w`
  columns). Independently, the live stream is mirrored to
  `trial_logs/runNNN_<timestamp>.csv` (uniform 100 Hz grid, zero-order
  hold) with a `.json` sidecar — a belt-and-braces copy that exists even
  if the import fails. `POST /api/import` re-imports the newest target
  log manually (e.g., from a previous session).
- If the model runs but no data flows, the console restarts the target
  recording once automatically; if the stream stays silent, the app's
  XCP streaming link is wedged — stop the model and reload the app on
  the Speedgoat (a reboot does this), then reconnect.

## MATLAB link

`matlabengine==24.2.*` is preinstalled in `.venv`. In your desktop MATLAB
(or `startup.m`):

```matlab
matlab.engine.shareEngine('AFO')
```

CONNECT then attaches to that session (no second MATLAB, no startup wait,
shared `tg`); without a shared session it starts a headless engine unless
`--no-spawn` is set. The model normally runs as the Speedgoat startup app,
so BUILD/LOAD are placeholders (`--mldatx <file>` enables LOAD). The
MATLAB helper functions live in `host_tools/matlab/`.

## Notes

- The console needs no internet — rig sessions on the onboard-router WiFi
  work fully offline.
- First rig session: verify the instrument stream appears after CONNECT,
  and that stop → `target_*.csv` import works; errors surface in the
  event log.
- `--http-host 0.0.0.0` makes the console reachable from other lab PCs.
