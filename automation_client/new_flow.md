# 当前主流程阶段说明

本文档记录 `DouyinAppiumTaskExecutor` 当前真实执行流程。它不再描述早期单机调试脚本，而是描述管理后台启动业务后，`TaskWorker` 调用主流程时的实际阶段。

主流程文件：

```text
automation_client/app/douyin_task_executor.py
```

主流程类：

```python
DouyinAppiumTaskExecutor
```

快速测试脚本：

```text
automation_client/app/debug_executor_task39.py
```

说明：`debug_executor_task39.py` 只是本地快速调用主流程的测试入口，正式业务仍由管理后台启动，`TaskWorker` 领取任务后调用同一个 `DouyinAppiumTaskExecutor`。

## 核心原则

- 页面发生明显变化后，不继续长期复用旧 Appium session。
- 关键阶段完成后执行：释放 driver -> clear_session -> 重新创建 driver。
- 每台设备使用独立 `systemPort`。
- 每次执行任务前，从后端读取“时间设置”页面配置的随机等待时间。
- 如果后端时间设置读取失败，使用本地默认时间，不中断任务。
- 当前成功流程不再获取视频分享链接。
- 评论完成后强制退出抖音，不再执行旧的关闭评论区、分享、复制链接、返回首页流程。

## 阶段 0：领取任务和读取配置

触发方：

```text
TaskWorker
```

步骤：

1. worker 检查设备是否在线。
2. worker 检查后台业务开关是否为 running。
3. worker 调用后端领取任务。
4. 后端返回医生、关键词、评论内容、任务明细 id、评论词库 id。
5. worker 调用后端 `start_task` 创建或复用 running 结果。
6. `DouyinAppiumTaskExecutor.execute()` 开始执行。
7. 执行器读取后台时间设置：

```text
GET /api/automation/timing-settings
```

当前 10 项时间设置：

```text
before_input
after_input
after_search
watch_video
after_like
after_favorite
comment_pre_input_click
comment_focus
after_comment_input
before_send_comment
```

## 阶段 1：创建 driver 并打开抖音

函数：

```python
DouyinAppiumTaskExecutor._ensure_douyin_home_page()
```

步骤：

1. 创建 Appium driver。
2. 调用 `DouyinActions.open_douyin()` 激活抖音。
3. 等待 `after_open_seconds`。
4. 释放 driver。
5. 执行 `clear_session`。
6. 重新创建 driver。
7. 读取 page source。
8. 判断是否已经在抖音首页。

首页判断：

```text
页面存在：首页 / 朋友 / 消息 等底部 Tab
页面不存在：搜索输入框 resource-id=com.ss.android.ugc.aweme:id/et_search_kw
```

如果不在首页：

1. 如果存在链接复制成功弹窗，先关闭。
2. 如果在视频页，点击左上角返回。
3. 如果在搜索页，点击搜索页返回。
4. 仍未回到首页时，最多执行 4 次 Android back。
5. 仍无法识别首页，则任务失败。

## 阶段 2：点击首页搜索入口

函数：

```python
DouyinAppiumTaskExecutor._click_home_search_entry_and_reconnect()
```

步骤：

1. 点击首页搜索入口。
2. 随机等待 `before_input`。
3. 释放 driver。
4. 执行 `clear_session`。
5. 重新创建 driver，等待搜索输入框。

当前首页搜索入口策略：

1. 优先使用 `accessibility id=搜索` 定位。
2. 找到元素后读取 `rect`，点击元素中心点。
3. 如果定位失败，使用屏幕比例坐标兜底。

## 阶段 3：输入搜索词并提交

函数：

```python
DouyinAppiumTaskExecutor._input_search_text_submit_and_reconnect()
```

搜索词格式：

```text
searchWord doctorName
```

示例：

```text
脑膜瘤 张明山
```

步骤：

1. 定位搜索输入框。
2. 清空输入框。
3. 输入搜索词。
4. 随机等待 `after_input`。
5. 点击搜索提交按钮或执行回车搜索动作。
6. 随机等待 `after_search`。
7. 释放 driver。
8. 执行 `clear_session`。
9. 重新创建 driver，进入搜索结果读取阶段。

## 阶段 4：查找并打开目标视频

函数：

```python
DouyinAppiumTaskExecutor._find_and_open_matching_video()
DouyinAppiumTaskExecutor._scan_search_result_tab_for_author()
```

查找策略：

1. 先在当前搜索结果页查找目标医生。
2. 读取当前页可见作者名。
3. 查找目标医生相关视频元素。
4. 如果命中目标医生但视频已经点赞，则跳过该视频。
5. 如果当前页未找到，向上滑动翻页。
6. 每次翻页后固定等待 2 秒。
7. 翻页后释放 driver，执行 `clear_session`，重连后继续读取。
8. 当前页连续 3 次未找到后，切换到“视频”Tab。
9. 在“视频”Tab 重复最多 3 次查找和翻页。
10. 找到未点赞目标视频后打开视频。

查找失败：

1. 强制退出抖音。
2. 抛出 `SearchResultNotFoundError`。
3. worker 回传 failed。

## 阶段 5：观看视频并点赞

函数：

```python
DouyinAppiumTaskExecutor._like_video_and_reconnect()
```

步骤：

1. 进入视频页。
2. 随机等待 `watch_video`，模拟观看视频。
3. 释放 driver。
4. 执行 `clear_session`。
5. 重新创建 driver。
6. 查找未点赞按钮。
7. 如果找到，点击点赞。
8. 如果找不到，认为可能已经点赞或按钮不可见，跳过。
9. 随机等待 `after_like`。
10. 释放 driver。
11. 执行 `clear_session`。
12. 重新创建 driver。

点赞 XPath：

```xpath
//android.widget.LinearLayout[contains(@content-desc,"未点赞") and contains(@content-desc,"喜欢") and contains(@content-desc,"按钮")]
```

## 阶段 6：收藏视频

函数：

```python
DouyinAppiumTaskExecutor._favorite_video_and_reconnect()
```

步骤：

1. 查找未收藏按钮。
2. 如果找到，点击收藏。
3. 如果找不到，认为可能已经收藏或按钮不可见，跳过。
4. 随机等待 `after_favorite`。
5. 释放 driver。
6. 执行 `clear_session`。
7. 重新创建 driver。

收藏 XPath：

```xpath
//android.widget.LinearLayout[contains(@content-desc,"未选中") and contains(@content-desc,"收藏") and contains(@content-desc,"按钮")]
```

## 阶段 7：打开评论面板并输入评论

函数：

```python
DouyinAppiumTaskExecutor._comment_video_and_reconnect()
```

步骤：

1. 点击评论按钮。
2. 等待评论输入框出现。
3. 点击评论输入框。
4. 随机等待 `comment_pre_input_click`，等待键盘和输入框稳定。
5. 释放 driver。
6. 执行 `clear_session`。
7. 重新创建 driver。
8. 再次聚焦评论输入框。
9. 随机等待 `comment_focus`。
10. 输入评论内容。
11. 随机等待 `after_comment_input`。

输入策略：

```text
优先 mobile: type
失败后 fallback 到 element.send_keys
再失败时 fallback 到 set_value / clipboard paste
```

当前正式流程为了稳定性，评论输入后允许跳过二次 page source 校验，避免个别设备再次 findElement 导致 UiAutomator2 卡死。

## 阶段 8：是否发送评论

配置：

```python
DouyinAppiumExecutorConfig.send_comment_enabled
```

如果 `send_comment_enabled=True`：

1. 随机等待 `before_send_comment`。
2. 点击发送按钮。
3. 等待 3 秒，确保发送请求已发出。
4. 强制退出抖音。
5. 返回 success。

如果 `send_comment_enabled=False`：

1. 不点击发送按钮。
2. 等待 3 秒。
3. 强制退出抖音。
4. 返回 success。

说明：

- 当前测试阶段可以通过关闭发送评论，避免消耗真实评论资源。
- 不发送时，后端仍会按当前任务执行结果处理，具体是否启用取决于业务测试目的。

## 阶段 9：强制退出抖音和回传结果

强制退出：

```text
adb -s {udid} shell am force-stop com.ss.android.ugc.aweme
```

执行成功：

```python
TaskExecutionResult.success()
```

执行失败：

```python
TaskExecutionResult.failed(fail_reason=...)
```

worker 回传：

```text
POST /api/automation/tasks/{task_item_id}/report
```

成功回传字段：

```text
status=success
resultId
commentBankItemId
publishAccount
logUrl
```

失败回传字段：

```text
status=failed
failReason
screenshotUrl
logUrl
```

当前成功结果默认不包含 `videoLink`，因为主流程已经移除了旧分享复制链接阶段。

## 阶段 10：释放资源和自动停止业务

无论成功或失败：

1. `finally` 中释放 Appium driver。
2. 执行 `clear_session` 清理 UiAutomator2 / Appium Settings / adb forward。
3. worker 将本地设备状态设回 `idle`。
4. 本轮任务结束后调用后端自动停止业务。
5. 管理后台“启动业务”按钮恢复到等待开启状态。

## 时间设置默认值

| key | 默认最小秒 | 默认最大秒 |
| --- | ---: | ---: |
| `before_input` | 3 | 15 |
| `after_input` | 2 | 5 |
| `after_search` | 2 | 3 |
| `watch_video` | 15 | 300 |
| `after_like` | 3 | 20 |
| `after_favorite` | 3 | 20 |
| `comment_pre_input_click` | 2 | 5 |
| `comment_focus` | 2 | 5 |
| `after_comment_input` | 5 | 5 |
| `before_send_comment` | 0 | 0 |

这些值可以在管理后台“时间设置”页面修改。

## 当前稳定性结论

- “页面大变化后断开重连”的策略有效，明显降低了 UiAutomator2 卡死概率。
- 搜索、打开视频、点赞、收藏、评论输入已经迁入主流程。
- 评论后强制退出抖音比旧的逐层关闭评论区、分享框、搜索页更稳定。
- 后续重点优化方向是：减少固定 2 秒等待、继续优化点赞/收藏按钮状态判断、把 `debug_executor_task39` 泛化为不绑定 39 的主流程测试入口。
