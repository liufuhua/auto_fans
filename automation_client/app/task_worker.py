from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from app.api_client import (
    AutomationApiClient,
    AutomationApiError,
    AutomationTimingSettingResult,
    ClaimTaskResult,
    StartTaskResult,
)
from app.device_manager import BackendDeviceConfig
from app.device_status import DeviceStatusRegistry
from app.logger import configure_device_file_logger, log_context

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskExecutionResult:
    status: str
    video_link: str | None = None
    result_summary: str | None = None
    fail_reason: str | None = None
    screenshot_url: str | None = None
    log_url: str | None = None
    report_to_backend: bool = True

    @classmethod
    def success(
        cls,
        *,
        video_link: str | None = None,
        result_summary: str | None = None,
        screenshot_url: str | None = None,
        log_url: str | None = None,
    ) -> TaskExecutionResult:
        return cls(
            status="success",
            video_link=video_link,
            result_summary=result_summary,
            screenshot_url=screenshot_url,
            log_url=log_url,
        )

    @classmethod
    def failed(
        cls,
        *,
        fail_reason: str,
        screenshot_url: str | None = None,
        log_url: str | None = None,
    ) -> TaskExecutionResult:
        return cls(
            status="failed",
            fail_reason=fail_reason,
            screenshot_url=screenshot_url,
            log_url=log_url,
        )

    @classmethod
    def no_report(cls) -> TaskExecutionResult:
        return cls(status="skipped", report_to_backend=False)


@dataclass(frozen=True)
class TaskWorkerRunResult:
    claimed_task: bool
    no_task_reason: str | None = None
    should_stop_business: bool = False


class TaskExecutor(Protocol):
    def execute(
        self,
        *,
        task: ClaimTaskResult,
        start_result: StartTaskResult,
        device: BackendDeviceConfig,
        api_client: AutomationApiClient,
    ) -> TaskExecutionResult:
        pass


class NoopTaskExecutor:
    def execute(
        self,
        *,
        task: ClaimTaskResult,
        start_result: StartTaskResult,
        device: BackendDeviceConfig,
        api_client: AutomationApiClient,
    ) -> TaskExecutionResult:
        logger.info(
            "noop execute task: device=%s taskItemId=%s resultId=%s commentBankItemId=%s",
            device.name,
            task.task_item_id,
            start_result.result_id,
            task.comment_bank_item_id,
        )
        return TaskExecutionResult.success()


class TaskWorker:
    """Single-device task worker."""

    def __init__(
        self,
        *,
        device: BackendDeviceConfig,
        api_client: AutomationApiClient,
        publish_account: str,
        poll_interval_seconds: float,
        outside_runtime_window_poll_seconds: float = 300,
        executor: TaskExecutor | None = None,
        stop_event: threading.Event | None = None,
        runtime_dir: str | Path = "runtime",
        status_registry: DeviceStatusRegistry | None = None,
        business_enabled: object | None = None,
        business_stopped: object | None = None,
        auto_stop_after_task: bool = True,
        current_minute_provider: Callable[[], int] | None = None,
    ) -> None:
        self.device = device
        self.api_client = api_client
        self.publish_account = publish_account
        self.poll_interval_seconds = poll_interval_seconds
        self.outside_runtime_window_poll_seconds = outside_runtime_window_poll_seconds
        self.executor = executor or NoopTaskExecutor()
        self.stop_event = stop_event or threading.Event()
        self.status_registry = status_registry
        self.business_enabled = business_enabled
        self.business_stopped = business_stopped
        self.auto_stop_after_task = auto_stop_after_task
        self.current_minute_provider = current_minute_provider or (
            lambda: datetime.now().hour * 60 + datetime.now().minute
        )
        self.log_file_path = configure_device_file_logger(
            device_name=device.name,
            runtime_dir=runtime_dir,
        )

    def run(self, max_iterations: int | None = None) -> None:
        iteration = 0
        while not self.stop_event.is_set():
            if max_iterations is not None and iteration >= max_iterations:
                return
            iteration += 1

            self.run_once()

    def run_once(self) -> TaskWorkerRunResult:
        if not self._device_online():
            with self._device_log_context():
                logger.info(
                    "device offline, skip task claim: device=%s udid=%s",
                    self.device.name,
                    self.device.udid,
                )
                self._wait()
            return TaskWorkerRunResult(claimed_task=False, no_task_reason="device_offline")

        if not self._business_enabled():
            self._set_runtime_status_if_online("idle")
            with self._device_log_context():
                logger.info("business stopped: device=%s udid=%s", self.device.name, self.device.udid)
                self._wait()
            return TaskWorkerRunResult(
                claimed_task=False,
                no_task_reason="business_stopped",
                should_stop_business=True,
            )

        self._set_runtime_status_if_online("idle")
        with self._device_log_context():
            self.heartbeat("idle")
            if not self._runtime_window_allows_claim():
                logger.info(
                    "outside runtime window, skip task claim: device=%s udid=%s",
                    self.device.name,
                    self.device.udid,
                )
                self._wait_outside_runtime_window()
                return TaskWorkerRunResult(
                    claimed_task=False,
                    no_task_reason="outside_runtime_window",
                )
            try:
                task = self.api_client.claim_task(
                    udid=self.device.udid,
                    publish_account=self.publish_account,
                )
            except AutomationApiError as exc:
                logger.warning(
                    "failed to claim task: device=%s udid=%s error=%s",
                    self.device.name,
                    self.device.udid,
                    exc,
                )
                self._set_runtime_status_if_online("idle")
                self._wait()
                return TaskWorkerRunResult(claimed_task=False, no_task_reason="claim_error")
            if not task.has_task:
                no_task_reason = task.reason or "no_task"
                should_stop = no_task_reason in {"task_completed", "business_stopped"}
                self._set_runtime_status_if_online("idle")
                logger.info(
                    "no task: device=%s udid=%s reason=%s",
                    self.device.name,
                    self.device.udid,
                    no_task_reason,
                )
                self._wait()
                return TaskWorkerRunResult(
                    claimed_task=False,
                    no_task_reason=no_task_reason,
                    should_stop_business=should_stop,
                )

        object.__setattr__(task, "publish_account", self.publish_account)
        if task.doctors and (
            task.task_item_id is None or task.comment_bank_item_id is None
        ):
            return self._run_home_feed_task(task)

        with self._device_log_context():
            logger.warning(
                "legacy search task is no longer supported: device=%s taskItemId=%s",
                self.device.name,
                task.task_item_id,
            )
        return TaskWorkerRunResult(
            claimed_task=False,
            no_task_reason="legacy_search_task_unsupported",
        )

    def _run_home_feed_task(self, task: ClaimTaskResult) -> TaskWorkerRunResult:
        doctor_names = ", ".join(item.doctor_name for item in task.doctors)
        start_result = StartTaskResult(result_id=0, status="home_feed")
        with self._device_log_context(result_id=start_result.result_id):
            logger.info(
                "claimed home-feed doctor list task: device=%s doctors=%s",
                self.device.name,
                doctor_names,
            )
            self._set_runtime_status_if_online("running")
            try:
                execution_result = self._execute_task(task, start_result)
                if execution_result.report_to_backend:
                    logger.warning(
                        "home-feed executor returned reportable result without concrete "
                        "comment claim: device=%s status=%s",
                        self.device.name,
                        execution_result.status,
                    )
                else:
                    logger.info(
                        "home-feed executor handled backend report: device=%s status=%s",
                        self.device.name,
                        execution_result.status,
                    )
                return TaskWorkerRunResult(claimed_task=True)
            finally:
                self._set_runtime_status_if_online("idle")

    def heartbeat(self, runtime_status: str) -> None:
        self.api_client.heartbeat_device(
            udid=self.device.udid,
            device_name=self.device.name,
            system_port=self.device.system_port,
            runtime_status=runtime_status,
            remark="automation_client worker heartbeat",
        )

    def stop(self) -> None:
        self.stop_event.set()

    def _wait(self) -> None:
        self.stop_event.wait(self.poll_interval_seconds)

    def _wait_outside_runtime_window(self) -> None:
        self.stop_event.wait(self.outside_runtime_window_poll_seconds)

    def _business_enabled(self) -> bool:
        if self.business_enabled is None:
            return True
        if callable(self.business_enabled):
            return bool(self.business_enabled())
        return bool(self.business_enabled)

    def _runtime_window_allows_claim(self) -> bool:
        try:
            settings = self.api_client.list_timing_settings()
        except Exception as exc:  # noqa: BLE001 - timing lookup failure should not stop workers.
            logger.warning(
                "failed to fetch runtime window settings: device=%s error=%s",
                self.device.name,
                exc,
            )
            return True

        start_minute = _single_timing_value(settings, "runtime_start_time", 0)
        end_minute = _single_timing_value(settings, "runtime_end_time", 23 * 60)
        return is_minute_in_runtime_window(
            self.current_minute_provider(),
            start_minute,
            end_minute,
        )

    def _set_runtime_status(self, status: str) -> None:
        if self.status_registry is not None:
            self.status_registry.set_status(self.device.udid, status)

    def _set_runtime_status_if_online(self, status: str) -> None:
        if self._device_online():
            self._set_runtime_status(status)

    def _device_online(self) -> bool:
        if self.status_registry is None:
            return True
        return self.status_registry.get_status(self.device.udid) != "offline"

    def _auto_stop_business(self, remark: str, *, force: bool) -> None:
        try:
            runtime = self.api_client.auto_stop_automation_runtime(
                remark=f"{self.device.name}: {remark}",
                force=force,
            )
            if runtime.business_status == "stopped":
                self._mark_business_stopped()
        except Exception as exc:  # noqa: BLE001 - auto stop should not break worker cleanup.
            logger.warning(
                "failed to auto stop business: device=%s reason=%s error=%s",
                self.device.name,
                remark,
                exc,
            )

    def _mark_business_stopped(self) -> None:
        if self.business_stopped is None:
            return
        if callable(self.business_stopped):
            self.business_stopped()

    def _execute_task(
        self,
        task: ClaimTaskResult,
        start_result: StartTaskResult,
    ) -> TaskExecutionResult:
        try:
            return self.executor.execute(
                task=task,
                start_result=start_result,
                device=self.device,
                api_client=self.api_client,
            )
        except Exception as exc:  # noqa: BLE001 - task failures must be reported to backend.
            logger.exception(
                "task execution failed: device=%s taskItemId=%s resultId=%s",
                self.device.name,
                task.task_item_id,
                start_result.result_id,
            )
            return TaskExecutionResult.failed(fail_reason=str(exc))

    def _device_log_context(
        self,
        *,
        task_item_id: int | None = None,
        result_id: int | None = None,
    ):
        return log_context(
            device_name=self.device.name,
            udid=self.device.udid,
            task_item_id=task_item_id,
            result_id=result_id,
            log_file_path=self.log_file_path,
        )

def _single_timing_value(
    settings: list[AutomationTimingSettingResult],
    key: str,
    default: int,
) -> int:
    for item in settings:
        if item.key == key:
            return int(item.max_seconds)
    return default


def is_minute_in_runtime_window(
    current_minute: int,
    start_minute: int,
    end_minute: int,
) -> bool:
    minutes_per_day = 24 * 60
    current = current_minute % minutes_per_day
    start = start_minute % minutes_per_day
    end = end_minute % minutes_per_day
    if start == end:
        return True
    if start < end:
        return start <= current < end
    return current >= start or current < end
