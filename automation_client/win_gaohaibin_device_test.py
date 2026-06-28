from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
AUTOMATION_CLIENT_DIR = ROOT_DIR / "automation_client"

sys.path.insert(0, str(AUTOMATION_CLIENT_DIR))

from app.api_client import AutomationApiClient, ClaimTaskResult, StartTaskResult  # noqa: E402
from app.appium_server_manager import AppiumServerManager  # noqa: E402
from app.config import settings  # noqa: E402
from app.device_manager import BackendDeviceConfig  # noqa: E402
from app.douyin_task_executor import DouyinAppiumExecutorConfig, DouyinAppiumTaskExecutor  # noqa: E402
from app.logger import configure_device_file_logger, configure_logging, log_context  # noqa: E402


DEFAULT_UDID = "MYQUT19C05007064"
DEFAULT_DEVICE_NAME = "北京2.0"
DEFAULT_SYSTEM_PORT = 8206
DEFAULT_APPIUM_SERVER_URL = "http://127.0.0.1:4726"
DEFAULT_DOCTOR = "高海滨"
DEFAULT_KEYWORD = "颅骨修补"
DEFAULT_COMMENT = "医德高尚"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Use one fixed Android device to run the real Douyin main flow with "
            "doctor=高海滨, keyword=颅骨修补, comment=医德高尚."
        )
    )
    parser.add_argument("--udid", default=DEFAULT_UDID)
    parser.add_argument("--device-name", default=DEFAULT_DEVICE_NAME)
    parser.add_argument("--system-port", type=int, default=DEFAULT_SYSTEM_PORT)
    parser.add_argument("--appium-server-url", default=DEFAULT_APPIUM_SERVER_URL)
    parser.add_argument("--api-base-url", default=settings.api_base_url)
    parser.add_argument("--doctor", default=DEFAULT_DOCTOR)
    parser.add_argument("--keyword", default=DEFAULT_KEYWORD)
    parser.add_argument("--comment", default=DEFAULT_COMMENT)
    parser.add_argument("--task-item-id", type=int, default=990001)
    parser.add_argument("--result-id", type=int, default=990001)
    parser.add_argument("--comment-bank-item-id", type=int, default=990001)
    parser.add_argument("--max-swipes", type=int, default=2)
    parser.add_argument("--swipe-percent", type=float, default=0.45)
    parser.add_argument("--watch-min-seconds", type=float, default=15)
    parser.add_argument("--watch-max-seconds", type=float, default=60)
    parser.add_argument(
        "--no-send-comment",
        action="store_true",
        help="Input the comment but do not tap the send button.",
    )
    parser.add_argument(
        "--no-manage-appium",
        action="store_true",
        help="Do not start/stop Appium in this script; use an already running server.",
    )
    parser.add_argument(
        "--no-force-stop-before",
        action="store_true",
        help="Do not force-stop Douyin before the test starts.",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def ensure_adb_on_path() -> None:
    platform_tools = Path.home() / "AppData/Local/Android/Sdk/platform-tools"
    if not platform_tools.exists():
        return
    path_parts = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    if str(platform_tools).lower() not in {item.lower() for item in path_parts}:
        os.environ["PATH"] = str(platform_tools) + os.pathsep + os.environ.get("PATH", "")


def force_stop_douyin(udid: str) -> None:
    commands = [
        ["adb", "-s", udid, "shell", "am", "force-stop", settings.douyin_package_name],
        ["adb", "-s", udid, "shell", "input", "keyevent", "HOME"],
    ]
    for command in commands:
        subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )


def build_device(args: argparse.Namespace) -> BackendDeviceConfig:
    return BackendDeviceConfig(
        id=990001,
        name=args.device_name,
        udid=args.udid,
        system_port=args.system_port,
        enabled_status="enabled",
        appium_server_url=args.appium_server_url,
    )


def build_task(args: argparse.Namespace) -> ClaimTaskResult:
    return ClaimTaskResult(
        has_task=True,
        task_id=args.task_item_id,
        task_item_id=args.task_item_id,
        doctor_id=990001,
        doctor_name=args.doctor,
        keyword_id=990001,
        keyword=args.keyword,
        search_word=args.keyword,
        comment_bank_item_id=args.comment_bank_item_id,
        comment_content=args.comment,
    )


def main() -> int:
    args = parse_args()
    ensure_adb_on_path()
    configure_logging(debug=args.debug)

    device = build_device(args)
    task = build_task(args)
    runtime_dir = AUTOMATION_CLIENT_DIR / "runtime"
    log_file_path = configure_device_file_logger(
        device_name=f"{device.name}_高海滨测试",
        runtime_dir=runtime_dir,
        debug=args.debug,
    )

    manager: AppiumServerManager | None = None
    if not args.no_manage_appium:
        manager = AppiumServerManager(
            default_server_url=args.appium_server_url,
            log_dir=ROOT_DIR / "logs",
            ports_file=ROOT_DIR / "logs" / "appium_ports.txt",
            on_demand_file=ROOT_DIR / "logs" / "appium_on_demand.txt",
        )

    print(
        "single-device main-flow test: "
        f"device={device.name}/{device.udid}:{device.system_port}, "
        f"appium={device.appium_server_url}, doctor={args.doctor}, "
        f"keyword={args.keyword}, comment={args.comment}, log={log_file_path}"
    )

    try:
        if manager is not None:
            manager.start_for_devices([device])
        if not args.no_force_stop_before:
            force_stop_douyin(device.udid)

        executor = DouyinAppiumTaskExecutor(
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
        with log_context(
            device_name=device.name,
            udid=device.udid,
            task_item_id=args.task_item_id,
            result_id=args.result_id,
            log_file_path=log_file_path,
        ):
            result = executor.execute(
                task=task,
                start_result=StartTaskResult(result_id=args.result_id, status="running"),
                device=device,
                api_client=AutomationApiClient(args.api_base_url),
            )
        print(f"test finished: {result}")
        return 0 if result.status == "success" else 1
    finally:
        if manager is not None:
            manager.stop_for_devices([device])


if __name__ == "__main__":
    raise SystemExit(main())
