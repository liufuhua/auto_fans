from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass

from app.adb import AdbClient
from app.api_client import AutomationApiClient, AutomationApiError
from app.appium_server_manager import AppiumServerManager
from app.config import settings
from app.device_manager import BackendDeviceConfig
from app.device_monitor import DeviceMonitor
from app.device_status import DeviceStatusRegistry
from app.douyin_task_executor import DouyinAppiumExecutorConfig, DouyinAppiumTaskExecutor
from app.logger import configure_stdio_encoding
from app.task_runner import TaskRunner

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunnerConfig:
    devices: list[BackendDeviceConfig]
    monitor_devices: list[BackendDeviceConfig]
    publish_account_by_udid: dict[str, str]
    once: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Douyin automation tasks on multiple devices.")
    parser.add_argument(
        "--device",
        action="append",
        default=[],
        metavar="UDID,NAME,SYSTEM_PORT[,PUBLISH_ACCOUNT]",
        help=(
            "Device config. Repeat for multiple devices. "
            "Default mode reads enabled devices from backend admin."
        ),
    )
    parser.add_argument(
        "--publish-account",
        action="append",
        default=[],
        metavar="UDID=ACCOUNT",
        help="Override publish account for a device. Repeatable.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one polling iteration per device, then exit.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=float(settings.poll_interval_seconds),
    )
    parser.add_argument("--max-workers", type=int, default=settings.max_workers)
    parser.add_argument("--api-base-url", default=settings.api_base_url)
    parser.add_argument("--appium-server-url", default=settings.appium_server_url)
    parser.add_argument("--adb-path", default=settings.adb_path)
    parser.add_argument("--device-probe-interval-seconds", type=float, default=30)
    parser.add_argument("--device-config-refresh-seconds", type=float, default=10)
    parser.add_argument("--runtime-poll-interval-seconds", type=float, default=5)
    parser.add_argument(
        "--manage-appium-servers",
        action="store_true",
        help="Start and stop local Appium servers only for the active device batch.",
    )
    parser.add_argument(
        "--appium-batch-size",
        type=int,
        default=5,
        help="Maximum number of devices whose Appium servers are active at the same time.",
    )
    return parser


def parse_device_spec(value: str, index: int) -> tuple[BackendDeviceConfig, str]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) not in {3, 4} or not all(parts[:3]):
        raise ValueError(
            "Invalid --device value. Expected: UDID,NAME,SYSTEM_PORT[,PUBLISH_ACCOUNT]"
        )

    udid, name, system_port_text = parts[:3]
    try:
        system_port = int(system_port_text)
    except ValueError as exc:
        raise ValueError(f"Invalid systemPort for device {udid}: {system_port_text}") from exc

    publish_account = parts[3] if len(parts) == 4 and parts[3] else name
    return (
        BackendDeviceConfig(
            id=index,
            name=name,
            udid=udid,
            system_port=system_port,
            enabled_status="enabled",
            device_model="huawei_nova_se6",
        ),
        publish_account,
    )


def parse_publish_account_overrides(values: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("Invalid --publish-account value. Expected: UDID=ACCOUNT")
        udid, account = [part.strip() for part in value.split("=", 1)]
        if not udid or not account:
            raise ValueError("Invalid --publish-account value. Expected: UDID=ACCOUNT")
        overrides[udid] = account
    return overrides


def discover_backend_devices(
    api_client: AutomationApiClient,
    adb_path: str,
) -> tuple[list[BackendDeviceConfig], list[BackendDeviceConfig], dict[str, str]]:
    online_udids = {device.udid for device in AdbClient(adb_path).online_devices()}
    backend_devices = [
        BackendDeviceConfig(
            id=device.id,
            name=device.name,
            udid=device.udid,
            system_port=device.system_port,
            enabled_status=device.enabled_status,
            device_model=device.device_model,
            appium_server_url=device.appium_server_url,
        )
        for device in api_client.list_device_configs()
        if device.enabled_status == "enabled"
    ]
    devices = list(backend_devices)
    publish_accounts = {device.udid: device.name for device in backend_devices}

    missing_udids = sorted(online_udids - {device.udid for device in backend_devices})
    for udid in missing_udids:
        logger.warning("skip adb device not configured in backend: udid=%s", udid)
    for device in backend_devices:
        if device.udid not in online_udids:
            logger.info("backend device is offline: device=%s udid=%s", device.name, device.udid)

    return devices, backend_devices, publish_accounts


def build_runner_config(args: argparse.Namespace, api_client: AutomationApiClient) -> RunnerConfig:
    devices: list[BackendDeviceConfig] = []
    monitor_devices: list[BackendDeviceConfig] = []
    publish_account_by_udid: dict[str, str] = {}

    if args.device:
        for index, value in enumerate(args.device, start=1):
            device, publish_account = parse_device_spec(value, index)
            devices.append(device)
            monitor_devices.append(device)
            publish_account_by_udid[device.udid] = publish_account
    else:
        devices, monitor_devices, publish_account_by_udid = discover_backend_devices(
            api_client,
            args.adb_path,
        )

    publish_account_by_udid.update(parse_publish_account_overrides(args.publish_account))
    duplicate_udids = _duplicates([device.udid for device in monitor_devices])
    if duplicate_udids:
        raise RuntimeError(f"Duplicate device UDID in runner config: {', '.join(duplicate_udids)}")
    duplicate_ports = _duplicates([str(device.system_port) for device in monitor_devices])
    if duplicate_ports:
        raise RuntimeError(f"Duplicate systemPort in runner config: {', '.join(duplicate_ports)}")

    return RunnerConfig(
        devices=devices,
        monitor_devices=monitor_devices,
        publish_account_by_udid=publish_account_by_udid,
        once=bool(args.once),
    )


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def runner_config_signature(config: RunnerConfig) -> tuple[object, ...]:
    return (
        tuple(
            sorted(
                (
                    device.id,
                    device.name,
                    device.udid,
                    device.device_model,
                    device.system_port,
                    device.enabled_status,
                )
                for device in config.monitor_devices
            )
        ),
        tuple(
            sorted(
                (
                    device.id,
                    device.name,
                    device.udid,
                    device.device_model,
                    device.system_port,
                    device.enabled_status,
                )
                for device in config.devices
            )
        ),
        tuple(sorted(config.publish_account_by_udid.items())),
        config.once,
    )


class AutomationRuntimeSwitch:
    def __init__(self, api_client: AutomationApiClient, poll_interval_seconds: float) -> None:
        self.api_client = api_client
        self.poll_interval_seconds = poll_interval_seconds
        self._last_checked_at = 0.0
        self._enabled = False

    def enabled(self) -> bool:
        now = time.monotonic()
        if now - self._last_checked_at < self.poll_interval_seconds:
            return self._enabled
        self._last_checked_at = now
        try:
            self._enabled = self.api_client.get_automation_runtime().business_status == "running"
        except AutomationApiError as exc:
            logger.warning("failed to fetch automation runtime status: %s", exc)
            self._enabled = False
        return self._enabled

    def mark_stopped(self) -> None:
        self._enabled = False
        self._last_checked_at = 0.0


def reset_runtime_on_client_start(api_client: AutomationApiClient) -> None:
    try:
        api_client.auto_stop_automation_runtime(
            remark="automation client startup: require manual start",
            force=True,
        )
    except AutomationApiError as exc:
        logger.warning("failed to reset automation runtime on client startup: %s", exc)


def reset_runtime_on_client_shutdown(api_client: AutomationApiClient) -> None:
    try:
        api_client.auto_stop_automation_runtime(
            remark="automation client shutdown: require manual start",
            force=True,
        )
    except AutomationApiError as exc:
        logger.warning("failed to reset automation runtime on client shutdown: %s", exc)


def run(args: argparse.Namespace) -> None:
    configure_stdio_encoding()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    if args.max_workers < 1:
        raise RuntimeError("--max-workers must be >= 1")

    api_client = AutomationApiClient(args.api_base_url)
    status_registry = DeviceStatusRegistry()
    runtime_switch = AutomationRuntimeSwitch(
        api_client=api_client,
        poll_interval_seconds=args.runtime_poll_interval_seconds,
    )
    reset_runtime_on_client_start(api_client)
    runtime_switch.mark_stopped()
    executor = DouyinAppiumTaskExecutor(
        config=DouyinAppiumExecutorConfig(appium_server_url=args.appium_server_url)
    )
    appium_server_manager = (
        AppiumServerManager(default_server_url=args.appium_server_url)
        if args.manage_appium_servers
        else None
    )
    runner_config = build_runner_config(args, api_client)

    logger.info(
        "starting task runner: devices=%s once=%s maxWorkers=%s",
        [f"{device.name}/{device.udid}:{device.system_port}" for device in runner_config.devices],
        runner_config.once,
        args.max_workers,
    )
    if runner_config.once:
        runner = create_task_runner(
            args=args,
            api_client=api_client,
            executor=executor,
            status_registry=status_registry,
            runtime_switch=runtime_switch,
            runner_config=runner_config,
            appium_server_manager=appium_server_manager,
        )
        monitor = create_device_monitor(
            args=args,
            api_client=api_client,
            status_registry=status_registry,
            runner=runner,
            runner_config=runner_config,
        )
        monitor.probe_once()
        try:
            runner.run_once_for_each_device()
            monitor.probe_once()
        finally:
            reset_runtime_on_client_shutdown(api_client)
            runtime_switch.mark_stopped()
        return

    runner = create_task_runner(
        args=args,
        api_client=api_client,
        executor=executor,
        status_registry=status_registry,
        runtime_switch=runtime_switch,
        runner_config=runner_config,
        appium_server_manager=appium_server_manager,
    )
    monitor = create_device_monitor(
        args=args,
        api_client=api_client,
        status_registry=status_registry,
        runner=runner,
        runner_config=runner_config,
    )
    config_signature = runner_config_signature(runner_config)
    last_config_refresh_at = time.monotonic()

    try:
        monitor.probe_once()
        monitor.start()
        runner.start()
        while True:
            runner.stop_event.wait(1)
            if runner.stop_event.is_set():
                break
            if args.device:
                continue
            now = time.monotonic()
            if now - last_config_refresh_at < args.device_config_refresh_seconds:
                continue
            last_config_refresh_at = now
            try:
                refreshed_config = build_runner_config(args, api_client)
            except (AutomationApiError, RuntimeError) as exc:
                logger.warning("failed to refresh backend device config: %s", exc)
                continue
            refreshed_signature = runner_config_signature(refreshed_config)
            if refreshed_signature == config_signature:
                continue
            if runner_config.devices and runtime_switch.enabled():
                logger.info("device config changed while business is running; defer reload")
                continue

            logger.info(
                "device config changed, reloading task runner: devices=%s",
                [
                    f"{device.name}/{device.udid}:{device.system_port}"
                    for device in refreshed_config.devices
                ],
            )
            runner.stop()
            monitor.stop()
            runner_config = refreshed_config
            config_signature = refreshed_signature
            runner = create_task_runner(
                args=args,
                api_client=api_client,
                executor=executor,
                status_registry=status_registry,
                runtime_switch=runtime_switch,
                runner_config=runner_config,
                appium_server_manager=appium_server_manager,
            )
            monitor = create_device_monitor(
                args=args,
                api_client=api_client,
                status_registry=status_registry,
                runner=runner,
                runner_config=runner_config,
            )
            monitor.probe_once()
            monitor.start()
            runner.start()
    except KeyboardInterrupt:
        logger.info("received keyboard interrupt, stopping task runner")
    finally:
        runner.stop()
        monitor.stop()
        reset_runtime_on_client_shutdown(api_client)
        runtime_switch.mark_stopped()


def create_task_runner(
    *,
    args: argparse.Namespace,
    api_client: AutomationApiClient,
    executor: DouyinAppiumTaskExecutor,
    status_registry: DeviceStatusRegistry,
    runtime_switch: AutomationRuntimeSwitch,
    runner_config: RunnerConfig,
    appium_server_manager: AppiumServerManager | None = None,
) -> TaskRunner:
    return TaskRunner(
        devices=runner_config.devices,
        api_client=api_client,
        publish_account_by_udid=runner_config.publish_account_by_udid,
        poll_interval_seconds=args.poll_interval_seconds,
        max_workers=args.max_workers,
        executor=executor,
        status_registry=status_registry,
        business_enabled=runtime_switch.enabled,
        business_stopped=runtime_switch.mark_stopped,
        appium_server_manager=appium_server_manager,
        appium_batch_size=args.appium_batch_size,
    )


def create_device_monitor(
    *,
    args: argparse.Namespace,
    api_client: AutomationApiClient,
    status_registry: DeviceStatusRegistry,
    runner: TaskRunner,
    runner_config: RunnerConfig,
) -> DeviceMonitor:
    return DeviceMonitor(
        devices=runner_config.monitor_devices,
        adb_client=AdbClient(args.adb_path),
        api_client=api_client,
        status_registry=status_registry,
        interval_seconds=args.device_probe_interval_seconds,
        stop_event=runner.stop_event,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
