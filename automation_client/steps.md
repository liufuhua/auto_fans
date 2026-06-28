# 抖音自动化执行流程

本文档记录当前多设备自动化测试的主控流程、设备探测流程和每台设备的并行子流程。

当前主流程入口已经切换为：

```text
automation_client/app/main.py
```

单设备快速测试入口 `app.debug_executor_task39` 仅用于调用主流程做本地验证，不作为正式业务入口。

## 一、主流程工作流程

### 1. 主流程目标

当前主流程不是“创建任务后立刻自动运行”的后端内置流程，而是：

```text
后端负责：任务、设备状态、业务开关、结果记录
前端负责：创建任务、查看设备、启动/停止业务
automation_client 负责：探测设备、领取任务、执行 Appium 自动化
```

因此主流程需要让 `automation_client` 常驻运行。它启动后会持续探测设备，
但只有管理后台点击“启动业务”后，才会开始领取每日任务并执行抖音自动化。

### 2. 启动前准备

需要先确认：

```text
后端 API 已启动
前端管理后台已启动
Appium Server 已启动
真机已连接，并且 adb devices 可以识别
设备已登录抖音
后台设备已配置省份
每台设备使用不同 systemPort
```

设备省份很重要：后端领取任务时会按设备省份匹配医生省份。设备没有省份时，
即使在线，也不会领取到需要地区匹配的任务。

可选：启动前清理 Appium Session，避免旧 session 占用 `systemPort`：

```bash
cd automation_client
scripts/clear_session.sh R5CW11CKN0B 8203
```

### 3. 启动客户端主控

入口文件：

```text
automation_client/app/main.py
```

如果希望一条命令同时启动后端、前端、Appium Server 和客户端主控，可以在项目根目录执行：

```bash
scripts/start_all.sh \
  --device R5CW11CKN0B,device_03,8203,device_03
```

这个脚本会把后端、前端、Appium 和客户端日志写到项目根目录：

```text
logs/
```

日志按天生成，例如：

```text
logs/api-2026-05-06.txt
logs/appium-2026-05-06.txt
logs/web_admin-2026-05-06.txt
logs/automation_client-2026-05-06.txt
```

其中：

```text
api 日志会记录后端请求和响应内容，包括 method、path、query、status、耗时、requestBody、responseBody。
appium 日志使用 debug 级别，记录 Appium Server 的请求、响应和 driver 运行细节。
```

推荐显式指定设备启动：

```bash
cd automation_client
.venv/bin/python -m app.main \
  --device R5CW11CKN0B,device_03,8203,device_03 \
  --device FMR0223830012928,device_01,8201,device_01
```

参数格式：

```text
--device UDID,设备名,systemPort,发布账号
```

示例：

```text
R5CW11CKN0B,device_03,8203,device_03
```

启动后，客户端主控会：

```text
解析设备配置
创建后端 API client
创建真实 Appium 执行器
创建设备状态注册表
创建设备探测器
创建多设备 TaskRunner
进入常驻运行
```

本地调试时，可以每台设备只执行一轮：

```bash
.venv/bin/python -m app.main \
  --once \
  --device R5CW11CKN0B,device_03,8203,device_03
```

不传 `--device` 时，客户端会从 `adb devices` 自动发现在线设备，并按顺序生成：

```text
已知设备使用固定映射：
FMR0223830012928 -> device_01 / 8201
adb-10AG3R2JNF001KK-WGRLsd._adb-tls-connect._tcp -> device_02 / 8202
R5CW11CKN0B -> device_03 / 8203

未知设备从 device_01 / 8201 开始自动分配未占用的 systemPort
```

### 4. 设备探测与后台状态同步

文件：

```text
automation_client/app/main.py
automation_client/app/device_monitor.py
automation_client/app/device_status.py
```

核心对象：

```python
DeviceMonitor
DeviceStatusRegistry
```

探测频率：

```text
默认每 30 秒一次
可通过 --device-probe-interval-seconds 调整
```

同步逻辑：

```text
adb devices 显示在线：上报 idle 或 running
adb devices 未发现设备：上报 offline
设备执行任务前：本地状态标记为 running
任务完成或失败回传后：本地状态标记为 idle
```

后端接口：

```text
POST /api/automation/devices/heartbeat
```

后台设备页：

```text
http://localhost:5173/devices
```

运行状态只分三种：

```text
offline 离线
idle 空闲
running 执行任务中
```

后端设备列表读取时，还会把心跳超过 90 秒的设备自动视为离线，避免客户端异常退出后
后台长期显示空闲或执行中。

### 5. 管理后台创建任务

页面：

```text
http://localhost:5173/daily-tasks
```

操作：

```text
点击“新建任务”
选择任务日期
配置医生、关键词、条数
创建每日任务
```

创建任务只是在后端生成 `pending` 状态的每日任务。此时如果业务开关没有启动，
客户端仍然不会领取任务。

### 6. 管理后台启动业务

页面：

```text
http://localhost:5173/daily-tasks
```

位置：

```text
“新建任务”按钮旁边
```

按钮：

```text
启动业务
停止业务
```

接口：

```text
GET /api/automation/runtime
POST /api/automation/runtime/start
POST /api/automation/runtime/stop
```

业务开关含义：

```text
businessStatus=stopped：客户端只探测设备，不领取任务
businessStatus=running：客户端开始领取任务并执行
```

启动业务后，已经常驻运行的 `automation_client` 会在下一次开关轮询时感知到状态变化，
随后各设备 worker 开始领取任务。

### 7. 创建并启动多设备 TaskRunner

文件：

```text
automation_client/app/task_runner.py
```

核心对象：

```python
TaskRunner
```

主控传入：

```text
devices
api_client
publish_account_by_udid
poll_interval_seconds
max_workers
executor=DouyinAppiumTaskExecutor
status_registry=DeviceStatusRegistry
business_enabled=AutomationRuntimeSwitch.enabled
```

持续运行模式：

```python
TaskRunner.start()
```

调试单轮模式：

```python
TaskRunner.run_once_for_each_device()
```

执行逻辑：

```text
使用 ThreadPoolExecutor
线程数 = min(设备数, maxWorkers)
每台设备创建一个 TaskWorker
每个 TaskWorker 在独立线程中循环执行
```

每个 `TaskWorker` 的主循环会先检查业务开关：

```text
业务未启动：等待下一轮
业务已启动：上报心跳、领取任务、执行任务、回传结果
```

### 8. 停止业务与停止主控

停止业务：

```text
在 daily-tasks 页面点击“停止业务”
后端 businessStatus 变为 stopped
客户端停止领取新任务
设备探测仍继续运行
```

停止客户端主控：

```text
终端按 Ctrl+C
app.main 捕获 KeyboardInterrupt
调用 TaskRunner.stop()
调用 DeviceMonitor.stop()
设置 stop_event
等待线程池内 worker 退出
```

## 二、并行子流程工作流程

并行子流程由 `TaskRunner` 创建。每台设备对应一个 `TaskWorker`，
每个 worker 在独立线程中运行。

入口文件：

```text
automation_client/app/task_runner.py
automation_client/app/task_worker.py
```

核心对象：

```python
TaskRunner
TaskWorker
TaskExecutionResult
TaskExecutor
```

每个子流程独立使用自己的：

```text
udid
deviceName
systemPort
publishAccount
runtime/logs/{deviceName}.log 作为执行结果默认 logUrl
```

### 1. 子流程创建

文件：

```text
automation_client/app/task_runner.py
automation_client/app/task_worker.py
```

函数：

```python
TaskRunner.start()
TaskRunner.run_once_for_each_device()
```

创建逻辑：

```text
TaskRunner 使用 ThreadPoolExecutor
线程数 = min(设备数, maxWorkers)
每台设备创建一个 TaskWorker
所有 worker 共用同一个 AutomationApiClient
所有 worker 共用同一个 DouyinAppiumTaskExecutor
所有 worker 共用同一个 DeviceStatusRegistry
所有 worker 共用同一个 business_enabled 回调
每台设备使用自己的 publishAccount
```

### 2. 子流程循环

文件：

```text
automation_client/app/task_worker.py
```

函数：

```python
TaskWorker.run()
TaskWorker.run_once()
```

循环逻辑：

```text
检查 stop_event
检查 max_iterations
执行 run_once()
run_once() 结束后进入下一轮
```

`run_once()` 的实际顺序：

```text
检查业务开关
业务未启动：本地状态设为 idle，等待 pollIntervalSeconds，不上报 heartbeat，不领取任务
业务已启动：本地状态设为 idle
上报 idle heartbeat
领取任务
无任务：本地状态保持 idle，等待 pollIntervalSeconds
有任务：调用 start_task
执行前：本地状态设为 running
执行 Appium 真实动作
回传执行结果
finally：本地状态设为 idle
```

说明：

```text
这里的“本地状态”写入 DeviceStatusRegistry。
真正同步到后端设备页的是 DeviceMonitor，它每 30 秒读取 DeviceStatusRegistry 并调用 heartbeat。
```

### 3. 业务开关判断

调用：

```python
TaskWorker._business_enabled()
```

来源：

```text
TaskRunner 传入 business_enabled=AutomationRuntimeSwitch.enabled
```

行为：

```text
businessStatus=stopped：worker 不领取任务，只等待下一轮
businessStatus=running：worker 开始 heartbeat、claim、start、execute、report
```

注意：

```text
业务未启动时，设备在线/离线状态仍由 DeviceMonitor 负责同步。
```

### 4. 上报设备心跳

调用：

```python
TaskWorker.heartbeat("idle")
AutomationApiClient.heartbeat_device()
```

后端接口：

```text
POST /api/automation/devices/heartbeat
```

请求字段：

```text
udid
deviceName
systemPort
runtimeStatus=idle
remark=automation_client worker heartbeat
```

作用：

```text
确认设备已注册并启用
更新设备心跳时间
更新设备运行状态
```

### 5. 领取任务

调用：

```python
AutomationApiClient.claim_task()
```

后端接口：

```text
POST /api/automation/tasks/claim
```

请求字段：

```text
udid
publishAccount
```

返回字段：

```text
hasTask
taskId
taskItemId
doctorId
doctorName
keywordId
keyword
searchWord
commentBankItemId
commentContent
```

无任务时：

```text
hasTask=false
worker 记录 no task
等待 pollIntervalSeconds
进入下一轮
```

后端并发保证：

```text
按 pending/running 任务筛选
按设备省份匹配医生省份
检查设备当天是否已对同一医生、同一关键词执行过 comment
使用 row lock 锁定 DailyTaskItem；数据库支持时使用 skip_locked
使用 row lock 锁定 CommentBankItem；数据库支持时使用 skip_locked
同一条评论不会被多台设备同时领取
同一台设备同一天不会重复执行同一医生同一关键词
第二天可以重新执行
```

相关后端文件：

```text
api/app/services/automation.py
api/app/models/device_action.py
```

### 6. 通知后端任务开始

调用：

```python
AutomationApiClient.start_task()
```

后端接口：

```text
POST /api/automation/tasks/{task_item_id}/start
```

作用：

```text
创建或复用 running 状态的 AutomationResult
返回 resultId
后续成功或失败都基于该 resultId 回传
```

如果领取结果缺少必要字段：

```text
taskItemId 为空：抛出 ValueError
commentBankItemId 为空：抛出 ValueError
```

### 7. 执行真实 Appium 动作

文件：

```text
automation_client/app/douyin_task_executor.py
```

核心对象：

```python
DouyinAppiumTaskExecutor
DouyinAppiumExecutorConfig
```

执行入口：

```python
DouyinAppiumTaskExecutor.execute()
```

执行器输入：

```text
task
start_result
device
api_client
```

执行器会先校验：

```text
keyword/searchWord 必须存在
doctorName 必须存在
commentContent 必须存在
```

每台设备会用自己的配置创建 Appium driver：

```text
udid
deviceName
systemPort
appPackage=com.ss.android.ugc.aweme
appActivity=.splash.SplashActivity
automationName=UiAutomator2
noReset=true
```

相关文件：

```text
automation_client/app/appium_driver.py
automation_client/app/douyin_actions.py
automation_client/app/douyin_search_support.py
automation_client/app/douyin_page_state.py
```

说明：

```text
douyin_task_executor 复用 douyin_search_support / douyin_page_state 中的正式公共能力。
真实动作封装在 DouyinActions 中。
```

进入搜索流程前，每个子任务都会先做页面前置校验：

```text
调用 DouyinActions.open_douyin() 激活抖音
读取当前 pageSource
判断当前是否为抖音首页
如果不在首页，则先尝试回到首页
只有确认回到首页后，才继续搜索并打开目标视频
```

首页判断规则：

```text
页面存在底部 Tab：首页、朋友、消息
页面不存在搜索输入框 resource-id=com.ss.android.ugc.aweme:id/et_search_kw
```

如果当前不在首页，会按以下顺序处理：

```text
如果存在“链接已复制成功”弹窗：先关闭弹窗
如果在视频页：点击左上角返回
如果在搜索页：点击搜索页左上角返回
如果仍未回到首页：最多执行 4 次 Android 系统返回键
如果仍无法识别首页：抛出异常，本次任务回传 failed
```

相关正式复用逻辑：

```text
automation_client/app/douyin_page_state.py
```

### 8. 搜索并打开目标视频

文件：

```text
automation_client/app/douyin_task_executor.py
```

当前拆分函数：

```python
DouyinAppiumTaskExecutor._click_home_search_entry_and_reconnect()
DouyinAppiumTaskExecutor._input_search_text_submit_and_reconnect()
DouyinAppiumTaskExecutor._find_and_open_matching_video()
```

搜索词格式：

```text
searchWord doctorName
```

示例：

```text
脑膜瘤 张明山
```

执行步骤：

```text
点击首页搜索入口
释放 driver，执行 clear_session，再重连等待搜索输入框
清空输入框
输入搜索词
点击搜索按钮
释放 driver，执行 clear_session，再重连读取搜索结果
先在当前搜索结果页查找目标作者
每次翻页后等待 2 秒，释放 driver，执行 clear_session，再重连读取新页面
当前页连续 3 次未找到目标作者时，切换到“视频”Tab
在“视频”Tab 继续最多 3 次查找和翻页
找到未点赞的目标作者视频后打开视频
```

查找不到目标作者时：

```text
强制退出抖音
抛出异常
TaskWorker 捕获异常
回传 failed
```

### 9. 执行视频动作

当前拆分函数：

```python
DouyinAppiumTaskExecutor._like_video_and_reconnect()
DouyinAppiumTaskExecutor._favorite_video_and_reconnect()
DouyinAppiumTaskExecutor._comment_video_and_reconnect()
```

当前完整动作：

```text
观看视频随机等待
释放 driver，执行 clear_session，再重连查找点赞按钮
点赞
点赞后随机等待
释放 driver，执行 clear_session，再重连
收藏
收藏后随机等待
释放 driver，执行 clear_session，再重连
打开评论面板
点击评论输入框
随机等待键盘和输入框稳定
释放 driver，执行 clear_session，再重连
再次聚焦评论输入框
输入领取到的 commentContent
输入后随机等待
如果 sendCommentEnabled=true：点击发送按钮，等待 3 秒
如果 sendCommentEnabled=false：不点击发送按钮，等待 3 秒
强制退出抖音
```

成功返回：

```text
TaskExecutionResult.success()
```

### 10. 回传执行结果

调用：

```python
AutomationApiClient.report_task()
```

后端接口：

```text
POST /api/automation/tasks/{task_item_id}/report
```

成功时回传：

```text
status=success
resultId
commentBankItemId
publishAccount
logUrl
```

失败时回传：

```text
status=failed
failReason
screenshotUrl
logUrl
```

日志默认路径：

```text
automation_client/runtime/logs/{deviceName}.log
如果执行器没有指定 logUrl，worker 会回传这个路径
```

截图默认路径：

```text
automation_client/runtime/screenshots/{udid}_{taskId}_{timestamp}.png
```

### 11. 失败处理

执行器内部异常：

```text
DouyinAppiumTaskExecutor 抛出异常
TaskWorker._execute_task 捕获异常
生成 TaskExecutionResult.failed
调用 report_task 回传 failed
```

Appium driver 释放：

```text
DouyinAppiumTaskExecutor.execute() finally 中调用 quit_with_timeout()
避免 driver 长时间占用设备 session
```

本地设备状态释放：

```text
TaskWorker.run_once() 在 report_task 外层使用 finally
无论执行成功、执行失败、回传异常，都会把 DeviceStatusRegistry 中的设备状态设回 idle
```

### 12. 停止处理

停止来源：

```text
主控 Ctrl+C
TaskRunner.stop()
TaskWorker.stop()
```

停止逻辑：

```text
设置 stop_event
worker 当前轮结束后退出循环
线程池 shutdown 等待 worker 结束
```

## 三、调试入口

单设备快速测试脚本仍然保留：

```bash
cd automation_client
.venv/bin/python -m app.debug_executor_task39 \
  --udid R5CW11CKN0B \
  --device-name device_03 \
  --system-port 8203 \
  --debug \
  --execute-video-actions
```

用途：

```text
通过固定 task39 数据快速调用 DouyinAppiumTaskExecutor 主流程
不作为当前多设备主控入口
```

## 四、验证命令

客户端测试：

```bash
cd automation_client
.venv/bin/python -m pytest -q
```

代码检查：

```bash
cd automation_client
.venv/bin/ruff check app tests
```

后端自动化接口检查：

```bash
cd api
PYTHONPATH=. uv run python -m scripts.check_automation
```
