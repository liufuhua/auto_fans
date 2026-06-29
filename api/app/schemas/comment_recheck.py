from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

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


class CommentRecheckItemRead(BaseModel):
    id: int
    automation_result_id: int = Field(serialization_alias="automationResultId")
    task_id: int = Field(serialization_alias="taskId")
    task_date: date = Field(serialization_alias="taskDate")
    doctor_id: int = Field(serialization_alias="doctorId")
    doctor_name: str = Field(serialization_alias="doctorName")
    keyword_id: int | None = Field(default=None, serialization_alias="keywordId")
    keyword: str = ""
    device_name: str = Field(serialization_alias="deviceName")
    publish_account: str = Field(serialization_alias="publishAccount")
    comment_content: str = Field(serialization_alias="commentContent")
    video_link: str | None = Field(default=None, serialization_alias="videoLink")
    status: CommentRecheckStatus
    checked_at: datetime | None = Field(default=None, serialization_alias="checkedAt")
    fail_reason: str | None = Field(default=None, serialization_alias="failReason")


class StartCommentRecheckPayload(BaseModel):
    ids: list[int] = Field(min_length=1)


class StartCommentRecheckResponse(BaseModel):
    submitted: int
    skipped: int = 0
    login_required: bool = Field(default=False, serialization_alias="loginRequired")


class CommentRecheckLoginStatusRead(BaseModel):
    logged_in: bool = Field(serialization_alias="loggedIn")
    session_id: str | None = Field(default=None, serialization_alias="sessionId")
    qr_code_url: str | None = Field(default=None, serialization_alias="qrCodeUrl")
    message: str | None = None


class ConfirmCommentRecheckLoginPayload(BaseModel):
    session_id: str | None = Field(
        default=None,
        validation_alias="sessionId",
        serialization_alias="sessionId",
    )
