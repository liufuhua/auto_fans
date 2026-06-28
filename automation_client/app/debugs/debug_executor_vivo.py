from __future__ import annotations

import argparse

from app.api_client import AutomationApiClient, ClaimTaskResult, StartTaskResult
from app.config import settings
from app.device_manager import BackendDeviceConfig
from app.douyin_task_executor import DouyinAppiumExecutorConfig, DouyinAppiumTaskExecutor
from app.logger import configure_logging


DEFAULT_APPIUM_SERVER_URL = "http://127.0.0.1:4721"


VIVO_SAMPLE_TASK = ClaimTaskResult(
    has_task=True,
    task_id=8594001,
    task_item_id=8594001,
    doctor_id=1,
    doctor_name="张明山",
    keyword_id=1,
    keyword="脑膜瘤",
    search_word="脑膜瘤",
    comment_bank_item_id=8594001,
    comment_content="明山主任真的太牛了，颅底肿瘤这种高难度手术，在您手里稳稳的，专业又靠谱！",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Call DouyinAppiumTaskExecutor directly for adapting vivo/R8594XIBXWXWKRVO. "
            "The doctor, keyword, and comment are static sample values from the database."
        )
    )
    parser.add_argument("--udid", default="R8594XIBXWXWKRVO")
    parser.add_argument("--device-name", default="R8594XIBXWXWKRVO")
    parser.add_argument("--system-port", type=int, default=8201)
    parser.add_argument("--appium-server-url", default=DEFAULT_APPIUM_SERVER_URL)
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
        device_model="vivo_y52",
        appium_server_url=args.appium_server_url,
    )
    start_result = StartTaskResult(result_id=8594001, status="running")
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
        task=VIVO_SAMPLE_TASK,
        start_result=start_result,
        device=device,
        api_client=api_client,
    )
    print(f"debug executor vivo finished: {result}")


if __name__ == "__main__":
    main()
