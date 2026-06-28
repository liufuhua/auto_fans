from __future__ import annotations

import argparse

from app.config import settings
from app.device_manager import BackendDeviceConfig
from app.douyin_search_support import log_step, quit_with_timeout
from app.douyin_task_executor import DouyinAppiumExecutorConfig, DouyinAppiumTaskExecutor
from app.logger import configure_logging


DEFAULT_APPIUM_SERVER_URL = "http://127.0.0.1:4721"
DEFAULT_COMMENT = "明山主任真的太牛了，颅底肿瘤这种高难度手术，在您手里稳稳的，专业又靠谱！"


class VivoCommentOnlyExecutor(DouyinAppiumTaskExecutor):
    """Comment-only debug runner that uses the same comment logic as production."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run only the Douyin comment stage on vivo/R8594XIBXWXWKRVO. "
            "The phone must already be on a Douyin video playback page."
        )
    )
    parser.add_argument("--udid", default="R8594XIBXWXWKRVO")
    parser.add_argument("--device-name", default="R8594XIBXWXWKRVO")
    parser.add_argument("--system-port", type=int, default=8201)
    parser.add_argument("--appium-server-url", default=DEFAULT_APPIUM_SERVER_URL)
    parser.add_argument("--comment", default=DEFAULT_COMMENT)
    parser.add_argument(
        "--send-comment",
        action="store_true",
        help="Actually tap the comment send button. Default inputs only.",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> None:
    cli_args = parse_args()
    configure_logging(debug=cli_args.debug)

    executor = VivoCommentOnlyExecutor(
        config=DouyinAppiumExecutorConfig(
            appium_server_url=cli_args.appium_server_url,
            execute_video_actions_enabled=True,
            send_comment_enabled=cli_args.send_comment,
        )
    )
    args = executor._build_args(
        device=BackendDeviceConfig(
            id=0,
            name=cli_args.device_name,
            udid=cli_args.udid,
            system_port=cli_args.system_port,
            enabled_status="enabled",
            device_model="vivo_y52",
            appium_server_url=cli_args.appium_server_url,
        ),
        config=executor.config,
    )
    args.package_name = settings.douyin_package_name
    args.app_activity = settings.douyin_app_activity
    args.app = settings.douyin_app_path

    log_step(
        "评论单阶段测试启动："
        f"udid={args.udid}, systemPort={args.system_port}, appium={args.appium_server_url}, "
        f"sendComment={cli_args.send_comment}, deviceModel={args.device_model}"
    )
    log_step("请确认真机当前已经停留在抖音视频播放页")

    managed_driver = executor._create_driver_from_args(args)
    driver = managed_driver.driver
    try:
        actions = executor._build_actions(
            driver=driver,
            args=args,
            task_id="debug_comment_only_vivo",
        )
        waits: dict[str, float] = {}
        driver = executor._comment_video_and_reconnect(
            actions=actions,
            args=args,
            comment=cli_args.comment,
            waits=waits,
            send_comment=cli_args.send_comment,
        )
        log_step(f"评论单阶段测试完成：waits={waits}")
    finally:
        quit_with_timeout(driver, args.quit_timeout_seconds)
        executor._clear_appium_session(args)


if __name__ == "__main__":
    main()
