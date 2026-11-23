import os
import yaml
import struct
import subprocess
import platform
from typing import Dict, Any

from constants import CONFIG_FILE


def load_config(path: str | None = None) -> Dict[str, Any]:
    """Load the config: AFO_GUI_CONFIG if set, else config.yaml next to this file."""
    if path is None:
        path = os.environ.get("AFO_GUI_CONFIG") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), CONFIG_FILE
        )
    with open(path, "r", encoding="utf-8") as fp:
        return yaml.safe_load(fp)


def decode_packet(data: bytes, fmt: str, mapping: Dict[str, int]) -> Dict[str, float]:
    """Decode *data* (binary) into a dict using *fmt* and *mapping*."""
    values = struct.unpack(fmt, data)
    return {name: values[idx] for name, idx in mapping.items()}


def is_host_reachable(host: str) -> bool:
    """Return True if *host* responds to a single ping."""
    param = "-n" if platform.system().lower().startswith("win") else "-c"
    try:
        result = subprocess.run(
            ["ping", param, "1", host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except Exception:
        return False


def raise_priority(log=None) -> str:
    """Run this receiver process at HIGH priority on Windows (the 1 kHz / 100 Hz UDP
    readers must not be starved by the browser, MATLAB or a test run). A process
    started by a test or soak tool (which lowers itself to BELOW_NORMAL; the child
    inherits it) stays low, so a test app never competes with the real one."""
    try:
        import os
        import psutil
        p = psutil.Process()
        if os.name != "nt":
            return "skipped (not Windows)"
        if p.nice() in (psutil.BELOW_NORMAL_PRIORITY_CLASS, psutil.IDLE_PRIORITY_CLASS):
            msg = "kept low priority (started by a test tool)"
        else:
            p.nice(psutil.HIGH_PRIORITY_CLASS)
            msg = "priority HIGH"
    except Exception as exc:  # psutil missing / access denied: run as is
        msg = f"priority unchanged ({exc})"
    if log is not None:
        log.info("receiver process: %s", msg)
    return msg
