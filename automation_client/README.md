# Douyin Automation Client

Python + Appium 多设备自动化执行端。

## 目录

```text
automation_client/
  pyproject.toml
  .env.example
  README.md
  app/
  config/
  runtime/
  tests/
```

## 目标

- 发现本机连接的 Android 设备。
- 为每台设备创建独立 Appium driver。
- 向后端上报设备心跳。
- 主动领取每日任务。
- 执行抖音固定动作：搜索、进入页面、点赞、收藏、评论。
- 回传执行结果。

## 后端接口

```text
POST /api/automation/devices/heartbeat
POST /api/automation/tasks/claim
POST /api/automation/tasks/{task_item_id}/start
POST /api/automation/tasks/{task_item_id}/report
```

## 环境变量

复制 `.env.example` 为 `.env` 后按本机环境调整。

```text
API_BASE_URL=http://127.0.0.1:8000/api
APPIUM_SERVER_URL=http://127.0.0.1:4723
POLL_INTERVAL_SECONDS=3
MAX_WORKERS=8
ADB_PATH=adb
```

当前本地已创建 `.env`，默认连接本机 FastAPI 和 Appium Server。

## 安装依赖

```bash
cd automation_client
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
```

当前已安装并验证：

```text
Appium-Python-Client 5.3.1
selenium 4.43.0
httpx 0.28.1
pytest 9.0.3
PyYAML 6.0.3
```

基础检查：

```bash
.venv/bin/python -m app.main
.venv/bin/ruff check app tests
.venv/bin/pytest -q
```

## 多设备主控启动

显式指定设备最稳，`systemPort` 每台设备必须不同：

```bash
cd automation_client
.venv/bin/python -m app.main \
  --device R5CW11CKN0B,device_03,8203,device_03 \
  --device FMR0223830012928,device_01,8201,device_01
```

本地调试时，每台设备只领取并执行一轮：

```bash
.venv/bin/python -m app.main \
  --once \
  --device R5CW11CKN0B,device_03,8203,device_03
```

不传 `--device` 时，主控会从 `adb devices` 自动发现在线设备，并按顺序使用
`device_01/8201`、`device_02/8202` 这类默认配置。后端领取任务仍会按设备省份过滤，
所以设备首次心跳创建后，需要在后台补齐省份配置。

## 真机调试命令

当前真机：

```text
UDID=FMR0223830012928
deviceName=device_01
systemPort=8201
```

检查设备是否在线：

```bash
adb devices
```

重启 ADB：

```bash
adb kill-server
adb start-server
adb devices
```

查询抖音包名：

```bash
adb -s FMR0223830012928 shell pm list packages | grep -E 'aweme|douyin|ugc'
```

查询抖音启动 Activity：

```bash
adb -s FMR0223830012928 shell cmd package resolve-activity --brief com.ss.android.ugc.aweme
```

当前结果：

```text
package=com.ss.android.ugc.aweme
activity=.splash.SplashActivity
```

ADB 直接打开抖音：

```bash
adb -s FMR0223830012928 shell monkey -p com.ss.android.ugc.aweme -c android.intent.category.LAUNCHER 1
```

启动 Appium Server：

```bash
cd /Users/liu/crewai/android_auto_test/automation_client
appium --address 127.0.0.1 --port 4723
```

检查 Appium Server：

```bash
curl http://127.0.0.1:4723/status
```

脚本方式打开抖音：

```bash
cd /Users/liu/crewai/android_auto_test/automation_client
scripts/open_douyin.sh
```

如果当前只有一台在线设备，脚本会自动使用该设备。

脚本方式指定设备：

```bash
scripts/open_douyin.sh FMR0223830012928 device_01 8201
```

当前新设备示例：

```bash
scripts/open_douyin.sh adb-10AG3R2JNF001KK-WGRLsd._adb-tls-connect._tcp device_02 8202
scripts/open_douyin.sh R5CW11CKN0B device_03 8203
```

脚本方式走 ADB 直启：

```bash
scripts/open_douyin.sh FMR0223830012928 device_01 8201 --adb-only
```

旧的首页搜索入口点击脚本和 task39 搜索流调试脚本已经删除。当前客户端只保留首页流执行方式。

当前视频动作定位：

```text
点赞：//android.widget.LinearLayout[contains(@content-desc,"未点赞") and contains(@content-desc,"喜欢") and contains(@content-desc,"按钮")]
收藏：//android.widget.LinearLayout[contains(@content-desc,"未选中") and contains(@content-desc,"收藏") and contains(@content-desc,"按钮")]
评论按钮：//android.widget.ImageView[contains(@content-desc,"评论") and contains(@content-desc,"按钮")]
评论输入框：//android.widget.EditText[@resource-id="com.ss.android.ugc.aweme:id/eoy"]
发送按钮：//android.widget.TextView[@resource-id="com.ss.android.ugc.aweme:id/es7"]
```

评论发送说明：

```text
1. 点击评论按钮
2. 等待评论输入框出现
3. 点击输入框，使输入法弹出并激活发送按钮
4. 随机等待 2-5 秒
5. 释放 driver，执行 clear_session，再重连
6. 再次聚焦输入框，优先通过 mobile: type 输入评论内容
7. 输入后随机等待，让输入状态稳定
8. 如果开启发送评论，则点击发送按钮并等待 3 秒
9. 如果未开启发送评论，则停留 3 秒
10. 强制退出抖音，由后端记录本次执行结果
```

获取当前搜索结果页可见视频作者名：

```bash
scripts/collect_video_authors.sh
```

指定设备和数量：

```bash
scripts/collect_video_authors.sh R5CW11CKN0B 4
```

当前作者名定位：

```text
//android.widget.TextView[@resource-id="com.ss.android.ugc.aweme:id/+j"]
```

清理 Appium / UiAutomator2 残留 session：

```bash
scripts/clear_session.sh
```

指定设备和端口清理：

```bash
scripts/clear_session.sh R5CW11CKN0B 8203
```

也可以继续使用旧脚本名：

```bash
scripts/clean_appium_session.sh R5CW11CKN0B 8203
```

如果 Appium Inspector 反复提示 `systemPort is busy`，先执行清理脚本，再重新 `Start Session`。
Inspector 也可以临时改用一个新的 `systemPort`，例如 `8209`，避开旧 session 残留。

如果 Appium 第一次初始化失败，可以手动安装 UiAutomator2 组件：

```bash
adb -s FMR0223830012928 install -r --no-incremental /Users/liu/.appium/node_modules/appium-uiautomator2-driver/node_modules/appium-uiautomator2-server/apks/appium-uiautomator2-server-v6.0.9.apk
adb -s FMR0223830012928 install -r --no-incremental /Users/liu/.appium/node_modules/appium-uiautomator2-driver/node_modules/appium-uiautomator2-server/apks/appium-uiautomator2-server-debug-androidTest.apk
```

说明：

- `scripts/open_douyin.sh` 默认走 Python + Appium。
- `scripts/open_douyin.sh ... --adb-only` 只负责打开抖音，不创建 Appium 会话。
- Python + Appium 模式要求 Appium Server 已启动，并且 `adb devices` 能看到目标设备。
- 当前推荐 `Appium v3.3.1 + uiautomator2@2.45.1`。
- 新版 `uiautomator2` 不再要求默认传入 `appium:app`，项目已配置 `DOUYIN_APP_PATH=`，优先通过已安装 App 的 `appPackage/appActivity` 启动。
- 如果需要强制使用本地 APK 创建 session，可以临时传入 `--app runtime/apks/douyin.apk`。

## ADB 设备发现

当前已实现：

- 执行 `adb devices`。
- 解析在线 Android 设备 UDID。
- 校验设备状态是否为 `device`。
- 和后端设备配置中的 UDID 做对齐。
- 输出在线设备、已匹配设备、未录入后台设备、后台配置但当前离线设备。

核心文件：

```text
app/adb.py
app/device_manager.py
tests/test_adb.py
```

当前本机 ADB 输出：

```text
List of devices attached
FMR0223830012928	device
```

和后端设备配置对齐结果：

```text
online: FMR0223830012928
matched: -
missing_in_backend: FMR0223830012928
offline_configured: device_01/emulator-5554, device_02/emulator-5556, device_03/emulator-5558, device_04/emulator-5560, device_05/emulator-5562, device_06/emulator-5564, device_07/emulator-5566, device_08/emulator-5568
disabled_configured: -
```

说明：

- 当前连接的真实设备 UDID 是 `FMR0223830012928`。
- 后台设备表目前还是 mock 的 `emulator-*` UDID。
- 后续需要在设备管理页面把某台设备的 ADB UDID 替换为 `FMR0223830012928`，自动化脚本才能匹配到该设备。

## 设备心跳

当前已实现：

- 调用后端接口 `POST /api/automation/devices/heartbeat`。
- 每台匹配设备上报 `udid`、`deviceName`、`systemPort`、`runtimeStatus`、`remark`。
- 后端返回 `deviceId`、`udid`、`runtimeStatus`、`lastHeartbeatAt`。

核心文件：

```text
app/api_client.py
app/device_manager.py
tests/test_api_client.py
```

真实设备心跳验证结果：

```text
heartbeat ok: deviceId=5, udid=FMR0223830012928, runtimeStatus=idle
```

说明：

- 当前 `device_01` 已匹配真实 UDID `FMR0223830012928`。
- 心跳会刷新后端设备表的 `lastHeartbeatAt`。
- 后续 worker 循环会定时调用该心跳逻辑。

## Appium Driver 管理

当前已实现：

- 每台设备独立创建 Appium driver。
- 每台设备使用独立 `systemPort`。
- Driver 创建失败可重试。
- Worker 退出时可统一调用 `quit()` 释放 driver。

核心文件：

```text
app/appium_driver.py
tests/test_appium_driver.py
```

默认 capability：

```text
platformName=Android
automationName=UiAutomator2
udid=<后端设备配置中的 ADB UDID>
deviceName=<后端设备名称>
systemPort=<后端设备 systemPort>
noReset=true
appPackage=com.ss.android.ugc.aweme
appActivity=.splash.SplashActivity
uiautomator2ServerInstallTimeout=120000
uiautomator2ServerLaunchTimeout=120000
uiautomator2ServerReadTimeout=120000
adbExecTimeout=120000
```

示例：

```python
from app.appium_driver import AppiumDriverFactory, appium_config_from_backend_device

factory = AppiumDriverFactory("http://127.0.0.1:4723", retries=2)
device_config = appium_config_from_backend_device(backend_device)
managed_driver = factory.create(device_config)

try:
    driver = managed_driver.driver
finally:
    managed_driver.quit()
```

测试结果：

```text
8 passed
```

## 多线程任务执行器

当前已实现：

- 使用 `ThreadPoolExecutor`。
- 每台设备一个 `TaskWorker`。
- 每个 worker 循环执行：
  - 上报心跳。
  - 领取任务。
  - 有任务则交给任务执行器执行。
  - 无任务则按 `POLL_INTERVAL_SECONDS` 等待。
  - 外部停止时退出循环。

核心文件：

```text
app/task_worker.py
app/task_runner.py
tests/test_task_worker.py
```

设计说明：

- `TaskRunner` 负责为多台设备创建 worker 并放入线程池。
- `TaskWorker` 负责单台设备的循环。
- `TaskExecutor` 是可插拔协议，后续 Appium 抖音动作会实现这个协议。
- 当前默认执行器是 `NoopTaskExecutor`，只记录领取到的任务，不执行真实 Appium 动作。
- `run_once_for_each_device()` 用于本地调试和测试，每台设备只跑一轮。

测试结果：

```text
13 passed
```

## 领取任务

当前已实现：

- 调用后端接口 `POST /api/automation/tasks/claim`。
- 每台设备通过 `udid` 和当前发布账号 `publishAccount` 主动领取任务。
- 后端无任务时返回 `hasTask=false`，worker 等待下一轮轮询。
- 后端有任务时返回医生、关键词、搜索词、评论词库内容等执行参数。

请求参数：

```json
{
  "udid": "FMR0223830012928",
  "publishAccount": "测试账号01"
}
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

核心文件：

```text
app/api_client.py
app/task_worker.py
tests/test_api_client.py
```

说明：

- `AutomationApiClient.claim_task()` 负责接口请求和返回字段解析。
- `TaskWorker.run_once()` 已接入领取任务流程。
- 当前默认执行器 `NoopTaskExecutor` 只接收任务对象，后续固定 Appium 动作会在真实执行器中实现。

测试结果：

```text
13 passed
```

## 开始执行回调

当前已实现：

- 动作开始前调用 `POST /api/automation/tasks/{task_item_id}/start`。
- worker 领取到任务后，先调用开始回调，再进入 Appium 动作执行器。
- 后端返回 `resultId` 和 `status`，后续执行结果回传会继续使用该 `resultId`。

请求参数：

```json
{
  "udid": "FMR0223830012928",
  "commentBankItemId": 5,
  "publishAccount": "测试账号01"
}
```

返回字段：

```text
resultId
status
```

核心文件：

```text
app/api_client.py
app/task_worker.py
tests/test_api_client.py
tests/test_task_worker.py
```

测试结果：

```text
18 passed
```

## 执行结果回传

当前已实现：

- 执行结束后调用 `POST /api/automation/tasks/{task_item_id}/report`。
- 执行器正常返回时，上报 `status=success`。
- 执行器抛出异常时，worker 捕获异常并上报 `status=failed` 和 `failReason`。
- 无论成功或失败，都会把后端已领取的评论词库标记为已使用。

请求参数：

```json
{
  "udid": "FMR0223830012928",
  "resultId": 8,
  "commentBankItemId": 5,
  "publishAccount": "测试账号01",
  "status": "success",
  "videoLink": null,
  "failReason": null,
  "screenshotUrl": null,
  "logUrl": null
}
```

返回字段：

```text
resultId
status
```

核心文件：

```text
app/api_client.py
app/task_worker.py
tests/test_api_client.py
tests/test_task_worker.py
```

测试结果：

```text
20 passed
```

## 日志与截图

当前已实现运行期目录：

```text
runtime/
  logs/
  screenshots/
```

日志文件规则：

```text
runtime/logs/device_01.log
runtime/logs/device_02.log
```

截图文件规则：

```text
runtime/screenshots/{udid}_{taskId}_{timestamp}.png
```

示例：

```text
runtime/screenshots/FMR0223830012928_2_20260507_143012_123456.png
```

核心文件：

```text
app/logger.py
app/douyin_actions.py
app/task_worker.py
tests/test_logger.py
tests/test_douyin_actions.py
tests/test_task_worker.py
```

说明：

- `TaskWorker` 初始化时会为当前设备创建日志文件。
- 执行结果回传时，如果执行器没有指定 `logUrl`，worker 会默认回传当前设备日志路径。
- `DouyinActions` 失败截图会使用 `udid`、`taskId`、毫秒级时间戳命名。
- 如果动作类暂时没有任务上下文，截图中的 `taskId` 会使用 `no_task`。

测试结果：

```text
24 passed
```

## 抖音固定动作封装

当前已实现固定动作类 `DouyinActions`：

```text
open_douyin()
enter_doctor_page()
open_target_video()
like_video()
favorite_video()
post_comment()
```

每一步统一处理：

- 等待元素可见或可点击。
- 失败时自动截图。
- 抛出包含 `udid`、步骤名、截图路径、原始错误的 `DouyinActionError`。
- 记录开始、成功、失败日志。

核心文件：

```text
app/douyin_actions.py
config/locators.yaml
tests/test_douyin_actions.py
```

定位配置：

```text
user_tab
doctor_page_entry
video_entry
like_button
favorite_button
comment_button
comment_input
send_comment_button
```

支持的定位方式：

```text
resource-id
content-desc
xpath
android_uiautomator
class_name
text
coordinate
```

说明：

- `config/locators.yaml` 目前保留为空值，等 Appium Inspector 调试真实抖音测试包时填入稳定的 `resource-id`、`content-desc`、`text` 或 `xpath`。
- 每个元素支持多种 `strategies`，执行时按配置顺序依次尝试。
- 定位策略优先级建议为：`resource-id` -> `content-desc` -> `text` -> `xpath` -> `coordinate`。
- `coordinate` 只作为兜底方案，需要配置 `x`、`y`。
- 失败截图默认保存到 `runtime/screenshots/`，命名格式为 `{udid}_{taskId}_{timestamp}.png`。

测试结果：

```text
24 passed
```
