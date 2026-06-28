from __future__ import annotations

import argparse
import subprocess
import time
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.device_manager import BackendDeviceConfig
from app.douyin_task_executor import DouyinAppiumExecutorConfig, DouyinAppiumTaskExecutor
from app.logger import configure_logging
from app.douyin_search_support import log_step, quit_with_timeout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Debug only the Douyin search input clipboard paste step. "
            "This script does not claim backend tasks and does not submit search."
        )
    )
    parser.add_argument("--udid", default="3B15CX00P3A00000")
    parser.add_argument("--device-name", default="device_05")
    parser.add_argument("--system-port", type=int, default=8205)
    parser.add_argument("--appium-server-url", default=settings.appium_server_url)
    parser.add_argument("--search-text", default="脑膜瘤 曹迎明")
    parser.add_argument("--after-open-seconds", type=float, default=2)
    parser.add_argument("--after-search-click-seconds", type=float, default=3)
    parser.add_argument("--after-paste-seconds", type=float, default=5)
    parser.add_argument("--keep-open-seconds", type=float, default=30)
    parser.add_argument(
        "--strategies",
        default="clipboard_keycode,mobile_type,send_keys,adb_input_text",
        help=(
            "Comma separated strategies: clipboard_keycode,mobile_type,send_keys,"
            "adb_input_text"
        ),
    )
    parser.add_argument(
        "--input-ready",
        action="store_true",
        help="Assume Douyin is already on the search input page and only test paste.",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def _read_element_text(element) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for name in ("text", "contentDescription", "content-desc", "value"):
        try:
            values[name] = element.get_attribute(name)
        except Exception as exc:  # noqa: BLE001 - best effort diagnostics.
            values[name] = f"<{type(exc).__name__}: {exc}>"
    return values


def _save_screenshot(driver, udid: str) -> Path | None:
    screenshot_dir = Path("runtime/screenshots")
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = screenshot_dir / f"{udid}_search_clipboard_paste_{timestamp}.png"
    try:
        driver.save_screenshot(str(path))
        return path
    except Exception as exc:  # noqa: BLE001 - diagnostics only.
        log_step(f"保存截图失败：{type(exc).__name__}: {exc}")
        return None


def _current_text(element) -> str:
    try:
        value = element.get_attribute("text")
    except Exception:  # noqa: BLE001 - diagnostics only.
        value = ""
    return "" if value in (None, "null") else str(value)


def _clear_input(driver, element) -> None:
    try:
        element.clear()
    except Exception as exc:  # noqa: BLE001 - fallback below.
        log_step(f"element.clear 失败，继续尝试按键清空：{type(exc).__name__}: {exc}")
    try:
        element.click()
    except Exception:  # noqa: BLE001 - best effort.
        pass
    try:
        driver.press_keycode(123)  # MOVE_END
        for _ in range(30):
            driver.press_keycode(67)  # DEL
    except Exception as exc:  # noqa: BLE001 - best effort.
        log_step(f"按键清空失败：{type(exc).__name__}: {exc}")


def _adb_input_text(udid: str, text: str) -> None:
    # Android's built-in `input text` is not reliable for Chinese, but we keep
    # it in this probe to prove whether this device/IME supports it.
    escaped = text.replace(" ", "%s")
    result = subprocess.run(
        ["adb", "-s", udid, "shell", "input", "text", escaped],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.stdout.strip():
        log_step(result.stdout.strip())
    if result.stderr.strip():
        log_step(result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(f"adb input text failed: returnCode={result.returncode}")


def _run_strategy(driver, executor, args, element, strategy: str, text: str) -> None:
    started_at = time.monotonic()
    if strategy == "clipboard_keycode":
        executor._input_search_text(driver, element, text)
        return
    if strategy == "mobile_type":
        element.click()
        driver.execute_script("mobile: type", {"text": text})
        log_step(f"mobile: type 已执行：elapsed={time.monotonic() - started_at:.2f}s")
        return
    if strategy == "send_keys":
        element.click()
        element.send_keys(text)
        log_step(f"send_keys 已执行：elapsed={time.monotonic() - started_at:.2f}s")
        return
    if strategy == "adb_input_text":
        element.click()
        _adb_input_text(args.udid, text)
        log_step(f"adb input text 已执行：elapsed={time.monotonic() - started_at:.2f}s")
        return
    raise ValueError(f"Unknown strategy: {strategy}")


def main() -> None:
    cli_args = parse_args()
    configure_logging(debug=cli_args.debug)

    config = DouyinAppiumExecutorConfig(
        appium_server_url=cli_args.appium_server_url,
        after_open_seconds=cli_args.after_open_seconds,
        before_input_min_seconds=cli_args.after_search_click_seconds,
        before_input_max_seconds=cli_args.after_search_click_seconds,
        execute_video_actions_enabled=False,
        send_comment_enabled=False,
    )
    executor = DouyinAppiumTaskExecutor(config)
    device = BackendDeviceConfig(
        id=0,
        name=cli_args.device_name,
        udid=cli_args.udid,
        system_port=cli_args.system_port,
        enabled_status="enabled",
    )
    args = executor._build_args(device, config=config)

    log_step(
        "开始搜索粘贴单项测试："
        f"device={cli_args.device_name}, udid={cli_args.udid}, "
        f"systemPort={cli_args.system_port}, searchText={cli_args.search_text}"
    )
    managed_driver = executor._create_driver_from_args(args)
    driver = managed_driver.driver
    try:
        if cli_args.input_ready:
            log_step("input-ready 模式：跳过打开抖音和点击首页搜索入口，直接等待当前搜索输入框")
        else:
            actions = executor._build_actions(
                driver=driver,
                args=args,
                task_id="debug_search_clipboard_paste_home",
            )
            driver = executor._ensure_douyin_home_page(
                driver=driver,
                actions=actions,
                args=args,
            )

            executor._click_home_search_entry(driver)
            log_step(f"首页搜索入口点击后等待 {cli_args.after_search_click_seconds:.2f}s")
            time.sleep(cli_args.after_search_click_seconds)

            log_step("搜索入口点击后释放 driver，执行 clear_session，再重连等待输入框")
            driver = executor._reconnect_driver(args=args, driver=driver)
        actions = executor._build_actions(
            driver=driver,
            args=args,
            task_id="debug_search_clipboard_paste_input",
        )
        strategies = [item.strip() for item in cli_args.strategies.split(",") if item.strip()]
        for strategy in strategies:
            search_input = actions._wait_visible("search_input")
            log_step(f"策略 {strategy}：搜索输入框已出现：rect={search_input.rect}")

            _clear_input(driver, search_input)
            time.sleep(0.5)
            search_input = actions._wait_visible("search_input")
            log_step(f"策略 {strategy}：清空后输入框 text={_current_text(search_input)!r}")

            try:
                _run_strategy(driver, executor, args, search_input, strategy, cli_args.search_text)
            except Exception as exc:  # noqa: BLE001 - continue to next strategy.
                log_step(f"策略 {strategy} 执行失败：{type(exc).__name__}: {exc}")
            log_step(f"策略 {strategy}：输入后等待 {cli_args.after_paste_seconds:.2f}s")
            time.sleep(cli_args.after_paste_seconds)

            search_input = actions._wait_visible("search_input")
            values = _read_element_text(search_input)
            actual_text = _current_text(search_input)
            source_has_text = cli_args.search_text in driver.page_source
            log_step(f"策略 {strategy}：搜索输入框属性：{values}")
            log_step(
                f"策略 {strategy}：actual={actual_text!r}, "
                f"matched={actual_text == cli_args.search_text}, "
                f"pageSourceHasText={source_has_text}"
            )

        screenshot = _save_screenshot(driver, cli_args.udid)
        if screenshot is not None:
            log_step(f"截图已保存：{screenshot}")

        if cli_args.keep_open_seconds > 0:
            log_step(f"保持当前页面 {cli_args.keep_open_seconds:.2f}s，方便观察真机")
            time.sleep(cli_args.keep_open_seconds)
    finally:
        quit_with_timeout(driver, args.quit_timeout_seconds)
        executor._clear_appium_session(args)
        log_step("搜索粘贴单项测试结束")


if __name__ == "__main__":
    main()
