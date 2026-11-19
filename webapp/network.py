import fnmatch
import logging
import math
import struct
import socket
import time
import threading
from typing import Dict, Any, List, Tuple

from constants import CONTROL_FMT, SAMPLE_RATE_HZ, UPDATE_MS, N_WINDOW_SEC, PARAM_FMT, BIN_WIDTH_SEC
from state import snapshots
from history import SignalHistory
from health import DataHealth

# minimum interval between control packets in seconds and nanoseconds
_MIN_CTRL_INTERVAL = UPDATE_MS / 1000.0
_CTRL_INTERVAL_NS = int(_MIN_CTRL_INTERVAL * 1_000_000_000)
_last_ctrl_ns = 0

# throttle SSE pushes so the browser is not overwhelmed
_SSE_PUSH_HZ = 30.0
_SSE_PUSH_INTERVAL = 1.0 / _SSE_PUSH_HZ
_last_emit_ts = 0.0

# cap points per snapshot; sized to hold the full rolling window with headroom
_HISTORY_MAX_POINTS = int(SAMPLE_RATE_HZ * N_WINDOW_SEC * 1.25)
# hard cap on buffered samples whatever the clock does (the live stream runs at
# 1 kHz; this allows 2 kHz with 2x headroom)
_HISTORY_MAX_SAMPLES = int(2000 * (N_WINDOW_SEC + 1) * 2)

# global stop event for graceful shutdown
_stop_event = threading.Event()
_history = SignalHistory(
    N_WINDOW_SEC,
    max_emit_points=_HISTORY_MAX_POINTS,
    max_samples=_HISTORY_MAX_SAMPLES,
    bin_width=BIN_WIDTH_SEC,
)
_health = DataHealth(window_sec=N_WINDOW_SEC)
# the live and fake sources briefly overlap while handing over, so every
# mutation of the rolling window is serialized
_history_lock = threading.Lock()
_logger = logging.getLogger("afo.network")

# a silence longer than this means the target went away (restart, reboot, cable)
LINK_TIMEOUT_SEC = 3.0
# model time running backwards by more than this is a restart, not packet reorder
_T_REWIND_TOL = 0.5
# the zeroed control packet is repeated because UDP gives no delivery guarantee
_ZERO_REPEATS = 3
_ZERO_REPEAT_INTERVAL = 0.1
# delay before rebuilding a listening socket that failed
_SOCKET_RETRY_SEC = 1.0
# receive buffer: larger than any UDP datagram, so an oversized packet is
# counted and dropped instead of raising WSAEMSGSIZE and rebuilding the socket
_RX_BUF_BYTES = 65536
# how often bad-data counts are written to the log
_SUMMARY_SEC = 10.0

# link bookkeeping, guarded by _link_lock
_link_lock = threading.Lock()
_link_session = 0
_link_last_rx = 0.0  # monotonic clock of the last live packet
_link_last_t = None  # model time of the last accepted live packet
_link_pending_t = None  # a time discontinuity waiting for confirmation
_link_up = False

# signal -> group for the health lamps
_GROUP_OF = {
    "time": "sync",
    "sync": "sync",
    "sv": "drive",
    "ankle_angle": "drive",
    "actual_torque": "drive",
    "demand_torque": "drive",
    "statusword": "drive",
    "sv_target": "drive",
    "uc": "drive",
    "heel_strike": "drive",
    "assistance_level": "drive",
}

# used when config.yaml has no validation section; values outside are rejected
_DEFAULT_RANGES = {
    "time": [0.0, 1.0e7],
    "sv": [-1.0, 5.0],
    "ankle_angle": [-180.0, 180.0],
    "pressure_*": [-50.0, 5000.0],
    "imu_1": [-16.0, 16.0],
    "imu_2": [-16.0, 16.0],
    "imu_3": [-16.0, 16.0],
    "imu_4": [-3.5, 3.5],
    "imu_5": [-3.5, 3.5],
    "imu_6": [-3.5, 3.5],
    "imu_7": [-35.0, 35.0],
    "imu_8": [-35.0, 35.0],
    "imu_9": [-35.0, 35.0],
    "imu_10": [-16.0, 16.0],
    "imu_11": [-16.0, 16.0],
    "imu_12": [-16.0, 16.0],
    "actual_torque": [-200.0, 200.0],
    "demand_torque": [-200.0, 200.0],
    "statusword": [0.0, 65535.0],
}


class _RateLimitedLog:
    """Log a recurring problem at most once per *interval*, with a count."""

    def __init__(self, logger: logging.Logger, interval: float = 1.0) -> None:
        self._logger = logger
        self._interval = interval
        self._last: Dict[str, float] = {}
        self._suppressed: Dict[str, int] = {}
        self._lock = threading.Lock()

    def __call__(self, key: str, level: int, msg: str, *args: Any, exc_info: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            last = self._last.get(key, 0.0)
            if now - last < self._interval:
                self._suppressed[key] = self._suppressed.get(key, 0) + 1
                return
            suppressed = self._suppressed.pop(key, 0)
            self._last[key] = now
        if suppressed:
            msg = msg + f" (+{suppressed} similar since last report)"
        self._logger.log(level, msg, *args, exc_info=exc_info)


_rl_log = _RateLimitedLog(_logger)

# per-signal rejected-value counts since the last summary, guarded by _bad_lock
_bad_lock = threading.Lock()
_bad_since_summary: Dict[str, List[int]] = {}  # name -> [non_finite, out_of_range]
_last_summary = 0.0
_last_states: Dict[str, str] = {}


_publish_hook = snapshots.publish
_readback_lock = threading.Lock()
from history import SlowBuffer  # noqa: E402
_slow = SlowBuffer()


def slow_data(names, window_s: float, max_points: int = 1500) -> Dict[str, Any]:
    """Training sub-page data (5431 at ~100 Hz, up to 330 s), min/max binned."""
    with _history_lock:
        return _slow.data(names, window_s, max_points)
_readback: Dict[str, Any] = {}


def get_readback(max_age_s: float = 3.0) -> Dict[str, Any]:
    """Latest valid command-related values from the bus (empty if stale)."""
    with _readback_lock:
        if not _readback or time.monotonic() - _readback.get("_at", 0) > max_age_s:
            return {}
        return {k: v for k, v in _readback.items() if not k.startswith("_")}


def set_publish_hook(fn) -> None:
    """Route every finished snapshot to *fn* instead of the in-process broadcaster."""
    global _publish_hook
    _publish_hook = fn


def get_health() -> Dict[str, object]:
    """Return the current data-health snapshot."""
    return _health.snapshot()


def request_shutdown() -> None:
    """Signal the network loops to exit cleanly."""
    _stop_event.set()


def get_stop_event() -> threading.Event:
    """Return the shared stop event so every loop watches the same flag."""
    return _stop_event


def is_shutdown_requested() -> bool:
    """True once shutdown has been requested."""
    return _stop_event.is_set()


def get_link_status() -> Dict[str, Any]:
    """Return the state of the incoming data stream."""
    with _link_lock:
        session = _link_session
        last_rx = _link_last_rx
    age = time.monotonic() - last_rx if last_rx else float("inf")
    return {"session": session, "connected": age < LINK_TIMEOUT_SEC, "age": age}


def live_data_seen() -> bool:
    """True once at least one packet has arrived from the real target."""
    with _link_lock:
        return _link_last_rx != 0.0


def send_control_packet(
    cfg: Dict[str, Any],
    zero: float,
    motor: float = 0.0,
    assist: float = 0.0,
    k_val: float = 0.0,
    calibrate_pressure: float = 0.0,
    reset_sv: float = 0.0,
    force: bool = False,
) -> None:
    """Send a 6-float packet containing the control signals and triggers.

    *force* bypasses the rate limiter, for packets that must not be dropped
    such as the zeroed controls pushed after the target restarts.
    """
    global _last_ctrl_ns

    if not force:
        now_ns = time.monotonic_ns()
        elapsed_ns = now_ns - _last_ctrl_ns
        if elapsed_ns < _CTRL_INTERVAL_NS:
            if _logger.isEnabledFor(logging.DEBUG):
                _logger.debug(
                    "control packet skipped; %.2f ms since last",
                    elapsed_ns / 1_000_000.0,
                )
            return
        _last_ctrl_ns = now_ns

    payload = struct.pack(
        CONTROL_FMT,
        zero,
        motor,
        assist,
        k_val,
        calibrate_pressure,
        reset_sv,
    )
    host = cfg["udp"]["send_host"]
    port = cfg["udp"]["send_port"]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.sendto(payload, (host, port))
        except OSError as exc:
            if _logger.isEnabledFor(logging.DEBUG):
                _logger.debug("control packet send failed: %s", exc)


def send_param_packet(
    cfg: Dict[str, Any],
    epsilon_up: float,
    epsilon_down: float,
    step_up: float,
    step_down: float,
    v_min: float,
) -> None:
    """Send a 5-float packet with tuning parameters."""
    payload = struct.pack(
        PARAM_FMT,
        float(epsilon_up),
        float(epsilon_down),
        float(step_up),
        float(step_down),
        float(v_min),
    )
    host = cfg["udp"]["send_host"]
    port = cfg["udp"].get("param_port", 5430)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.sendto(payload, (host, port))
        except OSError as exc:
            if _logger.isEnabledFor(logging.DEBUG):
                _logger.debug("param packet send failed: %s", exc)


def _zero_controls(cfg: Dict[str, Any]) -> None:
    """Push an all-zero control packet, repeated so a loss cannot hide it."""
    for attempt in range(_ZERO_REPEATS):
        if _stop_event.is_set():
            return
        send_control_packet(cfg, 0.0, force=True)
        if attempt + 1 < _ZERO_REPEATS:
            _stop_event.wait(_ZERO_REPEAT_INTERVAL)


def _begin_session(cfg: Dict[str, Any], session: int, reason: str) -> None:
    """Start from a clean slate after the target (re)started."""
    _history.reset()
    _slow.reset()
    snapshots.clear()
    # No control packet here: the model holds the last command it received, and
    # the console must never change a command by itself (see commands.py).
    _logger.info("data stream session %d: %s", session, reason)


def _note_live_sample(cfg: Dict[str, Any], t_val: float) -> str:
    """Check the model time of a live packet and track stream liveness.

    Returns "keep" when the sample belongs on the time axis, otherwise the
    reason it was dropped ("stale_time" or "time_jump"). A rewind or jump is
    only taken as a target restart once the next packet confirms the new time
    base, so a single corrupted time stamp can never reset the window (and
    zero the controls) or stall the trimming of the history.
    """
    global _link_session, _link_last_rx, _link_last_t, _link_pending_t, _link_up

    now = time.monotonic()
    with _link_lock:
        reason = None
        if _link_last_rx == 0.0 or _link_last_t is None:
            reason = "first packet received"
        elif now - _link_last_rx > LINK_TIMEOUT_SEC:
            reason = f"data resumed after {now - _link_last_rx:.1f} s of silence"
        else:
            dt = t_val - _link_last_t
            if 0.0 < dt <= LINK_TIMEOUT_SEC:
                _link_pending_t = None
            elif -_T_REWIND_TOL <= dt <= 0.0:
                # duplicate or reordered packet: the window must stay monotonic
                _link_last_rx = now
                return "stale_time"
            else:
                pending = _link_pending_t
                if pending is not None and 0.0 < t_val - pending <= LINK_TIMEOUT_SEC:
                    if dt < 0:
                        reason = f"model time restarted ({_link_last_t:.1f} s -> {t_val:.1f} s)"
                    else:
                        reason = f"model time jumped ahead by {dt:.1f} s"
                else:
                    _link_pending_t = t_val
                    _link_last_rx = now
                    return "time_jump"

        _link_last_rx = now
        _link_last_t = t_val
        _link_up = True
        if reason is None:
            return "keep"
        _link_pending_t = None
        _link_session += 1
        session = _link_session

    _begin_session(cfg, session, reason)
    return "keep"


def _check_link_timeout() -> None:
    """Log once when the stream falls quiet, so the console shows the drop."""
    global _link_up

    with _link_lock:
        if not _link_up or _link_last_rx == 0.0:
            return
        quiet = time.monotonic() - _link_last_rx
        if quiet <= LINK_TIMEOUT_SEC:
            return
        _link_up = False
    _logger.warning("no data for %.1f s; waiting for the target to come back", quiet)


def _range_for(name: str, ranges: Dict[str, Any]) -> Tuple[float, float] | None:
    if name in ranges:
        lo, hi = ranges[name]
        return float(lo), float(hi)
    for pattern, bounds in ranges.items():
        if "*" in pattern and fnmatch.fnmatch(name, pattern):
            lo, hi = bounds
            return float(lo), float(hi)
    return None


def _build_decoder(cfg: Dict[str, Any]):
    """Return ``(decode, packet_size)`` for the layout described by *cfg*.

    ``decode`` returns ``(sample, group_counts)``. Every value is checked:
    a non-finite value or one outside its plausible range becomes NaN in the
    sample (a gap in its own trace only) and is counted against its group.
    """
    packet_struct = struct.Struct(cfg["packet"]["format"])
    n_values = len(packet_struct.unpack(bytes(packet_struct.size)))
    mapping = cfg["signals"]
    validation = cfg.get("validation") or {}
    ranges = validation.get("ranges") or _DEFAULT_RANGES

    # (name, index, group, lo, hi) for every mapped signal inside the packet
    checks = []
    for name, idx in mapping.items():
        if idx is None or not (0 <= int(idx) < n_values):
            continue
        if name.startswith("imu_"):
            group = "imu"
        elif name.startswith("pressure_"):
            group = "fsr"
        else:
            group = _GROUP_OF.get(name, "drive")
        bounds = _range_for(name, ranges)
        lo, hi = bounds if bounds else (-math.inf, math.inf)
        checks.append((name, int(idx), group, lo, hi))

    name_to_idx = {name: idx for name, idx, _, _, _ in checks}
    idx_time = name_to_idx.get("time", name_to_idx.get("Time"))
    idx_ankle = name_to_idx.get("ankle_angle")
    idx_torque = name_to_idx.get("actual_torque")
    idx_demand = name_to_idx.get("demand_torque")
    idx_gait = name_to_idx.get("sv", name_to_idx.get("treadmill_velocity"))   # col 1 = SV
    idx_status = name_to_idx.get("statusword")
    press_indices: List[int | None] = [name_to_idx.get(f"pressure_{i}") for i in range(1, 9)]
    imu_indices: List[int | None] = [name_to_idx.get(f"imu_{i}") for i in range(1, 13)]
    nan = math.nan
    isfinite = math.isfinite

    def decode(buf_view: memoryview) -> Tuple[Dict[str, Any], Dict[str, Tuple[int, int]]]:
        raw = packet_struct.unpack_from(buf_view)
        clean = list(raw)
        counts = {"sync": [0, 0], "imu": [0, 0], "fsr": [0, 0], "drive": [0, 0]}
        bad_names = None
        for name, idx, group, lo, hi in checks:
            v = raw[idx]
            c = counts[group]
            c[1] += 1
            if isfinite(v):
                if lo <= v <= hi:
                    continue
                kind = 1  # out of range
            else:
                kind = 0  # NaN / Inf
            clean[idx] = nan
            c[0] += 1
            if bad_names is None:
                bad_names = []
            bad_names.append((name, kind))
        if bad_names:
            with _bad_lock:
                for name, kind in bad_names:
                    entry = _bad_since_summary.get(name)
                    if entry is None:
                        entry = _bad_since_summary[name] = [0, 0]
                    entry[kind] += 1

        def _v(idx: int | None) -> float:
            return nan if idx is None else clean[idx]

        sample = {
            "timestamp": time.time(),
            "t": _v(idx_time),
            "ankle": _v(idx_ankle),
            "torque": _v(idx_torque),
            "demand_torque": _v(idx_demand),
            "gait": _v(idx_gait),
            "press": [_v(idx) for idx in press_indices],
            "imu": [_v(idx) for idx in imu_indices],
            "statusword": _v(idx_status),
            "assistance_level": _v(name_to_idx.get("assistance_level")),
            "sv_target": _v(name_to_idx.get("sv_target")),
            "uc": _v(name_to_idx.get("uc")),
        }
        return sample, {g: (c[0], c[1]) for g, c in counts.items()}

    return decode, packet_struct.size


def _log_summary(force: bool = False) -> None:
    """Every _SUMMARY_SEC, log rejected values per signal and lamp changes."""
    global _last_summary
    now = time.monotonic()
    if not force and now - _last_summary < _SUMMARY_SEC:
        return
    _last_summary = now
    with _bad_lock:
        bad = dict(_bad_since_summary)
        _bad_since_summary.clear()
    snap = _health.snapshot()
    groups = snap["groups"]
    for group, info in groups.items():
        prev = _last_states.get(group)
        if prev != info["state"]:
            _logger.info("health %s: %s -> %s", group, prev or "start", info["state"])
            _last_states[group] = info["state"]
    if bad:
        parts = ", ".join(
            f"{name} {nf + oor} (non-finite {nf}, out-of-range {oor})"
            for name, (nf, oor) in sorted(bad.items())
        )
        _logger.warning("rejected values in the last %.0f s: %s", _SUMMARY_SEC, parts)
    pk = snap["packets"]
    if any(pk[k] for k in pk if k != "ok"):
        _logger.info(
            "packet totals: ok %d, bad length %d, bad time %d, stale time %d, time jump %d, errors %d",
            pk.get("ok", 0), pk.get("bad_length", 0), pk.get("bad_time", 0),
            pk.get("stale_time", 0), pk.get("time_jump", 0), pk.get("errors", 0),
        )


def _open_listen_socket(host: str, port: int) -> socket.socket | None:
    """Bind a UDP socket for the inbound stream, or return None on failure."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    try:
        sock.bind((host, port))
    except OSError as exc:
        _logger.error("cannot bind UDP %s:%d (%s)", host, port, exc)
        sock.close()
        return None
    sock.settimeout(1.0)
    _logger.info("listening for data on %s:%d", host, port)
    return sock


def start_udp_listener(
    cfg: Dict[str, Any],
    stop_event: threading.Event | None = None,
) -> None:
    """Listen to the UDP stream and push decoded packets to ``event_q``.

    The socket is rebuilt after any failure, and the loop keeps waiting through
    silences, so a target restart or a pulled cable never ends the feed.
    """
    if stop_event is None:
        stop_event = _stop_event
    decode, expected = _build_decoder(cfg)
    host = cfg["udp"]["listen_host"]
    port = cfg["udp"]["listen_port"]

    while not stop_event.is_set():
        sock = _open_listen_socket(host, port)
        if sock is None:
            stop_event.wait(_SOCKET_RETRY_SEC)
            continue
        try:
            _receive_loop(cfg, sock, decode, expected, stop_event)
        except OSError as exc:
            _logger.warning("UDP listener error (%s); rebuilding socket", exc)
            stop_event.wait(_SOCKET_RETRY_SEC)
        finally:
            sock.close()


def _receive_loop(
    cfg: Dict[str, Any],
    sock: socket.socket,
    decode,
    expected: int,
    stop_event: threading.Event,
) -> None:
    """Read datagrams until *stop_event* is set or the socket needs rebuilding.

    One bad packet never ends the loop: wrong sizes are counted and dropped,
    and any error while decoding or publishing is logged and skipped.
    """
    buf = bytearray(_RX_BUF_BYTES)
    buf_view = memoryview(buf)

    while not stop_event.is_set():
        try:
            nbytes, _ = sock.recvfrom_into(buf_view)
        except socket.timeout:
            _check_link_timeout()
            _log_summary()
            continue
        except ConnectionResetError:
            # Windows reports the ICMP "port unreachable" of a stopped target here
            _check_link_timeout()
            continue
        except OSError as exc:
            if getattr(exc, "winerror", None) == 10040:  # WSAEMSGSIZE
                _health.count_packet("bad_length")
                _rl_log("len", logging.WARNING, "oversized UDP packet dropped (expected %d bytes)", expected)
                continue
            raise
        if nbytes != expected:
            _health.count_packet("bad_length")
            _rl_log("len", logging.WARNING, "UDP packet of %d bytes dropped (expected %d)", nbytes, expected)
            continue

        try:
            sample, counts = decode(buf_view[:expected])
            _health.record(counts)
            _publish_sample(cfg, sample)
        except Exception:
            _health.count_packet("errors")
            _rl_log("decode", logging.ERROR, "error while handling a packet; skipped", exc_info=True)
        _log_summary()


def start_fake_data(cfg: Dict[str, Any], stop_event: threading.Event | None = None) -> None:
    """Generate synthetic samples until the real target starts sending.

    Exits for good once live packets appear, so fake traces can never be
    mistaken for readings from a target that just came back.
    """
    if stop_event is None:
        stop_event = _stop_event
    if live_data_seen():
        return
    _logger.info("no live target: generating fake data until real packets arrive")
    _history.reset()
    t = 0.0
    dt = 1.0 / SAMPLE_RATE_HZ
    while not stop_event.is_set():
        if live_data_seen():
            _logger.info("live data detected; stopping the fake data generator")
            return
        ankle = 20.0 * math.sin(t)
        torque = 5.0 * math.sin(t / 2.0)
        demand = 4.0 * math.sin(t / 2.0 + 0.5)
        pressures = [500.0 + 100.0 * math.sin(t + i) for i in range(8)]
        imus = [math.sin(t + i * 0.1) for i in range(12)]
        gait = 1.0 + 0.8 * math.sin(t / 2.0)  # simulate stride velocity in m/s

        _publish_sample(
            cfg,
            {
                "t": t,
                "ankle": ankle,
                "torque": torque,
                "demand_torque": demand,
                "gait": gait,
                "press": pressures,
                "imu": imus,
                "statusword": 1591,
            },
            live=False,
        )
        time.sleep(dt)
        t += dt


def _publish_sample(cfg: Dict[str, Any], sample: Dict[str, Any], live: bool = True) -> None:
    """Update the rolling history and push throttled snapshots to SSE clients."""
    global _last_emit_ts

    t_val = sample.get("t", math.nan)
    try:
        t_val = float(t_val)
    except (TypeError, ValueError):
        t_val = math.nan

    with _history_lock:
        if live:
            if not math.isfinite(t_val):
                # the time column was rejected by the decoder: the sample has
                # no place on the time axis, so it is dropped as a whole
                _health.count_packet("bad_time")
                _rl_log("time", logging.WARNING, "packet with unusable model time dropped")
                return
            # before add_sample: a restart clears the window, and this sample opens the new one
            verdict = _note_live_sample(cfg, t_val)
            if verdict != "keep":
                _health.count_packet(verdict)
                _rl_log(verdict, logging.WARNING, "packet dropped (%s) at model time %.3f s", verdict, t_val)
                return
        elif live_data_seen():
            # the real target took over; never mix fake samples into its window
            return
        _history.add_sample(sample)
        if live:
            _slow.add(sample)
            with _readback_lock:
                for key in ("statusword", "assistance_level", "demand_torque"):
                    v = sample.get(key)
                    if isinstance(v, float) and math.isfinite(v):
                        _readback[key] = v
                _readback["_at"] = time.monotonic()

        now = time.monotonic()
        if now - _last_emit_ts < _SSE_PUSH_INTERVAL:
            return

        snapshot = _history.snapshot()
        if not snapshot:
            return
        _last_emit_ts = now

    meta = snapshot.get("meta")
    if meta is None:
        meta = {}
        snapshot["meta"] = meta
    meta["emitted_at"] = now
    with _link_lock:
        meta["session"] = _link_session
    snapshot["health"] = _health.snapshot()

    trimmed = meta.get("samples_trimmed", 0)
    if trimmed and _logger.isEnabledFor(logging.DEBUG):
        _logger.debug("trimmed %d samples (emit_points=%s)", trimmed, meta.get("emit_points"))

    # every connected dashboard gets this snapshot (not just one of them).
    # In the web app the receiver runs in its own process and the hook ships
    # the encoded snapshot to the main process (see live_worker.py).
    _publish_hook(snapshot)
