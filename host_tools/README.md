# AFO Rig Console (host tools)

Web console for running AFO trials without the Simulink UI: live plots of the
Speedgoat UDP stream, per-trial CSV recording, and (optionally) model
load/start/stop + parameter tuning through the MATLAB engine.

## Quick start

Double-click **`start_console.bat`** — it sets up the Python environment on
first run, starts the server, and opens http://localhost:8321. With the rig
on, data appears by itself. To try it without the rig, also double-click
**`demo_data.bat`** (streams fake gait data into the console).

Manual equivalent:

```
cd host_tools
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python server.py            # console at http://localhost:8321
.venv\Scripts\python fake_speedgoat.py    # optional: sample data (second window)
```

Opening `dashboard.html` directly as a file runs the standalone mock demo
instead (press `d` for the scenario panel).

## Data path

- The Simulink model already sends 124-byte UDP packets (31 × float32 LE)
  to the host `192.168.7.15`: port **5432** at 333 Hz and port **5431** at
  ~1 kHz (same payload). The server listens on 5432 by default;
  `--udp-port 5431` switches to the full-rate stream.
- Live data goes to the browser over WebSocket; recordings are written to
  `host_tools/trial_logs/runNNN_<timestamp>.csv` with a `.json` sidecar
  (rows, gaps, timing). Recording starts/stops with the START/STOP buttons
  and works even when MATLAB is not connected.
- Channel names/order live in `CHANNELS` in `server.py` (the dashboard
  adopts them at connect). They are placeholders until the Mux3 order is
  confirmed with a wiggle test.

## MATLAB control plane (optional)

```
.venv\Scripts\pip install matlabengine==24.2.*
```

In your desktop MATLAB (or `startup.m`):

```matlab
matlab.engine.shareEngine('AFO')
```

CONNECT in the dashboard then attaches to that session (no second MATLAB,
no startup wait, shared `tg`); without a shared session it starts a
headless engine unless `--no-spawn` is set. Configure the app to load with
`--mldatx C:\path\to\app.mldatx` and the target name with `--target <name>`.

## Notes

- First run: allow python through the Windows Firewall for the UDP port
  (needed to receive from `192.168.7.5`). This is the #1 "no data" cause.
- Only one process can bind a UDP port — if an RL/agent script already
  listens on 5432, run the server with `--udp-port 5431`.
- `--http-host 0.0.0.0` makes the console reachable from other lab PCs.
