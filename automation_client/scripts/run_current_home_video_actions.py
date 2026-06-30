from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

CLIENT_ROOT = Path(__file__).resolve().parents[1]
if str(CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(CLIENT_ROOT))

from app.adb import AdbClient
from app.appium_driver import AppiumDeviceConfig
from app.appium_server_manager import AppiumServerManager
from app.config import settings
from app.device_manager import BackendDeviceConfig
from app.douyin_search_support import log_step, quit_with_timeout
from app.douyin_task_executor import DouyinAppiumExecutorConfig, DouyinAppiumTaskExecutor
from app.logger import configure_device_file_logger, configure_logging, log_context


DEFAULT_COMMENT = "AutoFans调试评论，请忽略。"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(debug=args.debug)

    udid = args.udid.strip() or detect_single_device(args.adb_path)
    if not udid:
        return 2

    appium_url = args.appium_server_url.strip()
    device = BackendDeviceConfig(
        id=0,
        name=args.device_name.strip() or udid,
        udid=udid,
        system_port=args.system_port,
        enabled_status="enabled",
        device_model=args.device_model.strip() or "huawei_nova_se6",
        appium_server_url=appium_url,
    )
    log_path = configure_device_file_logger(
        device_name=device.name,
        runtime_dir=CLIENT_ROOT / "runtime",
        debug=args.debug,
    )

    manager: AppiumServerManager | None = None
    if args.manage_appium:
        manager = AppiumServerManager(
            default_server_url=appium_url,
            log_dir=CLIENT_ROOT.parent / "logs",
            ports_file=CLIENT_ROOT.parent / "logs" / "debug_appium_ports.txt",
            on_demand_file=CLIENT_ROOT.parent / "logs" / "debug_appium_on_demand.txt",
            appium_bin=args.appium_bin.strip() or None,
        )
        manager.start_for_devices([device])

    config = DouyinAppiumExecutorConfig(
        appium_server_url=appium_url,
        package_name=args.package_name,
        app_activity=args.app_activity,
        app=args.app,
        wait_timeout_seconds=args.wait_timeout_seconds,
        quit_timeout_seconds=args.quit_timeout_seconds,
        watch_min_seconds=args.watch_seconds,
        watch_max_seconds=args.watch_seconds,
        after_like_min_seconds=args.after_like_seconds,
        after_like_max_seconds=args.after_like_seconds,
        after_favorite_min_seconds=args.after_favorite_seconds,
        after_favorite_max_seconds=args.after_favorite_seconds,
        comment_pre_input_min_seconds=args.comment_pre_input_seconds,
        comment_pre_input_max_seconds=args.comment_pre_input_seconds,
        comment_focus_min_seconds=args.comment_focus_seconds,
        comment_focus_max_seconds=args.comment_focus_seconds,
        after_comment_input_min_seconds=args.after_comment_input_seconds,
        after_comment_input_max_seconds=args.after_comment_input_seconds,
        before_send_min_seconds=args.before_send_seconds,
        before_send_max_seconds=args.before_send_seconds,
        send_comment_enabled=not args.no_send_comment,
    )
    executor = DouyinAppiumTaskExecutor(config=config)
    executor_args = executor._build_args(device, config=config)
    executor_args.adb_path = args.adb_path

    driver = None
    summary: dict[str, object] = {
        "udid": udid,
        "deviceName": device.name,
        "deviceModel": device.device_model,
        "appiumServerUrl": appium_url,
        "logPath": str(log_path),
        "comment": args.comment,
        "sendComment": not args.no_send_comment,
    }

    with log_context(
        device_name=device.name,
        udid=udid,
        result_id="debug",
        log_file_path=log_path,
    ):
        try:
            log_step("开始调试当前首页视频：默认当前视频已满足命中条件")
            appium_device = AppiumDeviceConfig(
                udid=udid,
                system_port=args.system_port,
                device_name=device.name,
                appium_server_url=appium_url,
                app=args.app,
                app_package=args.package_name,
                app_activity=args.app_activity,
            )
            managed_driver = executor.driver_factory.create(appium_device)
            driver = managed_driver.driver
            executor._configure_driver(driver)

            waits: dict[str, float] = {}
            actions = executor._build_actions(
                driver=driver,
                args=executor_args,
                task_id="debug_current_home_video_like",
            )
            like_success, driver = executor._like_video_and_reconnect(
                actions=actions,
                args=executor_args,
                waits=waits,
            )

            actions = executor._build_actions(
                driver=driver,
                args=executor_args,
                task_id="debug_current_home_video_favorite",
            )
            favorite_success, driver = executor._favorite_video_and_reconnect(
                actions=actions,
                args=executor_args,
                waits=waits,
            )

            actions = executor._build_actions(
                driver=driver,
                args=executor_args,
                task_id="debug_current_home_video_share",
            )
            share_success, video_link, driver = executor._share_video_and_reconnect(
                actions=actions,
                args=executor_args,
            )

            actions = executor._build_actions(
                driver=driver,
                args=executor_args,
                task_id="debug_current_home_video_comment",
            )
            driver = executor._comment_video_and_reconnect(
                actions=actions,
                args=executor_args,
                comment=args.comment,
                waits=waits,
                send_comment=not args.no_send_comment,
                force_stop_after_comment=False,
            )

            summary.update(
                {
                    "likeSuccess": like_success,
                    "favoriteSuccess": favorite_success,
                    "shareSuccess": share_success,
                    "videoLink": video_link,
                    "waits": waits,
                    "status": "success",
                }
            )
            log_step("当前首页视频调试流程完成")
            print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
            return 0
        except Exception as exc:  # noqa: BLE001 - this is a manual diagnostic script.
            summary.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
            log_step(f"当前首页视频调试流程失败：{type(exc).__name__}: {exc}")
            print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
            return 1
        finally:
            if driver is not None:
                try:
                    quit_with_timeout(driver, args.quit_timeout_seconds)
                except Exception as exc:  # noqa: BLE001
                    log_step(f"释放 driver 失败，继续清理：{type(exc).__name__}: {exc}")
                try:
                    executor._clear_appium_session(executor_args)
                except Exception as exc:  # noqa: BLE001
                    log_step(f"清理 Appium session 失败，继续退出：{type(exc).__name__}: {exc}")
            if manager is not None:
                manager.stop_for_devices([device])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "调试当前抖音首页视频的点赞、收藏、分享链接、评论发送流程。"
            "脚本假设当前视频已经满足命中要求，不做医生匹配。"
        )
    )
    parser.add_argument("--udid", default="", help="ADB 设备 UDID；不填则要求只有一台在线设备")
    parser.add_argument("--device-name", default="", help="日志中的设备名称；默认使用 UDID")
    parser.add_argument("--device-model", default="huawei_nova_se6", help="设备坐标配置名称")
    parser.add_argument("--system-port", type=int, default=8228, help="UiAutomator2 systemPort")
    parser.add_argument("--adb-path", default=settings.adb_path or "adb")
    parser.add_argument("--appium-server-url", default="http://127.0.0.1:4748")
    parser.add_argument("--manage-appium", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--appium-bin", default="", help="Appium 命令路径；默认自动查找 appium/appium.cmd")
    parser.add_argument("--package-name", default=settings.douyin_package_name)
    parser.add_argument("--app-activity", default=settings.douyin_app_activity)
    parser.add_argument("--app", default=settings.douyin_app_path)
    parser.add_argument("--comment", default=DEFAULT_COMMENT)
    parser.add_argument("--no-send-comment", action="store_true", help="只输入评论，不点击发送")
    parser.add_argument("--watch-seconds", type=float, default=3)
    parser.add_argument("--after-like-seconds", type=float, default=1)
    parser.add_argument("--after-favorite-seconds", type=float, default=1)
    parser.add_argument("--comment-pre-input-seconds", type=float, default=2)
    parser.add_argument("--comment-focus-seconds", type=float, default=1)
    parser.add_argument("--after-comment-input-seconds", type=float, default=1)
    parser.add_argument("--before-send-seconds", type=float, default=1)
    parser.add_argument("--wait-timeout-seconds", type=int, default=12)
    parser.add_argument("--quit-timeout-seconds", type=int, default=5)
    parser.add_argument("--debug", action="store_true")
    return parser


def detect_single_device(adb_path: str) -> str:
    devices = AdbClient(adb_path).online_devices()
    if len(devices) != 1:
        print("未指定 --udid，且当前在线设备数量不是 1：", file=sys.stderr)
        for device in devices:
            print(f"  {device.udid}", file=sys.stderr)
        return ""
    return devices[0].udid


if __name__ == "__main__":
    raise SystemExit(main())
