import argparse

import pytest

from app import main as app_main
from app.api_client import BackendDeviceConfigResult


def test_parse_device_spec_with_publish_account() -> None:
    device, publish_account = app_main.parse_device_spec(
        "R5CW11CKN0B,device_03,8203,device_03",
        1,
    )

    assert device.udid == "R5CW11CKN0B"
    assert device.name == "device_03"
    assert device.system_port == 8203
    assert publish_account == "device_03"


def test_parse_publish_account_overrides() -> None:
    overrides = app_main.parse_publish_account_overrides(["udid-1=账号1", "udid-2=账号2"])

    assert overrides == {"udid-1": "账号1", "udid-2": "账号2"}


def test_build_runner_config_rejects_duplicate_system_port() -> None:
    args = argparse.Namespace(
        device=[
            "udid-1,device_01,8201,账号1",
            "udid-2,device_02,8201,账号2",
        ],
        publish_account=[],
        adb_path="adb",
        once=True,
    )

    with pytest.raises(RuntimeError, match="Duplicate systemPort"):
        app_main.build_runner_config(args, FakeApiClient([]))


class FakeApiClient:
    def __init__(self, devices: list[BackendDeviceConfigResult]) -> None:
        self.devices = devices

    def list_device_configs(self) -> list[BackendDeviceConfigResult]:
        return self.devices


def test_build_runner_config_uses_backend_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAdbClient:
        def __init__(self, _adb_path: str) -> None:
            pass

        def online_devices(self):
            from app.adb import AdbDevice

            return [AdbDevice(udid="10AG3R2JNF001KK", status="device", raw="device")]

    monkeypatch.setattr(app_main, "AdbClient", FakeAdbClient)
    args = argparse.Namespace(
        device=[],
        publish_account=[],
        adb_path="adb",
        once=True,
    )
    api_client = FakeApiClient(
        [
            BackendDeviceConfigResult(
                id=6,
                name="device_02",
                udid="10AG3R2JNF001KK",
                system_port=8202,
                enabled_status="enabled",
                device_model="huawei_nova_se6",
            ),
            BackendDeviceConfigResult(
                id=7,
                name="device_03",
                udid="R5CW11CKN0B",
                system_port=8203,
                enabled_status="enabled",
            ),
        ]
    )

    config = app_main.build_runner_config(args, api_client)

    assert [device.name for device in config.devices] == ["device_02", "device_03"]
    assert [device.name for device in config.monitor_devices] == ["device_02", "device_03"]
    assert config.devices[0].device_model == "huawei_nova_se6"
    assert config.publish_account_by_udid == {
        "10AG3R2JNF001KK": "device_02",
        "R5CW11CKN0B": "device_03",
    }
    assert config.once is True


def test_build_runner_config_allows_no_online_backend_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAdbClient:
        def __init__(self, _adb_path: str) -> None:
            pass

        def online_devices(self):
            return []

    monkeypatch.setattr(app_main, "AdbClient", FakeAdbClient)
    args = argparse.Namespace(
        device=[],
        publish_account=[],
        adb_path="adb",
        once=True,
    )
    api_client = FakeApiClient(
        [
            BackendDeviceConfigResult(
                id=6,
                name="device_02",
                udid="10AG3R2JNF001KK",
                system_port=8202,
                enabled_status="enabled",
            )
        ]
    )

    config = app_main.build_runner_config(args, api_client)

    assert [device.name for device in config.devices] == ["device_02"]
    assert [device.name for device in config.monitor_devices] == ["device_02"]


def test_build_runner_config_allows_empty_backend_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAdbClient:
        def __init__(self, _adb_path: str) -> None:
            pass

        def online_devices(self):
            return []

    monkeypatch.setattr(app_main, "AdbClient", FakeAdbClient)
    args = argparse.Namespace(
        device=[],
        publish_account=[],
        adb_path="adb",
        once=False,
    )

    config = app_main.build_runner_config(args, FakeApiClient([]))

    assert config.devices == []
    assert config.monitor_devices == []


def test_runner_config_signature_changes_after_device_config_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAdbClient:
        def __init__(self, _adb_path: str) -> None:
            pass

        def online_devices(self):
            from app.adb import AdbDevice

            return [AdbDevice(udid="MYQUT19C05007064", status="device", raw="device")]

    monkeypatch.setattr(app_main, "AdbClient", FakeAdbClient)
    args = argparse.Namespace(
        device=[],
        publish_account=[],
        adb_path="adb",
        once=False,
    )

    before = app_main.build_runner_config(args, FakeApiClient([]))
    after = app_main.build_runner_config(
        args,
        FakeApiClient(
            [
                BackendDeviceConfigResult(
                    id=10,
                    name="device_06",
                    udid="MYQUT19C05007064",
                    system_port=8206,
                    enabled_status="enabled",
                )
            ]
        ),
    )

    assert app_main.runner_config_signature(before) != app_main.runner_config_signature(after)
    assert [device.name for device in after.devices] == ["device_06"]


def test_runner_config_signature_changes_after_device_model_update() -> None:
    before = app_main.RunnerConfig(
        devices=[
            app_main.BackendDeviceConfig(
                id=1,
                name="device_01",
                udid="udid-1",
                system_port=8201,
                enabled_status="enabled",
                device_model="vivo_y52",
            )
        ],
        monitor_devices=[],
        publish_account_by_udid={},
        once=False,
    )
    after = app_main.RunnerConfig(
        devices=[
            app_main.BackendDeviceConfig(
                id=1,
                name="device_01",
                udid="udid-1",
                system_port=8201,
                enabled_status="enabled",
                device_model="huawei_nova_se6",
            )
        ],
        monitor_devices=[],
        publish_account_by_udid={},
        once=False,
    )

    assert app_main.runner_config_signature(before) != app_main.runner_config_signature(after)
