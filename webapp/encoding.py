"""Strict JSON encoding of live snapshots (shared by the live worker process)."""
from __future__ import annotations

import json
import logging
import math
import time
from array import array

import numpy as np

_logger = logging.getLogger("afo.encoding")
_last_err = 0.0
_suppressed = 0


def json_default(obj):
    if isinstance(obj, np.ndarray):
        # NaN/Inf become null: valid JSON, and Plotly draws a gap there.
        # Sensor values are rounded to 6 significant digits (float32 carries ~7).
        vals = np.where(np.isfinite(obj), obj, np.nan).astype(np.float64)
        return [None if v != v else float(f"{v:.6g}") for v in vals.tolist()]
    if isinstance(obj, array):
        isfinite = math.isfinite
        return [v if isfinite(v) else None for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        v = float(obj)
        return v if math.isfinite(v) else None
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def encode_snapshot(sample) -> str | None:
    """Serialize one snapshot as strict JSON (allow_nan=False), or None.

    The browser's JSON.parse rejects NaN/Infinity tokens; with allow_nan=False
    such a frame can never be produced. A frame that still cannot be encoded
    is dropped and logged (rate-limited) instead of being sent.
    """
    global _last_err, _suppressed
    try:
        return json.dumps(sample, default=json_default, allow_nan=False)
    except (ValueError, TypeError, OverflowError):
        now = time.monotonic()
        if now - _last_err >= 1.0:
            extra = f" (+{_suppressed} similar)" if _suppressed else ""
            _logger.error("snapshot could not be encoded as JSON; frame skipped%s", extra, exc_info=True)
            _last_err = now
            _suppressed = 0
        else:
            _suppressed += 1
        return None
