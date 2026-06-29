from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

AutomationResultStatus = Literal["success", "failed"]
CommentRecheckStatus = Literal[
    "not_checked",
    "queued",
    "checking",
    "exists",
    "missing",
    "failed",
    "login_required",
    "captcha_required",
]


class AutomationResultItemRead(BaseModel):
    id: int
    task_id: int = Field(serialization_alias="taskId")
    task_date: date = Field(serialization_alias="taskDate")
    doctor_id: int = Field(serialization_alias="doctorId")
    doctor_name: str = Field(serialization_alias="doctorName")
    keyword_id: int | None = Field(default=None, serialization_alias="keywordId")
    keyword: str = ""
    device_id: int = Field(serialization_alias="deviceId")
    device_name: str = Field(serialization_alias="deviceName")
    publish_account: str = Field(serialization_alias="publishAccount")
    comment_content: str = Field(serialization_alias="commentContent")
    video_link: str | None = Field(default=None, serialization_alias="videoLink")
    status: AutomationResultStatus
    comment_recheck_status: CommentRecheckStatus | None = Field(
        default=None, serialization_alias="commentRecheckStatus"
    )
    comment_recheck_fail_reason: str | None = Field(
        default=None, serialization_alias="commentRecheckFailReason"
    )
    comment_recheck_checked_at: datetime | None = Field(
        default=None, serialization_alias="commentRecheckCheckedAt"
    )
    result_summary: str | None = Field(default=None, serialization_alias="resultSummary")
    fail_reason: str | None = Field(default=None, serialization_alias="failReason")
    started_at: datetime = Field(serialization_alias="startedAt")
    finished_at: datetime | None = Field(default=None, serialization_alias="finishedAt")
    screenshot_url: str | None = Field(default=None, serialization_alias="screenshotUrl")
    log_url: str | None = Field(default=None, serialization_alias="logUrl")
