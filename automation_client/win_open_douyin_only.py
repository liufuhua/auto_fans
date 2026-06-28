from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
AUTOMATION_CLIENT_DIR = ROOT_DIR / "automation_client"

sys.path.insert(0, str(AUTOMATION_CLIENT_DIR))

from app.appium_driver import AppiumDeviceConfig, AppiumDriverFactory  # noqa: E402
from app.appium_server_manager import AppiumServerManager  # noqa: E402
from app.config import settings  # noqa: E402
from app.device_manager import BackendDeviceConfig  # noqa: E402


DEFAULT_UDID = "MYQUT19C05007064"
DEFAULT_DEVICE_NAME = "北京2.0"
DEFAULT_SYSTEM_PORT = 8206
DEFAULT_APPIUM_SERVER_URL = "http://127.0.0.1:4726"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Click Douyin share, then click the share-link action on current page."
    )
    parser.add_argument("--udid", default=DEFAULT_UDID)
    parser.add_argument("--device-name", default=DEFAULT_DEVICE_NAME)
    parser.add_argument("--system-port", type=int, default=DEFAULT_SYSTEM_PORT)
    parser.add_argument("--appium-server-url", default=DEFAULT_APPIUM_SERVER_URL)
    parser.add_argument("--package-name", default=settings.douyin_package_name)
    parser.add_argument(
        "--force-stop-before",
        action="store_true",
        help="Force-stop Douyin before opening it.",
    )
    parser.add_argument(
        "--home-before",
        action="store_true",
        help="Press HOME before opening Douyin.",
    )
    parser.add_argument("--fallback-x", type=int, default=990)
    parser.add_argument("--fallback-y", type=int, default=1863)
    parser.add_argument("--share-link-fallback-x", type=int, default=613)
    parser.add_argument("--share-link-fallback-y", type=int, default=2103)
    parser.add_argument("--close-fallback-x", type=int, default=984)
    parser.add_argument("--close-fallback-y", type=int, default=1755)
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Do not tap fallback coordinates when the XML node is not found.",
    )
    parser.add_argument(
        "--no-manage-appium",
        action="store_true",
        help="Do not start/stop Appium in this script; use an already running server.",
    )
    return parser.parse_args()


def ensure_adb_on_path() -> None:
    platform_tools = Path.home() / "AppData/Local/Android/Sdk/platform-tools"
    if not platform_tools.exists():
        return
    path_parts = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    if str(platform_tools).lower() not in {item.lower() for item in path_parts}:
        os.environ["PATH"] = str(platform_tools) + os.pathsep + os.environ.get("PATH", "")


def run_adb(args: list[str]) -> subprocess.CompletedProcess[str]:
    command = ["adb", *args]
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def ensure_device_online(udid: str) -> None:
    result = run_adb(["devices"])
    if result.returncode != 0:
        raise RuntimeError(f"adb devices failed: {result.stderr.strip() or result.stdout.strip()}")
    marker = f"{udid}\tdevice"
    normalized = result.stdout.replace(" ", "\t")
    if marker not in normalized:
        raise RuntimeError(f"device is not online: {udid}\n{result.stdout.strip()}")


def parse_bounds_center(bounds: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not match:
        return None
    x1, y1, x2, y2 = (int(value) for value in match.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def dump_current_page_xml(udid: str) -> Path:
    remote_path = "/sdcard/current_douyin_share_probe.xml"
    local_path = AUTOMATION_CLIENT_DIR / "runtime" / "current_douyin_share_probe.xml"
    local_path.parent.mkdir(parents=True, exist_ok=True)

    dump_result = run_adb(["-s", udid, "shell", "uiautomator", "dump", remote_path])
    if dump_result.returncode != 0:
        raise RuntimeError(
            "uiautomator dump failed: "
            f"{dump_result.stderr.strip() or dump_result.stdout.strip()}"
        )
    pull_result = run_adb(["-s", udid, "pull", remote_path, str(local_path)])
    if pull_result.returncode != 0:
        raise RuntimeError(f"pull page xml failed: {pull_result.stderr.strip()}")
    return local_path


def find_share_button_center(xml_path: Path) -> tuple[int, int, str] | None:
    root = ET.parse(xml_path).getroot()
    fallback_node: tuple[int, int, str] | None = None
    for node in root.iter("node"):
        attrs = node.attrib
        desc = attrs.get("content-desc", "")
        resource_id = attrs.get("resource-id", "")
        bounds = attrs.get("bounds", "")
        center = parse_bounds_center(bounds)
        if center is None:
            continue
        if "分享" in desc and "按钮" in desc:
            return center[0], center[1], f"content-desc={desc}, bounds={bounds}"
        if resource_id in {
            "com.ss.android.ugc.aweme:id/zj0",
            "com.ss.android.ugc.aweme:id/share_container",
        }:
            fallback_node = (
                center[0],
                center[1],
                f"resource-id={resource_id}, bounds={bounds}",
            )
    return fallback_node


def find_share_link_center(xml_path: Path) -> tuple[int, int, str] | None:
    root = ET.parse(xml_path).getroot()
    parent_by_child = {child: parent for parent in root.iter("node") for child in parent}
    for node in root.iter("node"):
        attrs = node.attrib
        if attrs.get("text") != "分享链接":
            continue
        parent = parent_by_child.get(node)
        parent_attrs = parent.attrib if parent is not None else attrs
        bounds = parent_attrs.get("bounds", attrs.get("bounds", ""))
        center = parse_bounds_center(bounds)
        if center is None:
            continue
        source = (
            f"text=分享链接, parentBounds={bounds}, "
            f"parentClickable={parent_attrs.get('clickable', '')}"
        )
        return center[0], center[1], source
    return None


def find_link_copied_close_center(xml_path: Path) -> tuple[int, int, str] | None:
    root = ET.parse(xml_path).getroot()
    title_seen = False
    fallback: tuple[int, int, str] | None = None
    for node in root.iter("node"):
        attrs = node.attrib
        text = attrs.get("text", "")
        resource_id = attrs.get("resource-id", "")
        bounds = attrs.get("bounds", "")
        center = parse_bounds_center(bounds)
        if "链接已复制成功" in text:
            title_seen = True
        if center is None:
            continue
        if resource_id == "com.ss.android.ugc.aweme:id/zjj":
            return center[0], center[1], f"resource-id={resource_id}, bounds={bounds}"
        if title_seen and attrs.get("clickable") == "true" and attrs.get("class") == "android.widget.ImageView":
            fallback = center[0], center[1], f"class=ImageView clickable, bounds={bounds}"
    return fallback


def tap(udid: str, x: int, y: int) -> None:
    result = run_adb(["-s", udid, "shell", "input", "tap", str(x), str(y)])
    if result.returncode != 0:
        raise RuntimeError(f"adb tap failed: {result.stderr.strip() or result.stdout.strip()}")


def swipe_share_panel_left(udid: str) -> None:
    result = run_adb(["-s", udid, "shell", "input", "swipe", "980", "2075", "520", "2075", "400"])
    if result.returncode != 0:
        raise RuntimeError(f"adb swipe failed: {result.stderr.strip() or result.stdout.strip()}")


def read_clipboard_via_adb(udid: str) -> str | None:
    result = run_adb(["-s", udid, "shell", "cmd", "clipboard", "get"])
    output = "\n".join(part.strip() for part in [result.stdout, result.stderr] if part.strip())
    if result.returncode != 0 or not output or "No shell command implementation" in output:
        return None
    return output


def read_clipboard_via_appium(args: argparse.Namespace) -> str:
    manager: AppiumServerManager | None = None
    if not args.no_manage_appium:
        manager = AppiumServerManager(
            default_server_url=args.appium_server_url,
            log_dir=ROOT_DIR / "logs",
            ports_file=ROOT_DIR / "logs" / "appium_ports.txt",
            on_demand_file=ROOT_DIR / "logs" / "appium_on_demand.txt",
        )
        manager.start_for_devices(
            [
                BackendDeviceConfig(
                    id=0,
                    name=args.device_name,
                    udid=args.udid,
                    system_port=args.system_port,
                    enabled_status="enabled",
                    appium_server_url=args.appium_server_url,
                )
            ]
        )
    try:
        factory = AppiumDriverFactory(args.appium_server_url, retries=1)
        managed_driver = factory.create(
            AppiumDeviceConfig(
                udid=args.udid,
                system_port=args.system_port,
                device_name=args.device_name,
                appium_server_url=args.appium_server_url,
            )
        )
        try:
            clipboard_text = managed_driver.driver.get_clipboard_text()
        finally:
            managed_driver.quit()
    finally:
        if manager is not None:
            manager.stop_all()
    return str(clipboard_text or "").strip()


def read_clipboard_text(args: argparse.Namespace) -> str:
    clipboard_text = read_clipboard_via_adb(args.udid)
    if clipboard_text:
        return clipboard_text
    return read_clipboard_via_appium(args)


def main() -> int:
    args = parse_args()
    ensure_adb_on_path()
    ensure_device_online(args.udid)

    if args.force_stop_before:
        run_adb(["-s", args.udid, "shell", "am", "force-stop", args.package_name])
    if args.home_before:
        run_adb(["-s", args.udid, "shell", "input", "keyevent", "HOME"])

    xml_path = dump_current_page_xml(args.udid)
    share_center = find_share_button_center(xml_path)
    if share_center is None:
        if args.no_fallback:
            raise RuntimeError(f"share button not found in current page xml: {xml_path}")
        x, y = args.fallback_x, args.fallback_y
        source = "fallback coordinate"
    else:
        x, y, source = share_center
    tap(args.udid, x, y)
    print(f"clicked share: udid={args.udid}, x={x}, y={y}, source={source}")

    time.sleep(1)
    xml_path = dump_current_page_xml(args.udid)
    share_link_center = find_share_link_center(xml_path)
    if share_link_center is None:
        print("share link not visible yet, swipe share panel left")
        swipe_share_panel_left(args.udid)
        time.sleep(1)
        xml_path = dump_current_page_xml(args.udid)
        share_link_center = find_share_link_center(xml_path)

    if share_link_center is None:
        if args.no_fallback:
            raise RuntimeError(f"share link not found in current page xml: {xml_path}")
        x, y = args.share_link_fallback_x, args.share_link_fallback_y
        source = "share-link fallback coordinate"
    else:
        x, y, source = share_link_center
    tap(args.udid, x, y)
    print(f"clicked share link: udid={args.udid}, x={x}, y={y}, source={source}")

    time.sleep(1)
    clipboard_text = read_clipboard_text(args)
    print(f"copied link: {clipboard_text or '-'}")

    time.sleep(1)
    xml_path = dump_current_page_xml(args.udid)
    close_center = find_link_copied_close_center(xml_path)
    if close_center is None:
        if args.no_fallback:
            raise RuntimeError(f"link copied close button not found in current page xml: {xml_path}")
        x, y = args.close_fallback_x, args.close_fallback_y
        source = "close fallback coordinate"
    else:
        x, y, source = close_center
    tap(args.udid, x, y)
    print(f"closed link copied popup: udid={args.udid}, x={x}, y={y}, source={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
