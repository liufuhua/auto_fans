from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from pathlib import Path

from app.api_client import (
    AutomationApiClient,
    AutomationApiError,
    AutomationTimingSettingResult,
    ClaimTaskResult,
    StartTaskResult,
)
from app.appium_driver import AppiumDeviceConfig, AppiumDriverFactory
from app.config import settings
from app.douyin_page_state import (
    DEFAULT_SEARCH_BACK_XPATH,
    DEFAULT_VIDEO_BACK_XPATH,
    build_return_home_locators,
    get_page_source,
    has_link_copied_popup,
    has_search_page,
    has_video_back,
    is_home_page,
    press_android_back,
    safe_click,
)
from app.douyin_search_support import (
    DEFAULT_AUTHOR_XPATH,
    DEFAULT_COMMENT_BUTTON_XPATH,
    DEFAULT_COMMENT_INPUT_XPATH,
    DEFAULT_FAVORITE_XPATH,
    DEFAULT_INPUT_XPATH,
    DEFAULT_LIKE_XPATH,
    DEFAULT_LINK_COPIED_CLOSE_XPATH,
    DEFAULT_SEARCH_BUTTON_XPATH,
    DEFAULT_SEND_COMMENT_XPATH,
    DEFAULT_SUBMIT_XPATH,
    DEFAULT_VIDEO_TAB_XPATH,
    build_result_summary,
    build_search_locators,
    collect_matched_author_elements,
    log_step,
    quit_with_timeout,
    random_seconds,
)
from app.device_manager import BackendDeviceConfig
from app.douyin_actions import DouyinActions, LocatorSpec
from app.task_worker import TaskExecutionResult
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait


LIKE_XPATH = (
    '//android.widget.LinearLayout[contains(@content-desc,"未点赞") '
    'and contains(@content-desc,"喜欢") and contains(@content-desc,"按钮")]'
)
FAVORITE_XPATH = (
    '//android.widget.LinearLayout[contains(@content-desc,"未选中") '
    'and contains(@content-desc,"收藏") and contains(@content-desc,"按钮")]'
)
SHARE_XPATH = (
    '//android.widget.LinearLayout[contains(@content-desc,"分享") '
    'and contains(@content-desc,"按钮")]'
)
SHARE_LINK_XPATH = (
    '//android.view.ViewGroup[@clickable="true" '
    'and .//android.widget.TextView[@text="分享链接"]]'
)
LINK_COPIED_CLOSE_XPATH = (
    '//android.widget.ImageView[@resource-id="com.ss.android.ugc.aweme:id/zjj"]'
)


class SearchResultNotFoundError(RuntimeError):
    """Raised when the target author cannot be found in search results."""

    def __init__(self, message: str, *, active_driver=None) -> None:
        super().__init__(message)
        self.active_driver = active_driver


SEARCH_TAB_WORDS = ("综合", "视频", "用户", "直播", "商品", "地点", "图文", "经验", "问答")
BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass(frozen=True)
class DouyinAppiumExecutorConfig:
    appium_server_url: str = settings.appium_server_url
    package_name: str = settings.douyin_package_name
    app_activity: str = settings.douyin_app_activity
    app: str = settings.douyin_app_path
    wait_timeout_seconds: int = 12
    quit_timeout_seconds: int = 5
    after_open_seconds: float = 2
    return_home_step_wait_seconds: float = 1.5
    return_home_max_back_presses: int = 4
    before_input_min_seconds: float = 3
    before_input_max_seconds: float = 15
    after_input_min_seconds: float = 2
    after_input_max_seconds: float = 5
    after_search_min_seconds: float = 2
    after_search_max_seconds: float = 3
    after_swipe_min_seconds: float = 1
    after_swipe_max_seconds: float = 3
    watch_min_seconds: float = 15
    watch_max_seconds: float = 300
    after_like_min_seconds: float = 3
    after_like_max_seconds: float = 20
    after_favorite_min_seconds: float = 3
    after_favorite_max_seconds: float = 20
    comment_pre_input_min_seconds: float = 2
    comment_pre_input_max_seconds: float = 5
    comment_focus_min_seconds: float = 2
    comment_focus_max_seconds: float = 5
    after_comment_input_min_seconds: float = 5
    after_comment_input_max_seconds: float = 5
    before_send_min_seconds: float = 0
    before_send_max_seconds: float = 0
    douyin_restart_interval_minutes: float = 30
    max_swipes: int = 2
    swipe_percent: float = 0.45
    execute_video_actions_enabled: bool = True
    send_comment_enabled: bool = True
    allow_unverified_home_after_restart: bool = True


@dataclass(frozen=True)
class TapPointRatio:
    x: float
    y: float


@dataclass(frozen=True)
class DeviceTapProfile:
    comment_button: TapPointRatio
    comment_input: TapPointRatio
    active_comment_input: TapPointRatio
    send_button: TapPointRatio
    prefer_adb_active_comment_input: bool = False
    prefer_adb_send_button: bool = False


DEFAULT_DEVICE_MODEL = "huawei_nova_se6"
DEVICE_TAP_PROFILES: dict[str, DeviceTapProfile] = {
    "vivo_y52": DeviceTapProfile(
        comment_button=TapPointRatio(0.92, 0.58),
        comment_input=TapPointRatio(0.32, 0.965),
        active_comment_input=TapPointRatio(0.32, 0.965),
        send_button=TapPointRatio(0.894, 0.574),
        prefer_adb_active_comment_input=True,
        prefer_adb_send_button=True,
    ),
    "huawei_nova_se6": DeviceTapProfile(
        comment_button=TapPointRatio(0.92, 0.58),
        comment_input=TapPointRatio(0.32, 0.965),
        active_comment_input=TapPointRatio(0.32, 0.965),
        send_button=TapPointRatio(0.894, 0.555),
        prefer_adb_active_comment_input=True,
        prefer_adb_send_button=True,
    ),
}


class DouyinAppiumTaskExecutor:
    """TaskWorker executor that runs the real Douyin Appium search/comment flow."""

    def __init__(
        self,
        config: DouyinAppiumExecutorConfig | None = None,
        driver_factory: AppiumDriverFactory | None = None,
    ) -> None:
        self.config = config or DouyinAppiumExecutorConfig()
        self.driver_factory = driver_factory or AppiumDriverFactory(
            self.config.appium_server_url,
            retries=1,
        )
        self._latest_actions: DouyinActions | None = None

    def execute(
        self,
        *,
        task: ClaimTaskResult,
        start_result: StartTaskResult,
        device: BackendDeviceConfig,
        api_client: AutomationApiClient,
    ) -> TaskExecutionResult:
        keyword = task.search_word or task.keyword
        if not keyword:
            raise RuntimeError("领取到的任务缺少关键词")
        if not task.doctor_name:
            raise RuntimeError("领取到的任务缺少医生姓名")
        if not task.comment_content:
            raise RuntimeError("领取到的任务缺少评论内容")

        active_config = self._config_with_backend_timing(api_client)
        args = self._build_args(device, config=active_config)
        search_text = self._build_retry_search_text(
            keyword=keyword,
            doctor_name=task.doctor_name,
            doctor_real_name=task.doctor_real_name,
        )
        target_author = task.doctor_name
        app_path = str(Path(args.app).resolve()) if args.app else None
        appium_device = AppiumDeviceConfig(
            udid=device.udid,
            system_port=device.system_port,
            device_name=device.name,
            appium_server_url=device.appium_server_url,
            app=app_path,
            app_package=args.package_name,
            app_activity=args.app_activity,
        )

        log_step(
            "worker claimed task: "
            f"device={device.name}, resultId={start_result.result_id}, "
            f"doctor={task.doctor_name}, keyword={keyword}, searchText={search_text}, "
            f"doctorRealName={task.doctor_real_name or ''}, "
            f"deviceModel={device.device_model}, "
            f"创建 Appium driver：server={device.appium_server_url or active_config.appium_server_url}"
        )
        log_step("创建 Appium driver")
        managed_driver = self.driver_factory.create(appium_device)
        active_driver = managed_driver.driver
        self._configure_driver(active_driver)
        log_step("Appium driver 创建成功")
        waits: dict[str, float] = {}
        video_link: str | None = None
        try:
            actions = DouyinActions(
                driver=active_driver,
                locators=build_search_locators(args),
                udid=device.udid,
                package_name=args.package_name,
                wait_timeout_seconds=args.wait_timeout_seconds,
                task_id=task.task_item_id or "worker_search_task",
            )
            active_driver = self._ensure_douyin_home_page(
                driver=active_driver,
                actions=actions,
                args=args,
            )

            actions = DouyinActions(
                driver=active_driver,
                locators=build_search_locators(args),
                udid=device.udid,
                package_name=args.package_name,
                wait_timeout_seconds=args.wait_timeout_seconds,
                task_id=task.task_item_id or "worker_search_task",
            )
            try:
                matched_author, active_driver = self._find_with_name_first_search_plan(
                    actions=actions,
                    args=args,
                    doctor_name=target_author,
                    keyword_search_text=keyword,
                    combined_search_text=search_text,
                    waits=waits,
                )
            except SearchResultNotFoundError as exc:
                return TaskExecutionResult.failed(fail_reason=str(exc))
            actions = self._build_actions(
                driver=active_driver,
                args=args,
                task_id="worker_video_task_before_like",
            )
            if not self.config.execute_video_actions_enabled:
                log_step("临时测试模式：视频已打开，停止在点赞之前，不执行结果回传")
                return TaskExecutionResult.no_report()

            like_success, active_driver = self._like_video_and_reconnect(
                actions=actions,
                args=args,
                waits=waits,
            )
            actions = self._build_actions(
                driver=active_driver,
                args=args,
                task_id="worker_video_task_before_favorite",
            )
            favorite_success, active_driver = self._favorite_video_and_reconnect(
                actions=actions,
                args=args,
                waits=waits,
            )
            actions = self._build_actions(
                driver=active_driver,
                args=args,
                task_id="worker_video_task_before_share",
            )
            share_link_success, video_link, active_driver = self._share_video_and_reconnect(
                actions=actions,
                args=args,
            )
            if share_link_success and video_link:
                log_step(f"分享链接已缓存，等待任务完成后随结果上报：{video_link}")
            elif share_link_success:
                log_step("分享链接已点击复制，但读取剪贴板失败，继续执行评论流程")
            else:
                log_step("分享链接未复制成功，继续执行评论流程")
            actions = self._build_actions(
                driver=active_driver,
                args=args,
                task_id="worker_video_task_before_comment",
            )
            active_driver = self._comment_video_and_reconnect(
                actions=actions,
                args=args,
                comment=task.comment_content,
                waits=waits,
                send_comment=self.config.send_comment_enabled,
            )
            if self.config.send_comment_enabled:
                log_step("评论已发送，抖音已强制退出，任务执行成功")
            else:
                log_step("评论已输入但未发送，抖音已强制退出，任务执行成功")
            result_summary = build_result_summary(
                task=task,
                keyword=keyword,
                matched_author=matched_author,
                like_success=like_success,
                favorite_success=favorite_success,
                comment_success=True,
                backend_status="success",
                result_id=start_result.result_id,
                waits=waits,
                video_link=video_link,
            )
            return TaskExecutionResult.success(
                video_link=video_link,
                result_summary=result_summary,
            )
        finally:
            quit_with_timeout(active_driver, args.quit_timeout_seconds)
            self._clear_appium_session(args)

    def _ensure_douyin_home_page(
        self,
        *,
        driver,
        actions: DouyinActions,
        args: argparse.Namespace,
    ):
        log_step("确保抖音已打开")
        actions.open_douyin()
        if args.after_open_seconds > 0:
            time.sleep(args.after_open_seconds)

        log_step("打开抖音后释放 driver，执行 clear_session，再重连获取 page source")
        driver = self._reconnect_driver(args=args, driver=driver)
        source = get_page_source(driver)
        if is_home_page(source):
            log_step("当前已在抖音首页")
            return driver

        log_step("当前不在抖音首页，开始返回首页")
        return_actions = DouyinActions(
            driver=driver,
            locators=build_return_home_locators(args),
            udid=args.udid,
            package_name=args.package_name,
            wait_timeout_seconds=args.wait_timeout_seconds,
            task_id="return_home_preflight",
        )

        if has_link_copied_popup(source):
            if safe_click(return_actions, "link_copied_close_button", "关闭链接复制成功弹窗"):
                time.sleep(args.return_home_step_wait_seconds)
                source = get_page_source(driver)
                if is_home_page(source):
                    log_step("关闭链接复制成功弹窗后已回到首页")
                    return driver

        if has_video_back(source):
            if safe_click(return_actions, "video_back_button", "退出视频页，返回搜索页"):
                time.sleep(args.return_home_step_wait_seconds)
                source = get_page_source(driver)
                if is_home_page(source):
                    log_step("退出视频页后已回到首页")
                    return driver

        if has_search_page(source):
            if safe_click(return_actions, "search_back_button", "退出搜索页"):
                time.sleep(args.return_home_step_wait_seconds)
                source = get_page_source(driver)
                if is_home_page(source):
                    log_step("退出搜索页后已回到首页")
                    return driver

        for index in range(1, args.return_home_max_back_presses + 1):
            if is_home_page(source):
                log_step("已回到抖音首页")
                return driver
            press_android_back(driver, index)
            time.sleep(args.return_home_step_wait_seconds)
            source = get_page_source(driver)

        if is_home_page(source):
            log_step("已回到抖音首页")
            return driver

        log_step("常规返回未能回到首页，使用 adb launcher 重启抖音兜底")
        driver = self._restart_douyin_from_launcher(args=args, driver=driver)
        source = get_page_source(driver)
        if is_home_page(source):
            log_step("Douyin restarted from launcher and is now on home page")
            return driver

        if args.allow_unverified_home_after_restart:
            log_step(
                "Douyin home page was not recognized after restart/back fallback; "
                "continue with direct search-entry tap path"
            )
            return driver

        quit_with_timeout(driver, args.quit_timeout_seconds)
        raise RuntimeError("执行任务前未能识别到抖音首页，请手动观察当前页面")

    def _restart_douyin_from_launcher(self, *, args: argparse.Namespace, driver):
        log_step("Restart Douyin via adb launcher before Appium back fallback")
        commands = [
            ["adb", "-s", args.udid, "shell", "am", "force-stop", args.package_name],
            ["adb", "-s", args.udid, "shell", "input", "keyevent", "HOME"],
            [
                "adb",
                "-s",
                args.udid,
                "shell",
                "monkey",
                "-p",
                args.package_name,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
        ]
        for command in commands:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
            if result.stdout.strip():
                log_step(result.stdout.strip())
            if result.stderr.strip():
                log_step(result.stderr.strip())
        time.sleep(max(3, args.after_open_seconds))
        return self._reconnect_driver(args=args, driver=driver)

    def _reconnect_driver(self, *, args: argparse.Namespace, driver):
        quit_with_timeout(driver, args.quit_timeout_seconds)
        self._clear_appium_session(args)
        managed_driver = self._create_driver_from_args(args)
        return managed_driver.driver

    @staticmethod
    def _build_retry_search_text(
        *,
        keyword: str,
        doctor_name: str,
        doctor_real_name: str | None,
    ) -> str:
        real_name = (doctor_real_name or "").strip()
        search_name = real_name or doctor_name
        return f"{keyword} {search_name}".strip()

    def _create_driver_from_args(self, args: argparse.Namespace):
        app_path = str(Path(args.app).resolve()) if args.app else None
        appium_device = AppiumDeviceConfig(
            udid=args.udid,
            system_port=args.system_port,
            device_name=args.device_name,
            appium_server_url=args.appium_server_url,
            app=app_path,
            app_package=args.package_name,
            app_activity=args.app_activity,
        )
        log_step("重新创建 Appium driver")
        managed_driver = self.driver_factory.create(appium_device)
        self._configure_driver(managed_driver.driver)
        log_step("Appium driver 重连成功")
        return managed_driver

    def _configure_driver(self, driver) -> None:
        try:
            driver.implicitly_wait(0)
            driver.update_settings(
                {
                    "waitForIdleTimeout": 0,
                    "waitForSelectorTimeout": 3000,
                }
            )
            log_step("UiAutomator2 settings 已更新：waitForIdleTimeout=0")
        except Exception as exc:  # noqa: BLE001 - settings are best effort.
            log_step(f"UiAutomator2 settings 更新失败，继续执行：{type(exc).__name__}: {exc}")

    def _clear_appium_session(self, args: argparse.Namespace) -> None:
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "clear_session.sh"
        command = self._shell_script_command(script_path, args.udid, str(args.system_port))
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        if stdout.strip():
            log_step(stdout.strip())
        if stderr.strip():
            log_step(stderr.strip())

    @staticmethod
    def _shell_script_command(
        script_path: Path,
        *args: str,
        is_windows: bool | None = None,
    ) -> list[str]:
        if is_windows is None:
            is_windows = os.name == "nt"
        if not is_windows:
            return [str(script_path), *args]

        bash_path = None
        for candidate in (
            Path("C:/Program Files/Git/usr/bin/bash.exe"),
            Path("C:/Program Files/Git/bin/bash.exe"),
            Path("C:/msys64/usr/bin/bash.exe"),
        ):
            if candidate.exists():
                bash_path = str(candidate)
                break
        bash_path = bash_path or shutil.which("bash")
        if bash_path is None:
            raise RuntimeError(
                "Windows 环境执行 clear_session.sh 需要 Git Bash 或 MSYS2 bash，请先安装或加入 PATH"
            )

        script = shlex.quote(DouyinAppiumTaskExecutor._to_bash_path(script_path))
        script_args = " ".join(shlex.quote(arg) for arg in args)
        return [bash_path, "-lc", f"{script} {script_args}".strip()]

    @staticmethod
    def _to_bash_path(path: Path) -> str:
        raw = str(path)
        if len(raw) >= 3 and raw[1:3] == ":\\":
            drive = raw[0].lower()
            return f"/{drive}/{raw[3:].replace(chr(92), '/')}"
        return raw.replace("\\", "/")

    def _force_stop_douyin(self, args: argparse.Namespace) -> None:
        log_step(f"强制退出抖音：package={args.package_name}")
        result = subprocess.run(
            ["adb", "-s", args.udid, "shell", "am", "force-stop", args.package_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.stdout.strip():
            log_step(result.stdout.strip())
        if result.stderr.strip():
            log_step(result.stderr.strip())
        if result.returncode != 0:
            raise RuntimeError(f"强制退出抖音失败：returnCode={result.returncode}")
        log_step("抖音已强制退出")
        restart_interval_seconds = max(0, float(args.douyin_restart_interval_minutes) * 60)
        if restart_interval_seconds > 0:
            log_step(
                "等待抖音重启间隔："
                f"{args.douyin_restart_interval_minutes:g} 分钟"
            )
            time.sleep(restart_interval_seconds)

    def _click_home_search_entry_and_reconnect(
        self,
        *,
        actions: DouyinActions,
        args: argparse.Namespace,
        waits: dict[str, float],
    ):
        log_step("点击首页搜索入口")
        self._click_home_search_entry(actions.driver)
        log_step("首页搜索入口已点击")

        waits["before_input"] = random_seconds(
            args.before_input_min_seconds,
            args.before_input_max_seconds,
            "before input",
        )
        time.sleep(waits["before_input"])

        log_step("搜索入口点击后释放 driver，执行 clear_session，再重连等待输入框")
        return self._reconnect_driver(args=args, driver=actions.driver)

    def _input_search_text_submit_and_reconnect(
        self,
        *,
        actions: DouyinActions,
        args: argparse.Namespace,
        search_text: str,
        waits: dict[str, float],
    ):
        search_input = self._wait_search_input(actions=actions, args=args)
        log_step(f"搜索输入框已出现：rect={search_input.rect}")
        self._input_search_text(actions.driver, search_input, search_text)

        waits["after_input"] = random_seconds(
            args.after_input_min_seconds,
            args.after_input_max_seconds,
            "after input",
        )
        time.sleep(waits["after_input"])
        self._submit_search(actions.driver)
        log_step(f"搜索已提交：{search_text}")

        waits["after_search"] = random_seconds(
            args.after_search_min_seconds,
            args.after_search_max_seconds,
            "after search",
        )
        time.sleep(waits["after_search"])

        log_step("搜索提交后释放 driver，执行 clear_session，再重连读取搜索结果")
        return self._reconnect_driver(args=args, driver=actions.driver)

    def _wait_search_input(self, *, actions: DouyinActions, args: argparse.Namespace):
        try:
            return actions._wait_visible("search_input")
        except Exception as exc:
            if self._device_model(args) != "huawei_nova_se6":
                raise
            log_step(
                "华为搜索输入框主定位失败，开始使用机型兜底："
                f"{type(exc).__name__}: {exc}"
            )
            return self._wait_huawei_search_input(actions=actions, args=args)

    def _wait_huawei_search_input(self, *, actions: DouyinActions, args: argparse.Namespace):
        driver = actions.driver
        self._log_search_page_candidates(driver)
        for label, tap_ratio in (
            ("顶部搜索框中部", (0.50, 0.075)),
            ("顶部搜索入口右侧", (0.925, 0.082)),
        ):
            element = self._find_editable_search_input(driver)
            if element is not None:
                return element
            self._tap_by_ratio(driver, tap_ratio[0], tap_ratio[1], f"华为兜底点击{label}")
            time.sleep(1.2)
            self._log_search_page_candidates(driver)

        element = self._find_editable_search_input(driver)
        if element is not None:
            return element
        return actions._wait_visible("search_input")

    def _find_editable_search_input(self, driver):
        selectors = [
            (AppiumBy.ID, "com.ss.android.ugc.aweme:id/et_search_kw"),
            (AppiumBy.XPATH, '//android.widget.EditText[@clickable="true" or @enabled="true"]'),
            (
                AppiumBy.ANDROID_UIAUTOMATOR,
                'new UiSelector().className("android.widget.EditText").enabled(true)',
            ),
            (
                AppiumBy.XPATH,
                '//*[contains(@text,"搜索") or contains(@content-desc,"搜索")]',
            ),
        ]
        for by, value in selectors:
            try:
                elements = driver.find_elements(by, value)
            except Exception as exc:  # noqa: BLE001 - try next selector.
                log_step(f"华为搜索输入框兜底 selector 失败：{by}={value}；{type(exc).__name__}: {exc}")
                continue
            for element in elements:
                try:
                    if element.is_displayed():
                        log_step(
                            "华为搜索输入框兜底命中："
                            f"by={by} value={value} rect={element.rect}"
                        )
                        return element
                except Exception:
                    continue
        return None

    def _log_search_page_candidates(self, driver) -> None:
        try:
            source = driver.page_source
        except Exception as exc:  # noqa: BLE001 - best effort diagnostics.
            log_step(f"华为搜索页 page_source 获取失败：{type(exc).__name__}: {exc}")
            return
        try:
            root = ET.fromstring(source)
        except Exception as exc:  # noqa: BLE001 - source may be partial.
            log_step(f"华为搜索页 page_source 解析失败：{type(exc).__name__}: {exc}")
            return

        rows: list[str] = []
        for node in root.iter():
            class_name = node.attrib.get("class", "")
            text = node.attrib.get("text", "")
            desc = node.attrib.get("content-desc", "")
            resource_id = node.attrib.get("resource-id", "")
            if (
                class_name == "android.widget.EditText"
                or "搜索" in text
                or "搜索" in desc
                or "search" in resource_id.lower()
                or "et_search" in resource_id
            ):
                rows.append(
                    "class={class_name} text={text!r} desc={desc!r} "
                    "id={resource_id!r} bounds={bounds}".format(
                        class_name=class_name,
                        text=text,
                        desc=desc,
                        resource_id=resource_id,
                        bounds=node.attrib.get("bounds", ""),
                    )
                )
            if len(rows) >= 12:
                break
        if rows:
            log_step("华为搜索页候选节点：\n" + "\n".join(rows))
        else:
            log_step("华为搜索页未发现搜索相关节点或 EditText")

    def _tap_by_ratio(self, driver, x_ratio: float, y_ratio: float, label: str) -> None:
        size = driver.get_window_size()
        x = int(size["width"] * x_ratio)
        y = int(size["height"] * y_ratio)
        driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
        log_step(f"{label}：ratio=({x_ratio:.3f},{y_ratio:.3f}) size={size} point=({x},{y})")

    def _search_and_open_matching_video(
        self,
        *,
        actions: DouyinActions,
        args: argparse.Namespace,
        search_text: str,
        target_author: str,
        waits: dict[str, float],
        force_stop_on_not_found: bool = True,
    ):
        active_driver = self._click_home_search_entry_and_reconnect(
            actions=actions,
            args=args,
            waits=waits,
        )
        actions = self._build_actions(
            driver=active_driver,
            args=args,
            task_id="worker_search_task_after_search_click",
        )
        active_driver = self._input_search_text_submit_and_reconnect(
            actions=actions,
            args=args,
            search_text=search_text,
            waits=waits,
        )
        actions = self._build_actions(
            driver=active_driver,
            args=args,
            task_id="worker_search_task_after_submit",
        )
        return self._find_and_open_matching_video(
            actions=actions,
            args=args,
            target_author=target_author,
            force_stop_on_not_found=force_stop_on_not_found,
        )

    def _find_with_name_first_search_plan(
        self,
        *,
        actions: DouyinActions,
        args: argparse.Namespace,
        doctor_name: str,
        keyword_search_text: str,
        combined_search_text: str,
        waits: dict[str, float],
    ):
        log_step(f"关键词优先搜索：先使用关键词搜索：{keyword_search_text}，匹配医生昵称：{doctor_name}")
        name_only_error: SearchResultNotFoundError | None = None
        try:
            return self._search_and_open_matching_video(
                actions=actions,
                args=args,
                search_text=keyword_search_text,
                target_author=doctor_name,
                waits=waits,
                force_stop_on_not_found=False,
            )
        except SearchResultNotFoundError as name_only_error:
            captured_error = name_only_error
            log_step(
                "关键词搜索未找到符合要求的视频，准备回到首页后使用关键词+姓名重试："
                f"{combined_search_text}；nameOnlyError={name_only_error}"
            )

        latest_driver = getattr(captured_error, "active_driver", None) or actions.driver
        latest_actions = self._build_actions(
            driver=latest_driver,
            args=args,
            task_id="worker_search_task_before_retry_home",
        )
        active_driver = self._ensure_douyin_home_page(
            driver=latest_driver,
            actions=latest_actions,
            args=args,
        )
        retry_actions = self._build_actions(
            driver=active_driver,
            args=args,
            task_id="worker_search_task_retry_combined",
        )
        log_step(f"关键词+姓名搜索重试：{combined_search_text}")
        return self._search_and_open_matching_video(
            actions=retry_actions,
            args=args,
            search_text=combined_search_text,
            target_author=doctor_name,
            waits=waits,
        )

    def _find_and_open_matching_video(
        self,
        *,
        actions: DouyinActions,
        args: argparse.Namespace,
        target_author: str,
        force_stop_on_not_found: bool = True,
    ):
        driver = actions.driver
        try:
            result, driver = self._scan_search_result_tab_for_author(
                actions=actions,
                args=args,
                target_author=target_author,
                tab_label="当前搜索结果页",
                task_id_prefix="worker_search_task_after_result_swipe",
            )
            if result is not None:
                return result, driver

            log_step("当前搜索结果页连续 3 次未找到目标作者，切换到“视频”Tab 后继续查找")
            actions = self._build_actions(
                driver=driver,
                args=args,
                task_id="worker_search_task_before_video_tab",
            )
            self._click_search_tab_by_label(actions.driver, "视频")
            log_step("视频 Tab 已点击，等待 2 秒后重连读取视频结果")
            time.sleep(2)
            driver = self._reconnect_driver(args=args, driver=driver)
            actions = self._build_actions(
                driver=driver,
                args=args,
                task_id="worker_search_task_after_video_tab",
            )
            result, driver = self._scan_search_result_tab_for_author(
                actions=actions,
                args=args,
                target_author=target_author,
                tab_label="视频 Tab",
                task_id_prefix="worker_search_task_after_video_tab_swipe",
            )
            if result is not None:
                return result, driver

            fail_reason = f"搜索结果未找到目标账号：{target_author}"
            if force_stop_on_not_found:
                log_step(f"{fail_reason}，强制退出抖音并结束任务")
                self._force_stop_douyin(args)
            else:
                log_step(f"{fail_reason}，保留会话并交给下一搜索方案重试")
            raise SearchResultNotFoundError(fail_reason, active_driver=driver)
        except SearchResultNotFoundError:
            if force_stop_on_not_found:
                quit_with_timeout(driver, args.quit_timeout_seconds)
            raise
        except Exception:
            quit_with_timeout(driver, args.quit_timeout_seconds)
            raise

    def _scan_search_result_tab_for_author(
        self,
        *,
        actions: DouyinActions,
        args: argparse.Namespace,
        target_author: str,
        tab_label: str,
        task_id_prefix: str,
    ):
        driver = actions.driver
        for attempt in range(args.max_swipes + 1):
            log_step(f"{tab_label}：读取搜索结果作者列表：第 {attempt + 1} 次")
            visible_authors = actions.get_texts("video_author_name")
            log_step(f"{tab_label}：当前可见作者：{visible_authors}")
            log_step(f"{tab_label}：匹配目标作者：{target_author}")

            matched_items = collect_matched_author_elements(actions, target_author=target_author)
            for author_text, liked, like_desc, element in matched_items:
                if liked:
                    log_step(f"{tab_label}：跳过已点赞视频：{author_text}，likeDesc={like_desc!r}")
                    continue
                log_step(f"{tab_label}：找到未点赞目标作者并打开视频：{author_text}，likeDesc={like_desc!r}")
                element.click()
                log_step(f"临时测试模式：已打开目标作者视频，停止后续视频动作：{author_text}")
                return author_text, driver

            if matched_items:
                log_step(f"{tab_label}：当前页命中目标作者，但全部已点赞：{target_author}")
            else:
                log_step(f"{tab_label}：当前页未找到目标作者：{target_author}")
            if attempt >= args.max_swipes:
                break

            log_step(f"{tab_label}：执行手指向上滑屏幕，翻到下面内容：percent={args.swipe_percent:.2f}")
            actions.swipe_up(percent=args.swipe_percent)
            log_step(f"{tab_label}：翻页后等待 2 秒，再重连读取新页面")
            time.sleep(2)
            driver = self._reconnect_driver(args=args, driver=driver)
            actions = self._build_actions(
                driver=driver,
                args=args,
                task_id=f"{task_id_prefix}_{attempt + 1}",
            )

        return None, driver

    def _like_video_and_reconnect(
        self,
        *,
        actions: DouyinActions,
        args: argparse.Namespace,
        waits: dict[str, float],
    ):
        log_step("进入视频页，开始观看")
        waits["watch_video"] = random_seconds(
            args.watch_min_seconds,
            args.watch_max_seconds,
            "watch video",
        )
        time.sleep(waits["watch_video"])

        log_step("观看结束后释放 driver，执行 clear_session，再重连查找点赞按钮")
        driver = self._reconnect_driver(args=args, driver=actions.driver)
        log_step("开始点赞")
        like_done = self._click_optional_video_action(
            driver,
            xpath=LIKE_XPATH,
            label="点赞按钮",
        )
        log_step(f"点赞结果={'已点击' if like_done else '跳过'}")
        waits["after_like"] = random_seconds(
            args.after_like_min_seconds,
            args.after_like_max_seconds,
            "after like",
        )
        time.sleep(waits["after_like"])

        log_step("点赞阶段完成，释放 driver，执行 clear_session，再重连")
        return like_done, self._reconnect_driver(args=args, driver=driver)

    def _favorite_video_and_reconnect(
        self,
        *,
        actions: DouyinActions,
        args: argparse.Namespace,
        waits: dict[str, float],
    ):
        log_step("开始收藏")
        favorite_done = self._click_optional_video_action(
            actions.driver,
            xpath=FAVORITE_XPATH,
            label="收藏按钮",
        )
        log_step(f"收藏结果={'已点击' if favorite_done else '跳过'}")
        waits["after_favorite"] = random_seconds(
            args.after_favorite_min_seconds,
            args.after_favorite_max_seconds,
            "after favorite",
        )
        time.sleep(waits["after_favorite"])

        log_step("收藏阶段完成，释放 driver，执行 clear_session，再重连")
        return favorite_done, self._reconnect_driver(args=args, driver=actions.driver)

    def _share_video_and_reconnect(
        self,
        *,
        actions: DouyinActions,
        args: argparse.Namespace,
    ):
        log_step("开始点击分享")
        share_done = self._click_optional_video_action(
            actions.driver,
            xpath=SHARE_XPATH,
            label="分享按钮",
        )
        log_step(f"分享结果={'已点击' if share_done else '跳过'}")
        if not share_done:
            log_step("分享按钮未点击，释放 driver，执行 clear_session，再重连")
            return False, None, self._reconnect_driver(args=args, driver=actions.driver)

        log_step("等待分享弹窗出现")
        time.sleep(1)
        link_done = self._click_optional_video_action(
            actions.driver,
            xpath=SHARE_LINK_XPATH,
            label="分享链接按钮",
            wait_seconds=2,
        )
        if not link_done:
            log_step("当前可见区域未找到分享链接，向左滑动底部分享功能栏")
            self._swipe_share_panel_left_by_adb(args)
            time.sleep(1)
            link_done = self._click_optional_video_action(
                actions.driver,
                xpath=SHARE_LINK_XPATH,
                label="分享链接按钮",
                wait_seconds=4,
            )
        if not link_done:
            log_step("分享链接按钮未通过 XPath 找到，使用真机坐标兜底点击")
            self._tap_share_link_by_adb(args)
            link_done = True
        log_step(f"分享链接结果={'已点击' if link_done else '跳过'}")
        time.sleep(3)
        video_link = (
            self._read_copied_video_link(driver=actions.driver, args=args) if link_done else None
        )
        self._close_link_copied_popup(actions=actions, args=args)

        log_step("分享阶段完成，释放 driver，执行 clear_session，再重连")
        return link_done, video_link, self._reconnect_driver(args=args, driver=actions.driver)

    def _read_copied_video_link(
        self,
        *,
        driver,
        args: argparse.Namespace,
    ) -> str | None:
        try:
            clipboard_text = str(driver.get_clipboard_text() or "").strip()
            video_link = self._extract_video_link_from_clipboard(clipboard_text)
            if video_link:
                log_step(f"读取剪贴板分享链接成功：{video_link}")
                return video_link
        except Exception as exc:  # noqa: BLE001 - link capture should not fail the task.
            log_step(f"读取剪贴板分享链接失败，尝试 ADB 兜底：{type(exc).__name__}: {exc}")

        try:
            clipboard_text = self._adb_shell(
                args=args,
                shell_args=["cmd", "clipboard", "get"],
                capture=True,
            ).strip()
            if "No shell command implementation" not in clipboard_text:
                video_link = self._extract_video_link_from_clipboard(clipboard_text)
                if video_link:
                    log_step(f"ADB 读取剪贴板分享链接成功：{video_link}")
                    return video_link
        except Exception as exc:  # noqa: BLE001 - many devices do not expose clipboard via shell.
            log_step(f"ADB 读取剪贴板分享链接失败，跳过链接上报：{type(exc).__name__}: {exc}")

        return None

    @staticmethod
    def _extract_video_link_from_clipboard(clipboard_text: str) -> str | None:
        text = clipboard_text.strip()
        if not text:
            return None
        urls = [url.rstrip("，。,.、)") for url in re.findall(r"https?://[^\s]+", text)]
        if not urls:
            return None
        for url in urls:
            if "douyin" in url.lower():
                return url
        return urls[0]

    def _close_link_copied_popup(
        self,
        *,
        actions: DouyinActions,
        args: argparse.Namespace,
    ) -> bool:
        log_step("开始关闭链接复制成功弹窗")
        close_done = self._click_optional_video_action(
            actions.driver,
            xpath=LINK_COPIED_CLOSE_XPATH,
            label="链接复制成功弹窗关闭按钮",
            wait_seconds=3,
        )
        if not close_done:
            log_step("链接复制成功弹窗关闭按钮未通过 XPath 找到，使用真机坐标兜底点击")
            self._tap_screen_center_by_adb(args, "链接复制成功弹窗通用居中关闭兜底")
            # time.sleep(0.5)
            # self._tap_link_copied_close_by_adb(args)
            close_done = True
        log_step(f"链接复制成功弹窗关闭结果={'已点击' if close_done else '跳过'}")
        time.sleep(0.5)
        return close_done

    def _comment_video_and_reconnect(
        self,
        *,
        actions: DouyinActions,
        args: argparse.Namespace,
        comment: str,
        waits: dict[str, float],
        send_comment: bool,
    ):
        focus_wait_seconds = random_seconds(
            args.comment_focus_min_seconds,
            args.comment_focus_max_seconds,
            "after comment input focused",
        )
        waits["comment_focus"] = focus_wait_seconds
        after_input_wait_seconds = random_seconds(
            args.after_comment_input_min_seconds,
            args.after_comment_input_max_seconds,
            "after comment text input",
        )
        waits["after_comment_input"] = after_input_wait_seconds
        before_send_wait_seconds = random_seconds(
            args.before_send_min_seconds,
            args.before_send_max_seconds,
            "before send comment",
        )
        waits["before_send_comment"] = before_send_wait_seconds

        log_step("开始评论")
        log_step("评论步骤 1/7：点击评论按钮")
        log_step("评论步骤 2/7：预点击输入框，等待键盘和输入框稳定")
        log_step(f"评论步骤 3/7：再次聚焦输入框，等待 {focus_wait_seconds:.2f}s")
        log_step("评论步骤 4/7：重连后再次聚焦输入框，再使用 mobile: type 优先输入评论内容")
        log_step(f"评论步骤 5/7：输入后等待 {after_input_wait_seconds:.2f}s，让输入状态稳定")
        log_step(f"评论步骤 6/7：发送前等待 {before_send_wait_seconds:.2f}s")
        if send_comment:
            log_step("评论步骤 7/7：点击发送按钮")
        else:
            log_step("评论步骤 7/7：临时跳过发送按钮")

        log_step("评论步骤 1/7：点击评论按钮")
        try:
            self._tap_comment_button_by_adb(actions=actions, args=args)
        except Exception as exc:  # noqa: BLE001 - keep the failure reason actionable.
            self._force_stop_douyin(args)
            raise RuntimeError(
                "未找到视频页评论按钮，可能当前打开的是图文/文章页面，无法进入评论流程："
                f"{exc}"
            ) from exc
        log_step("评论步骤 2/7：预点击输入框，等待键盘和输入框稳定")
        # self._tap_comment_input_by_adb(args, "comment input pre-focus")
        pre_input_wait_seconds = random_seconds(
            args.comment_pre_input_min_seconds,
            args.comment_pre_input_max_seconds,
            "after comment pre input click",
        )
        waits["comment_pre_input_click"] = pre_input_wait_seconds
        time.sleep(pre_input_wait_seconds)

        log_step("输入评论内容前释放 driver，执行 clear_session，再重连")
        driver = self._reconnect_driver(args=args, driver=actions.driver)
        actions = self._build_actions(
            driver=driver,
            args=args,
            task_id="worker_video_task_post_comment",
        )
        self._tap_active_comment_input_by_adb(args, "comment input focus after reconnect")
        if focus_wait_seconds > 0:
            time.sleep(focus_wait_seconds)
        self._input_focused_comment_text(
            actions=actions,
            comment=comment,
            after_input_wait_seconds=after_input_wait_seconds,
        )
        if send_comment:
            log_step("发送前再次点击评论输入框，恢复键盘和发送按钮")
            self._tap_active_comment_input_by_adb(args, "comment input focus before send")
            time.sleep(1)
            log_step("发送前输入框已聚焦，释放 driver 并重连，避免 UiAutomator2 旧状态卡住发送按钮")
            driver = self._reconnect_driver(args=args, driver=actions.driver)
            actions = self._build_actions(
                driver=driver,
                args=args,
                task_id="worker_video_task_before_send_comment",
            )
            if before_send_wait_seconds > 0:
                time.sleep(before_send_wait_seconds)
            try:
                self._tap_comment_send_by_adb(args)
            except Exception as exc:  # noqa: BLE001 - last resort for devices with slow UIA.
                log_step(f"评论发送点击失败，改用 Appium 发送按钮兜底：{type(exc).__name__}: {exc}")
                actions._click("send_comment_button")
            log_step(f"评论发送成功：{comment}")
            log_step("评论发送后等待 30 秒，确保发送请求已发出")
            time.sleep(30)
            self._force_stop_douyin(args)
            return driver
        else:
            log_step(f"评论已输入但未发送：{comment}")
            log_step("未发送评论，等待 3 秒后强制退出抖音")
            time.sleep(3)
            self._force_stop_douyin(args)
            return driver

    def _input_focused_comment_text(
        self,
        *,
        actions: DouyinActions,
        comment: str,
        after_input_wait_seconds: float,
    ) -> None:
        log_step("评论输入：使用已聚焦输入框直接输入，避免再次查找 EditText")
        started_at = time.monotonic()
        try:
            actions.driver.execute_script("mobile: type", {"text": comment})
            log_step(f"COMMENT_METRIC input_text method=mobile_type outcome=success elapsed={time.monotonic() - started_at:.2f}s")
            log_step("评论输入：mobile: type 完成")
        except Exception as exc:  # noqa: BLE001 - clipboard paste is a useful fallback.
            log_step(
                "COMMENT_METRIC input_text method=mobile_type outcome=error "
                f"elapsed={time.monotonic() - started_at:.2f}s error={type(exc).__name__}"
            )
            log_step(f"评论输入：mobile: type 失败，改用剪贴板粘贴：{type(exc).__name__}: {exc}")
            fallback_started_at = time.monotonic()
            actions.driver.set_clipboard_text(comment)
            self._adb_shell(args=None, udid=actions.udid, shell_args=["input", "keyevent", "279"])
            log_step(f"COMMENT_METRIC input_text method=clipboard_paste outcome=success elapsed={time.monotonic() - fallback_started_at:.2f}s")
            log_step("评论输入：剪贴板粘贴完成")
        if after_input_wait_seconds > 0:
            time.sleep(after_input_wait_seconds)

    def _tap_comment_input_by_adb(self, args: argparse.Namespace, label: str) -> None:
        self._tap_profile_point(
            args,
            point=self._device_tap_profile(args).comment_input,
            label=f"ADB 点击评论输入框：{label}",
        )

    def _tap_comment_button_by_adb(self, *, actions: DouyinActions, args: argparse.Namespace) -> None:
        try:
            log_step("优先使用 Appium 定位评论按钮")
            actions._click("comment_button")
            log_step("Appium 评论按钮点击成功")
            return
        except Exception as exc:  # noqa: BLE001 - stale UiAutomator nodes need coordinate fallback.
            log_step(
                "Appium 评论按钮点击失败，改用 ADB 坐标兜底："
                f"{type(exc).__name__}: {exc}"
            )

        self._tap_profile_point(
            args,
            point=self._device_tap_profile(args).comment_button,
            label="ADB 点击评论按钮兜底",
        )

    def _tap_active_comment_input_by_adb(self, args: argparse.Namespace, label: str) -> None:
        profile = self._device_tap_profile(args)
        if profile.prefer_adb_active_comment_input:
            started_at = time.monotonic()
            log_step(
                "当前设备型号配置为优先 ADB 点击已展开评论输入框："
                f"deviceModel={self._device_model(args)} label={label}"
            )
            self._tap_profile_point(
                args,
                point=profile.active_comment_input,
                label=f"ADB 点击已展开评论输入框：{label}",
            )
            log_step(
                "COMMENT_METRIC active_comment_input method=adb_preferred outcome=success "
                f"label={label} deviceModel={self._device_model(args)} elapsed={time.monotonic() - started_at:.2f}s"
            )
            return

        if self._latest_actions is not None:
            started_at = time.monotonic()
            try:
                log_step(f"优先使用 Appium 定位已展开评论输入框：{label}")
                self._latest_actions._click("comment_input")
                log_step(
                    "COMMENT_METRIC active_comment_input method=appium outcome=success "
                    f"label={label} deviceModel={self._device_model(args)} elapsed={time.monotonic() - started_at:.2f}s"
                )
                log_step(f"Appium 已展开评论输入框点击成功：{label}")
                return
            except Exception as exc:  # noqa: BLE001 - ADB coordinate fallback supports variant UIs.
                log_step(
                    "COMMENT_METRIC active_comment_input method=appium outcome=error "
                    f"label={label} deviceModel={self._device_model(args)} "
                    f"elapsed={time.monotonic() - started_at:.2f}s error={type(exc).__name__}"
                )
                log_step(
                    "Appium 已展开评论输入框点击失败，改用 ADB 坐标兜底："
                    f"{type(exc).__name__}: {exc}"
                )

        fallback_started_at = time.monotonic()
        self._tap_profile_point(
            args,
            point=profile.active_comment_input,
            label=f"ADB 点击已展开评论输入框：{label}",
        )
        log_step(
            "COMMENT_METRIC active_comment_input method=adb_fallback outcome=success "
            f"label={label} deviceModel={self._device_model(args)} elapsed={time.monotonic() - fallback_started_at:.2f}s"
        )

    def _tap_comment_send_by_adb(self, args: argparse.Namespace) -> None:
        profile = self._device_tap_profile(args)
        if profile.prefer_adb_send_button:
            started_at = time.monotonic()
            log_step(
                "当前设备型号配置为优先 ADB 点击评论发送按钮："
                f"deviceModel={self._device_model(args)}"
            )
            self._tap_profile_point(
                args,
                point=profile.send_button,
                label="ADB 点击评论发送",
            )
            log_step(
                "COMMENT_METRIC send_comment method=adb_preferred outcome=success "
                f"deviceModel={self._device_model(args)} elapsed={time.monotonic() - started_at:.2f}s"
            )
            return

        if self._latest_actions is not None:
            started_at = time.monotonic()
            try:
                log_step("优先使用 Appium 定位发送按钮")
                self._latest_actions._click("send_comment_button")
                log_step(
                    "COMMENT_METRIC send_comment method=appium outcome=success "
                    f"deviceModel={self._device_model(args)} elapsed={time.monotonic() - started_at:.2f}s"
                )
                log_step("Appium 发送按钮点击成功")
                return
            except Exception as exc:  # noqa: BLE001 - ADB coordinate fallback supports variant UIs.
                log_step(
                    "COMMENT_METRIC send_comment method=appium outcome=error "
                    f"deviceModel={self._device_model(args)} elapsed={time.monotonic() - started_at:.2f}s "
                    f"error={type(exc).__name__}"
                )
                log_step(
                    "Appium 发送按钮点击失败，改用 ADB 坐标兜底："
                    f"{type(exc).__name__}: {exc}"
                )

        fallback_started_at = time.monotonic()
        self._tap_profile_point(
            args,
            point=profile.send_button,
            label="ADB 点击评论发送兜底",
        )
        log_step(
            "COMMENT_METRIC send_comment method=adb_fallback outcome=success "
            f"deviceModel={self._device_model(args)} elapsed={time.monotonic() - fallback_started_at:.2f}s"
        )

    def _tap_profile_point(
        self,
        args: argparse.Namespace,
        *,
        point: TapPointRatio,
        label: str,
    ) -> None:
        width, height = self._adb_window_size(args)
        x = int(width * point.x)
        y = int(height * point.y)
        log_step(
            f"{label}：deviceModel={self._device_model(args)} "
            f"x={x} y={y} ratio=({point.x:.3f},{point.y:.3f})"
        )
        self._adb_shell(args=args, shell_args=["input", "tap", str(x), str(y)])

    def _device_tap_profile(self, args: argparse.Namespace) -> DeviceTapProfile:
        return DEVICE_TAP_PROFILES.get(self._device_model(args), DEVICE_TAP_PROFILES[DEFAULT_DEVICE_MODEL])

    @staticmethod
    def _device_model(args: argparse.Namespace) -> str:
        value = str(getattr(args, "device_model", "") or DEFAULT_DEVICE_MODEL).strip()
        return value or DEFAULT_DEVICE_MODEL

    def _swipe_share_panel_left_by_adb(self, args: argparse.Namespace) -> None:
        width, height = self._adb_window_size(args)
        start_x = int(width * 0.91)
        end_x = int(width * 0.48)
        y = int(height * 0.94)
        log_step(f"ADB 左滑分享功能栏：start=({start_x},{y}) end=({end_x},{y})")
        self._adb_shell(
            args=args,
            shell_args=["input", "swipe", str(start_x), str(y), str(end_x), str(y), "400"],
        )

    def _tap_share_link_by_adb(self, args: argparse.Namespace) -> None:
        width, height = self._adb_window_size(args)
        x = int(width * 0.568)
        y = int(height * 0.952)
        log_step(f"ADB 点击分享链接兜底：x={x} y={y}")
        self._adb_shell(args=args, shell_args=["input", "tap", str(x), str(y)])

    def _tap_link_copied_close_by_adb(self, args: argparse.Namespace) -> None:
        width, height = self._adb_window_size(args)
        x = int(width * 0.911)
        y = int(height * 0.795)
        log_step(f"ADB 点击链接复制成功弹窗关闭兜底：x={x} y={y}")
        self._adb_shell(args=args, shell_args=["input", "tap", str(x), str(y)])

    def _tap_screen_center_by_adb(self, args: argparse.Namespace, label: str) -> None:
        width, height = self._adb_window_size(args)
        x = int(width * 0.5)
        y = int(height * 0.5)
        log_step(f"ADB {label}：x={x} y={y}")
        self._adb_shell(args=args, shell_args=["input", "tap", str(x), str(y)])

    def _adb_window_size(self, args: argparse.Namespace) -> tuple[int, int]:
        try:
            result = self._adb_shell(args=args, shell_args=["wm", "size"], capture=True)
            match = re.search(r"(\d+)x(\d+)", result)
            if match:
                return int(match.group(1)), int(match.group(2))
        except Exception as exc:  # noqa: BLE001 - default below matches the test devices.
            log_step(f"读取屏幕尺寸失败，使用默认 1080x2160：{type(exc).__name__}: {exc}")
        return 1080, 2160

    def _adb_shell(
        self,
        *,
        args: argparse.Namespace | None,
        shell_args: list[str],
        udid: str | None = None,
        capture: bool = False,
    ) -> str:
        adb_path = getattr(args, "adb_path", None) if args is not None else None
        device_udid = udid or getattr(args, "udid", None)
        if not device_udid:
            raise RuntimeError("missing adb device udid")
        command = [adb_path or "adb", "-s", device_udid, "shell", *shell_args]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "").strip())
        return result.stdout if capture else ""

    def _click_optional_video_action(
        self,
        driver,
        *,
        xpath: str,
        label: str,
        wait_seconds: float = 6,
    ) -> bool:
        started_at = time.monotonic()
        try:
            element = WebDriverWait(driver, wait_seconds).until(
                lambda current_driver: current_driver.find_element(AppiumBy.XPATH, xpath)
            )
        except Exception as exc:  # noqa: BLE001 - action may already be done.
            log_step(f"{label}未找到或已完成，跳过：{type(exc).__name__}: {exc}")
            return False
        self._click_video_action_element(driver, element, label, started_at)
        return True

    def _click_video_action_element(self, driver, element, label: str, started_at: float) -> None:
        element_id = getattr(element, "id", None)
        if element_id:
            try:
                driver.execute_script("mobile: clickGesture", {"elementId": element_id})
                log_step(
                    f"{label}已点击："
                    f"elementId={element_id}, elapsed={time.monotonic() - started_at:.2f}s"
                )
                return
            except Exception as exc:  # noqa: BLE001 - fallback to element.click below.
                log_step(f"{label} elementId 点击失败，回退 element.click：{type(exc).__name__}: {exc}")

        element.click()
        log_step(f"{label}已点击：element.click, elapsed={time.monotonic() - started_at:.2f}s")

    def _build_actions(self, *, driver, args: argparse.Namespace, task_id: str) -> DouyinActions:
        locators = build_search_locators(args)
        existing_send_locators = locators.get("send_comment_button")
        locators.locators["send_comment_button"] = [
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
            *existing_send_locators,
        ]
        actions = DouyinActions(
            driver=driver,
            locators=locators,
            udid=args.udid,
            package_name=args.package_name,
            wait_timeout_seconds=args.wait_timeout_seconds,
            task_id=task_id,
        )
        self._latest_actions = actions
        return actions

    def _click_search_tab_by_label(
        self,
        driver,
        label: str,
        *,
        max_top_y: int = 520,
    ) -> None:
        started_at = time.monotonic()
        source = driver.page_source
        candidates = self._search_tab_candidates_from_source(source, max_top_y=max_top_y)
        if candidates:
            formatted = ", ".join(
                f"#{index + 1}:{item['label']}@{item['click_bounds']}"
                for index, item in enumerate(candidates)
            )
            log_step(f"search tab candidates: {formatted}")
        else:
            log_step("search tab candidates not found in page source; fallback to XPath")

        target = next((item for item in candidates if item["label"] == label), None)
        if target is None:
            target = next((item for item in candidates if label in item["label"]), None)
        if target is not None:
            left, top, right, bottom = target["click_bounds"]
            x = (left + right) // 2
            y = (top + bottom) // 2
            driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
            log_step(
                f"search tab clicked: label={label}, "
                f"bounds={[left, top, right, bottom]}, center=({x},{y}), "
                f"elapsed={time.monotonic() - started_at:.2f}s"
            )
            return

        xpath = f'//*[@text="{label}" or @content-desc="{label}" or contains(@text,"{label}") or contains(@content-desc,"{label}")]'
        try:
            element = WebDriverWait(driver, 5).until(
                lambda current_driver: current_driver.find_element(AppiumBy.XPATH, xpath)
            )
            self._click_element_center(driver, element, f"切换Tab {label}", started_at)
            return
        except Exception as exc:  # noqa: BLE001 - include visible candidates in the failure.
            visible = [item["label"] for item in candidates]
            raise RuntimeError(f"search tab not found: {label}, visible tabs={visible}") from exc

    @staticmethod
    def _search_tab_candidates_from_source(
        source: str,
        *,
        max_top_y: int = 520,
    ) -> list[dict[str, object]]:
        try:
            root = ET.fromstring(source)
        except ET.ParseError:
            return []

        parent_map = {child: parent for parent in root.iter() for child in parent}
        candidates: list[dict[str, object]] = []
        seen: set[tuple[str, tuple[int, int, int, int]]] = set()
        for node in root.iter():
            label = (
                node.attrib.get("text")
                or node.attrib.get("content-desc")
                or ""
            ).strip()
            resource_id = node.attrib.get("resource-id", "")
            if not label:
                continue
            if not any(word in label for word in SEARCH_TAB_WORDS) and resource_id != "android:id/text1":
                continue

            label_bounds = DouyinAppiumTaskExecutor._parse_source_bounds(
                node.attrib.get("bounds")
            )
            if label_bounds is None or label_bounds[1] > max_top_y:
                continue
            click_node = DouyinAppiumTaskExecutor._closest_click_node(
                node,
                parent_map,
                max_top_y=max_top_y,
            )
            click_bounds = (
                DouyinAppiumTaskExecutor._parse_source_bounds(
                    click_node.attrib.get("bounds")
                )
                or label_bounds
            )
            key = (label, click_bounds)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "label": label,
                    "label_bounds": label_bounds,
                    "click_bounds": click_bounds,
                    "selected": click_node.attrib.get(
                        "selected",
                        node.attrib.get("selected", ""),
                    ),
                }
            )
        return sorted(candidates, key=lambda item: (item["click_bounds"][1], item["click_bounds"][0]))

    @staticmethod
    def _parse_source_bounds(value: str | None) -> tuple[int, int, int, int] | None:
        if not value:
            return None
        match = BOUNDS_RE.fullmatch(value)
        if not match:
            return None
        left, top, right, bottom = (int(item) for item in match.groups())
        if right <= left or bottom <= top:
            return None
        return left, top, right, bottom

    @staticmethod
    def _closest_click_node(
        node: ET.Element,
        parent_map: dict[ET.Element, ET.Element],
        *,
        max_top_y: int,
    ) -> ET.Element:
        current = node
        while True:
            bounds = DouyinAppiumTaskExecutor._parse_source_bounds(
                current.attrib.get("bounds")
            )
            if bounds and bounds[1] <= max_top_y and current.attrib.get("clickable") == "true":
                return current
            parent = parent_map.get(current)
            if parent is None:
                return node
            parent_bounds = DouyinAppiumTaskExecutor._parse_source_bounds(
                parent.attrib.get("bounds")
            )
            if parent_bounds is None or parent_bounds[1] > max_top_y:
                return node
            parent_width = parent_bounds[2] - parent_bounds[0]
            parent_height = parent_bounds[3] - parent_bounds[1]
            if parent_width > 500 or parent_height > 180:
                return node
            current = parent

    def _click_home_search_entry(self, driver) -> None:
        started_at = time.monotonic()
        capabilities = getattr(driver, "capabilities", {}) or {}
        udid = str(
            capabilities.get("udid")
            or capabilities.get("deviceUDID")
            or capabilities.get("appium:udid")
            or ""
        ).strip()
        if udid:
            result = subprocess.run(
                ["adb", "-s", udid, "shell", "input", "tap", "990", "164"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if result.returncode == 0:
                log_step(
                    "Home search entry clicked via adb tap point=(990,164), "
                    f"elapsed={time.monotonic() - started_at:.2f}s"
                )
                return
            log_step(
                "adb tap home search entry failed, continue with Appium fallback: "
                f"returnCode={result.returncode}, stderr={result.stderr.strip()}"
            )
        try:
            element = WebDriverWait(driver, 3).until(
                lambda current_driver: current_driver.find_element(
                    AppiumBy.ACCESSIBILITY_ID,
                    "搜索",
                )
            )
            rect = element.rect
            x = int(rect["x"] + rect["width"] / 2)
            y = int(rect["y"] + rect["height"] / 2)
            driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
            log_step(
                "首页搜索入口已点击："
                f"accessibility id=搜索, rect={rect}, center=({x},{y}), "
                f"elapsed={time.monotonic() - started_at:.2f}s"
            )
            return
        except Exception as exc:  # noqa: BLE001 - fallback to ratio click below.
            log_step(
                "accessibility id=搜索 点击失败，准备使用比例坐标兜底："
                f"{type(exc).__name__}: {exc}"
            )

        size = driver.get_window_size()
        x = int(size["width"] * 0.925)
        y = int(size["height"] * 0.082)
        driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
        log_step(
            "首页搜索入口已点击："
            f"ratio=(0.925,0.082), size={size}, point=({x},{y}), "
            f"elapsed={time.monotonic() - started_at:.2f}s"
        )

    def _input_search_text(self, driver, search_input, search_text: str) -> None:
        started_at = time.monotonic()
        try:
            search_input.clear()
        except Exception as exc:  # noqa: BLE001 - continue with focused input below.
            log_step(f"搜索输入框 clear 失败，继续尝试输入：{type(exc).__name__}: {exc}")

        errors: list[str] = []
        try:
            self._click_element_center(driver, search_input, "搜索输入框", started_at)
            driver.execute_script("mobile: type", {"text": search_text})
            log_step(f"搜索词通过 mobile: type 输入完成：{search_text}")
            return
        except Exception as exc:  # noqa: BLE001 - fallback to send_keys below.
            message = f"mobile: type failed: {type(exc).__name__}: {exc}"
            errors.append(message)
            log_step(f"搜索词 mobile: type 输入失败，准备回退 send_keys：{message}")

        try:
            search_input.clear()
        except Exception:
            pass
        try:
            search_input.click()
            search_input.send_keys(search_text)
            log_step(f"搜索词通过 send_keys 输入完成：{search_text}")
            return
        except Exception as exc:  # noqa: BLE001 - fallback to clipboard paste below.
            message = f"send_keys failed: {type(exc).__name__}: {exc}"
            errors.append(message)
            log_step(f"搜索词 send_keys 输入失败，准备回退剪贴板粘贴：{message}")

        try:
            search_input.clear()
            driver.set_clipboard_text(search_text)
            self._click_element_center(driver, search_input, "搜索输入框", started_at)
            driver.press_keycode(279)
            log_step(f"搜索词通过剪贴板粘贴完成：{search_text}")
            return
        except Exception as exc:  # noqa: BLE001 - fallback to send_keys below.
            message = f"clipboard paste failed: {type(exc).__name__}: {exc}"
            errors.append(message)
            log_step(f"搜索词剪贴板粘贴失败：{message}")
        raise RuntimeError(f"搜索词输入失败：{errors}")

    def _submit_search(self, driver) -> None:
        started_at = time.monotonic()
        time.sleep(0.5)
        try:
            driver.execute_script("mobile: performEditorAction", {"action": "search"})
            log_step(f"键盘搜索动作已执行：elapsed={time.monotonic() - started_at:.2f}s")
            return
        except Exception as exc:  # noqa: BLE001 - fallback to visible button below.
            log_step(f"键盘搜索动作失败，准备点击右上角搜索按钮：{type(exc).__name__}: {exc}")

        try:
            element = WebDriverWait(driver, 5).until(
                lambda current_driver: current_driver.find_element(
                    AppiumBy.ID,
                    "com.ss.android.ugc.aweme:id/4un",
                )
            )
            self._click_element_center(driver, element, "搜索提交按钮", started_at)
            return
        except Exception as exc:  # noqa: BLE001 - fallback to keyboard enter below.
            log_step(
                "搜索提交按钮定位失败，准备使用回车键兜底："
                f"{type(exc).__name__}: {exc}"
            )

        driver.press_keycode(66)
        log_step(f"回车键搜索动作已执行：elapsed={time.monotonic() - started_at:.2f}s")

    def _click_element_center(self, driver, element, label: str, started_at: float) -> None:
        rect = element.rect
        x = int(rect["x"] + rect["width"] / 2)
        y = int(rect["y"] + rect["height"] / 2)
        driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
        log_step(
            f"{label}已点击："
            f"rect={rect}, center=({x},{y}), elapsed={time.monotonic() - started_at:.2f}s"
        )

    def _config_with_backend_timing(
        self, api_client: AutomationApiClient
    ) -> DouyinAppiumExecutorConfig:
        try:
            timing_settings = api_client.list_timing_settings()
        except AutomationApiError as exc:
            log_step(f"读取后台时间设置失败，使用本地默认值：{exc}")
            return self.config
        return self._apply_timing_settings(self.config, timing_settings)

    @staticmethod
    def _apply_timing_settings(
        config: DouyinAppiumExecutorConfig,
        timing_settings: list[AutomationTimingSettingResult],
    ) -> DouyinAppiumExecutorConfig:
        field_mapping = {
            "before_input": ("before_input_min_seconds", "before_input_max_seconds"),
            "after_input": ("after_input_min_seconds", "after_input_max_seconds"),
            "after_search": ("after_search_min_seconds", "after_search_max_seconds"),
            "watch_video": ("watch_min_seconds", "watch_max_seconds"),
            "after_like": ("after_like_min_seconds", "after_like_max_seconds"),
            "after_favorite": ("after_favorite_min_seconds", "after_favorite_max_seconds"),
            "comment_pre_input_click": (
                "comment_pre_input_min_seconds",
                "comment_pre_input_max_seconds",
            ),
            "comment_focus": ("comment_focus_min_seconds", "comment_focus_max_seconds"),
            "after_comment_input": (
                "after_comment_input_min_seconds",
                "after_comment_input_max_seconds",
            ),
            "before_send_comment": ("before_send_min_seconds", "before_send_max_seconds"),
        }
        values: dict[str, float] = {}
        for setting in timing_settings:
            if setting.key == "douyin_restart_interval":
                values["douyin_restart_interval_minutes"] = setting.max_seconds
                continue
            fields = field_mapping.get(setting.key)
            if fields is None:
                continue
            min_field, max_field = fields
            values[min_field] = setting.min_seconds
            values[max_field] = setting.max_seconds
        if not values:
            return config
        log_step(f"已加载后台时间设置：{sorted(values)}")
        return replace(config, **values)

    def _build_args(
        self,
        device: BackendDeviceConfig,
        *,
        config: DouyinAppiumExecutorConfig | None = None,
    ) -> argparse.Namespace:
        config = config or self.config
        return argparse.Namespace(
            udid=device.udid,
            device_name=device.name,
            device_model=device.device_model,
            system_port=device.system_port,
            appium_server_url=device.appium_server_url or config.appium_server_url,
            package_name=config.package_name,
            app_activity=config.app_activity,
            app=config.app,
            search_button_xpath=DEFAULT_SEARCH_BUTTON_XPATH,
            input_xpath=DEFAULT_INPUT_XPATH,
            submit_xpath=DEFAULT_SUBMIT_XPATH,
            video_tab_xpath=DEFAULT_VIDEO_TAB_XPATH,
            author_xpath=DEFAULT_AUTHOR_XPATH,
            like_xpath=DEFAULT_LIKE_XPATH,
            favorite_xpath=DEFAULT_FAVORITE_XPATH,
            comment_button_xpath=DEFAULT_COMMENT_BUTTON_XPATH,
            comment_input_xpath=DEFAULT_COMMENT_INPUT_XPATH,
            send_comment_xpath=DEFAULT_SEND_COMMENT_XPATH,
            link_copied_close_xpath=DEFAULT_LINK_COPIED_CLOSE_XPATH,
            video_back_xpath=DEFAULT_VIDEO_BACK_XPATH,
            search_back_xpath=DEFAULT_SEARCH_BACK_XPATH,
            target_author="",
            after_open_seconds=config.after_open_seconds,
            return_home_step_wait_seconds=config.return_home_step_wait_seconds,
            return_home_max_back_presses=config.return_home_max_back_presses,
            before_input_min_seconds=config.before_input_min_seconds,
            before_input_max_seconds=config.before_input_max_seconds,
            after_input_min_seconds=config.after_input_min_seconds,
            after_input_max_seconds=config.after_input_max_seconds,
            after_search_min_seconds=config.after_search_min_seconds,
            after_search_max_seconds=config.after_search_max_seconds,
            after_swipe_min_seconds=config.after_swipe_min_seconds,
            after_swipe_max_seconds=config.after_swipe_max_seconds,
            watch_min_seconds=config.watch_min_seconds,
            watch_max_seconds=config.watch_max_seconds,
            after_like_min_seconds=config.after_like_min_seconds,
            after_like_max_seconds=config.after_like_max_seconds,
            after_favorite_min_seconds=config.after_favorite_min_seconds,
            after_favorite_max_seconds=config.after_favorite_max_seconds,
            comment_pre_input_min_seconds=config.comment_pre_input_min_seconds,
            comment_pre_input_max_seconds=config.comment_pre_input_max_seconds,
            comment_focus_min_seconds=config.comment_focus_min_seconds,
            comment_focus_max_seconds=config.comment_focus_max_seconds,
            after_comment_input_min_seconds=config.after_comment_input_min_seconds,
            after_comment_input_max_seconds=config.after_comment_input_max_seconds,
            before_send_min_seconds=config.before_send_min_seconds,
            before_send_max_seconds=config.before_send_max_seconds,
            douyin_restart_interval_minutes=config.douyin_restart_interval_minutes,
            max_swipes=config.max_swipes,
            swipe_percent=config.swipe_percent,
            allow_unverified_home_after_restart=config.allow_unverified_home_after_restart,
            wait_timeout_seconds=config.wait_timeout_seconds,
            quit_timeout_seconds=config.quit_timeout_seconds,
            debug=False,
        )
