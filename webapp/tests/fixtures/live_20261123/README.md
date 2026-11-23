# Live fixtures, 2026-11-23 (OMEN :8050, AFO_r1 running, rig idle)

Recorded from the page server's own outputs (no UDP rebind), 10:34:32-10:35:32 OMEN time.
STO engaged most of the time, insole not worn (FSR baseline 3-15 counts), drive in fault 0x0628.

De-identified: participant ID -> S00, every body / BIF mass value -> 70 (placeholder),
local paths -> <AFO_ROOT>. Sensor values, statuswords, timings and the setparam sequence
(block paths, order, readback ok/fail) are unchanged.

- `snapshots_latest_5431.csv`: one row per SSE frame (~21/s): wall time, t_latest (model s) and the
  latest value of each displayed 5431 channel (ankle, torque, demand_torque, gait, press_1..8,
  imu_1..3, statusword, ...). The page received 5431 at ~1000 packets/s.
- `snapshot_full_{first,middle,last}.json.gz`: three complete SSE frames (10 s min/max envelope
  per channel + meta), as the browser received them on the 9325992 page.
- `console_5433_latest.csv`: 5433 console packet, latest values polled at 10 Hz (12 floats:
  t_model, side, weight_kg, assist_mode, fixed_k_pct, cmd_*, imu_ok, imu_bad_count).
- `session_setup_excerpt.csv`, `run_control_excerpt.csv`: page logs from 10:04 on (connect,
  side/mass setparams with readback, start/stop with slrealtime status, file-log exports).
- `statusword_changes.log`: statusword transitions 10:23-10:36 incl. Motor fault resets
  (0x0628 -> 0x0637 operation enabled -> 0x0660 after Motor OFF).

The target RTC reads 2012; OMEN times are the real ones.
