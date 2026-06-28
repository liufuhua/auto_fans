from __future__ import annotations

import logging
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app.api_client import AutomationApiClient
from app.appium_server_manager import AppiumServerManager
from app.device_manager import BackendDeviceConfig
from app.device_status import DeviceStatusRegistry
from app.task_worker import TaskExecutor, TaskWorker, TaskWorkerRunResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceRoundResult:
    executed_any: bool
    should_stop: bool


class TaskRunner:
    """Multi-device task runner."""

    def __init__(
        self,
        *,
        devices: list[BackendDeviceConfig],
        api_client: AutomationApiClient,
        publish_account_by_udid: dict[str, str],
        poll_interval_seconds: float,
        max_workers: int,
        executor: TaskExecutor | None = None,
        status_registry: DeviceStatusRegistry | None = None,
        business_enabled: object | None = None,
        business_stopped: object | None = None,
        appium_server_manager: AppiumServerManager | None = None,
        appium_batch_size: int = 0,
        execution_order_log_path: str | Path | None = None,
    ) -> None:
        self.devices = devices
        self.api_client = api_client
        self.publish_account_by_udid = publish_account_by_udid
        self.poll_interval_seconds = poll_interval_seconds
        self.max_workers = max_workers
        self.executor = executor
        self.status_registry = status_registry
        self.business_enabled = business_enabled
        self.business_stopped = business_stopped
        self.appium_server_manager = appium_server_manager
        self.appium_batch_size = appium_batch_size
        self.stop_event = threading.Event()
        self._pool: ThreadPoolExecutor | None = None
        self._futures: list[Future[None]] = []
        self._batch_thread: threading.Thread | None = None
        self._execution_order_log_path = (
            Path(execution_order_log_path)
            if execution_order_log_path is not None
            else self._default_execution_order_log_path()
        )
        self._execution_order_seq = 0
        self._execution_order_lock = threading.Lock()

    def start(self) -> None:
        if self._pool is not None or self._batch_thread is not None:
            return
        if not self.devices:
            logger.info("no online devices matched for task workers")
            return

        if self.appium_server_manager is not None:
            self._batch_thread = threading.Thread(
                target=self._run_batched,
                name="device-batch-runner",
                daemon=True,
            )
            self._batch_thread.start()
            logger.info(
                "started batched task runner: devices=%s batchSize=%s",
                len(self.devices),
                self._effective_batch_size(),
            )
            return

        worker_count = min(len(self.devices), self.max_workers)
        self._pool = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="device")
        for device in self.devices:
            worker = TaskWorker(
                device=device,
                api_client=self.api_client,
                publish_account=self.publish_account_by_udid.get(device.udid, device.name),
                poll_interval_seconds=self.poll_interval_seconds,
                executor=self.executor,
                stop_event=self.stop_event,
                status_registry=self.status_registry,
                business_enabled=self.business_enabled,
                business_stopped=self.business_stopped,
            )
            self._futures.append(self._pool.submit(worker.run))
            logger.info("started worker: device=%s udid=%s", device.name, device.udid)

    def stop(self) -> None:
        self.stop_event.set()
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=False)
            self._pool = None
        if self._batch_thread is not None:
            self._batch_thread.join(timeout=30)
            self._batch_thread = None
        if self.appium_server_manager is not None:
            self.appium_server_manager.stop_all()

    def run_once_for_each_device(self) -> None:
        if not self.devices:
            logger.info("no online devices matched for one-shot task workers")
            return
        with ThreadPoolExecutor(
            max_workers=min(len(self.devices), self.max_workers),
            thread_name_prefix="device-once",
        ) as pool:
            futures = []
            for device in self.devices:
                worker = TaskWorker(
                    device=device,
                    api_client=self.api_client,
                    publish_account=self.publish_account_by_udid.get(device.udid, device.name),
                    poll_interval_seconds=self.poll_interval_seconds,
                    executor=self.executor,
                    stop_event=threading.Event(),
                    status_registry=self.status_registry,
                    business_enabled=self.business_enabled,
                    business_stopped=self.business_stopped,
                )
                futures.append(pool.submit(worker.run, 1))
            for future in futures:
                future.result()

    def _run_batched(self) -> None:
        while not self.stop_event.is_set():
            if not self._business_enabled():
                self._set_idle_for_online_devices()
                self.stop_event.wait(self.poll_interval_seconds)
                continue

            try:
                round_result = self._run_device_round_once()
            except Exception:
                logger.exception("device round failed")
                self.stop_event.wait(self.poll_interval_seconds)
                continue

            if round_result.should_stop:
                logger.info("device round requested scheduler stop")
                self.stop_event.set()
                break

            if not round_result.executed_any:
                logger.info("device round claimed no task; waiting before next poll")
                self.stop_event.wait(self.poll_interval_seconds)

    # Legacy fixed-batch helpers kept temporarily for rollback/reference.
    def _run_batch_once(self, devices: list[BackendDeviceConfig]) -> None:
        if self.appium_server_manager is None:
            return
        logger.info(
            "starting device batch: devices=%s",
            [f"{device.name}/{device.udid}:{device.system_port}" for device in devices],
        )
        self.appium_server_manager.start_for_devices(devices)
        try:
            worker_count = min(len(devices), self.max_workers, self._effective_batch_size())
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="device-batch") as pool:
                futures = [
                    pool.submit(self._run_worker_once, device, False)
                    for device in devices
                ]
                for future in futures:
                    try:
                        future.result()
                    except Exception:
                        logger.exception("device worker failed in batch")
        finally:
            self.appium_server_manager.stop_for_devices(devices)
            logger.info(
                "finished device batch: devices=%s",
                [device.name for device in devices],
            )

    def _run_device_round_once(self) -> DeviceRoundResult:
        devices = self._online_devices(self.devices)
        if not devices:
            self.stop_event.wait(self.poll_interval_seconds)
            return DeviceRoundResult(executed_any=False, should_stop=False)

        worker_count = min(len(devices), self.max_workers, self._effective_batch_size())
        if worker_count <= 0:
            return DeviceRoundResult(executed_any=False, should_stop=False)

        executed_any = False
        should_stop = False

        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="device-slot") as pool:
            futures: dict[Future[TaskWorkerRunResult], BackendDeviceConfig] = {}
            running_udids: set[str] = set()
            exhausted_udids: set[str] = set()
            next_device_index = 0

            def next_available_device() -> BackendDeviceConfig | None:
                nonlocal next_device_index
                if len(exhausted_udids) + len(running_udids) >= len(devices):
                    return None

                for _ in range(len(devices)):
                    next_device = devices[next_device_index]
                    next_device_index = (next_device_index + 1) % len(devices)
                    if next_device.udid in exhausted_udids or next_device.udid in running_udids:
                        continue
                    if (
                        self.status_registry is not None
                        and self.status_registry.get_status(next_device.udid) == "offline"
                    ):
                        exhausted_udids.add(next_device.udid)
                        continue
                    return next_device
                return None

            def submit_next() -> None:
                if self.stop_event.is_set() or should_stop:
                    return
                next_device = next_available_device()
                if next_device is None:
                    return
                running_udids.add(next_device.udid)
                futures[pool.submit(self._run_single_device_once, next_device)] = next_device

            for _ in range(worker_count):
                submit_next()

            while futures and not self.stop_event.is_set():
                done_futures, _pending_futures = wait(
                    futures,
                    return_when=FIRST_COMPLETED,
                )
                for done in done_futures:
                    device = futures.pop(done)
                    running_udids.discard(device.udid)
                    try:
                        result = done.result()
                    except Exception:
                        logger.exception(
                            "device slot failed: device=%s udid=%s",
                            device.name,
                            device.udid,
                        )
                        result = TaskWorkerRunResult(
                            claimed_task=False,
                            no_task_reason="worker_error",
                        )

                    executed_any = executed_any or result.claimed_task
                    should_stop = should_stop or result.should_stop_business
                    if not result.claimed_task:
                        exhausted_udids.add(device.udid)
                    if not should_stop:
                        while len(futures) < worker_count:
                            previous_future_count = len(futures)
                            submit_next()
                            if len(futures) == previous_future_count:
                                break

        return DeviceRoundResult(executed_any=executed_any, should_stop=should_stop)

    def _run_single_device_once(self, device: BackendDeviceConfig) -> TaskWorkerRunResult:
        if self.appium_server_manager is None:
            return self._run_worker_once(device, False)

        self._write_execution_order_log(device)
        logger.info(
            "starting device slot: device=%s udid=%s systemPort=%s",
            device.name,
            device.udid,
            device.system_port,
        )
        self.appium_server_manager.start_for_devices([device])
        try:
            return self._run_worker_once(device, False)
        finally:
            self.appium_server_manager.stop_for_devices([device])
            logger.info("finished device slot: device=%s udid=%s", device.name, device.udid)

    def _write_execution_order_log(self, device: BackendDeviceConfig) -> None:
        with self._execution_order_lock:
            self._execution_order_seq += 1
            seq = self._execution_order_seq
            appium_url = self._device_appium_url(device)
            line = (
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                f"seq={seq} "
                f"device={device.name} "
                f"udid={device.udid} "
                f"systemPort={device.system_port} "
                f"appium={appium_url}\n"
            )
            self._execution_order_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._execution_order_log_path.open("a", encoding="utf-8") as file:
                file.write(line)

    def _device_appium_url(self, device: BackendDeviceConfig) -> str:
        if device.appium_server_url:
            return device.appium_server_url
        if self.appium_server_manager is not None:
            return getattr(self.appium_server_manager, "default_server_url", "")
        return ""

    @staticmethod
    def _default_execution_order_log_path() -> Path:
        project_root = Path(__file__).resolve().parents[2]
        return project_root / "logs" / f"device_execution_order-{date.today().isoformat()}.txt"

    def _run_worker_once(
        self,
        device: BackendDeviceConfig,
        auto_stop_after_task: bool,
    ) -> TaskWorkerRunResult:
        worker = TaskWorker(
            device=device,
            api_client=self.api_client,
            publish_account=self.publish_account_by_udid.get(device.udid, device.name),
            poll_interval_seconds=self.poll_interval_seconds,
            executor=self.executor,
            stop_event=threading.Event(),
            status_registry=self.status_registry,
            business_enabled=self.business_enabled,
            business_stopped=self.business_stopped,
            auto_stop_after_task=auto_stop_after_task,
        )
        return worker.run_once()

    def _device_batches(self) -> list[list[BackendDeviceConfig]]:
        batch_size = self._effective_batch_size()
        return [
            self.devices[index : index + batch_size]
            for index in range(0, len(self.devices), batch_size)
        ]

    def _effective_batch_size(self) -> int:
        if self.appium_batch_size > 0:
            return self.appium_batch_size
        return max(1, min(self.max_workers, len(self.devices)))

    def _business_enabled(self) -> bool:
        if self.business_enabled is None:
            return True
        if callable(self.business_enabled):
            return bool(self.business_enabled())
        return bool(self.business_enabled)

    def _online_devices(self, devices: list[BackendDeviceConfig]) -> list[BackendDeviceConfig]:
        if self.status_registry is None:
            return devices
        return [
            device
            for device in devices
            if self.status_registry.get_status(device.udid) != "offline"
        ]

    def _set_idle_for_online_devices(self) -> None:
        if self.status_registry is None:
            return
        for device in self.devices:
            if self.status_registry.get_status(device.udid) != "offline":
                self.status_registry.set_status(device.udid, "idle")
