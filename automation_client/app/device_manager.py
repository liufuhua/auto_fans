from __future__ import annotations

from dataclasses import dataclass

from app.adb import AdbClient, AdbDevice
from app.api_client import AutomationApiClient, DeviceHeartbeatResult


@dataclass(frozen=True)
class BackendDeviceConfig:
    id: int
    name: str
    udid: str
    system_port: int
    enabled_status: str
    device_model: str = "huawei_nova_se6"
    appium_server_url: str | None = None


@dataclass(frozen=True)
class DeviceAlignment:
    online: list[AdbDevice]
    matched: list[tuple[AdbDevice, BackendDeviceConfig]]
    missing_in_backend: list[AdbDevice]
    offline_configured: list[BackendDeviceConfig]
    disabled_configured: list[BackendDeviceConfig]


class DeviceManager:
    """Coordinates local Android devices."""

    def __init__(self, adb_client: AdbClient) -> None:
        self.adb_client = adb_client

    def discover_online_devices(self) -> list[AdbDevice]:
        return self.adb_client.online_devices()

    def align_with_backend(self, backend_devices: list[BackendDeviceConfig]) -> DeviceAlignment:
        online_devices = self.discover_online_devices()
        online_by_udid = {device.udid: device for device in online_devices}
        backend_by_udid = {device.udid: device for device in backend_devices}

        matched = [
            (online_device, backend_by_udid[online_device.udid])
            for online_device in online_devices
            if online_device.udid in backend_by_udid
            and backend_by_udid[online_device.udid].enabled_status == "enabled"
        ]
        missing_in_backend = [
            online_device
            for online_device in online_devices
            if online_device.udid not in backend_by_udid
        ]
        offline_configured = [
            backend_device
            for backend_device in backend_devices
            if backend_device.enabled_status == "enabled"
            and backend_device.udid not in online_by_udid
        ]
        disabled_configured = [
            backend_device
            for backend_device in backend_devices
            if backend_device.enabled_status == "disabled"
        ]

        return DeviceAlignment(
            online=online_devices,
            matched=matched,
            missing_in_backend=missing_in_backend,
            offline_configured=offline_configured,
            disabled_configured=disabled_configured,
        )

    def heartbeat_matched_devices(
        self,
        api_client: AutomationApiClient,
        backend_devices: list[BackendDeviceConfig],
        runtime_status: str = "idle",
    ) -> list[DeviceHeartbeatResult]:
        alignment = self.align_with_backend(backend_devices)
        results: list[DeviceHeartbeatResult] = []
        for _adb_device, backend_device in alignment.matched:
            results.append(
                api_client.heartbeat_device(
                    udid=backend_device.udid,
                    device_name=backend_device.name,
                    system_port=backend_device.system_port,
                    runtime_status=runtime_status,
                    remark="automation_client heartbeat",
                )
            )
        return results
