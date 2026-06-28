from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DailyTaskStatus = Literal["pending", "running", "completed", "stopped", "exception"]
DailyTaskDispatchStatus = Literal[
    "not_dispatched",
    "dispatching",
    "dispatched",
    "dispatch_failed",
]
MAX_DAILY_TASK_ITEM_COUNT = 999


class DailyTaskConfigPayload(BaseModel):
    doctor_id: int = Field(serialization_alias="doctorId", validation_alias="doctorId")
    keyword_id: int = Field(serialization_alias="keywordId", validation_alias="keywordId")
    count: int = Field(ge=1, le=MAX_DAILY_TASK_ITEM_COUNT)
    sort_order: int = Field(default=0, serialization_alias="sortOrder", validation_alias="sortOrder")


class DailyTaskCreatePayload(BaseModel):
    task_date: date = Field(serialization_alias="taskDate", validation_alias="taskDate")
    configs: list[DailyTaskConfigPayload] = Field(min_length=1)


class DailyTaskItemRead(BaseModel):
    id: int
    task_id: int = Field(serialization_alias="taskId")
    sort_order: int = Field(default=0, serialization_alias="sortOrder")
    doctor_id: int = Field(serialization_alias="doctorId")
    doctor_name: str = Field(serialization_alias="doctorName")
    doctor_province: str = Field(default="", serialization_alias="doctorProvince")
    doctor_provinces: list[str] = Field(default_factory=list, serialization_alias="doctorProvinces")
    keyword_id: int = Field(serialization_alias="keywordId")
    keyword: str
    remaining_comment_count: int = Field(default=0, serialization_alias="remainingCommentCount")
    target_count: int = Field(serialization_alias="targetCount")
    claimed_count: int = Field(serialization_alias="claimedCount")
    dispatched_count: int = Field(default=0, serialization_alias="dispatchedCount")
    success_count: int = Field(serialization_alias="successCount")
    failed_count: int = Field(serialization_alias="failedCount")
    status: DailyTaskStatus


class DailyTaskItemSortOrderUpdate(BaseModel):
    id: int
    sort_order: int = Field(ge=1, serialization_alias="sortOrder", validation_alias="sortOrder")

    model_config = ConfigDict(populate_by_name=True)


class DailyTaskItemSortOrderPayload(BaseModel):
    items: list[DailyTaskItemSortOrderUpdate] = Field(min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class DailyTaskRead(BaseModel):
    id: int
    task_date: date = Field(serialization_alias="taskDate")
    status: DailyTaskStatus
    dispatch_status: DailyTaskDispatchStatus = Field(serialization_alias="dispatchStatus")
    dispatch_started_at: datetime | None = Field(
        default=None, serialization_alias="dispatchStartedAt"
    )
    dispatch_finished_at: datetime | None = Field(
        default=None, serialization_alias="dispatchFinishedAt"
    )
    dispatch_error: str | None = Field(default=None, serialization_alias="dispatchError")
    total_count: int = Field(serialization_alias="totalCount")
    success_count: int = Field(serialization_alias="successCount")
    failed_count: int = Field(serialization_alias="failedCount")
    stopped_count: int = Field(serialization_alias="stoppedCount")
    created_by: str = Field(serialization_alias="createdBy")
    created_at: datetime = Field(serialization_alias="createdAt")
    started_at: datetime | None = Field(default=None, serialization_alias="startedAt")
    finished_at: datetime | None = Field(default=None, serialization_alias="finishedAt")
    items: list[DailyTaskItemRead]


class DailyTaskDispatchRead(BaseModel):
    task_id: int = Field(serialization_alias="taskId")
    dispatch_status: DailyTaskDispatchStatus = Field(serialization_alias="dispatchStatus")
    device_count: int = Field(serialization_alias="deviceCount")
    pool_item_count: int = Field(serialization_alias="poolItemCount")
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class DailyTaskDevicePoolTaskRead(BaseModel):
    id: int
    doctor_name: str = Field(serialization_alias="doctorName")
    doctor_real_name: str = Field(default="", serialization_alias="doctorRealName")
    keyword: str
    comment_content: str = Field(serialization_alias="commentContent")
    status: str


class DailyTaskDeviceDetailRead(BaseModel):
    device_id: int = Field(serialization_alias="deviceId")
    device_name: str = Field(serialization_alias="deviceName")
    device_province: str = Field(default="", serialization_alias="deviceProvince")
    assigned_count: int = Field(serialization_alias="assignedCount")
    claimed_count: int = Field(serialization_alias="claimedCount")
    success_count: int = Field(serialization_alias="successCount")
    failed_count: int = Field(serialization_alias="failedCount")
    tasks: list[DailyTaskDevicePoolTaskRead]


class DailyTaskDeviceDetailsRead(BaseModel):
    task_id: int = Field(serialization_alias="taskId")
    items: list[DailyTaskDeviceDetailRead]

    model_config = ConfigDict(populate_by_name=True)
