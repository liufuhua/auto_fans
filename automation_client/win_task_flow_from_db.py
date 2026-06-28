from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
AUTOMATION_CLIENT_DIR = ROOT_DIR / "automation_client"

sys.path.insert(0, str(AUTOMATION_CLIENT_DIR))

from app.api_client import AutomationApiClient, ClaimTaskResult, StartTaskResult  # noqa: E402
from app.config import settings  # noqa: E402
from app.device_manager import BackendDeviceConfig  # noqa: E402
from app.douyin_task_executor import DouyinAppiumExecutorConfig, DouyinAppiumTaskExecutor  # noqa: E402
from app.logger import configure_logging  # noqa: E402


def ensure_adb_on_path() -> None:
    local_app_data = Path.home() / "AppData/Local"
    platform_tools = local_app_data / "Android/Sdk/platform-tools"
    if platform_tools.exists():
        current_path = str(platform_tools)
        path_parts = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
        if current_path.lower() not in {item.lower() for item in path_parts}:
            os.environ["PATH"] = current_path + os.pathsep + os.environ.get("PATH", "")


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the real Douyin Appium main flow with doctor/keyword/comment "
            "loaded from a daily task in the local database."
        )
    )
    parser.add_argument("--task-id", type=int, default=52)
    parser.add_argument("--device-name", default="device_06")
    parser.add_argument("--udid", default="")
    parser.add_argument("--system-port", type=int, default=0)
    parser.add_argument("--appium-server-url", default=settings.appium_server_url)
    parser.add_argument("--api-base-url", default=settings.api_base_url)
    parser.add_argument("--admin-account", default="admin")
    parser.add_argument("--admin-password", default="admin123456")
    parser.add_argument("--watch-min-seconds", type=float, default=15)
    parser.add_argument("--watch-max-seconds", type=float, default=60)
    parser.add_argument("--max-swipes", type=int, default=2)
    parser.add_argument("--swipe-percent", type=float, default=0.45)
    parser.add_argument(
        "--comment",
        default="",
        help="Override the task comment for this test run without changing database data.",
    )
    parser.add_argument(
        "--no-send-comment",
        action="store_true",
        help="Input the comment but do not tap the send button.",
    )
    parser.add_argument(
        "--no-force-stop-before",
        action="store_true",
        help="Do not force-stop Douyin before creating the Appium session.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only load and print task/device data; do not create an Appium session.",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def _api_data(payload: dict[str, object]) -> object:
    if payload.get("code") != "OK":
        raise RuntimeError(str(payload.get("message") or "backend api failed"))
    return payload.get("data")


def _login(client: httpx.Client, account: str, password: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"account": account, "password": password},
    )
    response.raise_for_status()
    data = _api_data(response.json())
    if not isinstance(data, dict) or "token" not in data:
        raise RuntimeError("login response missing token")
    return {"Authorization": f"Bearer {data['token']}"}


def _get(client: httpx.Client, path: str, headers: dict[str, str]) -> object:
    response = client.get(path, headers=headers)
    response.raise_for_status()
    return _api_data(response.json())


def load_task_flow_data(
    *, api_base_url: str, task_id: int, account: str, password: str
) -> TaskFlowData:
    with httpx.Client(base_url=api_base_url.rstrip("/"), timeout=20) as client:
        headers = _login(client, account, password)
        tasks_data = _get(
            client,
            f"/daily-tasks?page=1&pageSize=100&taskId={task_id}",
            headers,
        )
        if not isinstance(tasks_data, dict):
            raise RuntimeError("daily task api returned invalid data")
        task = next(
            (item for item in tasks_data.get("items", []) if item.get("id") == task_id),
            None,
        )
        if not isinstance(task, dict):
            raise RuntimeError(f"daily task not found: {task_id}")
        items = task.get("items")
        if not isinstance(items, list) or not items:
            raise RuntimeError(f"daily task has no items: {task_id}")
        task_item = items[0]
        if not isinstance(task_item, dict):
            raise RuntimeError("daily task item is invalid")

        results_data = _get(
            client,
            f"/automation-results?page=1&pageSize=20&taskId={task_id}",
            headers,
        )
        if not isinstance(results_data, dict):
            raise RuntimeError("automation result api returned invalid data")
        results = results_data.get("items")
        result = results[0] if isinstance(results, list) and results else None
        if not isinstance(result, dict):
            raise RuntimeError(
                f"task {task_id} has no automation result; cannot infer the exact comment"
            )
        comment = str(result.get("commentContent") or "").strip()
        if not comment:
            raise RuntimeError(f"task {task_id} result has empty comment")

        return TaskFlowData(
            task_id=task_id,
            task_item_id=int(task_item["id"]),
            doctor_id=int(task_item["doctorId"]),
            doctor_name=str(task_item["doctorName"]),
            keyword_id=int(task_item["keywordId"]),
            keyword=str(task_item["keyword"]),
            comment_bank_item_id=900052,
            comment_content=comment,
        )


def load_device(args: argparse.Namespace) -> BackendDeviceConfig:
    with httpx.Client(base_url=args.api_base_url.rstrip("/"), timeout=20) as client:
        headers = _login(client, args.admin_account, args.admin_password)
        data = _get(client, "/devices?page=1&pageSize=100", headers)
        if not isinstance(data, dict):
            raise RuntimeError("devices api returned invalid data")
        devices = data.get("items")
        if not isinstance(devices, list):
            raise RuntimeError("devices api returned invalid items")
        for device in devices:
            if not isinstance(device, dict):
                continue
            name_matches = args.device_name and str(device.get("name")) == args.device_name
            udid_matches = args.udid and str(device.get("udid")).strip() == args.udid.strip()
            if name_matches or udid_matches:
                return BackendDeviceConfig(
                    id=int(device["id"]),
                    name=str(device["name"]),
                    udid=args.udid.strip() or str(device["udid"]).strip(),
                    system_port=args.system_port or int(device["systemPort"]),
                    enabled_status=str(device["enabledStatus"]),
                )
    raise RuntimeError(f"device not found: name={args.device_name}, udid={args.udid}")


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
        subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )


def main() -> int:
    args = parse_args()
    ensure_adb_on_path()
    configure_logging(debug=args.debug)

    data = load_task_flow_data(
        api_base_url=args.api_base_url,
        task_id=args.task_id,
        account=args.admin_account,
        password=args.admin_password,
    )
    if args.comment.strip():
        data = TaskFlowData(
            task_id=data.task_id,
            task_item_id=data.task_item_id,
            doctor_id=data.doctor_id,
            doctor_name=data.doctor_name,
            keyword_id=data.keyword_id,
            keyword=data.keyword,
            comment_bank_item_id=data.comment_bank_item_id,
            comment_content=args.comment.strip(),
        )
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
        task=build_task(data),
        start_result=StartTaskResult(result_id=900052, status="running"),
        device=device,
        api_client=AutomationApiClient(args.api_base_url),
    )
    print(f"task flow finished: {result}")
    return 0 if result.status in {"success", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
