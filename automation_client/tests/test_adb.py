from app.adb import parse_adb_devices
from app.device_manager import BackendDeviceConfig, DeviceManager


class FakeAdbClient:
    def online_devices(self):
        return [
            device
            for device in parse_adb_devices(
                """
List of devices attached
emulator-5554	device
emulator-5556	offline
abc123	device
"""
            )
            if device.online
        ]


def test_parse_adb_devices() -> None:
    devices = parse_adb_devices(
        """
List of devices attached
emulator-5554	device
emulator-5556	offline
abc123	unauthorized
"""
    )

    assert [device.udid for device in devices] == ["emulator-5554", "emulator-5556", "abc123"]
    assert [device.status for device in devices] == ["device", "offline", "unauthorized"]
    assert devices[0].online is True
    assert devices[1].online is False


def test_device_alignment() -> None:
    manager = DeviceManager(FakeAdbClient())  # type: ignore[arg-type]
    alignment = manager.align_with_backend(
        [
            BackendDeviceConfig(
                id=1,
                name="device_01",
                udid="emulator-5554",
                system_port=8201,
                enabled_status="enabled",
            ),
            BackendDeviceConfig(
                id=2,
                name="device_02",
                udid="emulator-5558",
                system_port=8202,
                enabled_status="enabled",
            ),
            BackendDeviceConfig(
                id=3,
                name="device_03",
                udid="disabled-device",
                system_port=8203,
                enabled_status="disabled",
            ),
        ]
    )

    assert [device.udid for device in alignment.online] == ["emulator-5554", "abc123"]
    assert [device.udid for device, _ in alignment.matched] == ["emulator-5554"]
    assert [device.udid for device in alignment.missing_in_backend] == ["abc123"]
    assert [device.udid for device in alignment.offline_configured] == ["emulator-5558"]
    assert [device.udid for device in alignment.disabled_configured] == ["disabled-device"]
