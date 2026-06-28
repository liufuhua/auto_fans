from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.logger import sanitize_filename

logger = logging.getLogger(__name__)


class DouyinActionError(RuntimeError):
    pass


class DouyinLocatorError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocatorSpec:
    name: str
    by: str
    value: str = ""
    x: int | None = None
    y: int | None = None

    @property
    def is_coordinate(self) -> bool:
        return self._normalized_by() == "coordinate"

    def to_appium(self) -> tuple[str, str]:
        normalized_by = self._normalized_by()
        if normalized_by == "coordinate":
            raise DouyinLocatorError(f"Locator '{self.name}' is coordinate-only")
        if not self.value:
            raise DouyinLocatorError(f"Locator '{self.name}' has empty value")

        if normalized_by == "id":
            return AppiumBy.ID, self.value
        if normalized_by == "accessibility_id":
            return AppiumBy.ACCESSIBILITY_ID, self.value
        if normalized_by == "xpath":
            return AppiumBy.XPATH, self.value
        if normalized_by == "android_uiautomator":
            return AppiumBy.ANDROID_UIAUTOMATOR, self.value
        if normalized_by == "class_name":
            return AppiumBy.CLASS_NAME, self.value
        if normalized_by == "text":
            escaped = self.value.replace('"', '\\"')
            return AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().text("{escaped}")'

        raise DouyinLocatorError(f"Locator '{self.name}' has unsupported by='{self.by}'")

    def coordinate(self) -> tuple[int, int]:
        if self.x is None or self.y is None:
            raise DouyinLocatorError(f"Locator '{self.name}' coordinate requires x and y")
        return self.x, self.y

    def _normalized_by(self) -> str:
        aliases = {
            "resource-id": "id",
            "resource_id": "id",
            "content-desc": "accessibility_id",
            "content_desc": "accessibility_id",
            "accessibility-id": "accessibility_id",
            "uiautomator": "android_uiautomator",
            "android-uiautomator": "android_uiautomator",
            "class": "class_name",
            "coordinate": "coordinate",
            "coordinates": "coordinate",
            "坐标": "coordinate",
        }
        raw = self.by.strip()
        return aliases.get(raw, raw)


class LocatorRepository:
    def __init__(self, locators: dict[str, LocatorSpec | list[LocatorSpec]]) -> None:
        self.locators = locators

    @classmethod
    def from_yaml(cls, path: str | Path) -> LocatorRepository:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise DouyinLocatorError("Locator file must be a yaml mapping")

        locators: dict[str, LocatorSpec] = {}
        for name, item in raw.items():
            if not isinstance(item, dict):
                raise DouyinLocatorError(f"Locator '{name}' must be a mapping")
            locators[str(name)] = cls._parse_locator(str(name), item)
        return cls(locators)

    def get(self, name: str) -> list[LocatorSpec]:
        try:
            locator = self.locators[name]
        except KeyError as exc:
            raise DouyinLocatorError(f"Locator '{name}' not found") from exc
        if isinstance(locator, list):
            return locator
        return [locator]

    @staticmethod
    def _parse_locator(name: str, item: dict[str, object]) -> list[LocatorSpec]:
        raw_strategies = item.get("strategies")
        if isinstance(raw_strategies, list):
            return [
                LocatorRepository._parse_strategy(name, strategy)
                for strategy in raw_strategies
                if isinstance(strategy, dict)
            ]
        return [
            LocatorRepository._parse_strategy(
                name,
                item,
            )
        ]

    @staticmethod
    def _parse_strategy(name: str, item: dict[str, object]) -> LocatorSpec:
        return LocatorSpec(
            name=name,
            by=str(item.get("by") or ""),
            value=str(item.get("value") or ""),
            x=LocatorRepository._optional_int(item.get("x")),
            y=LocatorRepository._optional_int(item.get("y")),
        )

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value is None or value == "":
            return None
        return int(value)


class DouyinActions:
    """封装单台设备上的抖音 Appium 固定动作。"""

    def __init__(
        self,
        *,
        driver: Any,
        locators: LocatorRepository,
        udid: str,
        screenshot_dir: str | Path = "runtime/screenshots",
        package_name: str = "com.ss.android.ugc.aweme",
        wait_timeout_seconds: int = 15,
        task_id: int | str | None = None,
    ) -> None:
        self.driver = driver
        self.locators = locators
        self.udid = udid
        self.screenshot_dir = Path(screenshot_dir)
        self.package_name = package_name
        self.wait_timeout_seconds = wait_timeout_seconds
        self.task_id = task_id

    def with_task_context(self, task_id: int | str | None) -> DouyinActions:
        return DouyinActions(
            driver=self.driver,
            locators=self.locators,
            udid=self.udid,
            screenshot_dir=self.screenshot_dir,
            package_name=self.package_name,
            wait_timeout_seconds=self.wait_timeout_seconds,
            task_id=task_id,
        )

    def open_douyin(self) -> None:
        self._run_step("open_douyin", lambda: self.driver.activate_app(self.package_name))

    def search_keyword(self, keyword: str) -> None:
        def action() -> None:
            self._click("search_button")
            search_input = self._wait_visible("search_input")
            search_input.clear()
            search_input.send_keys(keyword)
            self._press_enter()

        self._run_step("search_keyword", action)

    def enter_doctor_page(self, doctor_name: str | None = None) -> None:
        def action() -> None:
            self._click("user_tab")
            self._click("doctor_page_entry")
            logger.info("entered doctor page: doctor=%s", doctor_name or "-")

        self._run_step("enter_doctor_page", action)

    def open_target_video(self) -> None:
        self._run_step("open_target_video", lambda: self._click("video_entry"))

    def like_video(self) -> None:
        def action() -> None:
            self._click("like_button")
            self._wait_for_page_source_marker(
                markers=("已点赞",),
                label="liked state",
            )

        self._run_step("like_video", action)

    def favorite_video(self) -> None:
        def action() -> None:
            self._click("favorite_button")
            self._wait_for_page_source_marker(
                markers=("取消收藏", "已收藏"),
                label="favorited state",
                required=False,
            )

        self._run_step("favorite_video", action)

    def post_comment(
        self,
        comment_content: str,
        *,
        pre_input_click_wait_seconds: float | None = None,
        focus_wait_seconds: float = 0,
        after_input_wait_seconds: float = 0,
        before_send_wait_seconds: float = 0,
        send_comment: bool = True,
    ) -> None:
        """打开评论面板，输入评论，校验输入结果，并按配置决定是否发送。

        完整自动化流程会走这个方法。当前正式顺序是先打开评论面板，
        再聚焦真实输入框，等待键盘稳定，输入、校验，最后按配置发送。
        """

        def action() -> None:
            # 先打开评论面板，再主动点击真实输入框，等键盘和输入框稳定后，
            # 再进入输入、校验、发送。
            logger.info("post_comment step: click comment button")
            self._click("comment_button")

            logger.info("post_comment step: pre-click comment input")
            comment_input = self._wait_visible("comment_input")
            comment_input.click()

            wait_after_pre_click = (
                random.uniform(2, 5)
                if pre_input_click_wait_seconds is None
                else pre_input_click_wait_seconds
            )
            if wait_after_pre_click > 0:
                logger.info(
                    "post_comment step: wait after pre-click %.2fs",
                    wait_after_pre_click,
                )
                time.sleep(wait_after_pre_click)

            self._input_comment_text_steps(
                comment_content,
                focus_wait_seconds=focus_wait_seconds,
                after_input_wait_seconds=after_input_wait_seconds,
                click_comment_button=False,
            )
            if before_send_wait_seconds > 0:
                logger.info("post_comment step: wait before send %.2fs", before_send_wait_seconds)
                time.sleep(before_send_wait_seconds)
            if not send_comment:
                logger.info("post_comment step: skip send button")
                return
            logger.info("post_comment step: click send button")
            self._click("send_comment_button")

        self._run_step("post_comment", action)

    def input_comment_text_only(
        self,
        comment_content: str,
        *,
        focus_wait_seconds: float = 0,
        after_input_wait_seconds: float = 0,
        click_comment_button: bool = True,
        refocus_input: bool = True,
        verify_after_input: bool = True,
    ) -> None:
        """仅用于调试：只输入评论内容，不点击发送。

        单独测试脚本会调用这个方法，用来确认文本是否真正进入抖音的
        EditText。它会刻意停在点击发送之前，方便把“输入”和“发送”
        分开排查。
        """

        def action() -> None:
            self._input_comment_text_steps(
                comment_content,
                focus_wait_seconds=focus_wait_seconds,
                after_input_wait_seconds=after_input_wait_seconds,
                click_comment_button=click_comment_button,
                refocus_input=refocus_input,
                verify_after_input=verify_after_input,
            )

        self._run_step("input_comment_text_only", action)

    def _input_comment_text_steps(
        self,
        comment_content: str,
        *,
        focus_wait_seconds: float,
        after_input_wait_seconds: float,
        click_comment_button: bool,
        refocus_input: bool = True,
        verify_after_input: bool = True,
    ) -> None:
        # 完整流程从视频播放页开始，因此需要先点击评论按钮打开评论面板。
        # 如果调用方已经打开评论面板，会传 click_comment_button=False，
        # 避免重复打开/关闭评论面板。
        if click_comment_button:
            logger.info("post_comment step: click comment button")
            self._click("comment_button")

        # 等待评论面板里的真实 EditText 出现。必须先让输入框获得焦点，
        # 否则抖音可能仍然只显示占位文案“爱评论的人，运气不会差”，
        # 后续输入会被忽略。
        logger.info("post_comment step: wait comment input")
        comment_input = self._wait_visible("comment_input")
        if refocus_input:
            logger.info("post_comment step: focus comment input")
            comment_input.click()
        else:
            logger.info("post_comment step: skip refocus comment input")

        # 给输入法/键盘一点时间绑定到 EditText。真机上如果刚点击就立刻
        # 输入，成功率不稳定。
        if focus_wait_seconds > 0:
            logger.info("post_comment step: wait after focus %.2fs", focus_wait_seconds)
            time.sleep(focus_wait_seconds)

        # 依次尝试已配置的输入策略。完整流程里长中文评论是最容易不稳定
        # 的部分，所以 _input_text 会记录实际使用了哪种输入方式。
        logger.info("post_comment step: input comment text")
        self._input_text(comment_input, comment_content)

        # 输入后先等待一下，让抖音有时间刷新 UI 层级和 page source。
        if after_input_wait_seconds > 0:
            logger.info("post_comment step: wait after input %.2fs", after_input_wait_seconds)
            time.sleep(after_input_wait_seconds)

        # 输入后重新读取输入框和 page source，确认评论文本已经进入真实 UI。
        # 调试阶段会在输入后停留，不发送评论；这时再次 findElement 容易在
        # 个别设备上卡住 UiAutomator2，因此允许调用方跳过这一步。
        if verify_after_input:
            self._assert_locator_has_text("comment_input", comment_content)
        else:
            logger.info("post_comment step: skip input verification")

    def get_texts(self, locator_name: str, limit: int | None = None) -> list[str]:
        def action() -> list[str]:
            texts: list[str] = []
            errors: list[str] = []
            for elements in self._find_elements_by_locator(locator_name, errors):
                for element in elements:
                    text = (getattr(element, "text", "") or "").strip()
                    if text:
                        texts.append(text)
                        if limit is not None and len(texts) >= limit:
                            return texts
                if texts:
                    return texts
            if errors:
                logger.info(
                    "get_texts fallback exhausted: locator=%s errors=%s",
                    locator_name,
                    errors,
                )
            return texts

        return self._run_step(f"get_texts:{locator_name}", action)

    def click_text_contains(self, locator_name: str, expected_text: str) -> str:
        def action() -> str:
            text = self.try_click_text_contains(locator_name, expected_text)
            if text is not None:
                return text
            raise DouyinLocatorError(
                f"Text not found for '{locator_name}': expected={expected_text}"
            )

        return self._run_step(f"click_text_contains:{locator_name}", action)

    def try_click_text_contains(self, locator_name: str, expected_text: str) -> str | None:
        logger.info(
            "douyin action start: udid=%s step=try_click_text_contains:%s",
            self.udid,
            locator_name,
        )
        errors: list[str] = []
        normalized_expected = self._normalize_text(expected_text)
        for elements in self._find_elements_by_locator(locator_name, errors):
            for element in elements:
                text = (getattr(element, "text", "") or "").strip()
                if normalized_expected and normalized_expected in self._normalize_text(text):
                    element.click()
                    logger.info(
                        "douyin action success: udid=%s step=try_click_text_contains:%s text=%s",
                        self.udid,
                        locator_name,
                        text,
                    )
                    return text
        logger.info(
            "douyin action skipped: udid=%s step=try_click_text_contains:%s expected=%s errors=%s",
            self.udid,
            locator_name,
            expected_text,
            errors,
        )
        return None

    def swipe_up(self, percent: float = 0.65) -> None:
        def action() -> None:
            size = self.driver.get_window_size()
            width = int(size["width"])
            height = int(size["height"])
            start_x = width // 2
            start_y = int(height * 0.82)
            end_y = int(height * max(0.18, 0.82 - percent))
            if hasattr(self.driver, "swipe"):
                self.driver.swipe(start_x, start_y, start_x, end_y, 500)
                return
            if hasattr(self.driver, "execute_script"):
                self.driver.execute_script(
                    "mobile: dragGesture",
                    {
                        "startX": start_x,
                        "startY": start_y,
                        "endX": start_x,
                        "endY": end_y,
                        "speed": 2500,
                    },
                )
                return
            raise DouyinActionError("Driver does not support swipe")

        self._run_step("swipe_up", action)

    def _click(self, locator_name: str) -> None:
        errors: list[str] = []
        for locator in self.locators.get(locator_name):
            try:
                if locator.is_coordinate:
                    self._tap(*locator.coordinate())
                    return
                self._wait_clickable(locator).click()
                return
            except Exception as exc:  # noqa: BLE001 - try next configured strategy.
                errors.append(f"{locator.by}={locator.value or (locator.x, locator.y)}: {exc}")
        raise DouyinLocatorError(f"All locator strategies failed for '{locator_name}': {errors}")

    def _wait_clickable(self, locator: LocatorSpec) -> Any:
        by, value = locator.to_appium()
        return WebDriverWait(self.driver, self.wait_timeout_seconds).until(
            EC.element_to_be_clickable((by, value))
        )

    def _wait_visible(self, locator_name: str) -> Any:
        errors: list[str] = []
        for locator in self.locators.get(locator_name):
            if locator.is_coordinate:
                continue
            try:
                by, value = locator.to_appium()
                return WebDriverWait(self.driver, self.wait_timeout_seconds).until(
                    EC.visibility_of_element_located((by, value))
                )
            except Exception as exc:  # noqa: BLE001 - try next configured strategy.
                errors.append(f"{locator.by}={locator.value}: {exc}")
        raise DouyinLocatorError(f"All locator strategies failed for '{locator_name}': {errors}")

    def _tap(self, x: int, y: int) -> None:
        if hasattr(self.driver, "execute_script"):
            self.driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
            return
        if hasattr(self.driver, "tap"):
            self.driver.tap([(x, y)])
            return
        raise DouyinActionError("Driver does not support coordinate tap")

    def _press_enter(self) -> None:
        if hasattr(self.driver, "press_keycode"):
            self.driver.press_keycode(66)
            return
        if hasattr(self.driver, "execute_script"):
            self.driver.execute_script("mobile: performEditorAction", {"action": "search"})
            return
        raise DouyinActionError("Driver does not support Android enter/search action")

    def _input_text(self, element: Any, text: str) -> None:
        errors: list[str] = []

        # 调用方已经在 _input_comment_text_steps 中聚焦过真实输入框。
        # 这里不再重复 element.click()，避免评论面板打开后再次 click 触发
        # UiAutomator2 长时间等待甚至 instrumentation 崩溃。
        if hasattr(self.driver, "execute_script"):
            try:
                self.driver.execute_script("mobile: type", {"text": text})
                logger.info("input text via mobile: type")
                return
            except Exception as exc:  # noqa: BLE001 - fallback to element input below.
                logger.warning("input text via mobile: type failed: %s", exc)
                errors.append(f"mobile type failed: {exc}")

        try:
            element.send_keys(text)
            logger.info("input text via send_keys")
            return
        except Exception as exc:  # noqa: BLE001 - fallback to other strategies.
            logger.warning("input text via send_keys failed: %s", exc)
            errors.append(f"send_keys failed: {exc}")

        # 有些 Appium 元素暴露 set_value，它比 send_keys 更直接；但 Android
        # EditText 是否支持取决于 App 和 driver，所以这里只作为兜底策略。
        if hasattr(element, "set_value"):
            try:
                element.set_value(text)
                logger.info("input text via set_value")
                return
            except Exception as exc:  # noqa: BLE001 - fallback to clipboard paste.
                logger.warning("input text via set_value failed: %s", exc)
                errors.append(f"set_value failed: {exc}")

        # 最后再尝试剪贴板粘贴。如果后续 Appium/driver 支持这个接口，
        # 它仍然可以作为兜底方案使用。
        if hasattr(self.driver, "set_clipboard_text"):
            try:
                self.driver.set_clipboard_text(text)
                self._paste_from_clipboard()
                logger.info("input text via clipboard paste")
                return
            except Exception as exc:  # noqa: BLE001 - fallback to send_keys.
                logger.warning("input text via clipboard paste failed: %s", exc)
                errors.append(f"clipboard paste failed: {exc}")

        raise DouyinActionError(f"Failed to input text: {errors}")

    def _paste_from_clipboard(self) -> None:
        if hasattr(self.driver, "press_keycode"):
            self.driver.press_keycode(279)
            return
        if hasattr(self.driver, "execute_script"):
            self.driver.execute_script(
                "mobile: shell",
                {"command": "input", "args": ["keyevent", "279"]},
            )
            return
        raise DouyinActionError("Driver does not support clipboard paste")

    def _assert_element_has_text(self, element: Any, expected_text: str) -> None:
        actual_text = self._read_element_text(element)
        if self._normalize_text(expected_text) not in self._normalize_text(actual_text):
            raise DouyinActionError(
                f"评论内容未进入输入框：expected={expected_text!r}, actual={actual_text!r}"
            )
        logger.info("comment input text verified")

    @staticmethod
    def _read_element_text(element: Any) -> str:
        for attribute_name in ("text", "value"):
            try:
                if attribute_name == "text":
                    value = getattr(element, "text", "")
                else:
                    value = element.get_attribute(attribute_name)
                if value:
                    return str(value)
            except Exception:  # noqa: BLE001 - try the next attribute.
                continue
        return ""

    def _assert_locator_has_text(self, locator_name: str, expected_text: str) -> None:
        actual_text = ""
        try:
            # 输入后重新定位输入框。键盘弹出或评论面板重绘后，原 element
            # 可能读到过期状态。
            refreshed_element = self._wait_visible(locator_name)
            actual_text = self._read_element_text(refreshed_element)
        except Exception as exc:  # noqa: BLE001 - page source check below may still work.
            logger.warning("failed to refresh locator text: locator=%s error=%s", locator_name, exc)

        source_contains = False
        try:
            # page source 是第二条校验通道。如果文本已经进入真实 Android
            # 层级，即使 get_attribute("value") 不可靠，Appium 通常也会在
            # source 里暴露出来。
            page_source = getattr(self.driver, "page_source", "") or ""
            source_contains = self._normalize_text(expected_text) in self._normalize_text(
                str(page_source)
            )
        except Exception as exc:  # noqa: BLE001 - fallback to element text.
            logger.warning("failed to read page source for text verification: %s", exc)

        element_contains = self._normalize_text(expected_text) in self._normalize_text(actual_text)
        if not source_contains and not element_contains:
            raise DouyinActionError(
                "评论内容未进入输入框："
                f"expected={expected_text!r}, actual={actual_text!r}, "
                f"sourceContains={source_contains}"
            )
        logger.info(
            "comment input text verified: elementContains=%s sourceContains=%s actual=%r",
            element_contains,
            source_contains,
            actual_text,
        )

    def _wait_for_page_source_marker(
        self,
        *,
        markers: tuple[str, ...],
        label: str,
        timeout_seconds: float = 5,
        required: bool = True,
    ) -> None:
        if not hasattr(self.driver, "page_source"):
            logger.info("%s verification skipped: driver has no page_source", label)
            return

        deadline = time.time() + timeout_seconds
        last_source = ""
        while time.time() < deadline:
            try:
                last_source = str(getattr(self.driver, "page_source", "") or "")
            except Exception as exc:  # noqa: BLE001 - retry until timeout.
                logger.info("failed to read page source for %s: %s", label, exc)
                last_source = ""
            if any(marker in last_source for marker in markers):
                logger.info("%s verified by page source marker: %s", label, markers)
                return
            time.sleep(0.5)

        message = f"{label} not verified by page source markers: {markers}"
        if required:
            raise DouyinActionError(message)
        logger.warning(message)

    def _find_elements_by_locator(self, locator_name: str, errors: list[str]) -> list[list[Any]]:
        groups: list[list[Any]] = []
        for locator in self.locators.get(locator_name):
            if locator.is_coordinate:
                continue
            try:
                by, value = locator.to_appium()
                elements = self.driver.find_elements(by, value)
                if elements:
                    groups.append(elements)
            except Exception as exc:  # noqa: BLE001 - try next configured strategy.
                errors.append(f"{locator.by}={locator.value}: {exc}")
        return groups

    @staticmethod
    def _normalize_text(value: str) -> str:
        return "".join(value.split())

    def _run_step(self, step: str, action: Any) -> Any:
        logger.info("douyin action start: udid=%s step=%s", self.udid, step)
        try:
            result = action()
            logger.info("douyin action success: udid=%s step=%s", self.udid, step)
            return result
        except Exception as exc:
            screenshot_path = self._save_failure_screenshot(step)
            message = (
                f"Douyin action failed: udid={self.udid}, step={step}, "
                f"screenshot={screenshot_path}, error={exc}"
            )
            logger.exception(message)
            if isinstance(exc, DouyinActionError | DouyinLocatorError):
                raise DouyinActionError(message) from exc
            raise DouyinActionError(message) from exc

    def _save_failure_screenshot(self, step: str) -> str:
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_udid = sanitize_filename(self.udid)
        safe_task_id = sanitize_filename(str(self.task_id or "no_task"))
        path = self.screenshot_dir / f"{safe_udid}_{safe_task_id}_{timestamp}.png"
        try:
            self.driver.save_screenshot(str(path))
            return str(path)
        except Exception as exc:  # noqa: BLE001 - screenshot is best effort.
            logger.warning(
                "failed to save screenshot: udid=%s step=%s error=%s", self.udid, step, exc
            )
            return "<screenshot failed>"
