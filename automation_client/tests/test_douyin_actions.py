from __future__ import annotations

from pathlib import Path

import pytest

from app.douyin_actions import (
    DouyinActionError,
    DouyinActions,
    LocatorRepository,
    LocatorSpec,
)


class FakeElement:
    def __init__(self, name: str, calls: list[tuple[str, str]]) -> None:
        self.name = name
        self.calls = calls
        self.text = name
        self.rect = {"x": 100, "y": 200, "width": 80, "height": 40}

    def click(self) -> None:
        self.calls.append(("click", self.name))

    def clear(self) -> None:
        self.calls.append(("clear", self.name))

    def send_keys(self, value: str) -> None:
        self.text = value
        self.calls.append(("send_keys", f"{self.name}:{value}"))

    def get_attribute(self, name: str) -> str:
        if name == "value":
            return self.text
        return ""

    def is_displayed(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True


class FakeDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.clipboard_text = ""
        self.elements = {
            ("accessibility id", "搜索"): FakeElement("search_button", self.calls),
            ("id", "search_input"): FakeElement("search_input", self.calls),
            (
                "-android uiautomator",
                'new UiSelector().text("用户")',
            ): FakeElement("user_tab", self.calls),
            ("xpath", "//doctor"): FakeElement("doctor_page_entry", self.calls),
            ("xpath", "//video"): FakeElement("video_entry", self.calls),
            ("accessibility id", "点赞"): FakeElement("like_button", self.calls),
            ("accessibility id", "收藏"): FakeElement("favorite_button", self.calls),
            ("accessibility id", "评论"): FakeElement("comment_button", self.calls),
            ("id", "comment_input"): FakeElement("comment_input", self.calls),
            ("accessibility id", "发送"): FakeElement("send_comment_button", self.calls),
        }

    def activate_app(self, package_name: str) -> None:
        self.calls.append(("activate_app", package_name))

    def find_element(self, by: str, value: str) -> FakeElement:
        return self.elements[(by, value)]

    def find_elements(self, by: str, value: str) -> list[FakeElement]:
        if (by, value) == ("id", "author_name"):
            return [
                FakeElement("神经外科权博士", self.calls),
                FakeElement("神外打工人", self.calls),
                FakeElement("天坛医院脑...", self.calls),
                FakeElement("神经外科陈...", self.calls),
            ]
        return [self.find_element(by, value)]

    def press_keycode(self, keycode: int) -> None:
        self.calls.append(("press_keycode", str(keycode)))
        if keycode == 279:
            self.elements[("id", "comment_input")].send_keys(self.clipboard_text)

    def set_clipboard_text(self, text: str) -> None:
        self.clipboard_text = text
        self.calls.append(("set_clipboard_text", text))

    def execute_script(self, script: str, params: dict[str, int | float | str]) -> None:
        if script == "mobile: type":
            self.elements[("id", "comment_input")].send_keys(str(params["text"]))
            return
        if "x" in params and "y" in params:
            self.calls.append(("execute_script", f"{script}:{params['x']},{params['y']}"))
            return
        self.calls.append(("execute_script", f"{script}:{params}"))

    def get_window_size(self) -> dict[str, int]:
        return {"width": 1080, "height": 2640}

    def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: int) -> None:
        self.calls.append(("swipe", f"{start_x},{start_y}->{end_x},{end_y}:{duration}"))

    def save_screenshot(self, path: str) -> None:
        Path(path).write_bytes(b"fake image")
        self.calls.append(("save_screenshot", path))


def build_locators() -> LocatorRepository:
    return LocatorRepository(
        {
            "search_button": LocatorSpec("search_button", "accessibility_id", "搜索"),
            "search_input": LocatorSpec("search_input", "id", "search_input"),
            "user_tab": LocatorSpec("user_tab", "text", "用户"),
            "doctor_page_entry": LocatorSpec("doctor_page_entry", "xpath", "//doctor"),
            "video_entry": LocatorSpec("video_entry", "xpath", "//video"),
            "like_button": LocatorSpec("like_button", "accessibility_id", "点赞"),
            "favorite_button": LocatorSpec("favorite_button", "accessibility_id", "收藏"),
            "comment_button": LocatorSpec("comment_button", "accessibility_id", "评论"),
            "comment_input": LocatorSpec("comment_input", "id", "comment_input"),
            "send_comment_button": LocatorSpec("send_comment_button", "accessibility_id", "发送"),
        }
    )


def test_douyin_fixed_actions_sequence(tmp_path: Path) -> None:
    driver = FakeDriver()
    actions = DouyinActions(
        driver=driver,
        locators=build_locators(),
        udid="device-1",
        screenshot_dir=tmp_path,
        wait_timeout_seconds=1,
    )

    actions.open_douyin()
    actions.search_keyword("脑膜瘤")
    actions.enter_doctor_page("张明山")
    actions.open_target_video()
    actions.like_video()
    actions.favorite_video()
    actions.post_comment("测试评论")

    assert driver.calls == [
        ("activate_app", "com.ss.android.ugc.aweme"),
        ("click", "search_button"),
        ("clear", "search_input"),
        ("send_keys", "search_input:脑膜瘤"),
        ("press_keycode", "66"),
        ("click", "user_tab"),
        ("click", "doctor_page_entry"),
        ("click", "video_entry"),
        ("click", "like_button"),
        ("click", "favorite_button"),
        ("click", "comment_button"),
        ("click", "comment_input"),
        ("click", "comment_input"),
        ("send_keys", "comment_input:测试评论"),
        ("click", "send_comment_button"),
    ]


def test_post_comment_can_skip_send(tmp_path: Path) -> None:
    driver = FakeDriver()
    actions = DouyinActions(
        driver=driver,
        locators=build_locators(),
        udid="device-1",
        screenshot_dir=tmp_path,
        wait_timeout_seconds=1,
    )

    actions.post_comment("测试评论", send_comment=False)

    assert ("send_keys", "comment_input:测试评论") in driver.calls
    assert ("click", "send_comment_button") not in driver.calls


def test_action_failure_saves_screenshot(tmp_path: Path) -> None:
    driver = FakeDriver()
    locators = LocatorRepository(
        {"like_button": LocatorSpec("like_button", "accessibility_id", "")}
    )
    actions = DouyinActions(
        driver=driver,
        locators=locators,
        udid="device-1",
        screenshot_dir=tmp_path,
        wait_timeout_seconds=1,
        task_id=2,
    )

    with pytest.raises(DouyinActionError, match="like_video"):
        actions.like_video()

    screenshots = list(tmp_path.glob("device-1_2_*.png"))
    assert len(screenshots) == 1


def test_action_task_context_updates_screenshot_task_id(tmp_path: Path) -> None:
    driver = FakeDriver()
    locators = LocatorRepository(
        {"like_button": LocatorSpec("like_button", "accessibility_id", "")}
    )
    actions = DouyinActions(
        driver=driver,
        locators=locators,
        udid="device-1",
        screenshot_dir=tmp_path,
        wait_timeout_seconds=1,
    ).with_task_context(9)

    with pytest.raises(DouyinActionError, match="like_video"):
        actions.like_video()

    screenshots = list(tmp_path.glob("device-1_9_*.png"))
    assert len(screenshots) == 1


def test_locator_repository_loads_strategy_priority_and_coordinate(tmp_path: Path) -> None:
    locator_file = tmp_path / "locators.yaml"
    locator_file.write_text(
        """
like_button:
  strategies:
    - by: resource-id
      value: ""
    - by: content-desc
      value: 点赞
    - by: coordinate
      x: 100
      y: 200
""",
        encoding="utf-8",
    )

    repository = LocatorRepository.from_yaml(locator_file)
    strategies = repository.get("like_button")

    assert [strategy.by for strategy in strategies] == [
        "resource-id",
        "content-desc",
        "coordinate",
    ]
    assert strategies[1].to_appium() == ("accessibility id", "点赞")
    assert strategies[2].coordinate() == (100, 200)


def test_click_uses_coordinate_fallback(tmp_path: Path) -> None:
    driver = FakeDriver()
    locators = LocatorRepository(
        {
            "like_button": [
                LocatorSpec("like_button", "resource-id", ""),
                LocatorSpec("like_button", "coordinate", x=100, y=200),
            ]
        }
    )
    actions = DouyinActions(
        driver=driver,
        locators=locators,
        udid="device-1",
        screenshot_dir=tmp_path,
        wait_timeout_seconds=1,
    )

    actions.like_video()

    assert ("execute_script", "mobile: clickGesture:100,200") in driver.calls


def test_get_texts_returns_limited_non_empty_texts(tmp_path: Path) -> None:
    driver = FakeDriver()
    actions = DouyinActions(
        driver=driver,
        locators=LocatorRepository(
            {"video_author_name": LocatorSpec("video_author_name", "resource-id", "author_name")}
        ),
        udid="device-1",
        screenshot_dir=tmp_path,
        wait_timeout_seconds=1,
    )

    assert actions.get_texts("video_author_name", limit=4) == [
        "神经外科权博士",
        "神外打工人",
        "天坛医院脑...",
        "神经外科陈...",
    ]


def test_try_click_text_contains_clicks_matching_author(tmp_path: Path) -> None:
    driver = FakeDriver()
    actions = DouyinActions(
        driver=driver,
        locators=LocatorRepository(
            {"video_author_name": LocatorSpec("video_author_name", "resource-id", "author_name")}
        ),
        udid="device-1",
        screenshot_dir=tmp_path,
        wait_timeout_seconds=1,
    )

    assert actions.try_click_text_contains("video_author_name", "打工人") == "神外打工人"
    assert ("click", "神外打工人") in driver.calls


def test_swipe_up_uses_real_upward_screen_swipe(tmp_path: Path) -> None:
    driver = FakeDriver()
    actions = DouyinActions(
        driver=driver,
        locators=build_locators(),
        udid="device-1",
        screenshot_dir=tmp_path,
        wait_timeout_seconds=1,
    )

    actions.swipe_up()

    assert ("swipe", "540,2164->540,475:500") in driver.calls
