from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.api_client import AutomationApiClient, ClaimTaskResult, StartTaskResult
from app.config import settings
from app.device_manager import BackendDeviceConfig
from app.douyin_task_executor import DouyinAppiumExecutorConfig, DouyinAppiumTaskExecutor
from app.logger import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Windows local test entry for the real Douyin Appium main flow."
    )
    parser.add_argument("--udid", default="R5CW11CKN0B")
    parser.add_argument("--device-name", default="device_03")
    parser.add_argument("--system-port", type=int, default=8203)
    parser.add_argument("--doctor-name", default="曹迎明")
    parser.add_argument("--keyword", default="脑膜瘤")
    parser.add_argument("--comment", default="太棒了")
    parser.add_argument("--appium-server-url", default=settings.appium_server_url)
    parser.add_argument("--api-base-url", default=settings.api_base_url)
    parser.add_argument("--watch-min-seconds", type=float, default=15)
    parser.add_argument("--watch-max-seconds", type=float, default=60)
    parser.add_argument("--max-swipes", type=int, default=2)
    parser.add_argument("--swipe-percent", type=float, default=0.45)
    parser.add_argument(
        "--no-send-comment",
        action="store_true",
        help="Input the comment but do not tap the send button.",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def build_task(args: argparse.Namespace) -> ClaimTaskResult:
    return ClaimTaskResult(
        has_task=True,
        task_id=900001,
        task_item_id=900001,
        doctor_id=900001,
        doctor_name=args.doctor_name,
        keyword_id=900001,
        keyword=args.keyword,
        search_word=args.keyword,
        comment_bank_item_id=900001,
        comment_content=args.comment,
    )


def main() -> None:
    args = parse_args()
    configure_logging(debug=args.debug)

    device = BackendDeviceConfig(
        id=900001,
        name=args.device_name,
        udid=args.udid,
        system_port=args.system_port,
        enabled_status="enabled",
    )
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

    result = executor.execute(
        task=build_task(args),
        start_result=StartTaskResult(result_id=900001, status="running"),
        device=device,
        api_client=AutomationApiClient(args.api_base_url),
    )
    print(f"win_test finished: {result}")


if __name__ == "__main__":
    main()
