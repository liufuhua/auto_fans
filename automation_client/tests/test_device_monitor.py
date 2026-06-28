from app.adb import AdbDevice
from app.device_manager import BackendDeviceConfig
from app.device_monitor import DeviceMonitor
from app.device_status import DeviceStatusRegistry


class FakeAdbClient:
    def online_devices(self):
        return [AdbDevice(udid="udid-1", status="device", raw="udid-1 device")]


class FakeApiClient:
    def __init__(self) -> None:
        self.heartbeats = []

    def heartbeat_device(self, **kwargs):
        self.heartbeats.append(kwargs)


def make_device(name: str, udid: str, system_port: int) -> BackendDeviceConfig:
    return BackendDeviceConfig(
        id=system_port,
        name=name,
        udid=udid,
        system_port=system_port,
        enabled_status="enabled",
    )


def test_device_monitor_syncs_online_and_offline_status() -> None:
    registry = DeviceStatusRegistry()
    registry.set_status("udid-1", "running")
    api_client = FakeApiClient()
    monitor = DeviceMonitor(
        devices=[
            make_device("device_01", "udid-1", 8201),
            make_device("device_02", "udid-2", 8202),
        ],
        adb_client=FakeAdbClient(),  # type: ignore[arg-type]
        api_client=api_client,  # type: ignore[arg-type]
        status_registry=registry,
        interval_seconds=30,
    )

    monitor.probe_once()

    assert registry.get_status("udid-2") == "offline"
    assert api_client.heartbeats == [
        {
            "udid": "udid-1",
            "device_name": "device_01",
            "system_port": 8201,
            "runtime_status": "running",
            "remark": "automation_client device monitor",
        },
        {
            "udid": "udid-2",
            "device_name": "device_02",
            "system_port": 8202,
            "runtime_status": "offline",
            "remark": "automation_client device monitor",
        },
    ]
