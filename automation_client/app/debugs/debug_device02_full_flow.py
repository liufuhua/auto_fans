from __future__ import annotations

import argparse
import time
from pathlib import Path

from app.appium_driver import AppiumDeviceConfig, AppiumDriverFactory
from app.config import settings
from app.douyin_search_support import log_step, quit_with_timeout
from app.douyin_task_executor import DouyinAppiumExecutorConfig
from app.logger import configure_logging
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait


LIKE_XPATH = (
    '//android.widget.LinearLayout[contains(@content-desc,"未点赞") '
    'and contains(@content-desc,"喜欢") and contains(@content-desc,"按钮")]'
)
FAVORITE_XPATH = (
    '//android.widget.LinearLayout[contains(@content-desc,"未选中") '
    'and contains(@content-desc,"收藏") and contains(@content-desc,"按钮")]'
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the real DouyinAppiumTaskExecutor with a fixed local test task, "
            "without claiming or reporting backend tasks."
        )
    )
    parser.add_argument("--udid", default="10AG3R2JNF001KK")
    parser.add_argument("--device-name", default="device_02")
    parser.add_argument("--system-port", type=int, default=8202)
    parser.add_argument("--doctor-name", default="曹迎明")
    parser.add_argument("--keyword", default="脑膜瘤")
    parser.add_argument("--comment", default="真是个好大夫")
    parser.add_argument("--appium-server-url", default=settings.appium_server_url)
    parser.add_argument("--package-name", default=settings.douyin_package_name)
    parser.add_argument("--app-activity", default=settings.douyin_app_activity)
    parser.add_argument("--app", default=settings.douyin_app_path)
    parser.add_argument("--wait-timeout-seconds", type=int, default=12)
    parser.add_argument("--quit-timeout-seconds", type=int, default=5)
    parser.add_argument("--after-open-seconds", type=float, default=2)
    parser.add_argument("--watch-min-seconds", type=float, default=3)
    parser.add_argument("--watch-max-seconds", type=float, default=5)
    parser.add_argument("--before-input-min-seconds", type=float, default=2)
    parser.add_argument("--before-input-max-seconds", type=float, default=4)
    parser.add_argument("--after-input-min-seconds", type=float, default=1)
    parser.add_argument("--after-input-max-seconds", type=float, default=2)
    parser.add_argument("--after-search-min-seconds", type=float, default=2)
    parser.add_argument("--after-search-max-seconds", type=float, default=3)
    parser.add_argument("--after-swipe-min-seconds", type=float, default=1)
    parser.add_argument("--after-swipe-max-seconds", type=float, default=2)
    parser.add_argument("--after-like-min-seconds", type=float, default=1)
    parser.add_argument("--after-like-max-seconds", type=float, default=2)
    parser.add_argument("--after-favorite-min-seconds", type=float, default=1)
    parser.add_argument("--after-favorite-max-seconds", type=float, default=2)
    parser.add_argument("--comment-focus-min-seconds", type=float, default=1)
    parser.add_argument("--comment-focus-max-seconds", type=float, default=2)
    parser.add_argument("--after-comment-input-min-seconds", type=float, default=1)
    parser.add_argument("--after-comment-input-max-seconds", type=float, default=2)
    parser.add_argument("--before-send-min-seconds", type=float, default=1)
    parser.add_argument("--before-send-max-seconds", type=float, default=2)
    parser.add_argument("--max-swipes", type=int, default=2)
    parser.add_argument("--swipe-percent", type=float, default=0.45)
    parser.add_argument(
        "--send-comment",
        action="store_true",
        help="Actually tap the send button. By default the main-flow test inputs only.",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def build_executor_config(args: argparse.Namespace) -> DouyinAppiumExecutorConfig:
    return DouyinAppiumExecutorConfig(
        appium_server_url=args.appium_server_url,
        package_name=args.package_name,
        app_activity=args.app_activity,
        app=args.app,
        wait_timeout_seconds=args.wait_timeout_seconds,
        quit_timeout_seconds=args.quit_timeout_seconds,
        after_open_seconds=args.after_open_seconds,
        before_input_min_seconds=args.before_input_min_seconds,
        before_input_max_seconds=args.before_input_max_seconds,
        after_input_min_seconds=args.after_input_min_seconds,
        after_input_max_seconds=args.after_input_max_seconds,
        after_search_min_seconds=args.after_search_min_seconds,
        after_search_max_seconds=args.after_search_max_seconds,
        after_swipe_min_seconds=args.after_swipe_min_seconds,
        after_swipe_max_seconds=args.after_swipe_max_seconds,
        watch_min_seconds=args.watch_min_seconds,
        watch_max_seconds=args.watch_max_seconds,
        after_like_min_seconds=args.after_like_min_seconds,
        after_like_max_seconds=args.after_like_max_seconds,
        after_favorite_min_seconds=args.after_favorite_min_seconds,
        after_favorite_max_seconds=args.after_favorite_max_seconds,
        comment_focus_min_seconds=args.comment_focus_min_seconds,
        comment_focus_max_seconds=args.comment_focus_max_seconds,
        after_comment_input_min_seconds=args.after_comment_input_min_seconds,
        after_comment_input_max_seconds=args.after_comment_input_max_seconds,
        before_send_min_seconds=args.before_send_min_seconds,
        before_send_max_seconds=args.before_send_max_seconds,
        max_swipes=args.max_swipes,
        swipe_percent=args.swipe_percent,
        execute_video_actions_enabled=True,
        send_comment_enabled=args.send_comment,
    )


def click_home_search_entry(driver) -> None:
    started_at = time.monotonic()
    try:
        element = WebDriverWait(driver, 3).until(
            lambda current_driver: current_driver.find_element(AppiumBy.ACCESSIBILITY_ID, "搜索")
        )
        rect = element.rect
        x = int(rect["x"] + rect["width"] / 2)
        y = int(rect["y"] + rect["height"] / 2)
        driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
        log_step(
            "首页搜索入口已点击："
            f"accessibility id=搜索, rect={rect}, center=({x},{y}), "
            f"elapsed={time.monotonic() - started_at:.2f}s"
        )
        return
    except Exception as exc:  # noqa: BLE001 - fallback to ratio click below.
        log_step(
            "accessibility id=搜索 点击失败，准备使用比例坐标兜底："
            f"{type(exc).__name__}: {exc}"
        )

    size = driver.get_window_size()
    x = int(size["width"] * 0.925)
    y = int(size["height"] * 0.082)
    driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
    log_step(
        "首页搜索入口已点击："
        f"ratio=(0.925,0.082), size={size}, point=({x},{y}), "
        f"elapsed={time.monotonic() - started_at:.2f}s"
    )


def input_search_text(driver, search_text: str) -> None:
    started_at = time.monotonic()
    element = WebDriverWait(driver, 5).until(
        lambda current_driver: current_driver.find_element(
            AppiumBy.ID,
            "com.ss.android.ugc.aweme:id/et_search_kw",
        )
    )
    log_step(
        "搜索输入框已找到："
        f"rect={element.rect}, elapsed={time.monotonic() - started_at:.2f}s"
    )
    element.clear()
    try:
        driver.set_clipboard_text(search_text)
        click_element_center(driver, element, "搜索输入框", time.monotonic())
        driver.press_keycode(279)
        log_step(f"搜索词通过剪贴板粘贴完成：{search_text}")
        return
    except Exception as exc:  # noqa: BLE001 - fallback to send_keys below.
        log_step(f"剪贴板粘贴输入失败，回退 send_keys：{type(exc).__name__}: {exc}")
    element.send_keys(search_text)
    log_step(f"搜索词通过 send_keys 输入完成：{search_text}")


def wait_search_input_visible(driver, label: str) -> None:
    started_at = time.monotonic()
    element = WebDriverWait(driver, 8).until(
        lambda current_driver: current_driver.find_element(
            AppiumBy.ID,
            "com.ss.android.ugc.aweme:id/et_search_kw",
        )
    )
    log_step(
        f"{label}：搜索输入框已出现："
        f"rect={element.rect}, elapsed={time.monotonic() - started_at:.2f}s"
    )


def click_element_center(driver, element, label: str, started_at: float) -> None:
    rect = element.rect
    x = int(rect["x"] + rect["width"] / 2)
    y = int(rect["y"] + rect["height"] / 2)
    driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
    log_step(
        f"{label}已点击："
        f"rect={rect}, center=({x},{y}), elapsed={time.monotonic() - started_at:.2f}s"
    )


def submit_search(driver) -> None:
    started_at = time.monotonic()
    time.sleep(0.5)
    try:
        driver.execute_script("mobile: performEditorAction", {"action": "search"})
        log_step(f"键盘搜索动作已执行：elapsed={time.monotonic() - started_at:.2f}s")
        return
    except Exception as exc:  # noqa: BLE001 - try visible button below.
        log_step(f"键盘搜索动作失败，准备点击右上角搜索按钮：{type(exc).__name__}: {exc}")

    try:
        element = WebDriverWait(driver, 5).until(
            lambda current_driver: current_driver.find_element(
                AppiumBy.ID,
                "com.ss.android.ugc.aweme:id/4un",
            )
        )
        click_element_center(driver, element, "搜索提交按钮", started_at)
        return
    except Exception as exc:  # noqa: BLE001 - fallback to keyboard search below.
        log_step(
            "搜索提交按钮定位失败，准备使用键盘搜索兜底："
            f"{type(exc).__name__}: {exc}"
        )

    fallback_started_at = time.monotonic()
    driver.press_keycode(66)
    log_step(f"回车键搜索动作已执行：elapsed={time.monotonic() - fallback_started_at:.2f}s")


def find_target_on_general_page(driver, target_text: str):
    started_at = time.monotonic()
    escaped_text = target_text.replace('"', '\\"')
    elements = WebDriverWait(driver, 8).until(
        lambda current_driver: current_driver.find_elements(
            AppiumBy.ANDROID_UIAUTOMATOR,
            f'new UiSelector().textContains("{escaped_text}")',
        )
        or False
    )
    log_step(
        "综合页目标文本查找完成："
        f"target={target_text}, count={len(elements)}, elapsed={time.monotonic() - started_at:.2f}s"
    )
    desc_candidates = []
    author_candidates = []
    for index, element in enumerate(elements, start=1):
        text = (getattr(element, "text", "") or "").strip()
        resource_id = element.get_attribute("resourceId") or ""
        rect = element.rect
        log_step(
            f"综合页命中项 {index}: "
            f"resourceId={resource_id!r}, text={text!r}, rect={rect}"
        )
        if resource_id == "com.ss.android.ugc.aweme:id/desc":
            desc_candidates.append(element)
        elif resource_id == "com.ss.android.ugc.aweme:id/+j":
            author_candidates.append(element)
    candidates = desc_candidates or author_candidates
    if not candidates:
        raise RuntimeError(f"综合页未找到可点击的视频描述：{target_text}")
    candidates.sort(key=lambda item: (item.rect["y"], item.rect["x"]))
    return candidates[0]


def click_optional_video_action(driver, *, xpath: str, label: str, wait_seconds: float = 6) -> bool:
    started_at = time.monotonic()
    try:
        element = WebDriverWait(driver, wait_seconds).until(
            lambda current_driver: current_driver.find_element(AppiumBy.XPATH, xpath)
        )
    except Exception as exc:  # noqa: BLE001 - action may already be done.
        log_step(f"{label}按钮未找到或已完成，跳过：{type(exc).__name__}: {exc}")
        return False
    click_element_center(driver, element, label, started_at)
    return True


def open_first_general_result(driver, target_text: str) -> None:
    started_at = time.monotonic()
    element = find_target_on_general_page(driver, target_text)
    click_element_center(driver, element, "综合页目标视频", started_at)
    time.sleep(1.5)


def like_video_only(driver, executor_config: DouyinAppiumExecutorConfig) -> None:
    log_step("阶段 4：进入视频页，开始短暂观看")
    time.sleep(executor_config.watch_min_seconds)
    log_step("阶段 4：开始点赞")
    like_done = click_optional_video_action(driver, xpath=LIKE_XPATH, label="点赞按钮")
    log_step(f"阶段 4：点赞结果={'已点击' if like_done else '跳过'}")
    time.sleep(executor_config.after_like_min_seconds)


def favorite_video_only(driver, executor_config: DouyinAppiumExecutorConfig) -> None:
    log_step("阶段 5：开始收藏")
    favorite_done = click_optional_video_action(driver, xpath=FAVORITE_XPATH, label="收藏按钮")
    log_step(f"阶段 5：收藏结果={'已点击' if favorite_done else '跳过'}")
    time.sleep(executor_config.after_favorite_min_seconds)


def clear_appium_session(args: argparse.Namespace) -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "clear_session.sh"
    subprocess_result = __import__("subprocess").run(
        [str(script_path), args.udid, str(args.system_port)],
        check=False,
        capture_output=True,
        text=True,
    )
    if subprocess_result.stdout.strip():
        log_step(subprocess_result.stdout.strip())
    if subprocess_result.stderr.strip():
        log_step(subprocess_result.stderr.strip())


def create_driver(args: argparse.Namespace):
    app_path = str(Path(args.app).resolve()) if args.app else None
    appium_device = AppiumDeviceConfig(
        udid=args.udid,
        system_port=args.system_port,
        device_name=args.device_name,
        app=app_path,
        app_package=args.package_name,
        app_activity=args.app_activity,
    )
    driver_factory = AppiumDriverFactory(args.appium_server_url, retries=0)
    log_step(f"创建 Appium driver：device={args.device_name}, udid={args.udid}")
    managed_driver = driver_factory.create(appium_device)
    driver = managed_driver.driver
    log_step("Appium driver 创建成功")
    try:
        driver.implicitly_wait(0)
        driver.update_settings(
            {
                "waitForIdleTimeout": 0,
                "waitForSelectorTimeout": 3000,
            }
        )
        log_step("UiAutomator2 settings 已更新：waitForIdleTimeout=0")
    except Exception as exc:  # noqa: BLE001 - settings are best effort for debug flow.
        log_step(f"UiAutomator2 settings 更新失败，继续执行：{type(exc).__name__}: {exc}")
    return managed_driver, driver


def close_driver_and_clear(
    *,
    args: argparse.Namespace,
    driver,
    quit_timeout_seconds: int,
    label: str,
) -> None:
    log_step(f"{label}：释放 Appium driver")
    quit_with_timeout(driver, quit_timeout_seconds)
    log_step(f"{label}：Appium driver 已释放")
    clear_appium_session(args)


def run_open_search_entry(args: argparse.Namespace, executor_config: DouyinAppiumExecutorConfig) -> None:
    managed_driver, driver = create_driver(args)
    del managed_driver
    try:
        log_step("阶段 1：确保抖音已打开")
        driver.activate_app(executor_config.package_name)
        if executor_config.after_open_seconds > 0:
            time.sleep(executor_config.after_open_seconds)
        log_step("阶段 1：确保抖音已打开over")
        log_step("阶段 1：点击首页搜索入口")
        click_home_search_entry(driver)
        wait_search_input_visible(driver, "阶段 1")
    finally:
        close_driver_and_clear(
            args=args,
            driver=driver,
            quit_timeout_seconds=executor_config.quit_timeout_seconds,
            label="阶段 1",
        )


def run_input_and_submit_search(
    args: argparse.Namespace,
    executor_config: DouyinAppiumExecutorConfig,
) -> None:
    managed_driver, driver = create_driver(args)
    del managed_driver
    try:
        search_text = f"{args.keyword} {args.doctor_name}"
        log_step("阶段 2：等待搜索输入框并输入搜索词")
        input_search_text(driver, search_text)
        log_step("阶段 2：点击搜索提交按钮")
        submit_search(driver)
        log_step("阶段 2：等待搜索结果页稳定")
        time.sleep(executor_config.after_search_min_seconds)
    finally:
        close_driver_and_clear(
            args=args,
            driver=driver,
            quit_timeout_seconds=executor_config.quit_timeout_seconds,
            label="阶段 2",
        )


def run_analyze_general_page(
    args: argparse.Namespace,
    executor_config: DouyinAppiumExecutorConfig,
) -> None:
    managed_driver, driver = create_driver(args)
    del managed_driver
    try:
        log_step("阶段 3：在综合页查找目标医生")
        open_first_general_result(driver, args.doctor_name)
        log_step("阶段 3：目标视频已点击，等待进入视频页")
    finally:
        close_driver_and_clear(
            args=args,
            driver=driver,
            quit_timeout_seconds=executor_config.quit_timeout_seconds,
            label="阶段 3",
        )


def run_like_video(
    args: argparse.Namespace,
    executor_config: DouyinAppiumExecutorConfig,
) -> None:
    managed_driver, driver = create_driver(args)
    del managed_driver
    try:
        like_video_only(driver, executor_config)
    finally:
        close_driver_and_clear(
            args=args,
            driver=driver,
            quit_timeout_seconds=executor_config.quit_timeout_seconds,
            label="阶段 4",
        )


def run_favorite_video(
    args: argparse.Namespace,
    executor_config: DouyinAppiumExecutorConfig,
) -> None:
    managed_driver, driver = create_driver(args)
    del managed_driver
    try:
        favorite_video_only(driver, executor_config)
    finally:
        close_driver_and_clear(
            args=args,
            driver=driver,
            quit_timeout_seconds=executor_config.quit_timeout_seconds,
            label="阶段 5",
        )


def run_attach_after_video_actions(
    args: argparse.Namespace,
    executor_config: DouyinAppiumExecutorConfig,
) -> None:
    managed_driver, driver = create_driver(args)
    del managed_driver
    try:
        log_step("阶段 6：点赞收藏后已重连到视频页面，临时停止")
        time.sleep(1)
    finally:
        close_driver_and_clear(
            args=args,
            driver=driver,
            quit_timeout_seconds=executor_config.quit_timeout_seconds,
            label="阶段 6",
        )


def main() -> None:
    args = parse_args()
    configure_logging(debug=args.debug)
    executor_config = build_executor_config(args)

    run_open_search_entry(args, executor_config)
    run_input_and_submit_search(args, executor_config)
    run_analyze_general_page(args, executor_config)
    run_like_video(args, executor_config)
    run_favorite_video(args, executor_config)
    run_attach_after_video_actions(args, executor_config)
    log_step("单独脚本临时停止：视频页点赞收藏后已完成重连")


if __name__ == "__main__":
    main()
