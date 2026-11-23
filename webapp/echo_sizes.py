"""The 5433 console echo, ONE place: the column tails each build adds and the packet lengths
(floats) they give. Everything that looks at an echo length imports from here: the receiver
(training_worker), the UDP settings links (udp_settings), the session's sticky build profile
(session), the status button (status) and the page state (pages/console_api). The page JS
never looks at echo lengths: it gets the server's flags (session.adv / session.guard).

    base   12 floats  run 12
    + DEFAULT_TAIL  -> 15  run 13 (Bi-LSTM state)
    + RUN14_TAIL    -> 18  run 14 (UDP settings 5434)
    + RUN15_TAIL    -> 31  run 15 (Advanced over 5435)
    + RUN16_TAIL    -> 44  run 16b (torque guard over 5436, flags)
    + RUN16C_TAIL   -> 45  run 16c (standing-still fade)
"""
from __future__ import annotations

from typing import List, Tuple

BASE_N = 12
DEFAULT_TAIL = ["bif_valid", "bif_cal_progress", "bif_bias_ready"]
# run 14 (UDP settings 5434): cols 15-17 = gyro_cal_request in use, last accepted 5434 seq
# (0 = none), bif_mass_kg in use (0 = unset) -> '<18f'
RUN14_TAIL = ["gyro_cal_request", "settings_seq", "bif_mass_kg"]
# run 15 (Advanced over UDP 5435): cols 18-30 -> '<31f'
RUN15_TAIL = ["sv_target_min", "sv_target_max", "target_step_up", "target_step_down", "step_up_window",
              "step_down_window", "high_assist_level", "high_assist_strides", "torque_p_gain", "torque_i_gain",
              "standing_still_cutoff", "adv_seq", "spring_stiffness"]
# run 16b (torque guard over UDP 5436): cols 31-43 -> '<44f'
RUN16_TAIL = ["slack_flag", "jam_flag", "slack_count", "slack_last_stride", "slack_floor_on", "slack_thr_nm", "slack_ms",
              "slack_floor_nm", "jam_cut_on", "jam_apnm", "jam_ms", "fb_filter", "guard_seq"]
# run 16c: col 44 = standstill_fade_ms in use -> '<45f'
RUN16C_TAIL = ["standstill_fade_ms"]

TAILS: List[List[str]] = [DEFAULT_TAIL, RUN14_TAIL, RUN15_TAIL, RUN16_TAIL, RUN16C_TAIL]


def _sizes() -> Tuple[int, ...]:
    out, n = [BASE_N], BASE_N
    for t in TAILS:
        n += len(t)
        out.append(n)
    return tuple(out)


# every echo length a build sends (12, 15, 18, 31, 44, 45): any of them = the console echo is alive
ECHO_SIZES: Tuple[int, ...] = _sizes()
ECHO_RUN13, ECHO_RUN14, ECHO_RUN15, ECHO_RUN16B, ECHO_RUN16C = ECHO_SIZES[1:]
# the smallest echo that carries each UDP link's echo / seq (an echo at least this long = that build or later)
UDP_SETTINGS_MIN = ECHO_RUN14        # 5434: side / mass / mode / K / gyro
ADV_UDP_MIN = ECHO_RUN15             # 5435: Advanced
GUARD_UDP_MIN = ECHO_RUN16B          # 5436: torque guard
FADE_MIN = ECHO_RUN16C               # standing-still fade in the echo

assert ECHO_SIZES == (12, 15, 18, 31, 44, 45), ECHO_SIZES
