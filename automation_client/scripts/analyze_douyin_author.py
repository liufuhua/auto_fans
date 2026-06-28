from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
REMOTE_XML = "/sdcard/auto_fans_current_window.xml"

EXACT_SKIP_WORDS = {
    "首页",
    "朋友",
    "消息",
    "我",
    "推荐",
    "关注",
    "精选",
    "经验",
    "视频",
    "图文",
    "直播",
    "商城",
    "搜索",
    "拍摄",
    "评论",
    "分享",
    "喜欢",
    "收藏",
    "私信",
}
CONTAINS_SKIP_WORDS = (
    "按钮",
    "已选中",
    "未选中",
    "点赞",
    "喜欢",
    "评论",
    "分享",
    "收藏",
    "搜索",
    "广告",
    "进入",
)


@dataclass(frozen=True)
class NodeInfo:
    text: str
    source_attr: str
    resource_id: str
    class_name: str
    bounds: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return int((left + right) / 2), int((top + bottom) / 2)


@dataclass(frozen=True)
class Candidate:
    node: NodeInfo
    score: int
    reasons: list[str]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="抓取当前手机页面 XML，并分析抖音首页视频作者名候选。"
    )
    parser.add_argument("--udid", default="", help="ADB 设备 UDID；不填则要求只有一台在线设备")
    parser.add_argument("--top", type=int, default=20, help="输出候选数量")
    parser.add_argument(
        "--output-dir",
        default="automation_client/runtime/page_sources",
        help="保存 XML 的目录",
    )
    args = parser.parse_args()

    udid = args.udid.strip() or detect_single_device()
    if not udid:
        return 2

    xml_text = dump_window_xml(udid)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    xml_path = output_dir / f"douyin_author_{udid}_{time.strftime('%Y%m%d_%H%M%S')}.xml"
    xml_path.write_text(xml_text, encoding="utf-8")

    nodes = parse_nodes(xml_text)
    candidates = rank_author_candidates(nodes)

    print(f"UDID: {udid}")
    print(f"XML: {xml_path}")
    print(f"visible text/content-desc nodes: {len(nodes)}")
    print()
    print("Top author candidates:")
    if not candidates:
        print("  未找到候选。请确认当前停留在抖音视频页，并允许无障碍/XML 读取。")
    for index, candidate in enumerate(candidates[: args.top], start=1):
        node = candidate.node
        x, y = node.center
        print(
            f"{index:02d}. score={candidate.score:>3} text={node.text!r} "
            f"attr={node.source_attr} bounds={format_bounds(node.bounds)} center=({x},{y}) "
            f"res={node.resource_id or '-'} class={node.class_name or '-'}"
        )
        print(f"    reasons: {', '.join(candidate.reasons)}")

    print()
    print("Lower-left raw nodes, useful for manual verification:")
    for node in lower_left_nodes(nodes)[:40]:
        x, y = node.center
        print(
            f"  text={node.text!r} attr={node.source_attr} bounds={format_bounds(node.bounds)} "
            f"center=({x},{y}) res={node.resource_id or '-'} class={node.class_name or '-'}"
        )
    return 0


def detect_single_device() -> str:
    result = run(["adb", "devices"], capture=True)
    devices: list[str] = []
    for line in result.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    if len(devices) != 1:
        print("未指定 --udid，且当前在线设备数量不是 1：", file=sys.stderr)
        print(result, file=sys.stderr)
        return ""
    return devices[0]


def dump_window_xml(udid: str) -> str:
    dump_result = run(
        ["adb", "-s", udid, "shell", "uiautomator", "dump", "--compressed", REMOTE_XML],
        capture=True,
        check=False,
    )
    if "ERROR" in dump_result.upper() or "Exception" in dump_result:
        dump_result = run(
            ["adb", "-s", udid, "shell", "uiautomator", "dump", REMOTE_XML],
            capture=True,
        )
    print(f"uiautomator dump: {dump_result.strip()}")
    return run(["adb", "-s", udid, "exec-out", "cat", REMOTE_XML], capture=True)


def parse_nodes(xml_text: str) -> list[NodeInfo]:
    root = ET.fromstring(xml_text)
    nodes: list[NodeInfo] = []
    seen: set[tuple[str, str, tuple[int, int, int, int]]] = set()
    for element in root.iter("node"):
        bounds = parse_bounds(element.attrib.get("bounds", ""))
        if bounds is None:
            continue
        for attr in ("text", "content-desc"):
            text = (element.attrib.get(attr) or "").strip()
            if not text:
                continue
            key = (attr, text, bounds)
            if key in seen:
                continue
            seen.add(key)
            nodes.append(
                NodeInfo(
                    text=text,
                    source_attr=attr,
                    resource_id=(element.attrib.get("resource-id") or "").strip(),
                    class_name=(element.attrib.get("class") or "").strip(),
                    bounds=bounds,
                )
            )
    return nodes


def rank_author_candidates(nodes: list[NodeInfo]) -> list[Candidate]:
    candidates = [score_node(node) for node in nodes]
    candidates = [candidate for candidate in candidates if candidate.score > 0]
    return sorted(
        candidates,
        key=lambda item: (
            item.score,
            -abs(item.node.center[0] - 220),
            -abs(item.node.center[1] - 1680),
        ),
        reverse=True,
    )


def score_node(node: NodeInfo) -> Candidate:
    text = clean_text(node.text)
    x, y = node.center
    left, top, right, bottom = node.bounds
    score = 0
    reasons: list[str] = []

    if text in EXACT_SKIP_WORDS:
        return Candidate(node, -100, ["exact navigation/control word"])
    if len(text) > 40:
        score -= 30
        reasons.append("too long")
    if any(word in text for word in CONTAINS_SKIP_WORDS):
        score -= 25
        reasons.append("contains control word")
    if re.fullmatch(r"[\d\s.,:：/+-]+", text):
        score -= 20
        reasons.append("numeric-like")

    if text.startswith("@"):
        score += 45
        reasons.append("starts with @")
    if "@" in text:
        score += 15
        reasons.append("contains @")
    if node.source_attr == "text":
        score += 10
        reasons.append("text attr")
    if node.resource_id:
        score += 4
        reasons.append("has resource-id")

    if 0 <= x <= 620:
        score += 18
        reasons.append("left/middle area")
    if 560 <= y <= 2050:
        score += 18
        reasons.append("video body vertical range")
    if y < 360:
        score -= 25
        reasons.append("top navigation area")
    if x > 820:
        score -= 20
        reasons.append("right action area")
    if bottom - top <= 90:
        score += 8
        reasons.append("short label height")
    if 2 <= len(text) <= 18:
        score += 12
        reasons.append("nickname length")
    if re.search(r"医生|团队|三博|医院|脑|外科|咨询", text):
        score += 18
        reasons.append("medical/account keyword")

    if not reasons:
        reasons.append("no strong signal")
    return Candidate(node, score, reasons)


def lower_left_nodes(nodes: list[NodeInfo]) -> list[NodeInfo]:
    return sorted(
        [
            node
            for node in nodes
            if node.center[0] < 720 and 500 <= node.center[1] <= 2150
        ],
        key=lambda node: (node.center[1], node.center[0]),
    )


def parse_bounds(value: str) -> tuple[int, int, int, int] | None:
    match = BOUNDS_RE.fullmatch(value.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def format_bounds(bounds: tuple[int, int, int, int]) -> str:
    left, top, right, bottom = bounds
    return f"[{left},{top}][{right},{bottom}]"


def clean_text(value: str) -> str:
    return value.strip().replace("\u200b", "")


def run(command: list[str], *, capture: bool, check: bool = True) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (result.stdout or "") + (result.stderr or "")
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{output}")
    return output


if __name__ == "__main__":
    raise SystemExit(main())
