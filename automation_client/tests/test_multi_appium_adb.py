from __future__ import annotations

import argparse
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT_DIR = Path(__file__).resolve().parents[2]
AUTOMATION_CLIENT_DIR = ROOT_DIR / "automation_client"
if str(AUTOMATION_CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_CLIENT_DIR))

from app.adb import AdbClient  # noqa: E402
from app.api_client import ClaimTaskResult, StartTaskResult  # noqa: E402
from app.appium_driver import AppiumDriverFactory  # noqa: E402
from app.config import settings  # noqa: E402
from app.douyin_search_support import log_step  # noqa: E402
from app.douyin_task_executor import (  # noqa: E402
    DouyinAppiumExecutorConfig,
    DouyinAppiumTaskExecutor,
)
from app.logger import configure_logging, log_context  # noqa: E402

_TEE_FILES = []


class TeeTextIO:
    def __init__(self, *streams) -> None:
        self.streams = streams
        self._lock = threading.Lock()
        self.encoding = getattr(streams[0], "encoding", "utf-8")

    def write(self, text: str) -> int:
        with self._lock:
            for stream in self.streams:
                stream.write(text)
                stream.flush()
        return len(text)

    def flush(self) -> None:
        with self._lock:
            for stream in self.streams:
                stream.flush()

    def isatty(self) -> bool:
        return bool(getattr(self.streams[0], "isatty", lambda: False)())


@dataclass(frozen=True)
class LocalDeviceConfig:
    id: int
    name: str
    udid: str
    system_port: int
    enabled_status: str
    appium_server_url: str


@dataclass(frozen=True)
class LocalTaskSpec:
    label: str
    device: LocalDeviceConfig
    doctor_name: str
    keyword: str
    comment: str
    task_item_id: int
    result_id: int


class LocalTimingApiClient:
    def list_timing_settings(self):
        return []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run two Douyin Appium main-flow tasks in parallel for multi-device testing."
    )
    parser.add_argument("--udid-1", default="", help="Device UDID for Appium port 4726.")
    parser.add_argument("--udid-2", default="", help="Device UDID for Appium port 4727.")
    parser.add_argument("--device-name-1", default="multi_device_01")
    parser.add_argument("--device-name-2", default="multi_device_02")
    parser.add_argument("--appium-url-1", default="http://127.0.0.1:4726")
    parser.add_argument("--appium-url-2", default="http://127.0.0.1:4727")
    parser.add_argument("--system-port-1", type=int, default=8022)
    parser.add_argument("--system-port-2", type=int, default=8023)
    parser.add_argument("--doctor-name", default="姜争")
    parser.add_argument("--keyword", default="结直肠癌")
    parser.add_argument("--comment-1", default="医术高超")
    parser.add_argument("--comment-2", default="宅心仁厚")
    parser.add_argument("--wait-timeout-seconds", type=int, default=12)
    parser.add_argument("--quit-timeout-seconds", type=int, default=5)
    parser.add_argument("--after-open-seconds", type=float, default=2)
    parser.add_argument("--watch-min-seconds", type=float, default=15)
    parser.add_argument("--watch-max-seconds", type=float, default=30)
    parser.add_argument("--before-input-min-seconds", type=float, default=3)
    parser.add_argument("--before-input-max-seconds", type=float, default=8)
    parser.add_argument("--after-input-min-seconds", type=float, default=2)
    parser.add_argument("--after-input-max-seconds", type=float, default=4)
    parser.add_argument("--after-search-min-seconds", type=float, default=2)
    parser.add_argument("--after-search-max-seconds", type=float, default=3)
    parser.add_argument("--after-swipe-min-seconds", type=float, default=1)
    parser.add_argument("--after-swipe-max-seconds", type=float, default=2)
    parser.add_argument("--after-like-min-seconds", type=float, default=3)
    parser.add_argument("--after-like-max-seconds", type=float, default=8)
    parser.add_argument("--after-favorite-min-seconds", type=float, default=3)
    parser.add_argument("--after-favorite-max-seconds", type=float, default=8)
    parser.add_argument("--comment-pre-input-min-seconds", type=float, default=2)
    parser.add_argument("--comment-pre-input-max-seconds", type=float, default=5)
    parser.add_argument("--comment-focus-min-seconds", type=float, default=2)
    parser.add_argument("--comment-focus-max-seconds", type=float, default=5)
    parser.add_argument("--after-comment-input-min-seconds", type=float, default=5)
    parser.add_argument("--after-comment-input-max-seconds", type=float, default=5)
    parser.add_argument("--before-send-min-seconds", type=float, default=0)
    parser.add_argument("--before-send-max-seconds", type=float, default=0)
    parser.add_argument("--max-swipes", type=int, default=2)
    parser.add_argument("--swipe-percent", type=float, default=0.45)
    parser.add_argument(
        "--input-only",
        action="store_true",
        help="Run the main flow but only input comment text; do not tap send.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--log-file",
        default="",
        help="Write console output and executor logging to this file while still printing to console.",
    )
    return parser.parse_args()


def configure_tee_log_file(path_value: str) -> None:
    if not path_value:
        return
    log_path = Path(path_value)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8", buffering=1)
    _TEE_FILES.append(log_file)
    sys.stdout = TeeTextIO(sys.stdout, log_file)
    sys.stderr = TeeTextIO(sys.stderr, log_file)


def discover_udids(explicit_udids: Sequence[str]) -> tuple[str, str]:
    explicit = [udid.strip() for udid in explicit_udids if udid.strip()]
    if len(explicit) == 2:
        return explicit[0], explicit[1]
    if len(explicit) == 1:
        raise RuntimeError("只传了一个 UDID，请同时传 --udid-1 和 --udid-2，或两个都不传自动发现。")

    devices = AdbClient().online_devices()
    udids = [device.udid for device in devices if device.online]
    if len(udids) < 2:
        raise RuntimeError(
            f"ADB 在线设备不足 2 台，当前发现：{udids}。请连接两台设备或手动传 --udid-1/--udid-2。"
        )
    return udids[0], udids[1]


def build_executor_config(args: argparse.Namespace, appium_server_url: str) -> DouyinAppiumExecutorConfig:
    return DouyinAppiumExecutorConfig(
        appium_server_url=appium_server_url,
        package_name=settings.douyin_package_name,
        app_activity=settings.douyin_app_activity,
        app=settings.douyin_app_path,
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
        comment_pre_input_min_seconds=args.comment_pre_input_min_seconds,
        comment_pre_input_max_seconds=args.comment_pre_input_max_seconds,
        comment_focus_min_seconds=args.comment_focus_min_seconds,
        comment_focus_max_seconds=args.comment_focus_max_seconds,
        after_comment_input_min_seconds=args.after_comment_input_min_seconds,
        after_comment_input_max_seconds=args.after_comment_input_max_seconds,
        before_send_min_seconds=args.before_send_min_seconds,
        before_send_max_seconds=args.before_send_max_seconds,
        max_swipes=args.max_swipes,
        swipe_percent=args.swipe_percent,
        execute_video_actions_enabled=True,
        send_comment_enabled=not args.input_only,
    )


def build_specs(args: argparse.Namespace) -> list[LocalTaskSpec]:
    udid_1, udid_2 = discover_udids([args.udid_1, args.udid_2])
    return [
        LocalTaskSpec(
            label="task1",
            device=LocalDeviceConfig(
                id=1,
                name=args.device_name_1,
                udid=udid_1,
                system_port=args.system_port_1,
                enabled_status="enabled",
                appium_server_url=args.appium_url_1,
            ),
            doctor_name=args.doctor_name,
            keyword=args.keyword,
            comment=args.comment_1,
            task_item_id=900001,
            result_id=910001,
        ),
        LocalTaskSpec(
            label="task2",
            device=LocalDeviceConfig(
                id=2,
                name=args.device_name_2,
                udid=udid_2,
                system_port=args.system_port_2,
                enabled_status="enabled",
                appium_server_url=args.appium_url_2,
            ),
            doctor_name=args.doctor_name,
            keyword=args.keyword,
            comment=args.comment_2,
            task_item_id=900002,
            result_id=910002,
        ),
    ]


def run_one(args: argparse.Namespace, spec: LocalTaskSpec) -> str:
    with log_context(device_name=spec.device.name, udid=spec.device.udid):
        log_step(
            f"{spec.label} start: appium={spec.device.appium_server_url}, "
            f"systemPort={spec.device.system_port}, doctor={spec.doctor_name}, "
            f"keyword={spec.keyword}, comment={spec.comment}"
        )
        executor_config = build_executor_config(args, spec.device.appium_server_url)
        executor = DouyinAppiumTaskExecutor(
            config=executor_config,
            driver_factory=AppiumDriverFactory(spec.device.appium_server_url, retries=1),
        )
        task = ClaimTaskResult(
            has_task=True,
            task_id=spec.task_item_id,
            task_item_id=spec.task_item_id,
            doctor_id=1,
            doctor_name=spec.doctor_name,
            keyword_id=1,
            keyword=spec.keyword,
            search_word=spec.keyword,
            comment_bank_item_id=spec.task_item_id,
            comment_content=spec.comment,
        )
        start_result = StartTaskResult(result_id=spec.result_id, status="running")
        result = executor.execute(
            task=task,
            start_result=start_result,
            device=spec.device,
            api_client=LocalTimingApiClient(),
        )
        if result.status == "success":
            log_step(f"{spec.label} success: {result.result_summary or ''}")
            return f"{spec.label}: success"
        if not result.report_to_backend:
            log_step(f"{spec.label} skipped report: status={result.status}")
            return f"{spec.label}: skipped"
        log_step(f"{spec.label} failed: {result.fail_reason or ''}")
        return f"{spec.label}: failed: {result.fail_reason or ''}"


def main() -> int:
    args = parse_args()
    configure_tee_log_file(args.log_file)
    configure_logging(debug=args.debug)
    specs = build_specs(args)
    log_step("并行测试开始")
    for spec in specs:
        log_step(
            f"{spec.label}: udid={spec.device.udid}, appium={spec.device.appium_server_url}, "
            f"systemPort={spec.device.system_port}"
        )

    results: list[str] = []
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="multi-appium") as executor:
        futures = [executor.submit(run_one, args, spec) for spec in specs]
        for future in as_completed(futures):
            results.append(future.result())

    log_step("并行测试结束：" + " | ".join(sorted(results)))
    return 0 if all(": success" in item or ": skipped" in item for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
