import threading
from typing import Any, Optional, Tuple


class SnapshotBroadcaster:
    """Hold the newest snapshot and wake every SSE client when it changes.

    The original single-slot queue handed each snapshot to only one client, so
    two open dashboards (laptop + tablet) split the updates between them. Here
    every client sees every snapshot; a slow client simply skips to the newest.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._seq = 0
        self._snap: Optional[Any] = None

    def publish(self, snapshot: Any) -> None:
        with self._cond:
            self._seq += 1
            self._snap = snapshot
            self._cond.notify_all()

    def clear(self) -> None:
        """Forget the current snapshot (used when the data source restarts)."""
        with self._cond:
            self._snap = None

    def wait_next(self, last_seq: int, timeout: float) -> Tuple[int, Optional[Any]]:
        """Return ``(seq, snapshot)`` newer than *last_seq*, or ``(last_seq, None)`` on timeout."""
        with self._cond:
            if self._seq == last_seq or self._snap is None:
                self._cond.wait(timeout)
            if self._seq != last_seq and self._snap is not None:
                return self._seq, self._snap
            return last_seq, None

    @property
    def seq(self) -> int:
        with self._cond:
            return self._seq


# newest snapshot for the SSE clients
snapshots = SnapshotBroadcaster()

# Limit concurrent SSE clients
MAX_CLIENTS = 5
_active_clients = 0
_client_lock = threading.Lock()
