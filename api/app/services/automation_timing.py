from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.automation_timing import AutomationTimingSetting
from app.schemas.automation_timing import (
    AutomationTimingSettingItem,
    AutomationTimingSettingsPayload,
)


@dataclass(frozen=True)
class DefaultTimingSetting:
    key: str
    label: str
    min_seconds: float
    max_seconds: float


DEFAULT_TIMING_SETTINGS: tuple[DefaultTimingSetting, ...] = (
    DefaultTimingSetting("watch_video", "视频观看时长", 15, 300),
    DefaultTimingSetting("after_like", "点赞后", 3, 20),
    DefaultTimingSetting("after_favorite", "收藏后", 3, 20),
    DefaultTimingSetting("comment_pre_input_click", "点击评论输入框后", 2, 5),
    DefaultTimingSetting("comment_focus", "重连后聚焦评论输入框", 2, 5),
    DefaultTimingSetting("after_comment_input", "评论输入后", 5, 5),
    DefaultTimingSetting("before_send_comment", "发送评论前", 0, 0),
    DefaultTimingSetting("single_device_daily_task_limit", "单设备每天最大任务量", 20, 20),
    DefaultTimingSetting("runtime_start_time", "运行开始时间", 8 * 60, 8 * 60),
    DefaultTimingSetting("runtime_end_time", "运行结束时间", 23 * 60, 23 * 60),
    DefaultTimingSetting("douyin_exit_interval", "退出抖音时间（分钟）", 20, 20),
    DefaultTimingSetting("douyin_reopen_interval", "重启抖音时间（分钟）", 20, 20),
)

DEPRECATED_TIMING_KEYS = {
    "runtime_start_hour",
    "runtime_end_hour",
    "before_input",
    "after_input",
    "after_search",
    "douyin_restart_interval",
}


def list_automation_timing_settings(db: Session) -> list[AutomationTimingSettingItem]:
    ensure_default_timing_settings(db)
    rows = db.scalars(
        select(AutomationTimingSetting)
        .where(AutomationTimingSetting.key.not_in(DEPRECATED_TIMING_KEYS))
        .order_by(AutomationTimingSetting.id.asc())
    ).all()
    return [_to_item(row) for row in rows]


def get_single_device_daily_task_limit(db: Session) -> int:
    ensure_default_timing_settings(db)
    row = db.scalar(
        select(AutomationTimingSetting).where(
            AutomationTimingSetting.key == "single_device_daily_task_limit"
        )
    )
    if row is None:
        return 20
    return max(0, int(row.max_seconds))


def update_automation_timing_settings(
    db: Session, payload: AutomationTimingSettingsPayload
) -> list[AutomationTimingSettingItem]:
    ensure_default_timing_settings(db)
    known_keys = {item.key for item in DEFAULT_TIMING_SETTINGS}
    rows_by_key = {
        row.key: row for row in db.scalars(select(AutomationTimingSetting)).all()
    }

    for item in payload.items:
        if item.key not in known_keys:
            raise AppException(
                f"未知时间设置项：{item.key}",
                code="AUTOMATION_TIMING_KEY_INVALID",
                status_code=400,
            )
        if item.min_seconds > item.max_seconds:
            raise AppException(
                "最小时间不能大于最大时间",
                code="AUTOMATION_TIMING_RANGE_INVALID",
                status_code=400,
            )
        row = rows_by_key[item.key]
        row.min_seconds = item.min_seconds
        row.max_seconds = item.max_seconds
        db.add(row)

    db.commit()
    return list_automation_timing_settings(db)


def reset_automation_timing_settings(db: Session) -> list[AutomationTimingSettingItem]:
    rows_by_key = {
        row.key: row for row in db.scalars(select(AutomationTimingSetting)).all()
    }
    for item in DEFAULT_TIMING_SETTINGS:
        row = rows_by_key.get(item.key)
        if row is None:
            row = AutomationTimingSetting(key=item.key, label=item.label)
        row.label = item.label
        row.min_seconds = item.min_seconds
        row.max_seconds = item.max_seconds
        db.add(row)
    db.commit()
    return list_automation_timing_settings(db)


def ensure_default_timing_settings(db: Session) -> None:
    existing_by_key = {
        row.key: row for row in db.scalars(select(AutomationTimingSetting)).all()
    }
    changed = False
    for key in DEPRECATED_TIMING_KEYS:
        row = existing_by_key.get(key)
        if row is not None:
            db.delete(row)
            changed = True
    for item in DEFAULT_TIMING_SETTINGS:
        row = existing_by_key.get(item.key)
        if row is None:
            db.add(
                AutomationTimingSetting(
                    key=item.key,
                    label=item.label,
                    min_seconds=item.min_seconds,
                    max_seconds=item.max_seconds,
                )
            )
            changed = True
        elif row.label != item.label:
            row.label = item.label
            db.add(row)
            changed = True
    if changed:
        db.commit()


def _to_item(row: AutomationTimingSetting) -> AutomationTimingSettingItem:
    return AutomationTimingSettingItem(
        id=row.id,
        key=row.key,
        label=row.label,
        min_seconds=row.min_seconds,
        max_seconds=row.max_seconds,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
