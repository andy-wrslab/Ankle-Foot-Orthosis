"""Model profiles: one web app for both Simulink apps on the Speedgoat.

AFO      the GPR model (weight is a Gain, side built 0 = left, no Bi-LSTM).
AFO_r1   GPR removed, Bi-LSTM drives the torque. Side built -1 (unset: the
         drive stays disabled until 0/1 is set), weight is a Constant (Value),
         BIF_mass_kg built 0 (<= 20 kg: Bi-LSTM moment 0, no assist), console
         packet on UDP 5433. Every Start resets all of them to the built values.

config.yaml ``target.model``: ``auto`` (default: the loaded app decides, AFO
when unknown), ``AFO`` or ``AFO_r1`` (used while the loaded app is unknown;
a different loaded app always wins, because its block paths are the real ones).
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

PROFILES: Dict[str, Dict[str, Any]] = {
    "AFO": {"app": "AFO", "label": "AFO (GPR)", "side_built": 0, "bif": False, "console_expected": False},
    "AFO_r1": {"app": "AFO_r1", "label": "AFO_r1 (Bi-LSTM)", "side_built": -1, "bif": True,
               "console_expected": True},
}
DEFAULT_MODEL = "AFO"

# BIF_Dbg (1x10): [state, M_bio, vGRF N/kg, xCoP mm, dM, imu_fallback, walk_started,
#                  calib_progress 0..1, m_raw, m_bif]; the Signals stream names
# a vector signal "name(k)" (1-based).
BIF_STATES = {0: "waiting for walk", 1: "calibrating", 2: "Bi-LSTM active", 3: "holding (IMU bad)",
              4: "physics-only fallback", 5: "bad input"}
DBG_STATE, DBG_PROGRESS = "bif_dbg(1)", "bif_dbg(8)"

# Logged signals of AFO_r1 (block, port -> logged name), found in AFO_r1.slx:
# Bi-LSTM Estimator 1..5, Drive Enable Logic 2..3, IMU Check 2..3.
R1_SIGNALS = ["estimated_ankle_moment", "bif_valid", "bif_stance", "bif_bias_ready", DBG_STATE, DBG_PROGRESS,
              "drive_enabled", "drive_state", "imu_ok", "imu_bad_count"]
R1_SIGNAL_LABELS = {DBG_STATE: "bif_dbg(1) state", DBG_PROGRESS: "bif_dbg(8) calib progress"}

# Console packet (5433) may grow by 3 floats: cols 12-14.
CONSOLE_TAIL = ["bif_valid", "bif_cal_progress", "bif_bias_ready"]

CHECKLIST = [("side", "Set foot side"), ("bif_mass", "Set mass"), ("bias", "IMU ready"),
             ("walk", "30 s calibration walk")]
BIF_MASS_MIN = 20.0       # BIF_mass_kg <= 20 -> Bi-LSTM invalid, no assist


def block_path(model: str, name: str) -> str:
    """Full block path; a '/' inside a block name is written '//' (Simulink and slrealtime)."""
    return f"{model}/{name.replace('/', '//')}"


def configured_model(cfg: Dict[str, Any]) -> Optional[str]:
    m = str(((cfg or {}).get("target") or {}).get("model") or "auto").strip()
    return m if m in PROFILES else None


def _f(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def bif_status(vals: Dict[str, Any], source: Optional[str]) -> Dict[str, Any]:
    """Bi-LSTM phase from bias_ready / valid (+ BIF_Dbg state and calib progress when known)."""
    ready, valid = _f(vals.get("bif_bias_ready")), _f(vals.get("bif_valid"))
    prog = _f(vals.get("bif_cal_progress"))
    state = _f(vals.get("state"))
    out: Dict[str, Any] = {"source": source, "bias_ready": ready, "valid": valid,
                           "progress_pct": None if prog is None else int(round(100 * max(0.0, min(1.0, prog)))),
                           "state": None if state is None else int(round(state))}
    out["state_text"] = BIF_STATES.get(out["state"]) if out["state"] is not None else None
    if ready is None and valid is None:
        out.update(phase="unknown", text="Bi-LSTM: state unknown (connect Signals)")
    elif ready is not None and ready < 0.5:
        out.update(phase="bias", text="Bi-LSTM: hold still 5 s… (IMU not ready yet)")
    elif valid is not None and valid >= 0.5:
        out.update(phase="valid", text="Bi-LSTM: valid")
    else:
        t = "Bi-LSTM: IMU ready · calibration walk"
        if out["progress_pct"] is not None:
            t += f" {out['progress_pct']} %"
        if out["state"] in (3, 4, 5):
            t += f" · {out['state_text']}"
        out.update(phase="walk", text=t)
    return out
