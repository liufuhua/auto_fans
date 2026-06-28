from pathlib import Path

from app.api_client import (
    AutomationTimingSettingResult,
    ClaimMatchedDoctorCommentResult,
    ClaimTaskDoctorResult,
    ClaimTaskResult,
    ReportTaskResult,
    StartTaskResult,
)
from app.device_manager import BackendDeviceConfig
from app.douyin_actions import DouyinActions, DouyinLocatorError, LocatorRepository
from app.douyin_task_executor import (
    DEVICE_TAP_PROFILES,
    DouyinAppiumExecutorConfig,
    DouyinAppiumTaskExecutor,
    SearchResultNotFoundError,
)
from app.appium_driver import ManagedAppiumDriver

HOME_SOURCE = """
<hierarchy>
  <node content-desc="首页，按钮" />
  <node content-desc="朋友，按钮" />
  <node content-desc="消息，按钮" />
</hierarchy>
"""

SEARCH_SOURCE = """
<hierarchy>
  <node resource-id="com.ss.android.ugc.aweme:id/bve" content-desc="返回" />
  <node resource-id="com.ss.android.ugc.aweme:id/et_search_kw" text="Doctor Gao" />
</hierarchy>
"""

HOME_FEED_SOURCE = """
<hierarchy>
  <node text="@偏瘫的飛" resource-id="com.ss.android.ugc.aweme:id/title" />
  <node content-desc="偏瘫的飛" resource-id="com.ss.android.ugc.aweme:id/user_avatar" />
  <node content-desc="喜欢，按钮" />
  <node content-desc="评论，按钮" />
  <node content-desc="分享，按钮" />
</hierarchy>
"""


class FakeDriver:
    def __init__(self, sources: list[str]) -> None:
        self.sources = sources
        self.activated_packages: list[str] = []
        self.pressed_keycodes: list[int] = []
        self.quit_count = 0

    def activate_app(self, package_name: str) -> None:
        self.activated_packages.append(package_name)

    @property
    def page_source(self) -> str:
        return self.sources[0]

    def press_keycode(self, keycode: int) -> None:
        self.pressed_keycodes.append(keycode)
        if len(self.sources) > 1:
            self.sources.pop(0)

    def quit(self) -> None:
        self.quit_count += 1


class FakeDriverFactory:
    def __init__(self, driver: object) -> None:
        self.driver = driver
        self.created_devices = []

    def create(self, device):
        self.created_devices.append(device)
        return ManagedAppiumDriver(device=device, driver=self.driver)


class FakeHomeFeedApiClient:
    def __init__(self) -> None:
        self.claim_comment_requests = []
        self.start_requests = []
        self.report_requests = []

    def list_timing_settings(self):
        return []

    def claim_matched_doctor_comment(self, **kwargs):
        self.claim_comment_requests.append(kwargs)
        return ClaimMatchedDoctorCommentResult(
            task_id=1,
            doctor_id=kwargs["doctor_id"],
            doctor_name="Doctor Gao",
            doctor_real_name="",
            keyword_id=12,
            keyword="home feed",
            search_word="home feed",
            comment_bank_item_id=88,
            comment_content="matched comment",
        )

    def start_task(self, **kwargs):
        self.start_requests.append(kwargs)
        return StartTaskResult(result_id=99, status="running")

    def report_task(self, **kwargs):
        self.report_requests.append(kwargs)
        return ReportTaskResult(result_id=kwargs["result_id"], status=kwargs["status"])


class FakeSearchInputElement:
    def __init__(self, rect: dict[str, int] | None = None) -> None:
        self.rect = rect or {"x": 10, "y": 20, "width": 300, "height": 60}
        self.cleared = False
        self.clicked = False
        self.sent_texts: list[str] = []

    def is_displayed(self) -> bool:
        return True

    def clear(self) -> None:
        self.cleared = True

    def click(self) -> None:
        self.clicked = True

    def send_keys(self, text: str) -> None:
        self.sent_texts.append(text)


class MissingSearchInputActions:
    def __init__(self, driver: object) -> None:
        self.driver = driver

    def _wait_visible(self, locator_name: str):
        assert locator_name == "search_input"
        raise DouyinLocatorError("search_input not found")


class HuaweiSearchFallbackDriver:
    def __init__(self) -> None:
        self.element = FakeSearchInputElement()
        self.find_calls: list[tuple[str, str]] = []
        self.click_gestures: list[dict[str, int]] = []
        self.mobile_typed_texts: list[str] = []
        self.keycodes: list[int] = []
        self.quit_count = 0

    @property
    def page_source(self) -> str:
        return """
        <hierarchy>
          <node class="android.widget.TextView" text="搜索" bounds="[900,60][1040,140]" />
          <node class="android.widget.EditText" text="" resource-id="custom.search.input" bounds="[80,80][860,150]" />
        </hierarchy>
        """

    def find_elements(self, by: str, value: str):
        self.find_calls.append((by, value))
        if value == "com.ss.android.ugc.aweme:id/et_search_kw":
            return []
        if "android.widget.EditText" in value:
            return [self.element]
        return []

    def get_window_size(self) -> dict[str, int]:
        return {"width": 1080, "height": 2408}

    def execute_script(self, name: str, payload: dict[str, object]) -> None:
        if name == "mobile: clickGesture":
            self.click_gestures.append(payload)
        if name == "mobile: type":
            self.mobile_typed_texts.append(str(payload["text"]))

    def press_keycode(self, keycode: int) -> None:
        self.keycodes.append(keycode)

    def quit(self) -> None:
        self.quit_count += 1


class MissingCommentButtonActions:
    def _click(self, locator_name: str) -> None:
        assert locator_name == "comment_button"
        raise DouyinLocatorError("comment_button not found")


class FakeSearchActions:
    def __init__(self, driver: object) -> None:
        self.driver = driver


class SearchAttemptRecorder:
    def __init__(self, *, fail_terms: set[str] | None = None) -> None:
        self.fail_terms = fail_terms or set()
        self.calls: list[str] = []
        self.targets: list[str] = []

    def run(self, *, search_text: str, **kwargs):
        self.calls.append(search_text)
        self.targets.append(kwargs["target_author"])
        if search_text in self.fail_terms:
            raise SearchResultNotFoundError(search_text)
        return f"matched by {search_text}", kwargs["actions"].driver


def make_device() -> BackendDeviceConfig:
    return BackendDeviceConfig(
        id=7,
        name="device_03",
        udid="R5CW11CKN0B",
        system_port=8203,
        enabled_status="enabled",
        appium_server_url="http://127.0.0.1:4726",
    )


def test_executor_builds_debug_search_compatible_args() -> None:
    config = DouyinAppiumExecutorConfig(
        appium_server_url="http://127.0.0.1:4723",
        wait_timeout_seconds=9,
        watch_min_seconds=5,
        watch_max_seconds=8,
        after_swipe_min_seconds=1.5,
        after_swipe_max_seconds=2.5,
    )
    executor = DouyinAppiumTaskExecutor(config=config)

    args = executor._build_args(make_device())

    assert args.udid == "R5CW11CKN0B"
    assert args.device_name == "device_03"
    assert args.system_port == 8203
    assert args.appium_server_url == "http://127.0.0.1:4726"
    assert args.wait_timeout_seconds == 9
    assert args.watch_min_seconds == 5
    assert args.watch_max_seconds == 8
    assert args.after_swipe_min_seconds == 1.5
    assert args.after_swipe_max_seconds == 2.5
    assert args.after_open_seconds == 2
    assert args.return_home_step_wait_seconds == 1.5
    assert args.return_home_max_back_presses == 4
    assert args.video_back_xpath
    assert args.search_back_xpath
    assert executor.config.execute_video_actions_enabled is True
    assert executor.config.send_comment_enabled is True
    assert args.comment_button_xpath


def test_executor_applies_backend_timing_settings() -> None:
    config = DouyinAppiumExecutorConfig(
        appium_server_url="http://127.0.0.1:4723",
        watch_min_seconds=15,
        watch_max_seconds=300,
    )

    updated = DouyinAppiumTaskExecutor._apply_timing_settings(
        config,
        [
            AutomationTimingSettingResult(
                key="watch_video",
                label="视频观看时长",
                min_seconds=30,
                max_seconds=60,
            ),
            AutomationTimingSettingResult(
                key="comment_pre_input_click",
                label="点击评论输入框后",
                min_seconds=2.5,
                max_seconds=4.5,
            ),
            AutomationTimingSettingResult(
                key="douyin_restart_interval",
                label="退出和重启抖音间隔时间",
                min_seconds=30,
                max_seconds=30,
            ),
        ],
    )

    assert updated.watch_min_seconds == 30
    assert updated.watch_max_seconds == 60
    assert updated.comment_pre_input_min_seconds == 2.5
    assert updated.comment_pre_input_max_seconds == 4.5
    assert updated.douyin_restart_interval_minutes == 30
    assert config.watch_min_seconds == 15
    assert config.watch_max_seconds == 300


def test_force_stop_douyin_waits_restart_interval_in_minutes(monkeypatch) -> None:
    config = DouyinAppiumExecutorConfig(douyin_restart_interval_minutes=30)
    executor = DouyinAppiumTaskExecutor(config=config)
    args = executor._build_args(make_device())
    commands = []
    sleeps = []

    class Completed:
        stdout = ""
        stderr = ""
        returncode = 0

    def fake_run(command, **kwargs):
        commands.append(command)
        return Completed()

    monkeypatch.setattr("app.douyin_task_executor.subprocess.run", fake_run)
    monkeypatch.setattr("app.douyin_task_executor.time.sleep", lambda seconds: sleeps.append(seconds))

    executor._force_stop_douyin(args)

    assert commands == [["adb", "-s", args.udid, "shell", "am", "force-stop", args.package_name]]
    assert sleeps == [1800]


def test_executor_shell_script_command_uses_script_directly_on_unix(monkeypatch) -> None:
    script_path = Path("/repo/automation_client/scripts/clear_session.sh")
    command = DouyinAppiumTaskExecutor._shell_script_command(
        script_path,
        "R5CW11CKN0B",
        "8203",
        is_windows=False,
    )

    assert command == [
        str(script_path),
        "R5CW11CKN0B",
        "8203",
    ]


def test_executor_shell_script_command_uses_bash_on_windows(monkeypatch) -> None:
    monkeypatch.setattr("app.douyin_task_executor.shutil.which", lambda name: "C:/Git/usr/bin/bash.exe")
    monkeypatch.setattr("app.douyin_task_executor.Path.exists", lambda self: False)
    script_path = Path("E:/android_auto_test/automation_client/scripts/clear_session.sh")

    command = DouyinAppiumTaskExecutor._shell_script_command(
        script_path,
        "R5CW11CKN0B",
        "8203",
        is_windows=True,
    )

    assert command == [
        "C:/Git/usr/bin/bash.exe",
        "-lc",
        "/e/android_auto_test/automation_client/scripts/clear_session.sh R5CW11CKN0B 8203",
    ]


def test_executor_finds_video_tab_when_it_is_after_user_and_product() -> None:
    source = """
    <hierarchy>
      <node text="综合" resource-id="android:id/text1" clickable="true" bounds="[51,247][209,387]" />
      <node text="用户" resource-id="android:id/text1" clickable="true" bounds="[209,247][367,387]" />
      <node text="商品" resource-id="android:id/text1" clickable="true" bounds="[367,247][525,387]" />
      <node text="视频" resource-id="android:id/text1" clickable="true" bounds="[525,247][683,387]" />
    </hierarchy>
    """

    candidates = DouyinAppiumTaskExecutor._search_tab_candidates_from_source(source)

    assert [item["label"] for item in candidates] == ["综合", "用户", "商品", "视频"]
    video = next(item for item in candidates if item["label"] == "视频")
    assert video["click_bounds"] == (525, 247, 683, 387)


def test_executor_finds_video_tab_when_it_is_second() -> None:
    source = """
    <hierarchy>
      <node text="综合" resource-id="android:id/text1" clickable="true" bounds="[51,247][209,387]" />
      <node text="视频" resource-id="android:id/text1" clickable="true" bounds="[209,247][367,387]" />
      <node text="用户" resource-id="android:id/text1" clickable="true" bounds="[367,247][525,387]" />
    </hierarchy>
    """

    candidates = DouyinAppiumTaskExecutor._search_tab_candidates_from_source(source)

    assert [item["label"] for item in candidates] == ["综合", "视频", "用户"]
    video = next(item for item in candidates if item["label"] == "视频")
    assert video["click_bounds"] == (209, 247, 367, 387)


def test_executor_preflight_opens_douyin_when_already_home(monkeypatch) -> None:
    config = DouyinAppiumExecutorConfig(
        appium_server_url="http://127.0.0.1:4723",
        after_open_seconds=0,
    )
    executor = DouyinAppiumTaskExecutor(config=config)
    args = executor._build_args(make_device())
    driver = FakeDriver([HOME_SOURCE])
    actions = DouyinActions(
        driver=driver,
        locators=LocatorRepository({}),
        udid=args.udid,
        package_name=args.package_name,
        wait_timeout_seconds=args.wait_timeout_seconds,
        task_id="test",
    )

    monkeypatch.setattr(executor, "_reconnect_driver", lambda *, args, driver: driver)

    executor._ensure_douyin_home_page(driver=driver, actions=actions, args=args)

    assert driver.activated_packages == [args.package_name]
    assert driver.pressed_keycodes == []


def test_executor_preflight_accepts_home_feed_without_back_presses(monkeypatch) -> None:
    config = DouyinAppiumExecutorConfig(
        appium_server_url="http://127.0.0.1:4723",
        after_open_seconds=0,
    )
    executor = DouyinAppiumTaskExecutor(config=config)
    args = executor._build_args(make_device())
    driver = FakeDriver([HOME_FEED_SOURCE])
    actions = DouyinActions(
        driver=driver,
        locators=LocatorRepository({}),
        udid=args.udid,
        package_name=args.package_name,
        wait_timeout_seconds=args.wait_timeout_seconds,
        task_id="test",
    )

    monkeypatch.setattr(executor, "_reconnect_driver", lambda *, args, driver: driver)

    executor._ensure_douyin_home_page(driver=driver, actions=actions, args=args)

    assert driver.activated_packages == [args.package_name]
    assert driver.pressed_keycodes == []


def test_executor_preflight_uses_back_until_home(monkeypatch) -> None:
    config = DouyinAppiumExecutorConfig(
        appium_server_url="http://127.0.0.1:4723",
        after_open_seconds=0,
        return_home_step_wait_seconds=0,
    )
    executor = DouyinAppiumTaskExecutor(config=config)
    args = executor._build_args(make_device())
    driver = FakeDriver(["<hierarchy><node text='unknown' /></hierarchy>", HOME_SOURCE])
    actions = DouyinActions(
        driver=driver,
        locators=LocatorRepository({}),
        udid=args.udid,
        package_name=args.package_name,
        wait_timeout_seconds=args.wait_timeout_seconds,
        task_id="test",
    )

    monkeypatch.setattr(executor, "_reconnect_driver", lambda *, args, driver: driver)

    executor._ensure_douyin_home_page(driver=driver, actions=actions, args=args)

    assert driver.activated_packages == [args.package_name]
    assert driver.pressed_keycodes == [4]


def test_executor_preflight_leaves_search_page_before_restart(monkeypatch) -> None:
    config = DouyinAppiumExecutorConfig(
        appium_server_url="http://127.0.0.1:4723",
        after_open_seconds=0,
        return_home_step_wait_seconds=0,
    )
    executor = DouyinAppiumTaskExecutor(config=config)
    args = executor._build_args(make_device())
    driver = FakeDriver([SEARCH_SOURCE, HOME_SOURCE])
    actions = DouyinActions(
        driver=driver,
        locators=LocatorRepository({}),
        udid=args.udid,
        package_name=args.package_name,
        wait_timeout_seconds=args.wait_timeout_seconds,
        task_id="test",
    )
    restart_calls = []
    safe_click_calls = []

    def fake_safe_click(actions, locator_name, label):
        safe_click_calls.append((locator_name, label))
        if locator_name == "search_back_button":
            driver.press_keycode(4)
            return True
        return False

    monkeypatch.setattr(executor, "_reconnect_driver", lambda *, args, driver: driver)
    monkeypatch.setattr(
        executor,
        "_restart_douyin_from_launcher",
        lambda *, args, driver: restart_calls.append(driver) or driver,
    )
    monkeypatch.setattr("app.douyin_task_executor.safe_click", fake_safe_click)

    executor._ensure_douyin_home_page(driver=driver, actions=actions, args=args)

    assert restart_calls == []
    assert safe_click_calls == [("search_back_button", "退出搜索页")]


def test_executor_retry_search_text_uses_keyword_and_real_name() -> None:
    assert (
        DouyinAppiumTaskExecutor._build_retry_search_text(
            keyword="脑膜瘤",
            doctor_name="北京三博张明山",
            doctor_real_name="张明山",
        )
        == "脑膜瘤 张明山"
    )


def test_executor_retry_search_text_falls_back_to_nickname_when_real_name_empty() -> None:
    assert (
        DouyinAppiumTaskExecutor._build_retry_search_text(
            keyword="脑膜瘤",
            doctor_name="北京三博张明山",
            doctor_real_name="",
        )
        == "脑膜瘤 北京三博张明山"
    )


def test_executor_search_plan_stops_after_name_only_success(monkeypatch) -> None:
    executor = DouyinAppiumTaskExecutor()
    args = executor._build_args(make_device())
    driver = object()
    actions = FakeSearchActions(driver)
    waits: dict[str, float] = {}
    recorder = SearchAttemptRecorder()

    monkeypatch.setattr(executor, "_search_and_open_matching_video", recorder.run)

    matched_author, active_driver = executor._find_with_name_first_search_plan(
        actions=actions,
        args=args,
        doctor_name="Doctor Gao",
        keyword_search_text="skull repair",
        combined_search_text="skull repair Doctor Gao",
        waits=waits,
    )

    assert matched_author == "matched by skull repair"
    assert active_driver is driver
    assert recorder.calls == ["skull repair"]
    assert recorder.targets == ["Doctor Gao"]


def test_executor_search_plan_retries_with_combined_term_after_name_not_found(
    monkeypatch,
) -> None:
    executor = DouyinAppiumTaskExecutor()
    args = executor._build_args(make_device())
    first_driver = object()
    second_driver = object()
    actions = FakeSearchActions(first_driver)
    waits: dict[str, float] = {}
    recorder = SearchAttemptRecorder(fail_terms={"skull repair"})
    rebuilt_actions: list[tuple[object, str]] = []

    monkeypatch.setattr(executor, "_search_and_open_matching_video", recorder.run)
    monkeypatch.setattr(
        executor,
        "_ensure_douyin_home_page",
        lambda *, driver, actions, args: second_driver,
    )

    def fake_build_actions(*, driver, args, task_id):
        rebuilt_actions.append((driver, task_id))
        return FakeSearchActions(driver)

    monkeypatch.setattr(executor, "_build_actions", fake_build_actions)

    matched_author, active_driver = executor._find_with_name_first_search_plan(
        actions=actions,
        args=args,
        doctor_name="Doctor Gao",
        keyword_search_text="skull repair",
        combined_search_text="skull repair Doctor Gao",
        waits=waits,
    )

    assert matched_author == "matched by skull repair Doctor Gao"
    assert active_driver is second_driver
    assert recorder.calls == ["skull repair", "skull repair Doctor Gao"]
    assert recorder.targets == ["Doctor Gao", "Doctor Gao"]
    assert rebuilt_actions == [
        (first_driver, "worker_search_task_before_retry_home"),
        (second_driver, "worker_search_task_retry_combined"),
    ]


def test_executor_search_plan_uses_latest_driver_after_keyword_not_found(monkeypatch) -> None:
    executor = DouyinAppiumTaskExecutor()
    args = executor._build_args(make_device())
    original_driver = object()
    latest_failed_driver = object()
    home_driver = object()
    actions = FakeSearchActions(original_driver)
    waits: dict[str, float] = {}
    home_calls: list[object] = []
    calls: list[str] = []

    def fake_search(*, search_text: str, actions, **kwargs):
        calls.append(search_text)
        if search_text == "skull repair":
            error = SearchResultNotFoundError(search_text)
            error.active_driver = latest_failed_driver
            raise error
        return f"matched by {search_text}", actions.driver

    def fake_ensure_home(*, driver, actions, args):
        home_calls.append(driver)
        return home_driver

    monkeypatch.setattr(executor, "_search_and_open_matching_video", fake_search)
    monkeypatch.setattr(executor, "_ensure_douyin_home_page", fake_ensure_home)
    monkeypatch.setattr(
        executor,
        "_build_actions",
        lambda *, driver, args, task_id: FakeSearchActions(driver),
    )

    matched_author, active_driver = executor._find_with_name_first_search_plan(
        actions=actions,
        args=args,
        doctor_name="Doctor Gao",
        keyword_search_text="skull repair",
        combined_search_text="skull repair Doctor Gao",
        waits=waits,
    )

    assert matched_author == "matched by skull repair Doctor Gao"
    assert active_driver is home_driver
    assert calls == ["skull repair", "skull repair Doctor Gao"]
    assert home_calls == [latest_failed_driver]


def test_executor_search_plan_raises_when_both_terms_not_found(monkeypatch) -> None:
    executor = DouyinAppiumTaskExecutor()
    args = executor._build_args(make_device())
    driver = object()
    actions = FakeSearchActions(driver)
    waits: dict[str, float] = {}
    recorder = SearchAttemptRecorder(
        fail_terms={"skull repair", "skull repair Doctor Gao"}
    )

    monkeypatch.setattr(executor, "_search_and_open_matching_video", recorder.run)
    monkeypatch.setattr(
        executor,
        "_ensure_douyin_home_page",
        lambda *, driver, actions, args: driver,
    )
    monkeypatch.setattr(
        executor,
        "_build_actions",
        lambda *, driver, args, task_id: FakeSearchActions(driver),
    )

    try:
        executor._find_with_name_first_search_plan(
            actions=actions,
            args=args,
            doctor_name="Doctor Gao",
            keyword_search_text="skull repair",
            combined_search_text="skull repair Doctor Gao",
            waits=waits,
        )
    except SearchResultNotFoundError as exc:
        assert str(exc) == "skull repair Doctor Gao"
    else:
        raise AssertionError("expected SearchResultNotFoundError")

    assert recorder.calls == ["skull repair", "skull repair Doctor Gao"]
    assert recorder.targets == ["Doctor Gao", "Doctor Gao"]


def test_huawei_search_input_falls_back_to_visible_edit_text(monkeypatch) -> None:
    config = DouyinAppiumExecutorConfig(
        after_input_min_seconds=0,
        after_input_max_seconds=0,
        after_search_min_seconds=0,
        after_search_max_seconds=0,
    )
    executor = DouyinAppiumTaskExecutor(config=config)
    device = BackendDeviceConfig(
        id=7,
        name="huawei_006",
        udid="MYQUT20414008419",
        system_port=8230,
        enabled_status="enabled",
        device_model="huawei_nova_se6",
        appium_server_url="http://127.0.0.1:4721",
    )
    args = executor._build_args(device)
    driver = HuaweiSearchFallbackDriver()
    actions = MissingSearchInputActions(driver)
    waits: dict[str, float] = {}

    monkeypatch.setattr(
        "app.douyin_task_executor.random_seconds",
        lambda min_seconds, max_seconds, label: 0,
    )
    monkeypatch.setattr(executor, "_reconnect_driver", lambda *, args, driver: driver)
    monkeypatch.setattr(executor, "_submit_search", lambda driver: driver.press_keycode(66))

    result_driver = executor._input_search_text_submit_and_reconnect(
        actions=actions,
        args=args,
        search_text="腱鞘炎手术",
        waits=waits,
    )

    assert result_driver is driver
    assert driver.mobile_typed_texts == ["腱鞘炎手术"]
    assert driver.keycodes == [66]
    assert waits == {"after_input": 0, "after_search": 0}


def test_executor_exits_douyin_with_clear_reason_when_comment_button_missing(monkeypatch) -> None:
    config = DouyinAppiumExecutorConfig(appium_server_url="http://127.0.0.1:4723")
    executor = DouyinAppiumTaskExecutor(config=config)
    args = executor._build_args(make_device())
    force_stop_calls = []

    monkeypatch.setattr(
        "app.douyin_task_executor.random_seconds",
        lambda min_seconds, max_seconds, label: 0,
    )
    monkeypatch.setattr(executor, "_force_stop_douyin", lambda args: force_stop_calls.append(args))

    try:
        executor._comment_video_and_reconnect(
            actions=MissingCommentButtonActions(),
            args=args,
            comment="测试评论",
            waits={},
            send_comment=True,
        )
    except RuntimeError as exc:
        assert "未找到视频页评论按钮" in str(exc)
        assert "图文/文章页面" in str(exc)
    else:
        raise AssertionError("expected clear comment-button failure")

    assert force_stop_calls == [args]


def test_vivo_comment_actions_prefer_adb_without_changing_huawei_coordinates() -> None:
    vivo_profile = DEVICE_TAP_PROFILES["vivo_y52"]
    huawei_profile = DEVICE_TAP_PROFILES["huawei_nova_se6"]

    assert vivo_profile.prefer_adb_active_comment_input is True
    assert vivo_profile.prefer_adb_send_button is True
    assert vivo_profile.active_comment_input.x == 0.32
    assert vivo_profile.active_comment_input.y == 0.965
    assert vivo_profile.send_button.x == 0.894
    assert vivo_profile.send_button.y == 0.574

    assert huawei_profile.prefer_adb_active_comment_input is True
    assert huawei_profile.prefer_adb_send_button is True
    assert huawei_profile.active_comment_input.x == 0.32
    assert huawei_profile.active_comment_input.y == 0.965
    assert huawei_profile.send_button.x == 0.894
    assert huawei_profile.send_button.y == 0.555


def test_home_feed_task_watches_and_swipes_until_author_matches(monkeypatch) -> None:
    driver = FakeDriver([HOME_SOURCE])
    executor = DouyinAppiumTaskExecutor(
        config=DouyinAppiumExecutorConfig(
            appium_server_url="http://127.0.0.1:4723",
            max_swipes=3,
        ),
        driver_factory=FakeDriverFactory(driver),  # type: ignore[arg-type]
    )
    api_client = FakeHomeFeedApiClient()
    task = ClaimTaskResult(
        has_task=True,
        publish_account="account-1",
        doctors=[ClaimTaskDoctorResult(doctor_id=31, doctor_name="Doctor Gao")],
    )
    calls = []
    authors = iter(["Other Author", "Clinic Doctor Gao"])

    monkeypatch.setattr(executor, "_configure_driver", lambda driver: None)
    monkeypatch.setattr(executor, "_ensure_douyin_home_page", lambda **kwargs: kwargs["driver"])
    monkeypatch.setattr(executor, "_get_home_feed_video_author_name", lambda driver: next(authors))
    monkeypatch.setattr(executor, "_watch_home_feed_video", lambda *, args, waits: calls.append("watch"))
    monkeypatch.setattr(
        executor,
        "_swipe_to_next_home_feed_video",
        lambda *, driver, actions, args: calls.append("swipe") or driver,
    )
    monkeypatch.setattr(
        executor,
        "_execute_home_feed_matched_comment",
        lambda **kwargs: calls.append(("matched", kwargs["matched_doctor"].doctor_id)) or driver,
    )
    monkeypatch.setattr("app.douyin_task_executor.quit_with_timeout", lambda driver, timeout: None)
    monkeypatch.setattr(executor, "_clear_appium_session", lambda args: None)

    result = executor.execute(
        task=task,
        start_result=StartTaskResult(result_id=0, status="home_feed"),
        device=make_device(),
        api_client=api_client,  # type: ignore[arg-type]
    )

    assert result.report_to_backend is False
    assert calls == ["watch", "swipe", "watch", ("matched", 31), "swipe"]


def test_home_feed_author_candidates_prefer_title_resource_id() -> None:
    source = """
    <hierarchy>
      <node text="视频" resource-id="android:id/text1" bounds="[0,0][100,80]" />
      <node text="@偏瘫的飛" resource-id="com.ss.android.ugc.aweme:id/title" bounds="[36,1842][290,1917]" />
      <node content-desc="偏瘫的飛" resource-id="com.ss.android.ugc.aweme:id/user_avatar" bounds="[915,998][1059,1142]" />
    </hierarchy>
    """

    candidates = DouyinAppiumTaskExecutor._author_candidates_from_source(source)

    assert candidates[0] == "偏瘫的飛"
    assert "视频" not in candidates


def test_home_feed_author_candidates_fall_back_to_user_avatar_description() -> None:
    source = """
    <hierarchy>
      <node text="视频" resource-id="android:id/text1" bounds="[0,0][100,80]" />
      <node text="" content-desc="偏瘫的飛" resource-id="com.ss.android.ugc.aweme:id/user_avatar" bounds="[915,998][1059,1142]" />
    </hierarchy>
    """

    candidates = DouyinAppiumTaskExecutor._author_candidates_from_source(source)

    assert candidates[0] == "偏瘫的飛"
    assert "视频" not in candidates


def test_home_feed_matched_author_claims_comment_and_reports_task_1(monkeypatch) -> None:
    driver = FakeDriver([HOME_SOURCE])
    executor = DouyinAppiumTaskExecutor(config=DouyinAppiumExecutorConfig())
    args = executor._build_args(make_device())
    api_client = FakeHomeFeedApiClient()
    matched_doctor = ClaimTaskDoctorResult(doctor_id=31, doctor_name="Doctor Gao")
    actions = FakeSearchActions(driver)
    calls = []

    monkeypatch.setattr(
        executor,
        "_like_video_and_reconnect",
        lambda *, actions, args, waits: calls.append("like") or (True, driver),
    )
    monkeypatch.setattr(
        executor,
        "_favorite_video_and_reconnect",
        lambda *, actions, args, waits: calls.append("favorite") or (True, driver),
    )
    monkeypatch.setattr(
        executor,
        "_share_video_and_reconnect",
        lambda *, actions, args: calls.append("share") or (True, "https://v.douyin.com/test/", driver),
    )
    monkeypatch.setattr(
        executor,
        "_comment_video_and_reconnect",
        lambda **kwargs: calls.append(("comment", kwargs["comment"], kwargs["force_stop_after_comment"])) or driver,
    )
    monkeypatch.setattr(executor, "_ensure_douyin_home_page", lambda **kwargs: calls.append("home") or kwargs["driver"])

    result_driver = executor._execute_home_feed_matched_comment(
        driver=driver,
        actions=actions,  # type: ignore[arg-type]
        args=args,
        waits={},
        api_client=api_client,  # type: ignore[arg-type]
        device=make_device(),
        matched_doctor=matched_doctor,
        author_name="Clinic Doctor Gao",
        publish_account="account-1",
    )

    assert result_driver is driver
    assert api_client.claim_comment_requests == [
        {"udid": "R5CW11CKN0B", "doctor_id": 31, "publish_account": "account-1"}
    ]
    assert api_client.start_requests == [
        {
            "task_item_id": 1,
            "udid": "R5CW11CKN0B",
            "comment_bank_item_id": 88,
            "publish_account": "account-1",
        }
    ]
    assert api_client.report_requests[0]["task_item_id"] == 1
    assert api_client.report_requests[0]["comment_bank_item_id"] == 88
    assert api_client.report_requests[0]["result_id"] == 99
    assert api_client.report_requests[0]["status"] == "success"
    assert api_client.report_requests[0]["video_link"] == "https://v.douyin.com/test/"
    assert calls == ["like", "favorite", "share", ("comment", "matched comment", False), "home"]
