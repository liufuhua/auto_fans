from datetime import date

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.datetime_utils import now_beijing
from app.models.automation_result import AutomationResult
from app.models.comment_recheck import CommentRecheckRecord
from app.models.daily_task import DailyTask
from app.models.device import Device
from app.models.doctor import Doctor, DoctorKeyword
from app.schemas.comment_recheck import CommentRecheckItemRead, StartCommentRecheckResponse
from app.schemas.common import PageParams, PageResult
from app.services.comment_recheck_worker import schedule_comment_rechecks_for_results
from app.services.douyin_playwright_session import douyin_playwright_session_manager

LEGACY_PENDING_STATUS = "pending"


def normalize_comment_recheck_status(status: str | None) -> str:
    if status is None:
        return "not_checked"
    if status == LEGACY_PENDING_STATUS:
        return "queued"
    return status


def _comment_recheck_base_statement() -> Select[
    tuple[AutomationResult, DailyTask, str, str, str, CommentRecheckRecord | None]
]:
    return (
        select(
            AutomationResult,
            DailyTask,
            Doctor.name,
            DoctorKeyword.keyword,
            Device.name,
            CommentRecheckRecord,
        )
        .join(DailyTask, DailyTask.id == AutomationResult.task_id)
        .join(Doctor, Doctor.id == AutomationResult.doctor_id)
        .join(DoctorKeyword, DoctorKeyword.id == AutomationResult.keyword_id)
        .join(Device, Device.id == AutomationResult.device_id)
        .outerjoin(
            CommentRecheckRecord,
            CommentRecheckRecord.automation_result_id == AutomationResult.id,
        )
        .where(AutomationResult.status == "success")
        .where(AutomationResult.video_link.is_not(None))
        .where(AutomationResult.video_link != "")
    )


def _apply_comment_recheck_filters(
    statement: Select[
        tuple[AutomationResult, DailyTask, str, str, str, CommentRecheckRecord | None]
    ],
    doctor_id: int | None,
    keyword_id: int | None,
    status: str | None,
    keyword: str | None,
    start_date: date | None,
    end_date: date | None,
) -> Select[tuple[AutomationResult, DailyTask, str, str, str, CommentRecheckRecord | None]]:
    if doctor_id:
        statement = statement.where(AutomationResult.doctor_id == doctor_id)
    if keyword_id:
        statement = statement.where(AutomationResult.keyword_id == keyword_id)
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date
    if start_date:
        statement = statement.where(DailyTask.task_date >= start_date)
    if end_date:
        statement = statement.where(DailyTask.task_date <= end_date)
    if status:
        if status == "not_checked":
            statement = statement.where(CommentRecheckRecord.id.is_(None))
        elif status == "queued":
            statement = statement.where(
                CommentRecheckRecord.status.in_(["queued", LEGACY_PENDING_STATUS])
            )
        else:
            statement = statement.where(CommentRecheckRecord.status == status)
    if keyword:
        keyword_like = f"%{keyword.strip()}%"
        statement = statement.where(
            or_(
                AutomationResult.comment_content.like(keyword_like),
                AutomationResult.publish_account.like(keyword_like),
                CommentRecheckRecord.fail_reason.like(keyword_like),
            )
        )
    return statement


def _to_comment_recheck_item_read(
    result: AutomationResult,
    task: DailyTask,
    doctor_name: str,
    keyword: str,
    device_name: str,
    record: CommentRecheckRecord | None,
) -> CommentRecheckItemRead:
    return CommentRecheckItemRead(
        id=result.id,
        automation_result_id=result.id,
        task_id=result.task_id,
        task_date=task.task_date,
        doctor_id=result.doctor_id,
        doctor_name=doctor_name,
        keyword_id=result.keyword_id,
        keyword=keyword,
        device_name=device_name,
        publish_account=result.publish_account,
        comment_content=result.comment_content,
        video_link=result.video_link,
        status=normalize_comment_recheck_status(record.status if record else None),
        checked_at=record.checked_at if record else None,
        fail_reason=record.fail_reason if record else None,
    )


def list_comment_recheck_items(
    db: Session,
    page_params: PageParams,
    doctor_id: int | None,
    keyword_id: int | None,
    status: str | None,
    keyword: str | None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> PageResult[CommentRecheckItemRead]:
    statement = _apply_comment_recheck_filters(
        _comment_recheck_base_statement(),
        doctor_id,
        keyword_id,
        status,
        keyword,
        start_date,
        end_date,
    )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(
        statement.order_by(AutomationResult.id.desc())
        .offset((page_params.page - 1) * page_params.page_size)
        .limit(page_params.page_size)
    ).all()
    return PageResult(
        items=[
            _to_comment_recheck_item_read(
                result,
                task,
                doctor_name,
                keyword_text,
                device_name,
                record,
            )
            for result, task, doctor_name, keyword_text, device_name, record in rows
        ],
        total=total,
    )


def start_comment_recheck(
    db: Session, automation_result_ids: list[int], task_date: date | None = None
) -> StartCommentRecheckResponse:
    unique_ids = list(dict.fromkeys(automation_result_ids))
    if not unique_ids:
        return StartCommentRecheckResponse(submitted=0, skipped=0)

    login_status = douyin_playwright_session_manager.ensure_login_status()
    if not login_status.logged_in:
        return StartCommentRecheckResponse(
            submitted=0,
            skipped=len(unique_ids),
            login_required=True,
        )

    statement = (
        select(AutomationResult.id)
        .join(DailyTask, DailyTask.id == AutomationResult.task_id)
        .where(AutomationResult.id.in_(unique_ids))
        .where(AutomationResult.status == "success")
        .where(AutomationResult.video_link.is_not(None))
        .where(AutomationResult.video_link != "")
    )
    if task_date is not None:
        statement = statement.where(DailyTask.task_date == task_date)

    eligible_result_ids = set(db.scalars(statement).all())
    if not eligible_result_ids:
        return StartCommentRecheckResponse(submitted=0, skipped=len(unique_ids))

    existing_records = db.scalars(
        select(CommentRecheckRecord).where(
            CommentRecheckRecord.automation_result_id.in_(eligible_result_ids)
        )
    ).all()
    record_by_result_id = {record.automation_result_id: record for record in existing_records}

    for result_id in eligible_result_ids:
        record = record_by_result_id.get(result_id)
        if record is None:
            db.add(CommentRecheckRecord(automation_result_id=result_id, status="queued"))
            continue
        record.status = "queued"
        record.checked_at = None
        record.fail_reason = None
        db.add(record)

    scheduled_result_ids = list(eligible_result_ids)

    db.commit()
    schedule_comment_rechecks_for_results(scheduled_result_ids, task_date=task_date)
    return StartCommentRecheckResponse(
        submitted=len(eligible_result_ids),
        skipped=len(unique_ids) - len(eligible_result_ids),
    )


def list_today_comment_recheck_result_ids(db: Session, task_date: date | None = None) -> list[int]:
    target_date = task_date or now_beijing().date()
    return list(
        db.scalars(
            select(AutomationResult.id)
            .join(DailyTask, DailyTask.id == AutomationResult.task_id)
            .where(DailyTask.task_date == target_date)
            .where(AutomationResult.status == "success")
            .where(AutomationResult.video_link.is_not(None))
            .where(AutomationResult.video_link != "")
        ).all()
    )


def list_comment_recheck_result_ids_by_date_range(
    db: Session, start_date: date, end_date: date
) -> list[int]:
    return list(
        db.scalars(
            select(AutomationResult.id)
            .join(DailyTask, DailyTask.id == AutomationResult.task_id)
            .where(DailyTask.task_date >= start_date)
            .where(DailyTask.task_date <= end_date)
            .where(AutomationResult.status == "success")
            .where(AutomationResult.video_link.is_not(None))
            .where(AutomationResult.video_link != "")
        ).all()
    )


def start_today_comment_recheck(
    db: Session, task_date: date | None = None
) -> StartCommentRecheckResponse:
    target_date = task_date or now_beijing().date()
    return start_comment_recheck(
        db,
        list_today_comment_recheck_result_ids(db, target_date),
        task_date=target_date,
    )


def start_comment_recheck_by_date_range(
    db: Session, start_date: date, end_date: date
) -> StartCommentRecheckResponse:
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_comment_recheck(
        db,
        list_comment_recheck_result_ids_by_date_range(db, start_date, end_date),
    )
