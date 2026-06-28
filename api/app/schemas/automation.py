from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AutomationRuntimeResponse(BaseModel):
    business_status: str = Field(serialization_alias="businessStatus")
    started_at: datetime | None = Field(default=None, serialization_alias="startedAt")
    stopped_at: datetime | None = Field(default=None, serialization_alias="stoppedAt")
    updated_at: datetime | None = Field(default=None, serialization_alias="updatedAt")
    remark: str = ""


class AutomationRuntimePayload(BaseModel):
    remark: str = Field(default="", max_length=255)
    force: bool = False


class AutomationServiceInfo(BaseModel):
    name: str
    status: str
    host: str | None = None
    port: int | None = None
    pid: int | None = None
    detail: str = ""
    device_name: str | None = Field(default=None, serialization_alias="deviceName")
    udid: str | None = None


class AutomationServiceStatusResponse(BaseModel):
    updated_at: datetime = Field(serialization_alias="updatedAt")
    services: dict[str, AutomationServiceInfo]
    appium_servers: list[AutomationServiceInfo] = Field(
        default_factory=list,
        serialization_alias="appiumServers",
    )


class DeviceHeartbeatPayload(BaseModel):
    udid: str = Field(min_length=1, max_length=128)
    device_name: str | None = Field(default=None, validation_alias="deviceName")
    system_port: int | None = Field(default=None, validation_alias="systemPort")
    runtime_status: str = Field(default="idle", validation_alias="runtimeStatus")
    remark: str = ""

    model_config = ConfigDict(str_strip_whitespace=True)


class DeviceHeartbeatResponse(BaseModel):
    device_id: int = Field(serialization_alias="deviceId")
    udid: str
    runtime_status: str = Field(serialization_alias="runtimeStatus")
    last_heartbeat_at: datetime = Field(serialization_alias="lastHeartbeatAt")


class AutomationDeviceConfigResponse(BaseModel):
    id: int
    name: str
    udid: str
    device_model: str = Field(default="huawei_nova_se6", serialization_alias="deviceModel")
    system_port: int = Field(serialization_alias="systemPort")
    enabled_status: str = Field(serialization_alias="enabledStatus")
    appium_server_url: str | None = Field(default=None, serialization_alias="appiumServerUrl")
    
    model_config = ConfigDict(str_strip_whitespace=True)


class ClaimTaskPayload(BaseModel):
    udid: str = Field(min_length=1, max_length=128)
    publish_account: str = Field(validation_alias="publishAccount", min_length=1, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)


class ClaimTaskResponse(BaseModel):
    has_task: bool = Field(serialization_alias="hasTask")
    reason: str | None = None
    task_id: int | None = Field(default=None, serialization_alias="taskId")
    task_item_id: int | None = Field(default=None, serialization_alias="taskItemId")
    doctor_id: int | None = Field(default=None, serialization_alias="doctorId")
    doctor_name: str | None = Field(default=None, serialization_alias="doctorName")
    doctor_real_name: str | None = Field(default=None, serialization_alias="doctorRealName")
    keyword_id: int | None = Field(default=None, serialization_alias="keywordId")
    keyword: str | None = None
    search_word: str | None = Field(default=None, serialization_alias="searchWord")
    comment_bank_item_id: int | None = Field(default=None, serialization_alias="commentBankItemId")
    comment_content: str | None = Field(default=None, serialization_alias="commentContent")


class StartTaskPayload(BaseModel):
    udid: str = Field(min_length=1, max_length=128)
    comment_bank_item_id: int = Field(validation_alias="commentBankItemId")
    publish_account: str = Field(validation_alias="publishAccount", min_length=1, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)


class StartTaskResponse(BaseModel):
    result_id: int = Field(serialization_alias="resultId")
    status: str


class ReportTaskPayload(BaseModel):
    udid: str = Field(min_length=1, max_length=128)
    result_id: int | None = Field(default=None, validation_alias="resultId")
    comment_bank_item_id: int = Field(validation_alias="commentBankItemId")
    publish_account: str = Field(validation_alias="publishAccount", min_length=1, max_length=100)
    status: str = Field(pattern="^(success|failed)$")
    video_link: str | None = Field(default=None, validation_alias="videoLink")
    result_summary: str | None = Field(default=None, validation_alias="resultSummary")
    fail_reason: str | None = Field(default=None, validation_alias="failReason")
    screenshot_url: str | None = Field(default=None, validation_alias="screenshotUrl")
    log_url: str | None = Field(default=None, validation_alias="logUrl")


class ReportTaskResponse(BaseModel):
    result_id: int = Field(serialization_alias="resultId")
    status: str
