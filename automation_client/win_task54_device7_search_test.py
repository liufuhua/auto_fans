from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
AUTOMATION_CLIENT_DIR = ROOT_DIR / "automation_client"
RUNTIME_DIR = AUTOMATION_CLIENT_DIR / "runtime"

sys.path.insert(0, str(AUTOMATION_CLIENT_DIR))

from app.api_client import AutomationApiClient, ClaimTaskResult, StartTaskResult  # noqa: E402
from app.appium_driver import AppiumDeviceConfig  # noqa: E402
from app.config import settings  # noqa: E402
from app.device_manager import BackendDeviceConfig  # noqa: E402
from app.douyin_task_executor import DouyinAppiumExecutorConfig, DouyinAppiumTaskExecutor  # noqa: E402
from app.douyin_search_support import log_step  # noqa: E402
from app.logger import configure_logging  # noqa: E402


@dataclass(frozen=True)
class TaskFlowData:
    task_id: int
    task_item_id: int
    doctor_id: int
    doctor_name: str
    keyword_id: int
    keyword: str
    comment_bank_item_id: int
    comment_content: str


def ensure_adb_on_path() -> None:
    platform_tools = Path.home() / "AppData/Local/Android/Sdk/platform-tools"
    if not platform_tools.exists():
        return
    current_path = str(platform_tools)
    path_parts = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    if current_path.lower() not in {item.lower() for item in path_parts}:
        os.environ["PATH"] = current_path + os.pathsep + os.environ.get("PATH", "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local fixed-data test for the Douyin Appium search flow."
    )
    parser.add_argument("--task-id", type=int, default=54)
    parser.add_argument("--device-name", default="device_07")
    parser.add_argument("--udid", default="MYQUT19C05007064")
    parser.add_argument("--system-port", type=int, default=8207)
    parser.add_argument("--doctor-name", default="姜争")
    parser.add_argument("--keyword", default="结直肠癌")
    parser.add_argument("--mode", choices=["search", "full"], default="search")
    parser.add_argument("--submit-search", action="store_true", default=True)
    parser.add_argument("--no-submit-search", dest="submit_search", action="store_false")
    parser.add_argument("--appium-server-url", default=settings.appium_server_url)
    parser.add_argument("--watch-min-seconds", type=float, default=10)
    parser.add_argument("--watch-max-seconds", type=float, default=20)
    parser.add_argument("--max-swipes", type=int, default=2)
    parser.add_argument("--swipe-percent", type=float, default=0.45)
    parser.add_argument("--comment", default="真的很好")
    parser.add_argument("--no-send-comment", action="store_true")
    parser.add_argument("--no-force-stop-before", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_task_flow_data(args: argparse.Namespace) -> TaskFlowData:
    return TaskFlowData(
        task_id=args.task_id,
        task_item_id=900054,
        doctor_id=900054,
        doctor_name=args.doctor_name.strip(),
        keyword_id=900054,
        keyword=args.keyword.strip(),
        comment_bank_item_id=900054,
        comment_content=args.comment.strip(),
    )


def load_device(args: argparse.Namespace) -> BackendDeviceConfig:
    return BackendDeviceConfig(
        id=900054,
        name=args.device_name,
        udid=args.udid,
        system_port=args.system_port,
        enabled_status="enabled",
    )


def build_task(data: TaskFlowData) -> ClaimTaskResult:
    return ClaimTaskResult(
        has_task=True,
        task_id=data.task_id,
        task_item_id=data.task_item_id,
        doctor_id=data.doctor_id,
        doctor_name=data.doctor_name,
        keyword_id=data.keyword_id,
        keyword=data.keyword,
        search_word=data.keyword,
        comment_bank_item_id=data.comment_bank_item_id,
        comment_content=data.comment_content,
    )


def force_stop_douyin(udid: str) -> None:
    commands = [
        ["adb", "-s", udid, "shell", "am", "force-stop", settings.douyin_package_name],
        ["adb", "-s", udid, "shell", "input", "keyevent", "HOME"],
        [
            "adb",
            "-s",
            udid,
            "shell",
            "monkey",
            "-p",
            settings.douyin_package_name,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
    ]
    for command in commands:
        subprocess.run(command, check=False, capture_output=True, text=True, timeout=20)


def build_executor(args: argparse.Namespace) -> DouyinAppiumTaskExecutor:
    return DouyinAppiumTaskExecutor(
        DouyinAppiumExecutorConfig(
            appium_server_url=args.appium_server_url,
            watch_min_seconds=args.watch_min_seconds,
            watch_max_seconds=args.watch_max_seconds,
            max_swipes=args.max_swipes,
            swipe_percent=args.swipe_percent,
            execute_video_actions_enabled=True,
            send_comment_enabled=not args.no_send_comment,
        )
    )


def run_search_test(
    *,
    args: argparse.Namespace,
    executor: DouyinAppiumTaskExecutor,
    device: BackendDeviceConfig,
    data: TaskFlowData,
) -> None:
    app_args = executor._build_args(device)
    app_path = str(Path(app_args.app).resolve()) if app_args.app else None
    appium_device = AppiumDeviceConfig(
        udid=device.udid,
        system_port=device.system_port,
        device_name=device.name,
        app=app_path,
        app_package=app_args.package_name,
        app_activity=app_args.app_activity,
    )
    search_text = f"{data.keyword} {data.doctor_name}"
    waits: dict[str, float] = {}
    managed_driver = executor.driver_factory.create(appium_device)
    driver = managed_driver.driver
    try:
        executor._configure_driver(driver)
        actions = executor._build_actions(
            driver=driver,
            args=app_args,
            task_id="device7_task54_search_test_home",
        )
        log_step("fast search test: open Douyin without slow home-page recovery")
        actions.open_douyin()
        if app_args.after_open_seconds > 0:
            time.sleep(app_args.after_open_seconds)
        actions = executor._build_actions(
            driver=driver,
            args=app_args,
            task_id="device7_task54_search_test_click",
        )
        driver = executor._click_home_search_entry_and_reconnect(
            actions=actions,
            args=app_args,
            waits=waits,
        )
        actions = executor._build_actions(
            driver=driver,
            args=app_args,
            task_id="device7_task54_search_test_input",
        )
        if args.submit_search:
            driver = executor._input_search_text_submit_and_reconnect(
                actions=actions,
                args=app_args,
                search_text=search_text,
                waits=waits,
            )
            log_step(f"device7 search test submitted: {search_text}")
        else:
            search_input = actions._wait_visible("search_input")
            log_step(f"device7 search input visible: rect={search_input.rect}")

        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        screenshot_path = RUNTIME_DIR / "device7_task54_search_test.png"
        source_path = RUNTIME_DIR / "device7_task54_search_test.xml"
        driver.save_screenshot(str(screenshot_path))
        source_path.write_text(driver.page_source, encoding="utf-8")
        print(f"screenshot={screenshot_path}")
        print(f"page_source={source_path}")
    finally:
        try:
            driver.quit()
        except Exception as exc:  # noqa: BLE001 - Appium session may already be cleared by reconnect.
            log_step(f"skip driver quit error: {type(exc).__name__}: {exc}")


def run_full_flow(
    *,
    args: argparse.Namespace,
    executor: DouyinAppiumTaskExecutor,
    device: BackendDeviceConfig,
    data: TaskFlowData,
) -> int:
    result = executor.execute(
        task=build_task(data),
        start_result=StartTaskResult(result_id=900054, status="running"),
        device=device,
        api_client=AutomationApiClient(args.api_base_url),
    )
    print(f"task flow finished: {result}")
    return 0 if result.status in {"success", "skipped"} else 1


def main() -> int:
    args = parse_args()
    ensure_adb_on_path()
    configure_logging(debug=args.debug)

    data = load_task_flow_data(args)
    device = load_device(args)
    print(
        "loaded task: "
        f"taskId={data.task_id}, taskItemId={data.task_item_id}, "
        f"doctor={data.doctor_name}, keyword={data.keyword}, "
        f"commentBankItemId={data.comment_bank_item_id}, comment={data.comment_content}"
    )
    print(
        "loaded device: "
        f"name={device.name}, udid={device.udid}, systemPort={device.system_port}"
    )
    if args.dry_run:
        return 0

    if not args.no_force_stop_before:
        force_stop_douyin(device.udid)
        time.sleep(2)

    executor = build_executor(args)
    if args.mode == "full":
        return run_full_flow(args=args, executor=executor, device=device, data=data)
    run_search_test(args=args, executor=executor, device=device, data=data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
