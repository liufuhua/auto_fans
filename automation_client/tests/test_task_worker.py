from app.api_client import (
    AutomationRuntimeState,
    AutomationTimingSettingResult,
    ClaimTaskDoctorResult,
    ClaimTaskResult,
    ReportTaskResult,
    StartTaskResult,
)
from app.device_manager import BackendDeviceConfig
from app.device_status import DeviceStatusRegistry
from app.task_runner import TaskRunner
from app.task_worker import TaskExecutionResult, TaskWorker, TaskWorkerRunResult


class FakeApiClient:
    def __init__(self, claims):
        self.claims = list(claims)
        self.heartbeats = []
        self.claim_requests = []
        self.start_requests = []
        self.report_requests = []
        self.auto_stop_requests = []
        self.report_error = None
        self.timing_settings = []

    def heartbeat_device(self, **kwargs):
        self.heartbeats.append(kwargs)

    def claim_task(self, **kwargs):
        self.claim_requests.append(kwargs)
        if self.claims:
            return self.claims.pop(0)
        return ClaimTaskResult(has_task=False)

    def start_task(self, **kwargs):
        self.start_requests.append(kwargs)
        return StartTaskResult(result_id=8, status="running")

    def report_task(self, **kwargs):
        self.report_requests.append(kwargs)
        if self.report_error is not None:
            raise self.report_error
        return ReportTaskResult(result_id=kwargs["result_id"], status=kwargs["status"])

    def auto_stop_automation_runtime(self, **kwargs):
        self.auto_stop_requests.append(kwargs)
        return AutomationRuntimeState(business_status="stopped")

    def list_timing_settings(self):
        return self.timing_settings


class RecordingExecutor:
    def __init__(self, result=None, error=None):
        self.tasks = []
        self.result = result or TaskExecutionResult.success(video_link="https://v.douyin.com/test/")
        self.error = error
        self.cleanup_calls = []

    def execute(self, *, task, start_result, device, api_client):
        self.tasks.append((task, start_result, device, api_client))
        if self.error is not None:
            raise self.error
        return self.result

    def cleanup_after_report_failure(self, *, device, error):
        self.cleanup_calls.append((device, error))


class FakeAppiumServerManager:
    def __init__(self):
        self.started = []
        self.stopped = []
        self.stop_all_calls = 0

    def start_for_devices(self, devices):
        self.started.append([device.udid for device in devices])

    def stop_for_devices(self, devices):
        self.stopped.append([device.udid for device in devices])

    def stop_all(self):
        self.stop_all_calls += 1


class SequencedRunner(TaskRunner):
    def __init__(self, *args, run_results, **kwargs):
        super().__init__(*args, **kwargs)
        self.run_results = list(run_results)
        self.run_order = []

    def _run_worker_once(self, device, auto_stop_after_task):
        self.run_order.append((device.udid, auto_stop_after_task))
        if not self.run_results:
            return TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty")
        return self.run_results.pop(0)


def make_device(name="device_01", udid="FMR0223830012928") -> BackendDeviceConfig:
    return BackendDeviceConfig(
        id=1,
        name=name,
        udid=udid,
        system_port=8201,
        enabled_status="enabled",
    )


def test_worker_waits_when_no_task() -> None:
    api_client = FakeApiClient([ClaimTaskResult(has_task=False)])
    executor = RecordingExecutor()
    stopped = []
    worker = TaskWorker(
        device=make_device(),
        api_client=api_client,  # type: ignore[arg-type]
        publish_account="测试账号01",
        poll_interval_seconds=0,
        executor=executor,
        runtime_dir="runtime",
        business_stopped=lambda: stopped.append(True),
    )

    worker.run(max_iterations=1)

    assert executor.tasks == []
    assert len(api_client.heartbeats) == 1
    assert len(api_client.claim_requests) == 1
    assert api_client.start_requests == []
    assert api_client.report_requests == []
    assert api_client.auto_stop_requests == [
        {"remark": "device_01: no task available", "force": False}
    ]
    assert stopped == [True]


def test_worker_rejects_legacy_search_task_without_start_or_report() -> None:
    task = ClaimTaskResult(
        has_task=True,
        task_id=1,
        task_item_id=2,
        doctor_id=3,
        doctor_name="doctor",
        keyword_id=4,
        keyword="keyword",
        search_word="keyword",
        comment_bank_item_id=5,
        comment_content="comment",
    )
    api_client = FakeApiClient([task])
    executor = RecordingExecutor()
    worker = TaskWorker(
        device=make_device(),
        api_client=api_client,  # type: ignore[arg-type]
        publish_account="account",
        poll_interval_seconds=0,
        executor=executor,
        runtime_dir="runtime",
    )

    result = worker.run_once()

    assert result.claimed_task is False
    assert result.no_task_reason == "legacy_search_task_unsupported"
    assert api_client.start_requests == []
    assert api_client.report_requests == []
    assert executor.tasks == []


def test_worker_executes_doctor_list_task_without_old_start_or_report() -> None:
    task = ClaimTaskResult(
        has_task=True,
        doctors=[
            ClaimTaskDoctorResult(doctor_id=31, doctor_name="doctor-a"),
            ClaimTaskDoctorResult(doctor_id=32, doctor_name="doctor-b"),
        ],
    )
    api_client = FakeApiClient([task])
    executor = RecordingExecutor(result=TaskExecutionResult.no_report())
    device = make_device()
    worker = TaskWorker(
        device=device,
        api_client=api_client,  # type: ignore[arg-type]
        publish_account="account",
        poll_interval_seconds=0,
        executor=executor,
        runtime_dir="runtime",
    )

    result = worker.run_once()

    assert result.claimed_task is True
    assert result.no_task_reason is None
    assert api_client.start_requests == []
    assert api_client.report_requests == []
    assert len(executor.tasks) == 1
    assert executor.tasks[0][0] is task
    assert executor.tasks[0][0].doctors == task.doctors
    assert executor.tasks[0][1] == StartTaskResult(result_id=0, status="home_feed")
    assert executor.tasks[0][2] is device


def test_worker_run_once_returns_no_task_reason() -> None:
    api_client = FakeApiClient([ClaimTaskResult(has_task=False, reason="device_pool_empty")])
    worker = TaskWorker(
        device=make_device(),
        api_client=api_client,  # type: ignore[arg-type]
        publish_account="account",
        poll_interval_seconds=0,
        executor=RecordingExecutor(),
        runtime_dir="runtime",
    )

    result = worker.run_once()

    assert result.claimed_task is False
    assert result.no_task_reason == "device_pool_empty"
    assert result.should_stop_business is False


def test_worker_does_not_claim_when_business_stopped() -> None:
    api_client = FakeApiClient([ClaimTaskResult(has_task=False)])
    executor = RecordingExecutor()
    registry = DeviceStatusRegistry()
    worker = TaskWorker(
        device=make_device(),
        api_client=api_client,  # type: ignore[arg-type]
        publish_account="测试账号01",
        poll_interval_seconds=0,
        executor=executor,
        runtime_dir="runtime",
        status_registry=registry,
        business_enabled=lambda: False,
    )

    worker.run(max_iterations=1)

    assert registry.get_status("FMR0223830012928") == "idle"
    assert api_client.heartbeats == []
    assert api_client.claim_requests == []
    assert executor.tasks == []
    assert api_client.auto_stop_requests == []


def test_worker_does_not_claim_outside_runtime_window() -> None:
    api_client = FakeApiClient([ClaimTaskResult(has_task=False)])
    api_client.timing_settings = [
        AutomationTimingSettingResult(
            key="runtime_start_time",
            label="运行开始时间",
            min_seconds=8 * 60 + 30,
            max_seconds=8 * 60 + 30,
        ),
        AutomationTimingSettingResult(
            key="runtime_end_time",
            label="运行结束时间",
            min_seconds=18 * 60,
            max_seconds=18 * 60,
        ),
    ]
    executor = RecordingExecutor()
    worker = TaskWorker(
        device=make_device(),
        api_client=api_client,  # type: ignore[arg-type]
        publish_account="测试账号01",
        poll_interval_seconds=0,
        executor=executor,
        runtime_dir="runtime",
        current_minute_provider=lambda: 18 * 60 + 1,
    )

    result = worker.run_once()

    assert result.claimed_task is False
    assert result.no_task_reason == "outside_runtime_window"
    assert api_client.heartbeats[0]["runtime_status"] == "idle"
    assert api_client.claim_requests == []
    assert executor.tasks == []


def test_runtime_window_allows_specific_minutes_inside_cross_day_range() -> None:
    from app.task_worker import is_minute_in_runtime_window

    assert is_minute_in_runtime_window(23 * 60 + 15, 22 * 60 + 30, 6 * 60)
    assert is_minute_in_runtime_window(5 * 60 + 59, 22 * 60 + 30, 6 * 60)
    assert not is_minute_in_runtime_window(21 * 60 + 59, 22 * 60 + 30, 6 * 60)
    assert not is_minute_in_runtime_window(6 * 60, 22 * 60 + 30, 6 * 60)


def test_worker_does_not_claim_when_device_offline() -> None:
    api_client = FakeApiClient([ClaimTaskResult(has_task=False)])
    executor = RecordingExecutor()
    registry = DeviceStatusRegistry()
    registry.set_status("FMR0223830012928", "offline")
    worker = TaskWorker(
        device=make_device(),
        api_client=api_client,  # type: ignore[arg-type]
        publish_account="测试账号01",
        poll_interval_seconds=0,
        executor=executor,
        runtime_dir="runtime",
        status_registry=registry,
        business_enabled=lambda: True,
    )

    worker.run(max_iterations=1)

    assert registry.get_status("FMR0223830012928") == "offline"
    assert api_client.heartbeats == []
    assert api_client.claim_requests == []
    assert executor.tasks == []
    assert api_client.auto_stop_requests == []


def test_runner_runs_once_for_each_device() -> None:
    devices = [
        make_device(name="device_01", udid="udid-1"),
        make_device(name="device_02", udid="udid-2"),
    ]
    api_client = FakeApiClient([ClaimTaskResult(has_task=False), ClaimTaskResult(has_task=False)])
    runner = TaskRunner(
        devices=devices,
        api_client=api_client,  # type: ignore[arg-type]
        publish_account_by_udid={"udid-1": "账号1", "udid-2": "账号2"},
        poll_interval_seconds=0,
        max_workers=8,
    )

    runner.run_once_for_each_device()

    assert {item["udid"] for item in api_client.heartbeats} == {"udid-1", "udid-2"}
    assert {item["publish_account"] for item in api_client.claim_requests} == {"账号1", "账号2"}


def test_batched_runner_starts_and_stops_one_device_per_slot() -> None:
    devices = [make_device(name=f"device_{i}", udid=f"udid-{i}") for i in range(1, 6)]
    appium_manager = FakeAppiumServerManager()
    runner = SequencedRunner(
        devices=devices,
        api_client=FakeApiClient([]),  # type: ignore[arg-type]
        publish_account_by_udid={},
        poll_interval_seconds=0,
        max_workers=8,
        appium_server_manager=appium_manager,  # type: ignore[arg-type]
        appium_batch_size=2,
        business_enabled=lambda: False,
        run_results=[
            TaskWorkerRunResult(claimed_task=True),
            TaskWorkerRunResult(claimed_task=True),
            TaskWorkerRunResult(claimed_task=True),
            TaskWorkerRunResult(claimed_task=True),
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
        ],
    )

    runner._run_device_round_once()

    assert appium_manager.started[:5] == [
        ["udid-1"],
        ["udid-2"],
        ["udid-3"],
        ["udid-4"],
        ["udid-5"],
    ]
    assert appium_manager.stopped[:5] == [
        ["udid-1"],
        ["udid-2"],
        ["udid-3"],
        ["udid-4"],
        ["udid-5"],
    ]
    assert [udid for udid, _auto_stop in runner.run_order] == [
        "udid-1",
        "udid-2",
        "udid-3",
        "udid-4",
        "udid-5",
        "udid-1",
        "udid-2",
        "udid-3",
        "udid-4",
    ]
    assert all(auto_stop is False for _udid, auto_stop in runner.run_order)


def test_batched_runner_cycles_back_to_available_devices_before_round_ends() -> None:
    devices = [make_device(name=f"device_{i}", udid=f"udid-{i}") for i in range(1, 4)]
    appium_manager = FakeAppiumServerManager()
    runner = SequencedRunner(
        devices=devices,
        api_client=FakeApiClient([]),  # type: ignore[arg-type]
        publish_account_by_udid={},
        poll_interval_seconds=0,
        max_workers=8,
        appium_server_manager=appium_manager,  # type: ignore[arg-type]
        appium_batch_size=2,
        business_enabled=lambda: True,
        run_results=[
            TaskWorkerRunResult(claimed_task=True),
            TaskWorkerRunResult(claimed_task=True),
            TaskWorkerRunResult(claimed_task=True),
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
        ],
    )

    result = runner._run_device_round_once()

    assert result.executed_any is True
    assert [udid for udid, _auto_stop in runner.run_order] == [
        "udid-1",
        "udid-2",
        "udid-3",
        "udid-1",
        "udid-2",
        "udid-3",
    ]


def test_batched_runner_writes_device_execution_order_log(tmp_path) -> None:
    devices = [make_device(name=f"device_{i}", udid=f"udid-{i}") for i in range(1, 3)]
    order_log_path = tmp_path / "device_execution_order.log"
    runner = SequencedRunner(
        devices=devices,
        api_client=FakeApiClient([]),  # type: ignore[arg-type]
        publish_account_by_udid={},
        poll_interval_seconds=0,
        max_workers=8,
        appium_server_manager=FakeAppiumServerManager(),  # type: ignore[arg-type]
        appium_batch_size=1,
        business_enabled=lambda: True,
        execution_order_log_path=order_log_path,
        run_results=[
            TaskWorkerRunResult(claimed_task=True),
            TaskWorkerRunResult(claimed_task=True),
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
        ],
    )

    runner._run_device_round_once()

    lines = order_log_path.read_text(encoding="utf-8").splitlines()
    assert "seq=1" in lines[0]
    assert "device=device_1" in lines[0]
    assert "udid=udid-1" in lines[0]
    assert "systemPort=8201" in lines[0]
    assert "seq=2" in lines[1]
    assert "device=device_2" in lines[1]
    assert "seq=3" in lines[2]
    assert "device=device_1" in lines[2]


def test_batched_runner_stops_round_when_task_completed_reason_seen() -> None:
    devices = [make_device(name=f"device_{i}", udid=f"udid-{i}") for i in range(1, 4)]
    appium_manager = FakeAppiumServerManager()
    runner = SequencedRunner(
        devices=devices,
        api_client=FakeApiClient([]),  # type: ignore[arg-type]
        publish_account_by_udid={},
        poll_interval_seconds=0,
        max_workers=8,
        appium_server_manager=appium_manager,  # type: ignore[arg-type]
        appium_batch_size=2,
        business_enabled=lambda: True,
        run_results=[
            TaskWorkerRunResult(
                claimed_task=False,
                no_task_reason="task_completed",
                should_stop_business=True,
            ),
        ],
    )

    result = runner._run_device_round_once()

    assert result.should_stop is True
    assert appium_manager.started == [["udid-1"], ["udid-2"]]
    assert appium_manager.stopped == [["udid-1"], ["udid-2"]]


def test_batched_runner_waits_when_full_round_claims_no_task(monkeypatch) -> None:
    devices = [make_device(name=f"device_{i}", udid=f"udid-{i}") for i in range(1, 3)]
    appium_manager = FakeAppiumServerManager()
    waits = []
    runner = SequencedRunner(
        devices=devices,
        api_client=FakeApiClient([]),  # type: ignore[arg-type]
        publish_account_by_udid={},
        poll_interval_seconds=3,
        max_workers=8,
        appium_server_manager=appium_manager,  # type: ignore[arg-type]
        appium_batch_size=2,
        business_enabled=lambda: True,
        run_results=[
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
            TaskWorkerRunResult(claimed_task=False, no_task_reason="device_pool_empty"),
        ],
    )

    original_wait = runner.stop_event.wait

    def fake_wait(seconds):
        waits.append(seconds)
        runner.stop_event.set()
        return original_wait(0)

    monkeypatch.setattr(runner.stop_event, "wait", fake_wait)

    runner._run_batched()

    assert waits == [3]
    assert appium_manager.started == [["udid-1"], ["udid-2"]]


def test_device_round_respects_effective_slots() -> None:
    devices = [make_device(name=f"device_{i}", udid=f"udid-{i}") for i in range(1, 5)]
    appium_manager = FakeAppiumServerManager()
    active = 0
    max_active = 0
    calls_by_udid = {}

    class SlowSequencedRunner(SequencedRunner):
        def _run_worker_once(self, device, auto_stop_after_task):
            nonlocal active, max_active
            calls_by_udid[device.udid] = calls_by_udid.get(device.udid, 0) + 1
            active += 1
            max_active = max(max_active, active)
            try:
                if calls_by_udid[device.udid] == 1:
                    return TaskWorkerRunResult(claimed_task=True)
                return TaskWorkerRunResult(
                    claimed_task=False,
                    no_task_reason="device_pool_empty",
                )
            finally:
                active -= 1

    runner = SlowSequencedRunner(
        devices=devices,
        api_client=FakeApiClient([]),  # type: ignore[arg-type]
        publish_account_by_udid={},
        poll_interval_seconds=0,
        max_workers=1,
        appium_server_manager=appium_manager,  # type: ignore[arg-type]
        appium_batch_size=3,
        business_enabled=lambda: True,
        run_results=[],
    )

    runner._run_device_round_once()

    assert max_active == 1
