# AFO web app (webapp/)

Run on the OMEN: double-click `webapp\AFO_app.bat` (conda base Python; `pip`
packages: dash, dash-extensions, plotly, numpy, h5py, scipy, pyyaml, websocket-client,
matlabengine for the MATLAB pages). Serves **:8050** (tablet: http://192.168.7.15:8050,
OMEN: http://127.0.0.1:8050). Listens for the Speedgoat on **UDP 5431** (live bus,
31 x float32) and **UDP 5433** (console packet, `config/console_udp_layout.json`; AFO_r1 profile);
sends commands to 192.168.7.5:5431 and parameters to :5430 only on a user press.
OMEN-only pages/APIs (Teensy, run control, Signals stream on/off) answer loopback
requests only. Target writes for session values are disabled in `config.yaml`
(`session.target_writes_enabled: false`) until enabled on purpose. Set
`console.view_only: true` in the config to run a watch-only console (no UDP commands).

Origin: developed on branch `afo-webapp-20261119` of SherimaX/GUI (local commits
951d5e0..9325992, then batch branch afo-mass-20261123 up to a5bdfe0 (2026-11-23, run 14 UDP settings), not pushed there: no write access), copied here as a subfolder.

---

# AFO web app
# AFO web app

One web app for the AFO rig, on **http://192.168.7.15:8050** (tablet) or
**http://127.0.0.1:8050** (on the OMEN).

| Page | What it does | Who can use it |
|---|---|---|
| **Home** | One tile per tool with live status: Speedgoat stream and rate, IMU/FSR health, target reachability, MATLAB worker, Teensy USB, firmware branch, recent logs | everyone |
| **Live** | The real-time dashboard: torque, ankle, SV, pressure and IMU plots, readouts, Zero / Motor / Assist / K / Calibrate / Reset SV, parameters, 2 s / 10 s | everyone |
| **Trials** | Open a saved Speedgoat log (.mat SDI export or a tee capture), zoomable synced plots, a data-health check (bad values, IMU byte slips, frozen Teensy, sync glitches; click to jump), CSV export of the view | everyone |
| **Signals** | Every SDI-instrumented model signal (Uc, assistance, SV estimator, PI terms, ...) live through the hidden MATLAB worker (host_tools streaming helpers); manual recovery buttons | viewing: everyone; stream on/off: OMEN only |
| **Teensy** | Firmware repo branch / log / diff, check out a branch, build for Teensy 4.1, flash (guarded), serial monitor | **OMEN only** |

Run control (Connect / Start / Stop / status / Export) has no page any more: it is an
OMEN-only API (`/api/run/...`, `/api/run/export`, `/api/run/export-name`) for the top bar.

**Commands are never sent by the console itself** (`commands.py`): no packet on server
start, new data session, page load/reload; each press sends the full command set from
the server's state with only that field changed; the model's latched commands from the
training stream (UDP 5433, `training_worker.py`, `config/training_udp_layout.json`) are
the authoritative readback.

**Session setup** (`session.py`): S-ID, foot side (confirm with the S-ID, safety
critical), weight, assistance mode RL / Fixed K, K %, SV target band; sent on commit
and read back (UDP echo first, getparam fallback); Motor/Assist blocked until the
target's side matches the confirmed side. Target writes are disabled in config.yaml
(`session.target_writes_enabled`) until enabled on purpose.

"OMEN only" is enforced by the server: those pages and every one of their
callbacks only answer requests from 127.0.0.1. From the tablet, or from
192.168.7.15 even on the OMEN itself, the pages show a locked notice.

## Start
Double-click **AFO_app.bat** (it uses the conda base Python). Stop it with Ctrl+C or by closing its window.

Before starting: nothing else may use TCP 8050 (stop any old GUI), and the app
listens for the Speedgoat on UDP 5431 (`config.yaml` → `udp.listen_port`).

## How it is built
* `app.py`: starts everything. `pages/shell.py`: the shared top bar and router.
* `live_worker.py` runs in **its own process**: UDP receive, per-value validation,
  history, strict-JSON encoding. `workers.LiveSupervisor` restarts it if it dies
  or goes silent, so the Live page keeps updating whatever the other pages do.
* `matlab_worker.py`: one MATLAB R2024b engine in its own process, used by Run
  control through `matlab/afo_rc.m`. Every call has a timeout, and a hung engine
  is killed and restarted.
* Compiles, flashes, trial decoding (`trials_data.py`) and the serial monitor run
  as subprocesses or background jobs. Pages poll their status.
* Flashing is refused while the Speedgoat stream is live (packets in the last
  5 s), without a clean build of the checked-out commit, or unless the branch
  name is typed. Every attempt, dry runs included, goes to `logs/flash_log.csv`.
  Run-control actions go to `logs/run_control.csv`.
* There are **no torque, assist or motor controls on Run control**. Those stay on
  the Live page, with STO as the hardware stop.

## Live data robustness (from GUI_robust)
Every incoming value is checked: it must be finite and inside the range set in
`config.yaml` → `validation`. A bad value becomes a gap in its own trace and is
counted on the health lamps. Packets with a bad time stamp or the wrong length
are dropped. Plots use min/max bins anchored to model time, so they don't flash.
The Motor button colour is the drive status from the statusword, with the same
colours as the original GUI. The ON/OFF pill shows the command toggle.

## Tests
`test/test_app.py` (end to end, localhost plus a request through 192.168.7.15
to prove the OMEN-only lock), `test/test_matlab_worker.py` (the engine path;
the target is not contacted).
