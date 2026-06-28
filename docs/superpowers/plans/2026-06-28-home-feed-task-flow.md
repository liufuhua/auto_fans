# 抖音首页流任务执行改造计划

> **给执行代理的说明：** 实施本计划时，需要使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，并按任务逐项勾选执行。

**目标：** 将现有“领取固定任务后搜索医生视频”的流程，改造成“首页观看视频、匹配作者昵称、命中后领取评论、执行互动并持续上报”的流程。

**架构：** 启动入口和设备调度层保持不变。后端 `claim` 改为返回可匹配的医生昵称列表；客户端在首页流中识别视频作者，命中医生后再向后端领取一条该医生的未使用评论；互动完成后统一归属到 `task_id=1` 上报。

**技术栈：** FastAPI、SQLAlchemy、pytest、Python 自动化客户端、Appium。

---

### 任务 1：调整后端任务接口

**涉及文件：**
- 修改：`api/app/schemas/automation.py`
- 修改：`api/app/services/automation.py`
- 修改：`api/app/api/routes/automation.py`
- 测试：`api/tests/test_automation_home_feed_flow.py`

- [x] 给 `ClaimTaskResponse` 增加 `doctors` 字段，返回所有可匹配的启用医生。
- [x] 新增“按命中医生领取一条未使用评论”的后端服务方法。
- [x] 新增客户端调用的领取评论接口。
- [x] 评论领取结果返回 `taskId=1`、`doctorId`、`doctorName`、`keywordId`、`keyword`、`commentBankItemId`、`commentContent`。
- [x] 添加测试：验证 claim 返回医生列表，验证命中医生后能领取未使用评论。

验证命令：

```powershell
cd E:\auto_fans\api
.\.venv\Scripts\python.exe -m pytest tests\test_automation_home_feed_flow.py -q
```

预期：新增测试通过。

### 任务 2：兼容新的结果上报方式

**涉及文件：**
- 修改：`api/app/services/automation.py`
- 测试：`api/tests/test_automation_home_feed_flow.py`

- [x] `start/report` 支持新的首页流评论任务，不再强制要求旧任务池记录。
- [x] 新流程产生的结果统一保存到 `task_id=1`。
- [x] 结果中保留真实医生、关键词、评论、设备、发布账号、视频链接、状态和摘要。
- [x] 成功领取的评论要标记为已使用。

验证命令：

```powershell
cd E:\auto_fans\api
.\.venv\Scripts\python.exe -m pytest tests\test_automation_home_feed_flow.py tests\test_task_pool_claim_phase2.py -q
```

预期：新流程测试通过，旧任务池测试不回退。

### 任务 3：调整客户端 API 模型

**涉及文件：**
- 修改：`automation_client/app/api_client.py`
- 测试：`automation_client/tests/test_task_worker.py`

- [x] `ClaimTaskResult` 支持医生列表。
- [x] 新增“按医生 ID 领取未使用评论”的客户端 API 方法。
- [x] 保留旧字段为可选，避免现有测试和调试脚本直接损坏。

验证命令：

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest tests\test_task_worker.py -q
```

预期：客户端 worker 测试通过。

### 任务 4：调整 TaskWorker 流程

**涉及文件：**
- 修改：`automation_client/app/task_worker.py`
- 测试：`automation_client/tests/test_task_worker.py`

- [x] 保持设备在线、业务开关、运行时间段、heartbeat 检查不变。
- [x] claim 成功后，不再要求必须有 `taskItemId` 和 `commentBankItemId`。
- [x] 将医生列表传给执行器。
- [x] 命中作者后，由执行器再领取该医生的评论；TaskWorker 不再提前调用旧的 `start_task` / `report_task`。
- [x] 每次命中互动成功后，按任务 1 上报结果。

验证命令：

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest tests\test_task_worker.py -q
```

预期：worker 能处理医生列表型任务。

### 任务 5：改造抖音执行器

**涉及文件：**
- 修改：`automation_client/app/douyin_task_executor.py`
- 测试：`automation_client/tests/test_douyin_task_executor.py`

- [x] 将旧的“搜索医生视频”执行方式改为“首页流观看”。
- [x] 按后台配置的 `watch_video` 时长停留观看。
- [x] 获取当前首页视频作者名称。
- [x] 使用 `医生昵称 in 视频作者名称` 判断是否命中。
- [x] 未命中时，滑动到下一个视频继续观看。
- [x] 命中时，领取该医生未使用评论，然后执行点赞、收藏、分享、评论、上报。
- [x] 评论成功后不退出抖音，返回首页并滑动到下一个视频。

验证命令：

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest tests\test_douyin_task_executor.py tests\test_task_worker.py -q
```

预期：执行器和 worker 测试通过。

### 任务 6：最终验证

验证命令：

```powershell
cd E:\auto_fans\api
.\.venv\Scripts\python.exe -m pytest -q
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest -q
```

预期：API 和自动化客户端测试全部通过。

结果：已通过。API `29 passed, 2 warnings`；automation_client `87 passed`。
