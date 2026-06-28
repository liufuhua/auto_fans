from __future__ import annotations

import argparse

from app.api_client import AutomationApiClient, ClaimTaskResult, StartTaskResult
from app.config import settings
from app.device_manager import BackendDeviceConfig
from app.douyin_task_executor import DouyinAppiumExecutorConfig, DouyinAppiumTaskExecutor
from app.logger import configure_logging


TASK_39 = ClaimTaskResult(
    has_task=True,
    task_id=39,
    task_item_id=41,
    doctor_id=17,
    doctor_name="姜争",
    keyword_id=16,
    keyword="结直肠癌",
    search_word="结直肠癌",
    comment_bank_item_id=14,
    comment_content="当地说没手术机会，找姜主任做了 NOSES 手术，现在康复得很好。",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Call DouyinAppiumTaskExecutor directly with task 39 data, "
            "without claiming, starting, or reporting a backend task."
        )
    )
    parser.add_argument("--udid", default="10AG3R2JNF001KK")
    parser.add_argument("--device-name", default="device_02")
    parser.add_argument("--system-port", type=int, default=8202)
    parser.add_argument("--appium-server-url", default=settings.appium_server_url)
    parser.add_argument("--api-base-url", default=settings.api_base_url)
    parser.add_argument(
        "--execute-video-actions",
        action="store_true",
        help="Run video actions after opening the video. Default stops before like/favorite.",
    )
    parser.add_argument(
        "--send-comment",
        action="store_true",
        help="Actually tap the comment send button. Default inputs only.",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(debug=args.debug)

    device = BackendDeviceConfig(
        id=0,
        name=args.device_name,
        udid=args.udid,
        system_port=args.system_port,
        enabled_status="enabled",
    )
    start_result = StartTaskResult(result_id=390001, status="running")
    api_client = AutomationApiClient(args.api_base_url)
    executor = DouyinAppiumTaskExecutor(
        DouyinAppiumExecutorConfig(
            appium_server_url=args.appium_server_url,
            watch_min_seconds=30,
            watch_max_seconds=60,
            execute_video_actions_enabled=args.execute_video_actions,
            send_comment_enabled=args.send_comment,
        )
    )

    result = executor.execute(
        task=TASK_39,
        start_result=start_result,
        device=device,
        api_client=api_client,
    )
    print(f"debug executor task39 finished: {result}")


if __name__ == "__main__":
    main()
