# 运行时间段与抖音退出重启循环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让后台启动业务后，客户端按运行时间段调度在线空闲设备，并按“退出抖音时间 / 重启抖音时间”循环执行首页流任务。

**Architecture:** `TaskWorker` 负责设备在线、业务开关、运行时间段、心跳和 claim；`TaskRunner` 负责多设备轮转；`DouyinAppiumTaskExecutor` 负责首页流执行、按运行时长退出抖音、等待后重启并继续执行。时间段判断保留现有跨天算法，只调整等待策略和执行循环。

**Tech Stack:** Python、pytest、FastAPI 后端配置、Appium 自动化客户端、Vue 配置管理页面。

---

## 文件结构

- 修改：`automation_client/app/task_worker.py`
  - 负责运行时间段判断、不在时间段内的 5 分钟轮询、取消首页流自动停止业务。
- 修改：`automation_client/app/task_runner.py`
  - 负责把 5 分钟轮询参数传给 worker，并保证在线空闲设备持续轮转。
- 修改：`automation_client/app/douyin_task_executor.py`
  - 负责首页流内部按运行时长退出抖音、等待重启、重新进入首页流。
- 修改：`automation_client/tests/test_task_worker.py`
  - 覆盖跨天时间段、时间段外 5 分钟等待、不自动停止业务。
- 修改：`automation_client/tests/test_douyin_task_executor.py`
  - 覆盖退出抖音计时、命中后延迟退出、重启等待后继续。
- 保持：`api/app/services/automation_timing.py`
  - 已有 `runtime_start_time`、`runtime_end_time`、`douyin_exit_interval`、`douyin_reopen_interval`。
- 保持：`web_admin/src/views/AutomationTimingSettings.vue`
  - 已显示运行时间和退出/重启时间配置。

---

### Task 1: 确认并保护跨天运行时间段判断

**Files:**
- Modify: `automation_client/tests/test_task_worker.py`
- Review: `automation_client/app/task_worker.py`

- [ ] **Step 1: 确认现有函数**

现有函数保留：

```python
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
```

- [ ] **Step 2: 补充测试用例**

在 `automation_client/tests/test_task_worker.py` 中确认或补充：

```python
def test_runtime_window_allows_same_start_end_as_full_day() -> None:
    from app.task_worker import is_minute_in_runtime_window

    assert is_minute_in_runtime_window(0, 8 * 60, 8 * 60)
    assert is_minute_in_runtime_window(12 * 60, 8 * 60, 8 * 60)
    assert is_minute_in_runtime_window(23 * 60 + 59, 8 * 60, 8 * 60)
```

- [ ] **Step 3: 运行测试**

Run:

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest tests\test_task_worker.py -k runtime_window -q
```

Expected: runtime window 测试通过。

---

### Task 2: 时间段外固定 5 分钟轮询

**Files:**
- Modify: `automation_client/app/task_worker.py`
- Modify: `automation_client/app/task_runner.py`
- Test: `automation_client/tests/test_task_worker.py`

- [ ] **Step 1: 写失败测试**

在 `automation_client/tests/test_task_worker.py` 增加：

```python
def test_worker_waits_five_minutes_outside_runtime_window(monkeypatch) -> None:
    api_client = FakeApiClient([ClaimTaskResult(has_task=False)])
    api_client.timing_settings = [
        AutomationTimingSettingResult(
            key="runtime_start_time",
            label="运行开始时间",
            min_seconds=8 * 60,
            max_seconds=8 * 60,
        ),
        AutomationTimingSettingResult(
            key="runtime_end_time",
            label="运行结束时间",
            min_seconds=18 * 60,
            max_seconds=18 * 60,
        ),
    ]
    waits = []
    worker = TaskWorker(
        device=make_device(),
        api_client=api_client,  # type: ignore[arg-type]
        publish_account="account",
        poll_interval_seconds=1,
        outside_runtime_window_poll_seconds=300,
        executor=RecordingExecutor(),
        runtime_dir="runtime",
        current_minute_provider=lambda: 7 * 60,
    )
    monkeypatch.setattr(worker.stop_event, "wait", lambda seconds: waits.append(seconds))

    result = worker.run_once()

    assert result.claimed_task is False
    assert result.no_task_reason == "outside_runtime_window"
    assert api_client.claim_requests == []
    assert waits == [300]
```

- [ ] **Step 2: 实现参数**

在 `TaskWorker.__init__()` 增加参数：

```python
outside_runtime_window_poll_seconds: float = 300,
```

并赋值：

```python
self.outside_runtime_window_poll_seconds = outside_runtime_window_poll_seconds
```

- [ ] **Step 3: 增加等待函数**

在 `TaskWorker` 中新增：

```python
def _wait_outside_runtime_window(self) -> None:
    self.stop_event.wait(self.outside_runtime_window_poll_seconds)
```

- [ ] **Step 4: 替换时间段外等待**

在 `TaskWorker.run_once()` 的 `outside_runtime_window` 分支中，把：

```python
self._wait()
```

改成：

```python
self._wait_outside_runtime_window()
```

- [ ] **Step 5: TaskRunner 传参**

在 `TaskRunner.__init__()` 增加：

```python
outside_runtime_window_poll_seconds: float = 300,
```

并在创建 `TaskWorker` 的三个位置传入：

```python
outside_runtime_window_poll_seconds=self.outside_runtime_window_poll_seconds,
```

- [ ] **Step 6: 运行测试**

Run:

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest tests\test_task_worker.py -k outside_runtime_window -q
```

Expected: 时间段外等待 300 秒测试通过。

---

### Task 3: 首页流不自动停止后台业务

**Files:**
- Modify: `automation_client/app/task_worker.py`
- Test: `automation_client/tests/test_task_worker.py`

- [ ] **Step 1: 写失败测试**

新增测试：

```python
def test_home_feed_worker_does_not_auto_stop_business_after_iteration() -> None:
    task = ClaimTaskResult(
        has_task=True,
        doctors=[ClaimTaskDoctorResult(doctor_id=31, doctor_name="doctor-a")],
    )
    api_client = FakeApiClient([task])
    executor = RecordingExecutor(result=TaskExecutionResult.no_report())
    worker = TaskWorker(
        device=make_device(),
        api_client=api_client,  # type: ignore[arg-type]
        publish_account="account",
        poll_interval_seconds=0,
        executor=executor,
        runtime_dir="runtime",
        auto_stop_after_task=True,
    )

    result = worker.run_once()

    assert result.claimed_task is True
    assert api_client.auto_stop_requests == []
```

- [ ] **Step 2: 修改 `_run_home_feed_task()`**

删除或绕开首页流 finally 中的自动停止：

```python
finally:
    self._set_runtime_status_if_online("idle")
```

不要再执行：

```python
if self.auto_stop_after_task:
    self._auto_stop_business("task iteration finished", force=True)
```

- [ ] **Step 3: 修改无任务分支**

首页流 claim 返回 `has_task=False` 时，不再自动停止后台业务。保留日志和等待：

```python
if self.auto_stop_after_task and no_task_reason not in {"no_doctors", "outside_runtime_window"}:
    ...
```

推荐更直接：新首页流阶段彻底移除 `no task available` 自动停止。

- [ ] **Step 4: 运行测试**

Run:

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest tests\test_task_worker.py -k "auto_stop or no_task or home_feed" -q
```

Expected: 首页流不会自动停止后台业务。

---

### Task 4: 首页流执行器增加退出计时

**Files:**
- Modify: `automation_client/app/douyin_task_executor.py`
- Test: `automation_client/tests/test_douyin_task_executor.py`

- [ ] **Step 1: 新增计时辅助函数测试**

新增测试：

```python
def test_exit_interval_reached_uses_minutes(monkeypatch) -> None:
    config = DouyinAppiumExecutorConfig(douyin_exit_interval_minutes=20)
    executor = DouyinAppiumTaskExecutor(config=config)
    args = executor._build_args(make_device())

    assert not executor._exit_interval_reached(100.0, args, now=100.0 + 1199)
    assert executor._exit_interval_reached(100.0, args, now=100.0 + 1200)
```

- [ ] **Step 2: 实现 `_exit_interval_reached()`**

在 `DouyinAppiumTaskExecutor` 中新增：

```python
def _exit_interval_reached(
    self,
    cycle_started_at: float,
    args: argparse.Namespace,
    *,
    now: float | None = None,
) -> bool:
    interval_seconds = max(0, float(args.douyin_exit_interval_minutes) * 60)
    if interval_seconds <= 0:
        return False
    current = time.monotonic() if now is None else now
    return current - cycle_started_at >= interval_seconds
```

- [ ] **Step 3: 在首页流循环中使用**

在 `_execute_home_feed_task()` 中创建：

```python
cycle_started_at = time.monotonic()
```

每次观看视频后、匹配医生前检查：

```python
if self._exit_interval_reached(cycle_started_at, args):
    active_driver = self._restart_home_feed_cycle(driver=active_driver, args=args)
    cycle_started_at = time.monotonic()
    continue
```

- [ ] **Step 4: 命中医生后延迟退出**

在命中医生并执行 `_execute_home_feed_matched_comment()` 后检查：

```python
if self._exit_interval_reached(cycle_started_at, args):
    active_driver = self._restart_home_feed_cycle(driver=active_driver, args=args)
    cycle_started_at = time.monotonic()
    continue
```

这样命中目标时不会中断评论和上报，会等上报完成后再退出抖音。

- [ ] **Step 5: 运行测试**

Run:

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest tests\test_douyin_task_executor.py -k exit_interval -q
```

Expected: 退出计时测试通过。

---

### Task 5: 抖音退出后等待重启并继续执行

**Files:**
- Modify: `automation_client/app/douyin_task_executor.py`
- Test: `automation_client/tests/test_douyin_task_executor.py`

- [ ] **Step 1: 写重启循环测试**

新增测试：

```python
def test_restart_home_feed_cycle_force_stops_waits_and_reopens(monkeypatch) -> None:
    config = DouyinAppiumExecutorConfig(
        douyin_exit_interval_minutes=0,
        douyin_reopen_interval_minutes=20,
        after_open_seconds=0,
    )
    executor = DouyinAppiumTaskExecutor(config=config)
    args = executor._build_args(make_device())
    driver = FakeDriver([HOME_SOURCE])
    calls = []

    monkeypatch.setattr(executor, "_force_stop_douyin", lambda args: calls.append("force_stop"))
    monkeypatch.setattr(
        executor,
        "_ensure_douyin_home_page",
        lambda *, driver, actions, args: calls.append("home") or driver,
    )

    result_driver = executor._restart_home_feed_cycle(driver=driver, args=args)

    assert result_driver is driver
    assert calls == ["force_stop", "home"]
```

- [ ] **Step 2: 实现 `_restart_home_feed_cycle()`**

在 `DouyinAppiumTaskExecutor` 中新增：

```python
def _restart_home_feed_cycle(self, *, driver, args: argparse.Namespace):
    self._force_stop_douyin(args)
    actions = self._build_actions(
        driver=driver,
        args=args,
        task_id="worker_home_feed_restart_cycle",
    )
    return self._ensure_douyin_home_page(driver=driver, actions=actions, args=args)
```

说明：`_force_stop_douyin()` 设置 `_douyin_reopen_pending=True`；`_ensure_douyin_home_page()` 已通过 `_wait_before_reopen_douyin_if_needed()` 等待 `douyin_reopen_interval_minutes`。

- [ ] **Step 3: 调整首页流循环**

在 `_execute_home_feed_task()` 中，退出时间到达后调用：

```python
active_driver = self._restart_home_feed_cycle(driver=active_driver, args=args)
cycle_started_at = time.monotonic()
```

- [ ] **Step 4: 避免单次任务结束就 return**

当前命中一次医生后会：

```python
return TaskExecutionResult.no_report()
```

改为继续循环：

```python
continue
```

让设备在运行时间段内持续刷首页流，由外层 `TaskWorker` 的下一轮时间段判断决定是否继续 claim。

- [ ] **Step 5: 运行测试**

Run:

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest tests\test_douyin_task_executor.py -q
```

Expected: 执行器测试全部通过。

---

### Task 6: 最终验证

**Files:**
- Test: `automation_client/tests/test_task_worker.py`
- Test: `automation_client/tests/test_douyin_task_executor.py`
- Test: `api/tests/test_automation_timing_defaults.py`
- Test: `web_admin`

- [ ] **Step 1: 后端配置测试**

Run:

```powershell
cd E:\auto_fans\api
.\.venv\Scripts\python.exe -m pytest tests\test_automation_timing_defaults.py -q
```

Expected: 通过。

- [ ] **Step 2: 客户端 worker 测试**

Run:

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest tests\test_task_worker.py -q
```

Expected: 通过。

- [ ] **Step 3: 客户端执行器测试**

Run:

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest tests\test_douyin_task_executor.py -q
```

Expected: 通过。

- [ ] **Step 4: 前端类型检查与构建**

Run:

```powershell
cd E:\auto_fans\web_admin
npm run typecheck
npm run build
```

Expected: `typecheck` 和 `build` 通过。

- [ ] **Step 5: 人工联调观察点**

启动服务后观察：

- 后台业务启动但不在运行时间段：设备保持空闲，每 5 分钟轮询。
- 到运行开始时间：在线空闲设备开始执行首页流。
- 首页流运行到 `退出抖音时间`：未命中时直接退出；命中时等上报完成后退出。
- 退出后等待 `重启抖音时间`，重新打开抖音继续首页流。
- 后台点击停止业务：下一轮不再 claim 和执行。

