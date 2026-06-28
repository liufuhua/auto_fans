from datetime import UTC, date, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.comment_bank import CommentBankItem
from app.models.daily_task import DailyTask, DailyTaskItem
from app.models.device import Device
from app.models.device_action import DeviceDoctorActionRecord
from app.models.device_task_pool import DeviceTaskPoolItem
from app.models.doctor import Doctor, DoctorKeyword
from app.models.doctor_province import DoctorProvince
from app.schemas.common import PageParams, PageResult
from app.schemas.daily_task import (
    DailyTaskCreatePayload,
    DailyTaskDeviceDetailRead,
    DailyTaskDeviceDetailsRead,
    DailyTaskDevicePoolTaskRead,
    DailyTaskDispatchRead,
    DailyTaskItemRead,
    DailyTaskItemSortOrderPayload,
    DailyTaskRead,
)
from app.services.automation_timing import get_single_device_daily_task_limit


TASK_POOL_ACTIVE_STATUSES = {"pending", "claimed", "running"}
TASK_POOL_TERMINAL_STATUSES = {"success", "failed", "skipped", "cancelled"}


def _task_statement() -> Select[tuple[DailyTask]]:
    return select(DailyTask)


def _apply_daily_task_filters(
    statement: Select[tuple[DailyTask]], task_date: str | None, status: str | None
) -> Select[tuple[DailyTask]]:
    if task_date:
        statement = statement.where(DailyTask.task_date == task_date)
    if status:
        statement = statement.where(DailyTask.status == status)
    return statement


def _calculate_task_status(task: DailyTask) -> str:
    if task.status == "stopped":
        return "stopped"
    if task.total_count > 0 and task.success_count + task.failed_count >= task.total_count:
        return "completed"
    return task.status


def refresh_task_progress(task: DailyTask) -> None:
    task.success_count = sum(item.success_count for item in task.items)
    task.failed_count = sum(item.failed_count for item in task.items)
    if task.status == "stopped":
        task.stopped_count = max(task.total_count - task.success_count - task.failed_count, 0)
    else:
        task.stopped_count = 0

    next_status = _calculate_task_status(task)
    if next_status == "completed" and task.status != "completed":
        task.finished_at = task.finished_at or datetime.now(UTC)
    task.status = next_status


def refresh_dispatched_task_progress(db: Session, task: DailyTask) -> None:
    pool_items = db.scalars(
        select(DeviceTaskPoolItem).where(DeviceTaskPoolItem.task_id == task.id)
    ).all()
    if task.dispatch_status != "dispatched" or not pool_items:
        refresh_task_progress(task)
        return

    pool_items_by_task_item: dict[int, list[DeviceTaskPoolItem]] = {}
    for pool_item in pool_items:
        pool_items_by_task_item.setdefault(pool_item.task_item_id, []).append(pool_item)

    task.success_count = sum(1 for pool_item in pool_items if pool_item.status == "success")
    task.failed_count = sum(1 for pool_item in pool_items if pool_item.status == "failed")
    task.stopped_count = sum(
        1 for pool_item in pool_items if pool_item.status in {"skipped", "cancelled"}
    )

    active_pool_count = sum(
        1 for pool_item in pool_items if pool_item.status in TASK_POOL_ACTIVE_STATUSES
    )
    terminal_pool_count = sum(
        1 for pool_item in pool_items if pool_item.status in TASK_POOL_TERMINAL_STATUSES
    )

    for item in task.items:
        item_pool_items = pool_items_by_task_item.get(item.id, [])
        if not item_pool_items:
            continue
        item.success_count = sum(
            1 for pool_item in item_pool_items if pool_item.status == "success"
        )
        item.failed_count = sum(1 for pool_item in item_pool_items if pool_item.status == "failed")
        item_active_count = sum(
            1 for pool_item in item_pool_items if pool_item.status in TASK_POOL_ACTIVE_STATUSES
        )
        item_terminal_count = sum(
            1 for pool_item in item_pool_items if pool_item.status in TASK_POOL_TERMINAL_STATUSES
        )
        if item_active_count == 0 and item_terminal_count == len(item_pool_items):
            item.status = "completed"
        else:
            item.status = "running"

    if task.status == "stopped":
        return
    if active_pool_count == 0 and terminal_pool_count == len(pool_items):
        task.status = "completed"
        task.finished_at = task.finished_at or datetime.now(UTC)
    else:
        task.status = "running"
        task.finished_at = None


def _to_task_item_read(
    item: DailyTaskItem,
    doctor_name_by_id: dict[int, str],
    doctor_provinces_by_id: dict[int, list[str]],
    keyword_by_id: dict[int, str],
    remaining_comment_count_by_pair: dict[tuple[int, int], int],
) -> DailyTaskItemRead:
    doctor_provinces = doctor_provinces_by_id.get(item.doctor_id, [])
    return DailyTaskItemRead(
        id=item.id,
        task_id=item.task_id,
        sort_order=item.sort_order,
        doctor_id=item.doctor_id,
        doctor_name=doctor_name_by_id.get(item.doctor_id, "未知医生"),
        doctor_province="、".join(doctor_provinces),
        doctor_provinces=doctor_provinces,
        keyword_id=item.keyword_id,
        remaining_comment_count=remaining_comment_count_by_pair.get(
            (item.doctor_id, item.keyword_id), 0
        ),
        keyword=keyword_by_id.get(item.keyword_id, "未知关键词"),
        target_count=item.target_count,
        claimed_count=item.claimed_count,
        dispatched_count=item.dispatched_count,
        success_count=item.success_count,
        failed_count=item.failed_count,
        status=item.status,
    )


def to_daily_task_read(db: Session, task: DailyTask) -> DailyTaskRead:
    doctor_ids = {item.doctor_id for item in task.items}
    keyword_ids = {item.keyword_id for item in task.items}
    doctors = (
        db.scalars(select(Doctor).where(Doctor.id.in_(doctor_ids))).all() if doctor_ids else []
    )
    keywords = (
        db.scalars(select(DoctorKeyword).where(DoctorKeyword.id.in_(keyword_ids))).all()
        if keyword_ids
        else []
    )
    doctor_name_by_id = {doctor.id: doctor.name for doctor in doctors}
    keyword_by_id = {keyword.id: keyword.keyword for keyword in keywords}
    remaining_comment_count_by_pair: dict[tuple[int, int], int] = {}
    if doctor_ids and keyword_ids:
        count_rows = db.execute(
            select(
                CommentBankItem.doctor_id,
                CommentBankItem.keyword_id,
                func.count(CommentBankItem.id),
            )
            .where(CommentBankItem.doctor_id.in_(doctor_ids))
            .where(CommentBankItem.keyword_id.in_(keyword_ids))
            .where(CommentBankItem.status == "unused")
            .group_by(CommentBankItem.doctor_id, CommentBankItem.keyword_id)
        ).all()
        remaining_comment_count_by_pair = {
            (doctor_id, keyword_id): count for doctor_id, keyword_id, count in count_rows
        }
    doctor_provinces_by_id: dict[int, list[str]] = {}
    if doctor_ids:
        doctor_province_rows = db.scalars(
            select(DoctorProvince)
            .where(DoctorProvince.doctor_id.in_(doctor_ids))
            .order_by(DoctorProvince.doctor_id.asc(), DoctorProvince.id.asc())
        ).all()
        for row in doctor_province_rows:
            doctor_provinces_by_id.setdefault(row.doctor_id, []).append(row.province)
    refresh_task_progress(task)
    return DailyTaskRead(
        id=task.id,
        task_date=task.task_date,
        status=task.status,
        dispatch_status=task.dispatch_status,
        dispatch_started_at=task.dispatch_started_at,
        dispatch_finished_at=task.dispatch_finished_at,
        dispatch_error=task.dispatch_error,
        total_count=task.total_count,
        success_count=task.success_count,
        failed_count=task.failed_count,
        stopped_count=task.stopped_count,
        created_by=task.created_by,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        items=[
            _to_task_item_read(
                item,
                doctor_name_by_id,
                doctor_provinces_by_id,
                keyword_by_id,
                remaining_comment_count_by_pair,
            )
            for item in sorted(task.items, key=lambda value: (value.sort_order, value.id))
        ],
    )


def list_daily_tasks(
    db: Session, page_params: PageParams, task_date: str | None, status: str | None
) -> PageResult[DailyTaskRead]:
    statement = _apply_daily_task_filters(_task_statement(), task_date, status)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    tasks = db.scalars(
        statement.order_by(DailyTask.id.desc())
        .offset((page_params.page - 1) * page_params.page_size)
        .limit(page_params.page_size)
    ).all()
    return PageResult(items=[to_daily_task_read(db, task) for task in tasks], total=total)


def list_daily_task_options(db: Session) -> list[DailyTaskRead]:
    tasks = db.scalars(select(DailyTask).order_by(DailyTask.id.desc()).limit(100)).all()
    return [to_daily_task_read(db, task) for task in tasks]


def _get_active_doctor_keyword(
    db: Session, doctor_id: int, keyword_id: int
) -> tuple[Doctor, DoctorKeyword]:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None or doctor.status != "active":
        raise AppException("医生不存在或已禁用", code="DOCTOR_UNAVAILABLE", status_code=400)

    keyword = db.get(DoctorKeyword, keyword_id)
    if keyword is None or keyword.status != "active" or keyword.doctor_id != doctor_id:
        raise AppException(
            "关键词不存在、已禁用或不属于该医生", code="KEYWORD_UNAVAILABLE", status_code=400
        )
    return doctor, keyword


def create_daily_task(
    db: Session, payload: DailyTaskCreatePayload, created_by: str, created_by_user_id: int
) -> DailyTaskRead:
    config_keys: set[tuple[int, int]] = set()
    task_items: list[DailyTaskItem] = []
    for index, config in enumerate(payload.configs, start=1):
        key = (config.doctor_id, config.keyword_id)
        if key in config_keys:
            raise AppException(
                "同一任务中医生和关键词配置不能重复",
                code="DAILY_TASK_DUPLICATED_ITEM",
                status_code=400,
            )
        config_keys.add(key)
        _get_active_doctor_keyword(db, config.doctor_id, config.keyword_id)
        task_items.append(
            DailyTaskItem(
                doctor_id=config.doctor_id,
                keyword_id=config.keyword_id,
                sort_order=config.sort_order or index,
                target_count=config.count,
                claimed_count=0,
                dispatched_count=0,
                success_count=0,
                failed_count=0,
                status="pending",
            )
        )

    task = DailyTask(
        task_date=payload.task_date,
        status="pending",
        total_count=sum(item.target_count for item in task_items),
        success_count=0,
        failed_count=0,
        stopped_count=0,
        created_by=created_by,
        created_by_user_id=created_by_user_id,
        items=task_items,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return to_daily_task_read(db, task)


def get_daily_task_or_404(db: Session, task_id: int) -> DailyTask:
    task = db.get(DailyTask, task_id)
    if task is None:
        raise AppException("每日任务不存在", code="DAILY_TASK_NOT_FOUND", status_code=404)
    return task


def _list_dispatch_candidate_devices(db: Session) -> list[Device]:
    return db.scalars(
        select(Device)
        .where(Device.enabled_status == "enabled")
        .where(Device.runtime_status.in_(["idle", "running"]))
        .where(Device.province != "")
        .order_by(Device.id.asc())
    ).all()


def _device_existing_daily_count(db: Session, device_id: int, task_date: date) -> int:
    used_count = (
        db.scalar(
            select(func.count(CommentBankItem.id))
            .join(DailyTask, DailyTask.id == CommentBankItem.used_task_id)
            .where(CommentBankItem.used_device_id == device_id)
            .where(DailyTask.task_date == task_date)
        )
        or 0
    )
    pool_count = (
        db.scalar(
            select(func.count(DeviceTaskPoolItem.id))
            .join(DailyTask, DailyTask.id == DeviceTaskPoolItem.task_id)
            .where(DeviceTaskPoolItem.device_id == device_id)
            .where(DailyTask.task_date == task_date)
            .where(
                DeviceTaskPoolItem.status.in_(
                    ["pending", "claimed", "running", "success", "failed"]
                )
            )
        )
        or 0
    )
    return used_count + pool_count


def _doctor_province_map(db: Session, doctor_ids: set[int]) -> dict[int, set[str]]:
    if not doctor_ids:
        return {}
    rows = db.execute(
        select(DoctorProvince.doctor_id, DoctorProvince.province).where(
            DoctorProvince.doctor_id.in_(doctor_ids)
        )
    ).all()
    result: dict[int, set[str]] = {}
    for doctor_id, province in rows:
        result.setdefault(doctor_id, set()).add(province)
    return result


def _existing_device_doctor_keyword_pairs(
    db: Session, task_date: date
) -> set[tuple[int, int, int]]:
    rows = db.execute(
        select(
            DeviceDoctorActionRecord.device_id,
            DeviceDoctorActionRecord.doctor_id,
            DeviceDoctorActionRecord.keyword_id,
        )
        .where(DeviceDoctorActionRecord.action_date == task_date)
        .where(DeviceDoctorActionRecord.action_type == "comment")
    ).all()
    pool_rows = db.execute(
        select(
            DeviceTaskPoolItem.device_id,
            DeviceTaskPoolItem.doctor_id,
            DeviceTaskPoolItem.keyword_id,
        )
        .join(DailyTask, DailyTask.id == DeviceTaskPoolItem.task_id)
        .where(DailyTask.task_date == task_date)
        .where(
            DeviceTaskPoolItem.status.in_(
                ["pending", "claimed", "running", "success", "failed"]
            )
        )
    ).all()
    return {tuple(row) for row in rows} | {tuple(row) for row in pool_rows}


def _unused_comments_for_item(db: Session, item: DailyTaskItem, limit: int) -> list[CommentBankItem]:
    used_pool_comment_ids = select(DeviceTaskPoolItem.comment_bank_item_id)
    return db.scalars(
        select(CommentBankItem)
        .where(CommentBankItem.doctor_id == item.doctor_id)
        .where(CommentBankItem.keyword_id == item.keyword_id)
        .where(CommentBankItem.status == "unused")
        .where(CommentBankItem.id.not_in(used_pool_comment_ids))
        .order_by(CommentBankItem.id.asc())
        .limit(limit)
    ).all()


def dispatch_daily_task(db: Session, task_id: int) -> DailyTaskDispatchRead:
    daily_limit = get_single_device_daily_task_limit(db)
    task = db.scalar(select(DailyTask).where(DailyTask.id == task_id).with_for_update())
    if task is None:
        raise AppException("每日任务不存在", code="DAILY_TASK_NOT_FOUND", status_code=404)
    if task.status != "pending":
        raise AppException("只有未开始任务可以开始分派", code="DAILY_TASK_NOT_PENDING", status_code=400)
    if task.dispatch_status == "dispatching":
        raise AppException("任务正在分派中", code="DAILY_TASK_DISPATCHING", status_code=409)
    if task.dispatch_status == "dispatched":
        raise AppException(
            "任务已经分派",
            code="DAILY_TASK_ALREADY_DISPATCHED",
            status_code=400,
        )
    existing_pool_count = (
        db.scalar(
            select(func.count(DeviceTaskPoolItem.id)).where(DeviceTaskPoolItem.task_id == task.id)
        )
        or 0
    )
    if existing_pool_count > 0:
        raise AppException(
            "任务已经存在分派记录",
            code="DAILY_TASK_POOL_ALREADY_EXISTS",
            status_code=400,
        )

    now = datetime.now(UTC)
    task.dispatch_status = "dispatching"
    task.dispatch_started_at = now
    task.dispatch_finished_at = None
    task.dispatch_error = None
    db.add(task)
    db.flush()

    devices = _list_dispatch_candidate_devices(db)
    active_items = [
        item
        for item in sorted(task.items, key=lambda value: (value.sort_order, value.id))
        if item.status == "pending" and item.target_count > 0
    ]
    doctor_ids = {item.doctor_id for item in active_items}
    keyword_ids = {item.keyword_id for item in active_items}
    doctors = (
        {doctor.id: doctor for doctor in db.scalars(select(Doctor).where(Doctor.id.in_(doctor_ids))).all()}
        if doctor_ids
        else {}
    )
    keywords = (
        {
            keyword.id: keyword
            for keyword in db.scalars(select(DoctorKeyword).where(DoctorKeyword.id.in_(keyword_ids))).all()
        }
        if keyword_ids
        else {}
    )
    province_by_doctor = _doctor_province_map(db, doctor_ids)
    device_counts = {
        device.id: _device_existing_daily_count(db, device.id, task.task_date) for device in devices
    }
    assigned_pairs = _existing_device_doctor_keyword_pairs(db, task.task_date)

    warnings: list[str] = []
    pool_order = 1
    pool_count = 0

    for item in active_items:
        doctor = doctors.get(item.doctor_id)
        keyword = keywords.get(item.keyword_id)
        if doctor is None or doctor.status != "active" or keyword is None or keyword.status != "active":
            warnings.append(f"任务明细 {item.id} 的医生或关键词已禁用，未分派")
            continue

        allowed_provinces = province_by_doctor.get(item.doctor_id, set())
        candidate_devices = [
            device
            for device in devices
            if device.province in allowed_provinces
            and (daily_limit <= 0 or device_counts[device.id] < daily_limit)
            and (device.id, item.doctor_id, item.keyword_id) not in assigned_pairs
        ]
        if not candidate_devices:
            warnings.append(f"{doctor.name}/{keyword.keyword} 没有可分派设备")
            continue

        comments = _unused_comments_for_item(db, item, item.target_count)
        if len(comments) < item.target_count:
            warnings.append(
                f"{doctor.name}/{keyword.keyword} 评论库存不足，目标{item.target_count}，库存{len(comments)}"
            )

        assigned_for_item = 0
        for comment in comments:
            available_devices = [
                device
                for device in candidate_devices
                if daily_limit <= 0 or device_counts[device.id] < daily_limit
                if (device.id, item.doctor_id, item.keyword_id) not in assigned_pairs
            ]
            if not available_devices:
                break
            device = min(available_devices, key=lambda value: device_counts[value.id])
            pool_item = DeviceTaskPoolItem(
                task_id=task.id,
                task_item_id=item.id,
                device_id=device.id,
                doctor_id=item.doctor_id,
                keyword_id=item.keyword_id,
                comment_bank_item_id=comment.id,
                pool_round=device_counts[device.id] + 1,
                pool_order=pool_order,
                status="pending",
            )
            item.dispatched_count += 1
            device_counts[device.id] += 1
            assigned_pairs.add((device.id, item.doctor_id, item.keyword_id))
            db.add_all([pool_item, item])
            pool_order += 1
            pool_count += 1
            assigned_for_item += 1
            if assigned_for_item >= item.target_count:
                break

        if assigned_for_item < item.target_count:
            warnings.append(
                f"{doctor.name}/{keyword.keyword} 目标{item.target_count}，实际分派{assigned_for_item}"
            )

    task.dispatch_status = "dispatched" if pool_count > 0 else "dispatch_failed"
    task.dispatch_finished_at = datetime.now(UTC)
    task.dispatch_error = "\n".join(warnings) if warnings else None
    db.add(task)
    db.commit()
    db.refresh(task)
    return DailyTaskDispatchRead(
        task_id=task.id,
        dispatch_status=task.dispatch_status,
        device_count=len(devices),
        pool_item_count=pool_count,
        warnings=warnings,
    )


def reset_daily_task_dispatch(db: Session, task_id: int) -> None:
    task = get_daily_task_or_404(db, task_id)
    if task.status != "pending":
        raise AppException(
            "只有未开始任务可以重置分派结果",
            code="DAILY_TASK_NOT_PENDING",
            status_code=400,
        )

    pool_items = db.scalars(
        select(DeviceTaskPoolItem).where(DeviceTaskPoolItem.task_id == task.id)
    ).all()
    started_statuses = {"claimed", "running", "success", "failed"}
    if any(pool_item.status in started_statuses for pool_item in pool_items):
        raise AppException(
            "任务池已有领取或执行记录，不能清空分派结果",
            code="DAILY_TASK_POOL_ALREADY_STARTED",
            status_code=400,
        )

    db.query(DeviceTaskPoolItem).filter(DeviceTaskPoolItem.task_id == task.id).delete(
        synchronize_session=False
    )
    for item in task.items:
        item.dispatched_count = 0
        item.status = "pending"
        db.add(item)
    task.dispatch_status = "not_dispatched"
    task.dispatch_started_at = None
    task.dispatch_finished_at = None
    task.dispatch_error = None
    db.add(task)
    db.commit()


def list_daily_task_device_details(db: Session, task_id: int) -> DailyTaskDeviceDetailsRead:
    get_daily_task_or_404(db, task_id)
    rows = db.execute(
        select(DeviceTaskPoolItem, Device, Doctor, DoctorKeyword, CommentBankItem)
        .join(Device, Device.id == DeviceTaskPoolItem.device_id)
        .join(Doctor, Doctor.id == DeviceTaskPoolItem.doctor_id)
        .join(DoctorKeyword, DoctorKeyword.id == DeviceTaskPoolItem.keyword_id)
        .join(CommentBankItem, CommentBankItem.id == DeviceTaskPoolItem.comment_bank_item_id)
        .where(DeviceTaskPoolItem.task_id == task_id)
        .order_by(Device.id.asc(), DeviceTaskPoolItem.pool_order.asc(), DeviceTaskPoolItem.id.asc())
    ).all()

    details_by_device: dict[int, DailyTaskDeviceDetailRead] = {}
    for pool_item, device, doctor, keyword, comment in rows:
        detail = details_by_device.get(device.id)
        if detail is None:
            detail = DailyTaskDeviceDetailRead(
                device_id=device.id,
                device_name=device.name,
                device_province=device.province or "",
                assigned_count=0,
                claimed_count=0,
                success_count=0,
                failed_count=0,
                tasks=[],
            )
            details_by_device[device.id] = detail

        detail.assigned_count += 1
        if pool_item.status in {"claimed", "running", "success", "failed"}:
            detail.claimed_count += 1
        if pool_item.status == "success":
            detail.success_count += 1
        if pool_item.status == "failed":
            detail.failed_count += 1
        detail.tasks.append(
            DailyTaskDevicePoolTaskRead(
                id=pool_item.id,
                doctor_name=doctor.name,
                doctor_real_name=doctor.real_name,
                keyword=keyword.keyword,
                comment_content=comment.content,
                status=pool_item.status,
            )
        )

    return DailyTaskDeviceDetailsRead(task_id=task_id, items=list(details_by_device.values()))


def update_daily_task_item_sort_order(
    db: Session, task_id: int, payload: DailyTaskItemSortOrderPayload
) -> DailyTaskRead:
    task = get_daily_task_or_404(db, task_id)
    if task.status != "pending":
        raise AppException(
            "只有未开始任务可以调整明细顺序",
            code="DAILY_TASK_NOT_PENDING",
            status_code=400,
        )
    if task.dispatch_status in {"dispatching", "dispatched"}:
        raise AppException(
            "任务正在分派或已分派，不能调整明细顺序",
            code="DAILY_TASK_ALREADY_DISPATCHED",
            status_code=400,
        )

    task_items_by_id = {item.id: item for item in task.items}
    item_ids = [item.id for item in payload.items]
    if len(set(item_ids)) != len(item_ids) or any(item_id not in task_items_by_id for item_id in item_ids):
        raise AppException("任务明细不存在", code="TASK_ITEM_NOT_FOUND", status_code=404)

    ordered_items = sorted(task.items, key=lambda value: (value.sort_order, value.id))
    for payload_item in payload.items:
        item = task_items_by_id[payload_item.id]
        ordered_items = [candidate for candidate in ordered_items if candidate.id != item.id]
        target_index = min(max(payload_item.sort_order - 1, 0), len(ordered_items))
        ordered_items.insert(target_index, item)

    for index, item in enumerate(ordered_items, start=1):
        item.sort_order = index
        db.add(item)

    db.commit()
    db.refresh(task)
    return to_daily_task_read(db, task)


def stop_daily_task(db: Session, task_id: int) -> None:
    task = get_daily_task_or_404(db, task_id)
    if task.status in {"completed", "stopped"}:
        return

    now = datetime.now(UTC)
    pool_items = db.scalars(
        select(DeviceTaskPoolItem).where(DeviceTaskPoolItem.task_id == task.id)
    ).all()
    for pool_item in pool_items:
        if pool_item.status in {"pending", "claimed"}:
            pool_item.status = "cancelled"
            pool_item.finished_at = pool_item.finished_at or now
            pool_item.fail_reason = pool_item.fail_reason or "task stopped"
            db.add(pool_item)

    refresh_dispatched_task_progress(db, task)
    task.status = "stopped"
    task.stopped_count = max(task.total_count - task.success_count - task.failed_count, 0)
    task.finished_at = now
    for item in task.items:
        if item.status != "completed":
            item.status = "stopped"
    db.add(task)
    db.commit()
