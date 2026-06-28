# 评论校验 Playwright 重做方案

## 目标

重新整理“执行结果页面”的评论校验功能，改成以后端 Playwright 为核心的登录态管理和评论检查流程。

核心体验：

1. 用户在执行结果页选择需要校验的结果。
2. 点击“校验评论”。
3. 如果后端 Playwright 已登录抖音，直接开始校验。
4. 如果未登录，前端弹出抖音登录二维码。
5. 用户扫码登录后点击确认，后端保存登录态。
6. 登录成功后自动继续执行评论检查。
7. 检查结果回写数据库，并在执行结果页展示。

原有 Selenium 评论校验代码在 Playwright 新流程完成并验证后删除，不再保留双实现。

## 总体选择

使用 Playwright，不再引入 Selenium fallback。

原因：

- Playwright 更适合处理二维码登录、持久化浏览器上下文、截图和页面状态轮询。
- 单一浏览器自动化技术栈更容易维护。
- 当前 Selenium 逻辑完成迁移后不再保留，避免后续出现两套登录态、两套浏览器进程和两套异常处理。

## 模块拆分

建议新增或重构为以下模块：

```text
api/app/services/comment_recheck.py
  评论校验数据库服务：
  - 列表查询
  - 创建校验任务
  - 重置校验状态
  - 更新校验结果

api/app/services/douyin_playwright_session.py
  抖音 Playwright 登录态服务：
  - 启动/复用 persistent context
  - 判断是否已登录
  - 打开登录页
  - 截取登录二维码
  - 确认登录成功
  - 关闭浏览器会话

api/app/services/douyin_comment_checker.py
  抖音评论检查服务：
  - 打开视频链接
  - 等待评论区加载
  - 查找指定评论内容
  - 返回 exists/missing/failed/captcha_required/login_required

api/app/services/comment_recheck_worker.py
  评论校验执行器：
  - 串行或有限并发执行校验
  - 控制同一时间只跑一个浏览器检查任务
  - 处理中断、超时、验证码、登录失效
  - 写入 checked_at 和 fail_reason
```

旧文件迁移完成后删除：

```text
api/app/services/comment_recheck_browser.py
```

如果相关测试或脚本仍引用旧 Selenium 服务，也同步改为 Playwright 服务。

## 登录态设计

Playwright 使用持久化用户目录保存抖音登录态：

```text
runtime/douyin_playwright_profile/
```

推荐启动方式：

```python
chromium.launch_persistent_context(
    user_data_dir=str(profile_dir),
    headless=True,
    viewport={"width": 1280, "height": 900},
)
```

说明：

- 登录态保存在 `runtime/douyin_playwright_profile/`。
- 后端服务重启后应继续复用登录态。
- 如果登录态过期，后端返回 `login_required`，前端重新弹二维码。
- 登录二维码使用 Playwright 对页面二维码区域截图，不依赖抖音内部二维码 URL。

## 状态设计

当前状态：

```python
pending | exists | missing | failed | captcha_required
```

建议调整为：

```python
not_checked
queued
checking
exists
missing
failed
login_required
captcha_required
```

含义：

- `not_checked`：未校验。数据库中可以没有 `CommentRecheckRecord`，前端展示时映射为未校验。
- `queued`：已提交校验，等待 worker 执行。
- `checking`：正在检查。
- `exists`：评论存在。
- `missing`：评论不存在。
- `failed`：校验失败。
- `login_required`：抖音未登录或登录失效。
- `captcha_required`：需要验证码或人工验证。

如果希望减少改动，也可以短期保留旧状态，但至少需要把 `pending` 统一解释成“已提交/等待校验”，不要同时承担“未校验”和“校验中”。

## Schema 建议

`api/app/schemas/comment_recheck.py` 建议整理为：

```python
CommentRecheckStatus = Literal[
    "not_checked",
    "queued",
    "checking",
    "exists",
    "missing",
    "failed",
    "login_required",
    "captcha_required",
]


class CommentRecheckLoginStatusRead(BaseModel):
    logged_in: bool = Field(serialization_alias="loggedIn")
    session_id: str | None = Field(default=None, serialization_alias="sessionId")
    qr_code_url: str | None = Field(default=None, serialization_alias="qrCodeUrl")
    message: str | None = None


class StartCommentRecheckPayload(BaseModel):
    ids: list[int] = Field(min_length=1)


class StartCommentRecheckResponse(BaseModel):
    submitted: int
    skipped: int = 0
    login_required: bool = Field(default=False, serialization_alias="loginRequired")
```

执行结果列表的 schema 建议补充：

```python
comment_recheck_checked_at: datetime | None = Field(
    default=None,
    serialization_alias="commentRecheckCheckedAt",
)
```

这样执行结果页可以展示“校验过”的时间，而不是只能看到状态。

## API 设计

### 查询登录状态

```http
GET /api/comment-results/recheck/login-status
```

已登录：

```json
{
  "loggedIn": true,
  "sessionId": null,
  "qrCodeUrl": null,
  "message": "已登录"
}
```

未登录：

```json
{
  "loggedIn": false,
  "sessionId": "20260613143000",
  "qrCodeUrl": "/api/comment-results/recheck/login-qr?sessionId=20260613143000",
  "message": "请扫码登录抖音"
}
```

### 创建登录会话

```http
POST /api/comment-results/recheck/login-session
```

职责：

- 启动或复用 Playwright persistent context。
- 打开抖音登录页面。
- 等待二维码出现。
- 返回二维码截图地址。

### 获取登录二维码截图

```http
GET /api/comment-results/recheck/login-qr?sessionId=xxx
```

返回 `image/png`。

二维码截图来源：

- 优先定位二维码 DOM 区域后截图。
- 如果定位失败，可退化为页面局部截图，并在前端提示刷新二维码。

### 确认登录

```http
POST /api/comment-results/recheck/confirm-login
```

请求：

```json
{
  "sessionId": "20260613143000"
}
```

返回：

```json
{
  "loggedIn": true,
  "message": "登录成功"
}
```

如果仍未登录：

```json
{
  "loggedIn": false,
  "message": "尚未检测到登录成功，请扫码后重试"
}
```

### 发起评论校验

```http
POST /api/comment-results/recheck
```

请求：

```json
{
  "ids": [101, 102, 103]
}
```

返回：

```json
{
  "submitted": 3,
  "skipped": 0,
  "loginRequired": false
}
```

如果未登录：

```json
{
  "submitted": 0,
  "skipped": 3,
  "loginRequired": true
}
```

## 前端交互

执行结果页建议调整：

1. 表格增加多选。
2. 主按钮改为“校验评论”。
3. 用户至少选择一条成功且有视频链接的记录后才能校验。
4. 点击后调用 `login-status`。
5. 已登录则直接调用 `POST /comment-results/recheck`。
6. 未登录则弹出“抖音扫码登录”对话框。
7. 对话框展示二维码截图。
8. 用户扫码完成后点击“我已登录”。
9. 前端调用 `confirm-login`。
10. 确认成功后自动提交原本选择的校验任务。
11. 提交成功后刷新执行结果列表。

执行结果页展示建议：

- 未校验
- 已提交
- 校验中
- 评论存在
- 评论不存在
- 需要登录
- 需要验证码
- 校验失败

如果后端返回 `commentRecheckCheckedAt`，表格可增加“校验时间”列，或在状态 tooltip 里展示。

## Worker 执行流程

每条评论校验建议流程：

1. 从数据库取出 `queued` 记录。
2. 更新状态为 `checking`。
3. 检查 Playwright 登录态。
4. 如果未登录，更新为 `login_required`。
5. 打开 `AutomationResult.video_link`。
6. 等待页面主要内容加载。
7. 检测是否出现验证码、登录弹窗、访问异常。
8. 加载评论区域。
9. 滚动并查找 `AutomationResult.comment_content`。
10. 找到则写入 `exists`。
11. 未找到则写入 `missing`。
12. 异常则写入 `failed` 和 `fail_reason`。
13. 每次结束都写入 `checked_at`。

建议先串行执行，后续确认稳定后再考虑小并发。

## Playwright 检查策略

评论内容匹配建议分层：

1. 精确匹配完整评论文本。
2. 去除空白、换行、特殊空格后匹配。
3. 如果评论过长，使用前后关键片段匹配。
4. 保留失败时页面截图或 HTML 片段，方便排查。

失败原因建议标准化：

- `未登录抖音`
- `需要验证码`
- `视频页面打开失败`
- `评论区加载超时`
- `未找到对应评论内容`
- `页面结构变化，未能定位评论区`

## 旧 Selenium 删除计划

Playwright 新流程完成后删除或替换：

```text
api/app/services/comment_recheck_browser.py
```

同步检查并处理引用：

```text
api/app/services/comment_recheck.py
api/scripts/check_comment_recheck.py
api/scripts/check_integration.py
api/tests/
```

删除时机：

1. Playwright 登录二维码流程可用。
2. Playwright 能复用登录态。
3. 至少一条真实视频链接能完成评论检查。
4. 执行结果页能触发校验并展示结果。
5. 后端自检脚本通过。

## 分阶段实施

### 第一阶段：接口和状态整理

- 更新 `comment_recheck.py` schema。
- 更新执行结果 schema，补充 `commentRecheckCheckedAt`。
- 新增登录状态相关接口。
- 暂不接入真实 Playwright 检查，只完成接口骨架。

当前进度：已完成。

已落地内容：

- `CommentRecheckStatus` 已整理为 `not_checked / queued / checking / exists / missing / failed / login_required / captcha_required`。
- 后端对历史 `pending` 做兼容映射，对外统一返回 `queued`。
- 新提交的评论校验任务写入 `queued`。
- `StartCommentRecheckResponse` 已从 `checked` 调整为 `submitted / skipped / loginRequired`。
- 执行结果接口已补充 `commentRecheckCheckedAt`。
- 已新增登录接口骨架：
  - `GET /api/comment-results/recheck/login-status`
  - `POST /api/comment-results/recheck/login-session`
  - `POST /api/comment-results/recheck/confirm-login`
- 第一阶段登录接口暂不启动 Playwright，统一返回“Playwright 登录流程尚未接入”。
- 前端类型、mock API、状态文案已同步新状态和新响应结构。
- 旧 Selenium worker 临时兼容 `queued` 和历史 `pending`，确保 Playwright 完成前现有流程不被状态改名打断。

验证情况：

- 后端 `app.main` 导入正常。
- 后端 `compileall app scripts/check_comment_recheck.py` 通过。
- 前端 `npm run typecheck` 通过。
- `scripts/check_comment_recheck.py` 未完整运行，原因是当前 api venv 缺少 TestClient 依赖 `httpx`。

### 第二阶段：Playwright 登录态

- 增加 Playwright 依赖。
- 新增 `douyin_playwright_session.py`。
- 实现启动浏览器、打开登录页、二维码截图、确认登录。
- 前端执行结果页弹出二维码登录框。

当前进度：已完成。

已落地内容：

- `pyproject.toml` 已增加 `playwright` 依赖。
- 已新增配置项：
  - `DOUYIN_PLAYWRIGHT_PROFILE_DIR`
  - `DOUYIN_PLAYWRIGHT_QR_DIR`
  - `DOUYIN_PLAYWRIGHT_HEADLESS`
  - `DOUYIN_PLAYWRIGHT_PAGE_TIMEOUT_SECONDS`
- `DOUYIN_PLAYWRIGHT_HEADLESS` 默认值调整为 `false`。抖音登录页在 headless 模式下更容易触发验证，可见浏览器模式更利于扫码登录。
- 已新增 `api/app/services/douyin_playwright_session.py`：
  - 启动并复用 Playwright persistent context。
  - 使用 `runtime/douyin_playwright_profile/` 保存登录态。
  - 打开抖音登录页。
  - 判断登录 cookie。
  - 截取登录二维码或登录弹窗截图。
  - 确认扫码登录状态。
- 登录接口已接入真实 Playwright service：
  - `GET /api/comment-results/recheck/login-status`
  - `POST /api/comment-results/recheck/login-session`
  - `GET /api/comment-results/recheck/login-qr?sessionId=xxx`
  - `POST /api/comment-results/recheck/confirm-login`
- 前端执行结果页已接入扫码登录弹窗：
  - 点击“评论校验”前先查询抖音登录态。
  - 未登录时创建登录会话。
  - 通过鉴权接口获取二维码图片 blob。
  - 展示二维码弹窗。
  - 用户点击“我已登录”后确认登录状态。
  - 登录成功后继续提交原本的评论校验请求。

验证情况：

- 已在 api venv 安装 `playwright`。
- 已执行 `playwright install chromium`，本机 Chromium 浏览器二进制已下载。
- 后端 Playwright 登录会话烟测通过，可以打开抖音登录页并生成登录弹窗截图，二维码可见。
- 后端 `app.main` 导入正常。
- 后端 `compileall app` 通过。
- 前端 `npm run typecheck` 通过。

注意事项：

- 如果部署在没有桌面的服务器环境，需要重新评估 `DOUYIN_PLAYWRIGHT_HEADLESS=true` 时的抖音风控表现。
- 如果抖音先出现验证码，当前实现会把验证页面截图给前端，并提示用户在浏览器窗口完成验证后刷新二维码。
- 当前阶段只完成登录态和二维码弹窗，不执行评论内容检查。

### 第三阶段：Playwright 评论检查

- 新增 `douyin_comment_checker.py`。
- 新增或重构 `comment_recheck_worker.py`。
- `POST /comment-results/recheck` 改为提交 Playwright worker。
- 校验结果写入数据库。

当前进度：已完成。

已落地内容：

- 已新增 `api/app/services/douyin_comment_checker.py`：
  - 使用 Playwright 登录态上下文打开视频链接。
  - 检测登录失效、验证码、视频不存在等页面状态。
  - 滚动页面并匹配目标评论内容。
  - 返回 `exists / missing / failed / login_required / captcha_required`。
- 已新增 `api/app/services/comment_recheck_worker.py`：
  - 查询 `queued` 和历史 `pending` 校验记录。
  - 执行前写入 `checking`。
  - 执行完成后写入最终状态、`checked_at` 和 `fail_reason`。
  - 使用全局锁保证同一时间只跑一个评论校验任务。
- `api/app/services/comment_recheck.py` 已切换到 Playwright worker 调度。
- 发起校验前会确认抖音登录态：
  - 已登录：写入 `queued` 并启动 Playwright worker。
  - 未登录：返回 `loginRequired=true`，不提交队列。
- `scripts/check_comment_recheck.py` 已同步第三阶段行为，允许未登录时返回 `loginRequired`。

验证情况：

- 后端 `app.main` 导入正常。
- 后端 `compileall app scripts/check_comment_recheck.py` 通过。
- 前端 `npm run typecheck` 通过。

注意事项：

- 当前阶段 Playwright worker 已接管新调度入口。
- 旧 Selenium 文件 `comment_recheck_browser.py` 暂未删除，留到第五阶段统一清理引用和依赖。
- 真实评论匹配效果依赖抖音页面结构，第四阶段或真实联调时需要用实际视频链接继续微调滚动和评论区定位策略。

### 第四阶段：前端体验整理

- 执行结果页支持多选校验。
- 未登录时自动弹二维码。
- 登录成功后自动继续提交。
- 状态和校验时间展示清晰化。
- 保留“今日全部校验”作为次级入口，或删除。

当前进度：已完成。

已落地内容：

- 执行结果页已支持表格多选。
- 主入口已调整为“校验选中”：
  - 只允许选择成功、有视频链接、且不处于 `queued/checking` 的结果。
  - 未选择可校验结果时按钮禁用。
  - 点击后先检查抖音登录态。
  - 未登录时弹出扫码登录框。
  - 登录成功后继续提交原本选择的校验任务。
- “校验今日”已保留为次级入口。
- 表格已新增当前页可校验数量和已选数量提示。
- 执行结果页已新增“校验时间”列。
- 校验状态 tooltip 已补充失败原因和校验时间。

验证情况：

- 前端 `npm run typecheck` 通过。
- 后端 `compileall app` 通过。
- 本地 Vite 页面 `http://127.0.0.1:5173/automation-results` 可访问。
- in-app browser 当前不可用，未完成浏览器截图验证。

### 第五阶段：删除 Selenium

- 删除 `comment_recheck_browser.py`。
- 删除 Selenium 相关依赖和配置。
- 修正所有旧引用。
- 运行后端自检和前端类型检查。

## 风险点

- 抖音登录页 DOM 结构可能变化，二维码定位需要容错。
- 抖音可能触发验证码或风控，必须明确展示 `captcha_required`。
- headless 模式可能和 headed 模式行为不同，必要时支持配置：

```text
DOUYIN_PLAYWRIGHT_HEADLESS=false
```

- Windows 环境下浏览器 profile 锁可能导致重复启动失败，需要进程锁。
- 后端服务重启时要能恢复或重建 Playwright context。

## 建议配置项

```text
DOUYIN_PLAYWRIGHT_PROFILE_DIR=runtime/douyin_playwright_profile
DOUYIN_PLAYWRIGHT_QR_DIR=runtime/douyin_login_qr
DOUYIN_PLAYWRIGHT_HEADLESS=false
DOUYIN_PLAYWRIGHT_PAGE_TIMEOUT_SECONDS=45
DOUYIN_RECHECK_MAX_ITEMS_PER_RUN=100
DOUYIN_RECHECK_COMMENT_TIMEOUT_SECONDS=60
```

## 推荐最终体验

执行结果页主流程：

1. 勾选要校验的执行结果。
2. 点击“校验评论”。
3. 如果未登录，弹出二维码。
4. 扫码后点“我已登录”。
5. 系统自动提交校验。
6. 表格状态从“已提交”变为“校验中”，最后变为“评论存在”或“评论不存在”。

这比当前“一键校验今天全部结果”的体验更可控，也更容易理解。
