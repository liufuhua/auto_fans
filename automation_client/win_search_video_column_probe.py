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

AUTOMATION_CLIENT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = AUTOMATION_CLIENT_DIR / "runtime"
sys.path.insert(0, str(AUTOMATION_CLIENT_DIR))

from app.appium_driver import AppiumDeviceConfig, AppiumDriverFactory  # noqa: E402
from app.config import settings  # noqa: E402
from app.logger import configure_logging  # noqa: E402

AUTHOR_RESOURCE_ID = "com.ss.android.ugc.aweme:id/+j"
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
class SourceNode:
    text: str
    content_desc: str
    resource_id: str
    class_name: str
    clickable: str
    bounds: Bounds

    def label(self) -> str:
        return self.text or self.content_desc or self.resource_id or self.class_name


@dataclass(frozen=True)
class VideoCandidate:
    index: int
    column: str
    author: SourceNode | None
    cover: SourceNode | None
    like_y_only: SourceNode | None
    like_same_column: SourceNode | None

    @property
    def sort_bounds(self) -> Bounds:
        if self.cover is not None:
            return self.cover.bounds
        if self.author is not None:
            return self.author.bounds
        raise ValueError("candidate has no bounds")

    @property
    def author_text(self) -> str:
        return self.author.text if self.author is not None else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe the current Douyin search/video result page and compare left/right "
            "video candidates. Put the phone on the result page before running."
        )
    )
    parser.add_argument("--udid", required=True)
    parser.add_argument("--device-name", default="device_probe")
    parser.add_argument("--system-port", type=int, default=8208)
    parser.add_argument("--appium-server-url", default=settings.appium_server_url)
    parser.add_argument("--package-name", default=settings.douyin_package_name)
    parser.add_argument("--app-activity", default=settings.douyin_app_activity)
    parser.add_argument("--app", default=settings.douyin_app_path)
    parser.add_argument("--target-author", default="")
    parser.add_argument("--column", choices=["left", "right", "any"], default="any")
    parser.add_argument("--index", type=int, default=1, help="1-based index within the selected column.")
    parser.add_argument("--click", action="store_true", help="Actually tap the selected candidate.")
    parser.add_argument(
        "--click-mode",
        choices=["cover", "author"],
        default="cover",
        help="Tap cover center or the existing-flow author text center.",
    )
    parser.add_argument("--min-top-y", type=int, default=360)
    parser.add_argument("--after-click-seconds", type=float, default=1.5)
    parser.add_argument("--quit-timeout-seconds", type=int, default=5)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def log_step(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


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
        log_step(f"warning: driver.quit() timed out after {timeout_seconds}s")


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


def get_screen_width(root: ET.Element) -> int:
    width = root.attrib.get("width")
    if width and width.isdigit():
        return int(width)
    bounds = parse_bounds(root.attrib.get("bounds"))
    if bounds is not None:
        return bounds.width
    return 1080


def column_for(bounds: Bounds, screen_width: int) -> str:
    return "left" if bounds.center_x < screen_width / 2 else "right"


def is_like_node(node: SourceNode) -> bool:
    value = node.content_desc
    return "点赞" in value or "喜欢" in value or "已点赞" in value


def is_liked(node: SourceNode | None) -> bool:
    if node is None:
        return False
    value = node.content_desc
    return "已点赞" in value or value.startswith("已点")


def as_source_node(element: ET.Element) -> SourceNode | None:
    bounds = parse_bounds(element.attrib.get("bounds"))
    if bounds is None:
        return None
    return SourceNode(
        text=(element.attrib.get("text") or "").strip(),
        content_desc=(element.attrib.get("content-desc") or "").strip(),
        resource_id=element.attrib.get("resource-id", ""),
        class_name=element.attrib.get("class", ""),
        clickable=element.attrib.get("clickable", ""),
        bounds=bounds,
    )


def dedupe_nodes(nodes: list[SourceNode]) -> list[SourceNode]:
    seen: set[tuple[str, str, str]] = set()
    result: list[SourceNode] = []
    for node in nodes:
        key = (node.resource_id, node.content_desc or node.text, node.bounds.as_text())
        if key in seen:
            continue
        seen.add(key)
        result.append(node)
    return result


def collect_nodes(page_source: str, *, min_top_y: int) -> tuple[int, list[SourceNode], list[SourceNode], list[SourceNode]]:
    root = ET.fromstring(page_source)
    screen_width = get_screen_width(root)
    authors: list[SourceNode] = []
    covers: list[SourceNode] = []
    likes: list[SourceNode] = []

    for element in root.iter():
        node = as_source_node(element)
        if node is None or node.bounds.top < min_top_y:
            continue
        if node.resource_id == AUTHOR_RESOURCE_ID and node.text:
            authors.append(node)
        if "视频封面" in node.content_desc:
            covers.append(node)
        if is_like_node(node):
            likes.append(node)

    clickable_covers = [node for node in covers if node.clickable == "true"]
    if clickable_covers:
        covers = clickable_covers

    return screen_width, dedupe_nodes(authors), dedupe_nodes(covers), dedupe_nodes(likes)


def nearest_like(author: SourceNode, likes: list[SourceNode], *, screen_width: int, same_column: bool) -> SourceNode | None:
    choices = likes
    if same_column:
        author_column = column_for(author.bounds, screen_width)
        choices = [node for node in likes if column_for(node.bounds, screen_width) == author_column]
    if not choices:
        return None
    return min(choices, key=lambda node: abs(node.bounds.center_y - author.bounds.center_y))


def nearest_cover(author: SourceNode, covers: list[SourceNode], *, screen_width: int) -> SourceNode | None:
    author_column = column_for(author.bounds, screen_width)
    same_column = [node for node in covers if column_for(node.bounds, screen_width) == author_column]
    if not same_column:
        return None

    def score(cover: SourceNode) -> tuple[int, int]:
        vertical_gap = 0
        if author.bounds.center_y < cover.bounds.top:
            vertical_gap = cover.bounds.top - author.bounds.center_y
        elif author.bounds.center_y > cover.bounds.bottom:
            vertical_gap = author.bounds.center_y - cover.bounds.bottom
        return vertical_gap, abs(cover.bounds.center_y - author.bounds.center_y)

    return min(same_column, key=score)


def collect_candidates(
    page_source: str,
    *,
    min_top_y: int,
) -> tuple[int, list[SourceNode], list[SourceNode], list[SourceNode], list[VideoCandidate]]:
    screen_width, authors, covers, likes = collect_nodes(page_source, min_top_y=min_top_y)
    candidates: list[VideoCandidate] = []
    used_cover_bounds: set[str] = set()

    for author in authors:
        cover = nearest_cover(author, covers, screen_width=screen_width)
        if cover is not None:
            used_cover_bounds.add(cover.bounds.as_text())
        candidates.append(
            VideoCandidate(
                index=0,
                column=column_for(author.bounds, screen_width),
                author=author,
                cover=cover,
                like_y_only=nearest_like(author, likes, screen_width=screen_width, same_column=False),
                like_same_column=nearest_like(author, likes, screen_width=screen_width, same_column=True),
            )
        )

    for cover in covers:
        if cover.bounds.as_text() in used_cover_bounds:
            continue
        candidates.append(
            VideoCandidate(
                index=0,
                column=column_for(cover.bounds, screen_width),
                author=None,
                cover=cover,
                like_y_only=None,
                like_same_column=None,
            )
        )

    candidates.sort(key=lambda item: (item.sort_bounds.top, item.sort_bounds.left))
    indexed = [
        VideoCandidate(
            index=index + 1,
            column=item.column,
            author=item.author,
            cover=item.cover,
            like_y_only=item.like_y_only,
            like_same_column=item.like_same_column,
        )
        for index, item in enumerate(candidates)
    ]
    return screen_width, authors, covers, likes, indexed


def save_snapshot(driver: Any) -> tuple[str, Path, Path]:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source_path = RUNTIME_DIR / f"search_video_column_probe_{stamp}.xml"
    screenshot_path = RUNTIME_DIR / f"search_video_column_probe_{stamp}.png"
    page_source = str(driver.page_source or "")
    source_path.write_text(page_source, encoding="utf-8")
    try:
        driver.save_screenshot(str(screenshot_path))
    except Exception as exc:  # noqa: BLE001
        log_step(f"warning: save screenshot failed: {type(exc).__name__}: {exc}")
    return page_source, source_path, screenshot_path


def format_like(node: SourceNode | None) -> str:
    if node is None:
        return "-"
    state = "liked" if is_liked(node) else "not-liked/unknown"
    return f"{state} {node.content_desc!r} {node.bounds.as_text()}"


def dump_candidates(
    *,
    screen_width: int,
    authors: list[SourceNode],
    covers: list[SourceNode],
    likes: list[SourceNode],
    candidates: list[VideoCandidate],
    target_author: str,
) -> None:
    log_step(
        f"screenWidth={screen_width}, authors={len(authors)}, covers={len(covers)}, "
        f"likes={len(likes)}, candidates={len(candidates)}"
    )
    for item in candidates:
        author_text = item.author_text or "-"
        matched = bool(target_author and target_author in author_text)
        author_bounds = item.author.bounds.as_text() if item.author is not None else "-"
        cover_bounds = item.cover.bounds.as_text() if item.cover is not None else "-"
        cover_clickable = item.cover.clickable if item.cover is not None else "-"
        print(
            "  "
            f"#{item.index:02d} column={item.column:<5} matched={matched} "
            f"author={author_text!r} authorBounds={author_bounds} "
            f"coverBounds={cover_bounds} coverClickable={cover_clickable}",
            flush=True,
        )
        if item.author is not None:
            print(f"      likeByYOnly={format_like(item.like_y_only)}", flush=True)
            print(f"      likeBySameColumn={format_like(item.like_same_column)}", flush=True)


def choose_candidate(candidates: list[VideoCandidate], *, column: str, index: int, target_author: str) -> VideoCandidate | None:
    choices = candidates
    if column != "any":
        choices = [item for item in choices if item.column == column]
    if target_author:
        matched = [item for item in choices if target_author in item.author_text]
        if matched:
            choices = matched
    if index < 1 or index > len(choices):
        return None
    return choices[index - 1]


def tap(driver: Any, bounds: Bounds) -> None:
    try:
        driver.execute_script("mobile: clickGesture", {"x": bounds.center_x, "y": bounds.center_y})
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
        f"connect Appium: server={args.appium_server_url}, udid={args.udid}, "
        f"systemPort={args.system_port}"
    )
    managed_driver = AppiumDriverFactory(args.appium_server_url, retries=1).create(device)
    try:
        driver = managed_driver.driver
        page_source, source_path, screenshot_path = save_snapshot(driver)
        log_step(f"snapshot saved: xml={source_path}, screenshot={screenshot_path}")

        screen_width, authors, covers, likes, candidates = collect_candidates(
            page_source,
            min_top_y=args.min_top_y,
        )
        dump_candidates(
            screen_width=screen_width,
            authors=authors,
            covers=covers,
            likes=likes,
            candidates=candidates,
            target_author=args.target_author.strip(),
        )

        selected = choose_candidate(
            candidates,
            column=args.column,
            index=args.index,
            target_author=args.target_author.strip(),
        )
        if selected is None:
            log_step(
                f"no candidate selected: column={args.column}, index={args.index}, "
                f"targetAuthor={args.target_author!r}"
            )
            return 2

        tap_node = selected.cover if args.click_mode == "cover" else selected.author
        if tap_node is None:
            log_step(f"selected candidate has no {args.click_mode} node")
            return 3
        log_step(
            f"selected #{selected.index}: column={selected.column}, author={selected.author_text!r}, "
            f"tapMode={args.click_mode}, tap=({tap_node.bounds.center_x},{tap_node.bounds.center_y}), "
            f"bounds={tap_node.bounds.as_text()}"
        )
        if not args.click:
            log_step("dry run: add --click to tap the selected candidate")
            return 0

        tap(driver, tap_node.bounds)
        time.sleep(args.after_click_seconds)
        log_step("tap sent")
        return 0
    finally:
        quit_with_timeout(managed_driver.driver, args.quit_timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
