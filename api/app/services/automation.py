import logging
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.datetime_utils import now_beijing
from app.core.exceptions import AppException
from app.models.automation_runtime import AutomationRuntime
from app.models.automation_result import AutomationResult
from app.models.comment_bank import CommentBankItem
from app.models.daily_task import DailyTask, DailyTaskItem
from app.models.device import Device
from app.models.device_action import DeviceDoctorActionRecord
from app.models.device_task_pool import DeviceTaskPoolItem
from app.models.doctor import Doctor, DoctorKeyword
from app.models.doctor_province import DoctorProvince
from app.schemas.automation import (
    AutomationDeviceConfigResponse,
    AutomationRuntimePayload,
    AutomationRuntimeResponse,
    ClaimTaskPayload,
    ClaimTaskResponse,
    DeviceHeartbeatPayload,
    DeviceHeartbeatResponse,
    ReportTaskPayload,
    ReportTaskResponse,
    StartTaskPayload,
    StartTaskResponse,
)
from app.services.daily_tasks import refresh_dispatched_task_progress
from app.services.automation_timing import get_single_device_daily_task_limit


RUNTIME_SINGLETON_ID = 1
POOL_ACTIVE_STATUSES = ("pending", "claimed", "running")
logger = logging.getLogger(__name__)


def get_runtime_state(db: Session) -> AutomationRuntimeResponse:
    runtime = _get_or_create_runtime(db)
    return _to_runtime_response(runtime)


def start_runtime(db: Session, payload: AutomationRuntimePayload) -> AutomationRuntimeResponse:
    runtime = _get_or_create_runtime(db)
    now = now_beijing()
    runtime.business_status = "running"
    runtime.started_at = runtime.started_at or now
    runtime.stopped_at = None
    runtime.remark = payload.remark
    db.add(runtime)
    db.commit()
    db.refresh(runtime)
    return _to_runtime_response(runtime)


def stop_runtime(db: Session, payload: AutomationRuntimePayload) -> AutomationRuntimeResponse:
    runtime = _get_or_create_runtime(db)
    runtime.business_status = "stopped"
    runtime.stopped_at = now_beijing()
    runtime.remark = payload.remark
    db.add(runtime)
    db.commit()
    db.refresh(runtime)
    return _to_runtime_response(runtime)


def auto_stop_runtime(db: Session, payload: AutomationRuntimePayload) -> AutomationRuntimeResponse:
    runtime = _get_or_create_runtime(db)
    if not payload.force and _has_running_work(db):
        return _to_runtime_response(runtime)
    return stop_runtime(db, payload)


def _has_running_work(db: Session) -> bool:
    running_task_id = db.scalar(select(DailyTask.id).where(DailyTask.status == "running").limit(1))
    if running_task_id is not None:
        return True
    running_result_id = db.scalar(
        select(AutomationResult.id)
        .join(DailyTask, DailyTask.id == AutomationResult.task_id)
        .where(AutomationResult.status == "running")
        .where(DailyTask.status == "running")
        .limit(1)
    )
    return running_result_id is not None


def _get_or_create_runtime(db: Session) -> AutomationRuntime:
    runtime = db.get(AutomationRuntime, RUNTIME_SINGLETON_ID)
    if runtime is not None:
        return runtime
    runtime = AutomationRuntime(id=RUNTIME_SINGLETON_ID, business_status="stopped")
    db.add(runtime)
    db.commit()
    db.refresh(runtime)
    return runtime


def _to_runtime_response(runtime: AutomationRuntime) -> AutomationRuntimeResponse:
    return AutomationRuntimeResponse(
        business_status=runtime.business_status,
        started_at=runtime.started_at,
        stopped_at=runtime.stopped_at,
        updated_at=runtime.updated_at,
        remark=runtime.remark,
    )


def get_enabled_device_by_udid(db: Session, udid: str) -> Device:
    normalized_udid = udid.strip()
    device = db.scalar(select(Device).where(Device.udid == normalized_udid))
    if device is None:
        device = db.scalar(select(Device).where(func.trim(Device.udid) == normalized_udid))
    if device is None:
        raise AppException(
            "设备不存在，请先上报心跳",
            code="DEVICE_NOT_FOUND",
            status_code=404,
        )
    if device.enabled_status != "enabled":
        raise AppException("设备已禁用", code="DEVICE_DISABLED", status_code=403)
    if device.udid != normalized_udid:
        device.udid = normalized_udid
        db.add(device)
        db.commit()
        db.refresh(device)
    return device


def list_enabled_device_configs(db: Session) -> list[AutomationDeviceConfigResponse]:
    devices = db.scalars(
        select(Device).where(Device.enabled_status == "enabled").order_by(Device.id.asc())
    ).all()
    return [
        AutomationDeviceConfigResponse(
            id=device.id,
            name=device.name,
            udid=device.udid.strip(),
            device_model=device.device_model or "huawei_nova_se6",
            system_port=device.system_port,
            enabled_status=device.enabled_status,
            appium_server_url=device.appium_server_url,
        )
        for device in devices
    ]


def heartbeat_device(db: Session, payload: DeviceHeartbeatPayload) -> DeviceHeartbeatResponse:
    now = now_beijing()
    udid = payload.udid.strip()
    device = db.scalar(select(Device).where(Device.udid == udid))
    if device is None:
        device = db.scalar(select(Device).where(func.trim(Device.udid) == udid))
    if device is None:
        if payload.system_port is None:
            raise AppException(
                "新设备首次心跳必须提供 systemPort",
                code="SYSTEM_PORT_REQUIRED",
                status_code=400,
            )
        device = Device(
            name=payload.device_name or udid,
            udid=udid,
            system_port=payload.system_port,
            enabled_status="enabled",
            runtime_status=payload.runtime_status,
            last_heartbeat_at=now,
            remark=payload.remark,
        )
    else:
        if device.udid != udid:
            device.udid = udid
        if payload.device_name:
            device.name = payload.device_name
        if payload.system_port is not None:
            device.system_port = payload.system_port
        device.runtime_status = payload.runtime_status
        device.last_heartbeat_at = now
        if payload.remark:
            device.remark = payload.remark

    db.add(device)
    db.commit()
    db.refresh(device)
    return DeviceHeartbeatResponse(
        device_id=device.id,
        udid=device.udid,
        runtime_status=device.runtime_status,
        last_heartbeat_at=device.last_heartbeat_at,
    )


def claim_task(db: Session, payload: ClaimTaskPayload) -> ClaimTaskResponse:
    device = get_enabled_device_by_udid(db, payload.udid)
    today = date.today()
    daily_task_limit = get_single_device_daily_task_limit(db)
    if daily_task_limit > 0 and _device_claimed_count_for_date(db, device.id, today) >= daily_task_limit:
        return ClaimTaskResponse(has_task=False, reason="daily_limit_reached")

    pool_item = db.scalar(
        _with_row_lock(
            db,
            select(DeviceTaskPoolItem)
            .join(DailyTask, DailyTask.id == DeviceTaskPoolItem.task_id)
            .where(DailyTask.task_date == today)
            .where(DailyTask.status.in_(["pending", "running"]))
            .where(DailyTask.dispatch_status == "dispatched")
            .where(DeviceTaskPoolItem.device_id == device.id)
            .where(DeviceTaskPoolItem.status == "pending")
            .order_by(
                DailyTask.id.asc(),
                DeviceTaskPoolItem.pool_round.asc(),
                DeviceTaskPoolItem.pool_order.asc(),
                DeviceTaskPoolItem.id.asc(),
            )
            .limit(1)
            .execution_options(populate_existing=True),
        )
    )
    if pool_item is None:
        return ClaimTaskResponse(has_task=False, reason=_claim_no_task_reason(db, device.id, today))

    return _claim_task_pool_item(db, payload, device, pool_item)


def _claim_task_pool_item(
    db: Session,
    payload: ClaimTaskPayload,
    device: Device,
    pool_item: DeviceTaskPoolItem,
) -> ClaimTaskResponse:
    task = db.get(DailyTask, pool_item.task_id)
    item = db.get(DailyTaskItem, pool_item.task_item_id)
    doctor = db.get(Doctor, pool_item.doctor_id)
    keyword = db.get(DoctorKeyword, pool_item.keyword_id)
    comment = db.get(CommentBankItem, pool_item.comment_bank_item_id)
    if (
        task is None
        or item is None
        or doctor is None
        or keyword is None
        or comment is None
        or task.status not in {"pending", "running"}
        or task.dispatch_status != "dispatched"
        or item.status not in {"pending", "running"}
        or doctor.status != "active"
        or keyword.status != "active"
    ):
        pool_item.status = "skipped"
        pool_item.finished_at = now_beijing()
        pool_item.fail_reason = "invalid task pool item"
        db.add(pool_item)
        db.commit()
        return ClaimTaskResponse(has_task=False, reason="device_pool_empty")

    now = now_beijing()
    comment.status = "used"
    comment.used_device_id = device.id
    comment.used_account = payload.publish_account
    comment.used_task_id = task.id
    comment.used_at = comment.used_at or now

    pool_item.status = "claimed"
    pool_item.claimed_at = now

    item.claimed_count += 1
    item.status = "running"
    task.status = "running"
    task.started_at = task.started_at or now
    device.runtime_status = "running"
    device.last_heartbeat_at = now

    db.add_all([comment, pool_item, item, task, device])
    db.commit()
    return ClaimTaskResponse(
        has_task=True,
        task_id=task.id,
        task_item_id=item.id,
        doctor_id=doctor.id,
        doctor_name=doctor.name,
        doctor_real_name=doctor.real_name,
        keyword_id=keyword.id,
        keyword=keyword.keyword,
        search_word=comment.search_word,
        comment_bank_item_id=comment.id,
        comment_content=comment.content,
    )


def _claim_no_task_reason(db: Session, device_id: int, task_date: date) -> str:
    active_task_ids = db.scalars(
        select(DailyTask.id)
        .where(DailyTask.task_date == task_date)
        .where(DailyTask.status.in_(["pending", "running"]))
    ).all()
    if not active_task_ids:
        dispatched_task_ids = db.scalars(
            select(DailyTask.id)
            .where(DailyTask.task_date == task_date)
            .where(DailyTask.dispatch_status == "dispatched")
        ).all()
        if dispatched_task_ids and not _has_active_pool_items(db, dispatched_task_ids):
            return "task_completed"
        return "no_task"

    dispatched_task_ids = db.scalars(
        select(DailyTask.id)
        .where(DailyTask.id.in_(active_task_ids))
        .where(DailyTask.dispatch_status == "dispatched")
    ).all()
    if not dispatched_task_ids:
        return "not_dispatched"

    device_pool_count = (
        db.scalar(
            select(func.count(DeviceTaskPoolItem.id))
            .where(DeviceTaskPoolItem.task_id.in_(dispatched_task_ids))
            .where(DeviceTaskPoolItem.device_id == device_id)
        )
        or 0
    )
    if device_pool_count > 0 and not _has_active_pool_items(db, dispatched_task_ids):
        return "task_completed"
    return "device_pool_empty"


def _has_active_pool_items(db: Session, task_ids: list[int]) -> bool:
    return (
        db.scalar(
            select(func.count(DeviceTaskPoolItem.id))
            .where(DeviceTaskPoolItem.task_id.in_(task_ids))
            .where(DeviceTaskPoolItem.status.in_(POOL_ACTIVE_STATUSES))
        )
        or 0
    ) > 0


def _claim_task_dynamic_legacy(db: Session, payload: ClaimTaskPayload) -> ClaimTaskResponse:
    """Legacy dynamic claim path kept for rollback while V2 task-pool claim stabilizes."""
    device = get_enabled_device_by_udid(db, payload.udid)
    today = date.today()
    daily_task_limit = get_single_device_daily_task_limit(db)
    if daily_task_limit > 0 and _device_claimed_count_for_date(db, device.id, today) >= daily_task_limit:
        return ClaimTaskResponse(has_task=False, reason="daily_limit_reached")

    rows = db.execute(
        select(DailyTaskItem.id)
        .join(DailyTask, DailyTask.id == DailyTaskItem.task_id)
        .join(Doctor, Doctor.id == DailyTaskItem.doctor_id)
        .join(DoctorKeyword, DoctorKeyword.id == DailyTaskItem.keyword_id)
        .where(DailyTask.task_date == today)
        .where(DailyTask.status.in_(["pending", "running"]))
        .where(DailyTaskItem.status.in_(["pending", "running"]))
        .where(DailyTaskItem.claimed_count < DailyTaskItem.target_count)
        .where(Doctor.status == "active")
        .where(DoctorKeyword.status == "active")
        .order_by(DailyTask.id.asc(), DailyTaskItem.sort_order.asc(), DailyTaskItem.id.asc())
    ).all()

    for (item_id,) in rows:
        locked_item = db.scalar(
            _with_row_lock(
                db,
                select(DailyTaskItem)
                .where(DailyTaskItem.id == item_id)
                .where(DailyTaskItem.status.in_(["pending", "running"]))
                .where(DailyTaskItem.claimed_count < DailyTaskItem.target_count)
                .execution_options(populate_existing=True),
                skip_locked=False,
            )
        )
        if locked_item is None:
            continue

        item = locked_item
        task = db.get(DailyTask, item.task_id)
        doctor = db.get(Doctor, item.doctor_id)
        keyword = db.get(DoctorKeyword, item.keyword_id)
        if (
            task is None
            or doctor is None
            or keyword is None
            or task.status not in {"pending", "running"}
            or doctor.status != "active"
            or keyword.status != "active"
        ):
            db.rollback()
            continue

        if not _device_matches_doctor_region(db, device, doctor):
            db.rollback()
            continue

        already_acted = db.scalar(
            select(DeviceDoctorActionRecord.id).where(
                DeviceDoctorActionRecord.device_id == device.id,
                DeviceDoctorActionRecord.doctor_id == item.doctor_id,
                DeviceDoctorActionRecord.keyword_id == item.keyword_id,
                DeviceDoctorActionRecord.action_type == "comment",
                DeviceDoctorActionRecord.action_date == task.task_date,
            )
        )
        if already_acted:
            db.rollback()
            continue

        comment_stmt = (
            select(CommentBankItem)
            .where(CommentBankItem.doctor_id == item.doctor_id)
            .where(CommentBankItem.keyword_id == item.keyword_id)
            .where(CommentBankItem.status == "unused")
            .order_by(CommentBankItem.id.asc())
            .limit(1)
        )
        comment = db.scalar(_with_row_lock(db, comment_stmt))
        if comment is None:
            db.rollback()
            continue

        now = now_beijing()
        comment.status = "used"
        comment.used_device_id = device.id
        comment.used_account = payload.publish_account
        comment.used_task_id = task.id
        comment.used_at = now

        item.claimed_count += 1
        item.status = "running"
        task.status = "running"
        task.started_at = task.started_at or now
        device.runtime_status = "running"
        device.last_heartbeat_at = now

        db.add_all([comment, item, task, device])
        db.commit()
        return ClaimTaskResponse(
            has_task=True,
            task_id=task.id,
            task_item_id=item.id,
            doctor_id=doctor.id,
            doctor_name=doctor.name,
            doctor_real_name=doctor.real_name,
            keyword_id=keyword.id,
            keyword=keyword.keyword,
            search_word=comment.search_word,
            comment_bank_item_id=comment.id,
            comment_content=comment.content,
        )

    db.rollback()
    return ClaimTaskResponse(has_task=False)


def _device_claimed_count_for_date(db: Session, device_id: int, task_date: date) -> int:
    return (
        db.scalar(
            select(func.count(CommentBankItem.id))
            .join(DailyTask, DailyTask.id == CommentBankItem.used_task_id)
            .where(CommentBankItem.used_device_id == device_id)
            .where(DailyTask.task_date == task_date)
        )
        or 0
    )


def _device_matches_doctor_region(db: Session, device: Device, doctor: Doctor) -> bool:
    device_province = (device.province or "").strip()
    if not device_province:
        return False
    return (
        db.scalar(
            select(DoctorProvince.id)
            .where(DoctorProvince.doctor_id == doctor.id)
            .where(DoctorProvince.province == device_province)
            .limit(1)
        )
        is not None
    )


def _with_row_lock(db: Session, statement, *, skip_locked: bool = True):
    if skip_locked and _supports_skip_locked(db):
        return statement.with_for_update(skip_locked=True)
    return statement.with_for_update()


def _supports_skip_locked(db: Session) -> bool:
    bind = db.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == "mysql":
        version_info = getattr(bind.dialect, "server_version_info", None)
        if not version_info:
            return False
        return tuple(version_info) >= (8, 0, 1)
    return dialect_name in {"postgresql", "oracle"}


def _get_task_item_or_404(db: Session, task_item_id: int) -> DailyTaskItem:
    item = db.get(DailyTaskItem, task_item_id)
    if item is None:
        raise AppException("任务明细不存在", code="TASK_ITEM_NOT_FOUND", status_code=404)
    return item


def _get_claimed_comment_or_404(
    db: Session, comment_bank_item_id: int, task_item: DailyTaskItem, device: Device
) -> CommentBankItem:
    comment = db.get(CommentBankItem, comment_bank_item_id)
    if comment is None:
        raise AppException(
            "评论词库不存在",
            code="COMMENT_BANK_ITEM_NOT_FOUND",
            status_code=404,
        )
    if comment.doctor_id != task_item.doctor_id or comment.keyword_id != task_item.keyword_id:
        raise AppException(
            "评论词库与任务明细不匹配", code="COMMENT_TASK_MISMATCH", status_code=400
        )
    if comment.used_device_id not in {None, device.id}:
        raise AppException(
            "评论词库已被其他设备领取", code="COMMENT_ALREADY_CLAIMED", status_code=409
        )
    return comment


def _get_claimed_pool_item_or_404(
    db: Session,
    task_item_id: int,
    comment_bank_item_id: int,
    device_id: int,
) -> DeviceTaskPoolItem:
    pool_item = db.scalar(
        _with_row_lock(
            db,
            select(DeviceTaskPoolItem)
            .where(DeviceTaskPoolItem.task_item_id == task_item_id)
            .where(DeviceTaskPoolItem.comment_bank_item_id == comment_bank_item_id)
            .where(DeviceTaskPoolItem.device_id == device_id)
            .execution_options(populate_existing=True),
            skip_locked=False,
        )
    )
    if pool_item is None:
        raise AppException("任务池记录不存在", code="TASK_POOL_ITEM_NOT_FOUND", status_code=404)
    if pool_item.status not in {"claimed", "running"}:
        raise AppException(
            "任务池记录状态不允许开始执行",
            code="TASK_POOL_ITEM_STATUS_INVALID",
            status_code=409,
        )
    return pool_item


def start_task(db: Session, task_item_id: int, payload: StartTaskPayload) -> StartTaskResponse:
    device = get_enabled_device_by_udid(db, payload.udid)
    item = _get_task_item_or_404(db, task_item_id)
    comment = _get_claimed_comment_or_404(db, payload.comment_bank_item_id, item, device)
    pool_item = _get_claimed_pool_item_or_404(db, item.id, comment.id, device.id)
    existing_result = db.scalar(
        select(AutomationResult).where(
            AutomationResult.task_item_id == item.id,
            AutomationResult.device_id == device.id,
            AutomationResult.comment_bank_item_id == comment.id,
            AutomationResult.status == "running",
        )
    )
    if existing_result is not None:
        now = now_beijing()
        pool_item.status = "running"
        pool_item.started_at = pool_item.started_at or now
        pool_item.result_id = existing_result.id
        db.add(pool_item)
        db.commit()
        return StartTaskResponse(result_id=existing_result.id, status=existing_result.status)

    now = now_beijing()
    result = AutomationResult(
        task_id=item.task_id,
        task_item_id=item.id,
        doctor_id=item.doctor_id,
        keyword_id=item.keyword_id,
        device_id=device.id,
        comment_bank_item_id=comment.id,
        publish_account=payload.publish_account,
        comment_content=comment.content,
        video_link=None,
        status="running",
        result_summary=None,
        fail_reason=None,
        started_at=now,
        finished_at=None,
        screenshot_url=None,
        log_url=None,
    )
    item.status = "running"
    pool_item.status = "running"
    pool_item.started_at = pool_item.started_at or now
    device.runtime_status = "running"
    device.last_heartbeat_at = now
    db.add_all([result, pool_item, item, device])
    db.commit()
    db.refresh(result)
    pool_item.result_id = result.id
    db.add(pool_item)
    db.commit()
    return StartTaskResponse(result_id=result.id, status=result.status)


def report_task(db: Session, task_item_id: int, payload: ReportTaskPayload) -> ReportTaskResponse:
    device = get_enabled_device_by_udid(db, payload.udid)
    item = _get_task_item_or_404(db, task_item_id)
    task = db.get(DailyTask, item.task_id)
    if task is None:
        raise AppException("每日任务不存在", code="DAILY_TASK_NOT_FOUND", status_code=404)
    comment = _get_claimed_comment_or_404(db, payload.comment_bank_item_id, item, device)
    pool_item = _get_claimed_pool_item_or_404(db, item.id, comment.id, device.id)

    result = db.get(AutomationResult, payload.result_id) if payload.result_id else None
    if result is None:
        result = db.scalar(
            select(AutomationResult).where(
                AutomationResult.task_item_id == item.id,
                AutomationResult.device_id == device.id,
                AutomationResult.comment_bank_item_id == comment.id,
            )
        )
    if result is None:
        result = AutomationResult(
            task_id=item.task_id,
            task_item_id=item.id,
            doctor_id=item.doctor_id,
            keyword_id=item.keyword_id,
            device_id=device.id,
            comment_bank_item_id=comment.id,
            publish_account=payload.publish_account,
            comment_content=comment.content,
            status="running",
            started_at=now_beijing(),
        )

    old_status = result.status
    now = now_beijing()
    result.publish_account = payload.publish_account
    result.video_link = payload.video_link
    result.status = payload.status
    result.result_summary = payload.result_summary
    result.fail_reason = payload.fail_reason
    result.finished_at = now
    result.screenshot_url = payload.screenshot_url
    result.log_url = payload.log_url
    db.add(result)
    db.flush()

    comment.status = "used"
    comment.used_device_id = device.id
    comment.used_account = payload.publish_account
    comment.used_task_id = task.id
    comment.used_at = comment.used_at or now

    pool_item.status = payload.status
    pool_item.finished_at = now
    pool_item.result_id = result.id
    pool_item.fail_reason = payload.fail_reason if payload.status == "failed" else None
    logger.info(
        "report task pool item updated: pool_item_id=%s device_id=%s task_item_id=%s comment_bank_item_id=%s status=%s",
        pool_item.id,
        device.id,
        item.id,
        comment.id,
        payload.status,
    )

    _apply_result_count(item, old_status, payload.status)
    if item.success_count + item.failed_count >= item.target_count:
        item.status = "completed"
    else:
        item.status = "running"
    refresh_dispatched_task_progress(db, task)

    action_record = db.scalar(
        select(DeviceDoctorActionRecord).where(
            DeviceDoctorActionRecord.device_id == device.id,
            DeviceDoctorActionRecord.doctor_id == item.doctor_id,
            DeviceDoctorActionRecord.keyword_id == item.keyword_id,
            DeviceDoctorActionRecord.action_type == "comment",
            DeviceDoctorActionRecord.action_date == task.task_date,
        )
    )
    if action_record is None:
        action_record = DeviceDoctorActionRecord(
            device_id=device.id,
            doctor_id=item.doctor_id,
            keyword_id=item.keyword_id,
            task_id=task.id,
            action_type="comment",
            action_date=task.task_date,
            status=payload.status,
            acted_at=now,
        )
    action_record.task_id = task.id
    action_record.result_id = result.id if result.id else None
    action_record.status = payload.status
    action_record.action_date = task.task_date
    action_record.acted_at = now

    device.runtime_status = "idle"
    device.last_heartbeat_at = now
    db.add_all([result, comment, pool_item, item, task, action_record, device])
    db.commit()
    db.refresh(result)
    if action_record.result_id is None:
        action_record.result_id = result.id
        db.add(action_record)
        db.commit()
    return ReportTaskResponse(result_id=result.id, status=result.status)


def _apply_result_count(item: DailyTaskItem, old_status: str, new_status: str) -> None:
    if old_status == new_status and old_status in {"success", "failed"}:
        return
    if old_status == "success":
        item.success_count = max(item.success_count - 1, 0)
    if old_status == "failed":
        item.failed_count = max(item.failed_count - 1, 0)
    if new_status == "success":
        item.success_count += 1
    if new_status == "failed":
        item.failed_count += 1
