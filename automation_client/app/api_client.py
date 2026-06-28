from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import httpx


class AutomationApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class AutomationRuntimeState:
    business_status: str
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    updated_at: datetime | None = None
    remark: str = ""


@dataclass(frozen=True)
class DeviceHeartbeatResult:
    device_id: int
    udid: str
    runtime_status: str
    last_heartbeat_at: datetime


@dataclass(frozen=True)
class BackendDeviceConfigResult:
    id: int
    name: str
    udid: str
    system_port: int
    enabled_status: str
    device_model: str = "huawei_nova_se6"
    appium_server_url: str | None = None


@dataclass(frozen=True)
class AutomationTimingSettingResult:
    key: str
    label: str
    min_seconds: float
    max_seconds: float


@dataclass(frozen=True)
class ClaimTaskDoctorResult:
    doctor_id: int
    doctor_name: str
    doctor_real_name: str = ""


@dataclass(frozen=True)
class ClaimTaskResult:
    has_task: bool
    reason: str | None = None
    doctors: list[ClaimTaskDoctorResult] = field(default_factory=list)
    publish_account: str | None = None
    task_id: int | None = None
    task_item_id: int | None = None
    doctor_id: int | None = None
    doctor_name: str | None = None
    doctor_real_name: str | None = None
    keyword_id: int | None = None
    keyword: str | None = None
    search_word: str | None = None
    comment_bank_item_id: int | None = None
    comment_content: str | None = None


@dataclass(frozen=True)
class ClaimMatchedDoctorCommentResult:
    task_id: int
    doctor_id: int
    doctor_name: str
    doctor_real_name: str
    keyword_id: int
    keyword: str
    search_word: str
    comment_bank_item_id: int
    comment_content: str


@dataclass(frozen=True)
class StartTaskResult:
    result_id: int
    status: str


@dataclass(frozen=True)
class ReportTaskResult:
    result_id: int
    status: str


class AutomationApiClient:
    """HTTP client for backend automation APIs."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def heartbeat_device(
        self,
        *,
        udid: str,
        device_name: str,
        system_port: int,
        runtime_status: str,
        remark: str = "",
    ) -> DeviceHeartbeatResult:
        data = self._post(
            "/automation/devices/heartbeat",
            json={
                "udid": udid,
                "deviceName": device_name,
                "systemPort": system_port,
                "runtimeStatus": runtime_status,
                "remark": remark,
            },
        )
        return DeviceHeartbeatResult(
            device_id=int(data["deviceId"]),
            udid=str(data["udid"]),
            runtime_status=str(data["runtimeStatus"]),
            last_heartbeat_at=datetime.fromisoformat(str(data["lastHeartbeatAt"])),
        )

    def get_automation_runtime(self) -> AutomationRuntimeState:
        data = self._get("/automation/runtime")
        return AutomationRuntimeState(
            business_status=str(data["businessStatus"]),
            started_at=_parse_datetime(data.get("startedAt")),
            stopped_at=_parse_datetime(data.get("stoppedAt")),
            updated_at=_parse_datetime(data.get("updatedAt")),
            remark=str(data.get("remark") or ""),
        )

    def list_device_configs(self) -> list[BackendDeviceConfigResult]:
        data = self._get_list("/automation/devices/configs")
        configs: list[BackendDeviceConfigResult] = []
        for item in data:
            if not isinstance(item, dict):
                raise AutomationApiError("backend api returned invalid device config")
            configs.append(
                BackendDeviceConfigResult(
                    id=int(item["id"]),
                    name=str(item["name"]).strip(),
                    udid=str(item["udid"]).strip(),
                    device_model=str(item.get("deviceModel") or "huawei_nova_se6").strip(),
                    system_port=int(item["systemPort"]),
                    enabled_status=str(item["enabledStatus"]).strip(),
                    appium_server_url=(
                        str(item["appiumServerUrl"]).strip()
                        if item.get("appiumServerUrl")
                        else None
                    ),
                )
            )
        return configs

    def list_timing_settings(self) -> list[AutomationTimingSettingResult]:
        data = self._get_list("/automation/timing-settings")
        settings: list[AutomationTimingSettingResult] = []
        for item in data:
            if not isinstance(item, dict):
                raise AutomationApiError("backend api returned invalid timing setting")
            settings.append(
                AutomationTimingSettingResult(
                    key=str(item["key"]),
                    label=str(item["label"]),
                    min_seconds=float(item["minSeconds"]),
                    max_seconds=float(item["maxSeconds"]),
                )
            )
        return settings

    def auto_stop_automation_runtime(
        self, *, remark: str, force: bool = False
    ) -> AutomationRuntimeState:
        data = self._post(
            "/automation/runtime/auto-stop",
            json={
                "remark": remark,
                "force": force,
            },
        )
        return AutomationRuntimeState(
            business_status=str(data["businessStatus"]),
            started_at=_parse_datetime(data.get("startedAt")),
            stopped_at=_parse_datetime(data.get("stoppedAt")),
            updated_at=_parse_datetime(data.get("updatedAt")),
            remark=str(data.get("remark") or ""),
        )

    def claim_task(self, *, udid: str, publish_account: str) -> ClaimTaskResult:
        data = self._post(
            "/automation/tasks/claim",
            json={
                "udid": udid,
                "publishAccount": publish_account,
            },
        )
        doctors = _parse_claim_task_doctors(data.get("doctors"))
        if not bool(data.get("hasTask")):
            reason = data.get("reason")
            return ClaimTaskResult(
                has_task=False,
                reason=str(reason) if reason else None,
                doctors=doctors,
            )

        return ClaimTaskResult(
            has_task=True,
            reason=str(data["reason"]) if data.get("reason") else None,
            doctors=doctors,
            task_id=_optional_int(data.get("taskId")),
            task_item_id=_optional_int(data.get("taskItemId")),
            doctor_id=_optional_int(data.get("doctorId")),
            doctor_name=_optional_str(data.get("doctorName")),
            doctor_real_name=_optional_str(data.get("doctorRealName")),
            keyword_id=_optional_int(data.get("keywordId")),
            keyword=_optional_str(data.get("keyword")),
            search_word=_optional_str(data.get("searchWord")),
            comment_bank_item_id=_optional_int(data.get("commentBankItemId")),
            comment_content=_optional_str(data.get("commentContent")),
        )

    def claim_matched_doctor_comment(
        self,
        *,
        udid: str,
        doctor_id: int,
        publish_account: str,
    ) -> ClaimMatchedDoctorCommentResult:
        data = self._post(
            "/automation/tasks/matched-comment/claim",
            json={
                "udid": udid,
                "doctorId": doctor_id,
                "publishAccount": publish_account,
            },
        )
        return ClaimMatchedDoctorCommentResult(
            task_id=int(data["taskId"]),
            doctor_id=int(data["doctorId"]),
            doctor_name=str(data["doctorName"]),
            doctor_real_name=str(data.get("doctorRealName") or ""),
            keyword_id=int(data["keywordId"]),
            keyword=str(data["keyword"]),
            search_word=str(data["searchWord"]),
            comment_bank_item_id=int(data["commentBankItemId"]),
            comment_content=str(data["commentContent"]),
        )

    def start_task(
        self,
        *,
        task_item_id: int,
        udid: str,
        comment_bank_item_id: int,
        publish_account: str,
    ) -> StartTaskResult:
        data = self._post(
            f"/automation/tasks/{task_item_id}/start",
            json={
                "udid": udid,
                "commentBankItemId": comment_bank_item_id,
                "publishAccount": publish_account,
            },
        )
        return StartTaskResult(
            result_id=int(data["resultId"]),
            status=str(data["status"]),
        )

    def report_task(
        self,
        *,
        task_item_id: int,
        udid: str,
        result_id: int | None,
        comment_bank_item_id: int,
        publish_account: str,
        status: str,
        video_link: str | None = None,
        result_summary: str | None = None,
        fail_reason: str | None = None,
        screenshot_url: str | None = None,
        log_url: str | None = None,
    ) -> ReportTaskResult:
        data = self._post(
            f"/automation/tasks/{task_item_id}/report",
            json={
                "udid": udid,
                "resultId": result_id,
                "commentBankItemId": comment_bank_item_id,
                "publishAccount": publish_account,
                "status": status,
                "videoLink": video_link,
                "resultSummary": result_summary,
                "failReason": fail_reason,
                "screenshotUrl": screenshot_url,
                "logUrl": log_url,
            },
        )
        return ReportTaskResult(
            result_id=int(data["resultId"]),
            status=str(data["status"]),
        )

    def _post(self, path: str, json: dict[str, object]) -> dict[str, object]:
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.post(path, json=json)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AutomationApiError(str(exc)) from exc

        payload = response.json()
        if payload.get("code") != "OK":
            raise AutomationApiError(str(payload.get("message") or "backend api failed"))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AutomationApiError("backend api returned invalid data")
        return data

    def _get(self, path: str) -> dict[str, object]:
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.get(path)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AutomationApiError(str(exc)) from exc

        payload = response.json()
        if payload.get("code") != "OK":
            raise AutomationApiError(str(payload.get("message") or "backend api failed"))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AutomationApiError("backend api returned invalid data")
        return data

    def _get_list(self, path: str) -> list[object]:
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.get(path)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AutomationApiError(str(exc)) from exc

        payload = response.json()
        if payload.get("code") != "OK":
            raise AutomationApiError(str(payload.get("message") or "backend api failed"))
        data = payload.get("data")
        if not isinstance(data, list):
            raise AutomationApiError("backend api returned invalid list data")
        return data


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value))


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _parse_claim_task_doctors(value: object) -> list[ClaimTaskDoctorResult]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AutomationApiError("backend api returned invalid doctors data")
    doctors: list[ClaimTaskDoctorResult] = []
    for item in value:
        if not isinstance(item, dict):
            raise AutomationApiError("backend api returned invalid doctor item")
        doctors.append(
            ClaimTaskDoctorResult(
                doctor_id=int(item["doctorId"]),
                doctor_name=str(item["doctorName"]),
                doctor_real_name=str(item.get("doctorRealName") or ""),
            )
        )
    return doctors
