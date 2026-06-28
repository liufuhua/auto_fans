from __future__ import annotations

import argparse
import re
import sys
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.appium_driver import AppiumDeviceConfig, AppiumDriverFactory
from app.config import settings
from app.logger import configure_logging


TAB_WORDS = ("综合", "视频", "用户", "直播", "商品", "地点", "经验", "问答")
BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center_x(self) -> int:
        return (self.left + self.right) // 2

    @property
    def center_y(self) -> int:
        return (self.top + self.bottom) // 2

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def as_text(self) -> str:
        return f"[{self.left},{self.top}][{self.right},{self.bottom}]"


@dataclass(frozen=True)
class TabCandidate:
    index: int
    label: str
    text: str
    content_desc: str
    class_name: str
    resource_id: str
    selected: str
    clickable: str
    label_bounds: Bounds
    click_bounds: Bounds


def log_step(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Test switching the current Douyin search page to the video tab. "
            "Put the phone on the search result page before running this script."
        )
    )
    parser.add_argument("--udid", default="R5CW11CKN0B")
    parser.add_argument("--device-name", default="device_03")
    parser.add_argument("--system-port", type=int, default=8203)
    parser.add_argument("--label", default="视频")
    parser.add_argument("--max-top-y", type=int, default=520)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--after-click-seconds", type=float, default=1.5)
    parser.add_argument("--page-source-output", default="")
    parser.add_argument("--appium-server-url", default=settings.appium_server_url)
    parser.add_argument("--package-name", default=settings.douyin_package_name)
    parser.add_argument("--app-activity", default=settings.douyin_app_activity)
    parser.add_argument("--app", default=settings.douyin_app_path)
    parser.add_argument("--quit-timeout-seconds", type=int, default=5)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def quit_with_timeout(driver: Any, timeout_seconds: int) -> None:
    done = threading.Event()

    def quit_driver() -> None:
        try:
            driver.quit()
        finally:
            done.set()

    thread = threading.Thread(target=quit_driver, daemon=True)
    thread.start()
    if not done.wait(timeout_seconds):
        log_step(f"warning: driver.quit() timed out after {timeout_seconds}s; exiting")


def parse_bounds(value: str | None) -> Bounds | None:
    if not value:
        return None
    match = BOUNDS_RE.fullmatch(value)
    if not match:
        return None
    left, top, right, bottom = (int(item) for item in match.groups())
    if right <= left or bottom <= top:
        return None
    return Bounds(left=left, top=top, right=right, bottom=bottom)


def node_label(node: ET.Element) -> str:
    text = (node.attrib.get("text") or "").strip()
    content_desc = (node.attrib.get("content-desc") or "").strip()
    return text or content_desc


def is_tab_label(label: str, resource_id: str) -> bool:
    if any(word in label for word in TAB_WORDS):
        return True
    return resource_id == "android:id/text1" and bool(label)


def closest_click_node(
    node: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    *,
    max_top_y: int,
) -> ET.Element:
    current = node
    best = node
    while True:
        bounds = parse_bounds(current.attrib.get("bounds"))
        if bounds and bounds.top <= max_top_y and current.attrib.get("clickable") == "true":
            best = current
            break
        parent = parent_map.get(current)
        if parent is None:
            break
        parent_bounds = parse_bounds(parent.attrib.get("bounds"))
        if parent_bounds is None or parent_bounds.top > max_top_y:
            break
        if parent_bounds.width > 500 or parent_bounds.height > 180:
            break
        current = parent
    return best


def collect_tab_candidates(page_source: str, *, max_top_y: int) -> list[TabCandidate]:
    root = ET.fromstring(page_source)
    parent_map = {child: parent for parent in root.iter() for child in parent}
    candidates: list[TabCandidate] = []
    seen: set[tuple[str, str]] = set()

    for node in root.iter():
        label = node_label(node)
        resource_id = node.attrib.get("resource-id", "")
        if not is_tab_label(label, resource_id):
            continue
        label_bounds = parse_bounds(node.attrib.get("bounds"))
        if label_bounds is None or label_bounds.top > max_top_y:
            continue
        click_node = closest_click_node(node, parent_map, max_top_y=max_top_y)
        click_bounds = parse_bounds(click_node.attrib.get("bounds")) or label_bounds
        key = (label, click_bounds.as_text())
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            TabCandidate(
                index=0,
                label=label,
                text=node.attrib.get("text", ""),
                content_desc=node.attrib.get("content-desc", ""),
                class_name=node.attrib.get("class", ""),
                resource_id=resource_id,
                selected=click_node.attrib.get("selected", node.attrib.get("selected", "")),
                clickable=click_node.attrib.get("clickable", node.attrib.get("clickable", "")),
                label_bounds=label_bounds,
                click_bounds=click_bounds,
            )
        )

    candidates.sort(key=lambda item: (item.click_bounds.top, item.click_bounds.left))
    return [
        TabCandidate(
            index=index + 1,
            label=item.label,
            text=item.text,
            content_desc=item.content_desc,
            class_name=item.class_name,
            resource_id=item.resource_id,
            selected=item.selected,
            clickable=item.clickable,
            label_bounds=item.label_bounds,
            click_bounds=item.click_bounds,
        )
        for index, item in enumerate(candidates)
    ]


def choose_tab(candidates: list[TabCandidate], label: str) -> TabCandidate | None:
    exact = [item for item in candidates if item.label == label]
    if exact:
        return exact[0]
    contains = [item for item in candidates if label in item.label]
    return contains[0] if contains else None


def dump_candidates(candidates: list[TabCandidate]) -> None:
    if not candidates:
        log_step("未识别到顶部 Tab 候选")
        return
    log_step("当前识别到的顶部 Tab 候选：")
    for item in candidates:
        print(
            "  "
            f"#{item.index} label={item.label!r} "
            f"selected={item.selected!r} clickable={item.clickable!r} "
            f"labelBounds={item.label_bounds.as_text()} "
            f"clickBounds={item.click_bounds.as_text()} "
            f"class={item.class_name!r} id={item.resource_id!r}",
            flush=True,
        )


def save_page_source(page_source: str, output: str) -> None:
    if not output:
        return
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(page_source, encoding="utf-8")
    log_step(f"已保存 page source：{output_path}")


def click_bounds(driver: Any, bounds: Bounds) -> None:
    try:
        driver.execute_script(
            "mobile: clickGesture",
            {"x": bounds.center_x, "y": bounds.center_y},
        )
    except Exception:
        driver.tap([(bounds.center_x, bounds.center_y)])


def main() -> int:
    args = parse_args()
    configure_logging(debug=args.debug)

    app_path = str(Path(args.app).resolve()) if args.app else None
    device = AppiumDeviceConfig(
        udid=args.udid,
        system_port=args.system_port,
        device_name=args.device_name,
        app=app_path,
        app_package=args.package_name,
        app_activity=args.app_activity,
    )

    log_step(
        "连接 Appium："
        f"server={args.appium_server_url}, udid={args.udid}, "
        f"systemPort={args.system_port}"
    )
    managed_driver = AppiumDriverFactory(args.appium_server_url, retries=1).create(device)
    try:
        driver = managed_driver.driver
        page_source = driver.page_source
        save_page_source(page_source, args.page_source_output)
        candidates = collect_tab_candidates(page_source, max_top_y=args.max_top_y)
        dump_candidates(candidates)

        target = choose_tab(candidates, args.label)
        if target is None:
            log_step(f"未找到目标 Tab：{args.label!r}")
            return 2

        log_step(
            f"准备点击目标 Tab：#{target.index} {target.label!r}, "
            f"center=({target.click_bounds.center_x},{target.click_bounds.center_y}), "
            f"bounds={target.click_bounds.as_text()}"
        )
        if args.dry_run:
            log_step("dry-run 模式，不执行点击")
            return 0

        click_bounds(driver, target.click_bounds)
        time.sleep(args.after_click_seconds)

        after_source = driver.page_source
        after_candidates = collect_tab_candidates(after_source, max_top_y=args.max_top_y)
        selected = [item for item in after_candidates if item.selected == "true"]
        log_step("点击后重新识别 Tab：")
        dump_candidates(after_candidates)
        if selected:
            log_step("点击后 selected=true 的 Tab：" + ", ".join(item.label for item in selected))
        else:
            log_step("点击后未在 page source 中看到 selected=true，仅能确认点击已发出")
        return 0
    finally:
        quit_with_timeout(managed_driver.driver, args.quit_timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
