from __future__ import annotations

import logging
import threading

from app.adb import AdbClient, AdbError
from app.api_client import AutomationApiClient, AutomationApiError
from app.device_manager import BackendDeviceConfig
from app.device_status import DeviceStatusRegistry

logger = logging.getLogger(__name__)


class DeviceMonitor:
    """Polls ADB and syncs device runtime status to backend."""

    def __init__(
        self,
        *,
        devices: list[BackendDeviceConfig],
        adb_client: AdbClient,
        api_client: AutomationApiClient,
        status_registry: DeviceStatusRegistry,
        interval_seconds: float = 30,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.devices = devices
        self.adb_client = adb_client
        self.api_client = api_client
        self.status_registry = status_registry
        self.interval_seconds = interval_seconds
        self.stop_event = stop_event or threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self.run, name="device-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds))
            self._thread = None

    def run(self) -> None:
        while not self.stop_event.is_set():
            self.probe_once()
            self.stop_event.wait(self.interval_seconds)

    def probe_once(self) -> None:
        try:
            online_udids = {device.udid for device in self.adb_client.online_devices()}
        except AdbError as exc:
            logger.warning("failed to probe adb devices: %s", exc)
            online_udids = set()

        for device in self.devices:
            if device.udid in online_udids:
                if self.status_registry.get_status(device.udid) == "offline":
                    self.status_registry.set_status(device.udid, "idle")
                runtime_status = self.status_registry.get_status(device.udid)
            else:
                runtime_status = "offline"
                self.status_registry.set_status(device.udid, runtime_status)
            try:
                self.api_client.heartbeat_device(
                    udid=device.udid,
                    device_name=device.name,
                    system_port=device.system_port,
                    runtime_status=runtime_status,
                    remark="automation_client device monitor",
                )
            except AutomationApiError as exc:
                logger.warning(
                    "failed to sync device status: device=%s udid=%s status=%s error=%s",
                    device.name,
                    device.udid,
                    runtime_status,
                    exc,
                )
