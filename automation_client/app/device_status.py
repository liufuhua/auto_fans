from __future__ import annotations

import threading


class DeviceStatusRegistry:
    """Tracks each local device status for heartbeat reporting."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._statuses: dict[str, str] = {}

    def set_status(self, udid: str, status: str) -> None:
        with self._lock:
            self._statuses[udid] = status

    def get_status(self, udid: str) -> str:
        with self._lock:
            return self._statuses.get(udid, "idle")
