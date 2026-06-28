from __future__ import annotations

import argparse

from app.douyin_actions import DouyinActions, LocatorRepository, LocatorSpec
from app.douyin_search_support import log_step


DEFAULT_LINK_COPIED_CLOSE_XPATH = (
    '//android.widget.ImageView[@resource-id="com.ss.android.ugc.aweme:id/zks"]'
)
DEFAULT_VIDEO_BACK_XPATH = (
    '//android.widget.ImageView[@resource-id="com.ss.android.ugc.aweme:id/back_btn" '
    'and (@content-desc="返回" or @content-desc="关闭" or @content-desc="杩斿洖")]'
)
DEFAULT_SEARCH_BACK_XPATH = (
    '//android.widget.ImageView[@resource-id="com.ss.android.ugc.aweme:id/bve" '
    'and (@content-desc="返回" or @content-desc="杩斿洖")]'
)


def build_return_home_locators(args: argparse.Namespace) -> LocatorRepository:
    return LocatorRepository(
        {
            "link_copied_close_button": [
                LocatorSpec(
                    "link_copied_close_button",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/zks",
                ),
                LocatorSpec(
                    "link_copied_close_button",
                    "xpath",
                    args.link_copied_close_xpath,
                ),
            ],
            "video_back_button": [
                LocatorSpec("video_back_button", "xpath", args.video_back_xpath),
                LocatorSpec("video_back_button", "coordinate", x=95, y=170),
            ],
            "search_back_button": [
                LocatorSpec("search_back_button", "xpath", args.search_back_xpath),
                LocatorSpec("search_back_button", "coordinate", x=90, y=164),
            ],
        }
    )


def get_page_source(driver) -> str:
    try:
        return str(driver.page_source or "")
    except Exception as exc:  # noqa: BLE001 - page source is best-effort in fallback flow.
        log_step(f"读取页面结构失败，继续兜底返回：{exc}")
        return ""


def is_home_page(source: str) -> bool:
    has_home_tab = (
        'content-desc="首页，按钮"' in source
        or 'text="首页"' in source
        or 'content-desc="棣栭〉锛屾寜閽?' in source
        or 'text="棣栭〉"' in source
    )
    has_bottom_tabs = (
        (
            ('content-desc="消息，按钮"' in source or 'text="消息"' in source)
            and ('content-desc="我，按钮"' in source or 'text="我"' in source)
        )
        or (
            'content-desc="朋友，按钮"' in source
            and 'content-desc="消息，按钮"' in source
        )
        or (
            'content-desc="鏈嬪弸锛屾寜閽?' in source
            and 'content-desc="娑堟伅锛屾寜閽?' in source
        )
    )
    has_search_input = 'resource-id="com.ss.android.ugc.aweme:id/et_search_kw"' in source
    return has_home_tab and has_bottom_tabs and not has_search_input


def is_home_feed_page(source: str) -> bool:
    if not source or has_search_page(source):
        return False
    if 'resource-id="com.ss.android.ugc.aweme:id/back_btn"' in source:
        return False
    has_author = (
        'resource-id="com.ss.android.ugc.aweme:id/title"' in source
        or 'resource-id="com.ss.android.ugc.aweme:id/user_avatar"' in source
    )
    has_video_actions = any(
        marker in source
        for marker in (
            "喜欢",
            "评论",
            "收藏",
            "分享",
            "鍠滄",
            "璇勮",
            "鏀惰棌",
            "鍒嗕韩",
        )
    )
    return has_author and has_video_actions


def has_link_copied_popup(source: str) -> bool:
    return (
        "链接已复制成功" in source
        or "閾炬帴宸插鍒舵垚鍔?" in source
        or 'resource-id="com.ss.android.ugc.aweme:id/zks"' in source
    )


def has_video_back(source: str) -> bool:
    if is_home_page(source):
        return False
    has_back_button = (
        'resource-id="com.ss.android.ugc.aweme:id/back_btn"' in source
        or 'content-desc="返回"' in source
        or 'content-desc="关闭"' in source
        or 'content-desc="杩斿洖"' in source
    )
    has_video_container = 'content-desc="视频"' in source or 'content-desc="瑙嗛"' in source
    has_comment_or_like = (
        "评论" in source
        or "喜欢" in source
        or "收藏" in source
        or "璇勮" in source
        or "鍠滄" in source
        or "鏀惰棌" in source
    )
    return has_back_button and has_video_container and has_comment_or_like


def has_search_page(source: str) -> bool:
    return (
        'resource-id="com.ss.android.ugc.aweme:id/et_search_kw"' in source
        or 'resource-id="com.ss.android.ugc.aweme:id/bve"' in source
    )


def safe_click(actions: DouyinActions, locator_name: str, label: str) -> bool:
    try:
        log_step(f"尝试点击：{label}")
        actions._click(locator_name)
        log_step(f"点击成功：{label}")
        return True
    except Exception as exc:  # noqa: BLE001 - fallback flow should keep trying.
        log_step(f"跳过：{label}，原因：{exc}")
        return False


def press_android_back(driver, index: int) -> None:
    log_step(f"执行系统返回键：第 {index} 次")
    if hasattr(driver, "press_keycode"):
        driver.press_keycode(4)
        return
    driver.back()
