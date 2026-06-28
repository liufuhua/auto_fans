from __future__ import annotations

import argparse

from app.config import settings
from app.device_manager import BackendDeviceConfig
from app.douyin_actions import DouyinActions, LocatorSpec
from app.douyin_search_support import log_step, quit_with_timeout
from app.douyin_task_executor import DouyinAppiumExecutorConfig, DouyinAppiumTaskExecutor
from app.logger import configure_logging


DEFAULT_APPIUM_SERVER_URL = "http://127.0.0.1:4722"
DEFAULT_COMMENT = "手术操作精细严谨，材料贴合自然，完好保护头部组织，没有留下后遗症。"
DEFAULT_ACTIVE_INPUT_X_RATIO = 0.32
DEFAULT_ACTIVE_INPUT_Y_RATIO = 0.965
DEFAULT_SEND_X_RATIO = 0.895
DEFAULT_SEND_Y_RATIO = 0.961


class HuaweiNovaSE6CommentOnlyExecutor(DouyinAppiumTaskExecutor):
    def __init__(
        self,
        config: DouyinAppiumExecutorConfig,
        *,
        active_input_x_ratio: float,
        active_input_y_ratio: float,
        send_x_ratio: float,
        send_y_ratio: float,
    ) -> None:
        super().__init__(config)
        self.active_input_x_ratio = active_input_x_ratio
        self.active_input_y_ratio = active_input_y_ratio
        self.send_x_ratio = send_x_ratio
        self.send_y_ratio = send_y_ratio
        self._latest_actions: DouyinActions | None = None

    def _build_actions(self, *, driver, args: argparse.Namespace, task_id: str) -> DouyinActions:
        actions = super()._build_actions(driver=driver, args=args, task_id=task_id)
        locators = actions.locators.locators
        existing = actions.locators.get("send_comment_button")
        locators["send_comment_button"] = [
            LocatorSpec(
                "send_comment_button",
                "resource-id",
                "com.ss.android.ugc.aweme:id/et6",
            ),
            LocatorSpec(
                "send_comment_button",
                "resource-id",
                "com.ss.android.ugc.aweme:id/et-",
            ),
            LocatorSpec("send_comment_button", "text", "发送"),
            *existing,
        ]
        self._latest_actions = actions
        return actions

    def _tap_active_comment_input_by_adb(self, args: argparse.Namespace, label: str) -> None:
        if label == "comment input focus before send":
            log_step("huawei nova se6 debug 发送前强制使用 ADB 点击底部评论输入框")
            self._tap_active_comment_input_with_ratio(args, label)
            return

        if self._latest_actions is not None:
            try:
                log_step(f"huawei nova se6 debug 优先使用 Appium 定位已展开评论输入框：{label}")
                self._latest_actions._click("comment_input")
                log_step(f"huawei nova se6 debug Appium 已展开评论输入框点击成功：{label}")
                return
            except Exception as exc:  # noqa: BLE001 - this debug script verifies ADB fallback.
                log_step(
                    "huawei nova se6 debug Appium 已展开评论输入框点击失败，改用 ADB 坐标兜底："
                    f"{type(exc).__name__}: {exc}"
                )

        self._tap_active_comment_input_with_ratio(args, label)

    def _tap_active_comment_input_with_ratio(self, args: argparse.Namespace, label: str) -> None:
        width, height = self._adb_window_size(args)
        x = int(width * self.active_input_x_ratio)
        y = int(height * self.active_input_y_ratio)
        log_step(
            "huawei nova se6 debug ADB 点击已展开评论输入框："
            f"{label} x={x} y={y} "
            f"ratio=({self.active_input_x_ratio:.3f},{self.active_input_y_ratio:.3f})"
        )
        self._adb_shell(args=args, shell_args=["input", "tap", str(x), str(y)])

    def _tap_comment_send_by_adb(self, args: argparse.Namespace) -> None:
        if self._latest_actions is not None:
            try:
                log_step("huawei nova se6 debug 优先使用 Appium 定位发送按钮")
                self._latest_actions._click("send_comment_button")
                log_step("huawei nova se6 debug Appium 发送按钮点击成功")
                return
            except Exception as exc:  # noqa: BLE001 - this debug script verifies ADB fallback.
                log_step(
                    "huawei nova se6 debug Appium 发送按钮点击失败，改用 ADB 坐标兜底："
                    f"{type(exc).__name__}: {exc}"
                )

        width, height = self._adb_window_size(args)
        x = int(width * self.send_x_ratio)
        y = int(height * self.send_y_ratio)
        log_step(
            "huawei nova se6 debug ADB 点击评论发送兜底："
            f"x={x} y={y} ratio=({self.send_x_ratio:.3f},{self.send_y_ratio:.3f})"
        )
        self._adb_shell(args=args, shell_args=["input", "tap", str(x), str(y)])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run only the Douyin comment stage on huawei nova SE6/MYQUT20414008419. "
            "The phone must already be on a Douyin video playback page."
        )
    )
    parser.add_argument("--udid", default="MYQUT20414008419")
    parser.add_argument("--device-name", default="MYQUT20414008419")
    parser.add_argument("--system-port", type=int, default=8202)
    parser.add_argument("--appium-server-url", default=DEFAULT_APPIUM_SERVER_URL)
    parser.add_argument("--comment", default=DEFAULT_COMMENT)
    parser.add_argument("--active-input-x-ratio", type=float, default=DEFAULT_ACTIVE_INPUT_X_RATIO)
    parser.add_argument("--active-input-y-ratio", type=float, default=DEFAULT_ACTIVE_INPUT_Y_RATIO)
    parser.add_argument("--send-x-ratio", type=float, default=DEFAULT_SEND_X_RATIO)
    parser.add_argument("--send-y-ratio", type=float, default=DEFAULT_SEND_Y_RATIO)
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

    executor = HuaweiNovaSE6CommentOnlyExecutor(
        DouyinAppiumExecutorConfig(
            appium_server_url=cli_args.appium_server_url,
            execute_video_actions_enabled=True,
            send_comment_enabled=cli_args.send_comment,
        ),
        active_input_x_ratio=cli_args.active_input_x_ratio,
        active_input_y_ratio=cli_args.active_input_y_ratio,
        send_x_ratio=cli_args.send_x_ratio,
        send_y_ratio=cli_args.send_y_ratio,
    )
    args = executor._build_args(
        device=BackendDeviceConfig(
            id=0,
            name=cli_args.device_name,
            udid=cli_args.udid,
            system_port=cli_args.system_port,
            enabled_status="enabled",
            device_model="huawei_nova_se6",
            appium_server_url=cli_args.appium_server_url,
        ),
        config=executor.config,
    )
    args.package_name = settings.douyin_package_name
    args.app_activity = settings.douyin_app_activity
    args.app = settings.douyin_app_path

    log_step(
        "华为 nova SE6 评论单阶段测试启动："
        f"udid={args.udid}, systemPort={args.system_port}, appium={args.appium_server_url}, "
        f"sendComment={cli_args.send_comment}, "
        f"activeInputRatio=({cli_args.active_input_x_ratio:.3f},{cli_args.active_input_y_ratio:.3f}), "
        f"sendRatio=({cli_args.send_x_ratio:.3f},{cli_args.send_y_ratio:.3f})"
    )
    log_step("请确认真机当前已经停留在抖音视频播放页")

    managed_driver = executor._create_driver_from_args(args)
    driver = managed_driver.driver
    try:
        actions = executor._build_actions(
            driver=driver,
            args=args,
            task_id="debug_comment_only_huawei_nova_se6",
        )
        waits: dict[str, float] = {}
        driver = executor._comment_video_and_reconnect(
            actions=actions,
            args=args,
            comment=cli_args.comment,
            waits=waits,
            send_comment=cli_args.send_comment,
        )
        log_step(f"华为 nova SE6 评论单阶段测试完成：waits={waits}")
    finally:
        quit_with_timeout(driver, args.quit_timeout_seconds)
        executor._clear_appium_session(args)


if __name__ == "__main__":
    main()
