from __future__ import annotations

import logging
from datetime import date
from threading import Lock, Thread

from sqlalchemy import select

from app.core.playwright_logging import playwright_log_file
from app.core.datetime_utils import now_beijing
from app.db.session import SessionLocal
from app.models.automation_result import AutomationResult
from app.models.comment_recheck import CommentRecheckRecord
from app.models.daily_task import DailyTask
from app.services.douyin_comment_checker import CommentCheckResult, check_douyin_comment
from app.services.douyin_playwright_session import douyin_playwright_session_manager

logger = logging.getLogger(__name__)

_worker_lock = Lock()


def schedule_comment_rechecks_for_results(
    result_ids: list[int], task_date: date | None = None
) -> None:
    if not result_ids:
        logger.info("skip scheduling comment recheck: empty result ids")
        return

    thread = Thread(
        target=run_comment_rechecks_for_results,
        kwargs={"result_ids": result_ids, "task_date": task_date},
        name="comment-recheck-playwright",
        daemon=True,
    )
    thread.start()


def run_pending_comment_rechecks(limit: int = 100) -> None:
    if not _worker_lock.acquire(blocking=False):
        logger.info("comment recheck playwright job already running")
        return
    try:
        with playwright_log_file() as log_path:
            logger.info("comment recheck playwright log file: %s", log_path)
            _run_comment_rechecks(limit=limit)
    finally:
        douyin_playwright_session_manager.close()
        _worker_lock.release()


def run_comment_rechecks_for_results(
    result_ids: list[int], task_date: date | None = None, limit: int | None = None
) -> None:
    if not _worker_lock.acquire(blocking=False):
        logger.info("comment recheck playwright job already running")
        return
    try:
        with playwright_log_file() as log_path:
            logger.info("comment recheck playwright log file: %s", log_path)
            _run_comment_rechecks(result_ids=result_ids, task_date=task_date, limit=limit)
    finally:
        douyin_playwright_session_manager.close()
        _worker_lock.release()


def _run_comment_rechecks(
    result_ids: list[int] | None = None,
    task_date: date | None = None,
    limit: int | None = None,
) -> None:
    rows = _load_queued_rows(result_ids=result_ids, task_date=task_date, limit=limit)
    if not rows:
        logger.info("no queued comment recheck records")
        return

    for record_id, video_link, comment_content in rows:
        logger.info("start comment recheck record: record_id=%s link=%s", record_id, video_link)
        _mark_record_checking(record_id)
        try:
            result = check_douyin_comment(video_link, comment_content)
        except Exception as exc:
            logger.exception("playwright comment recheck failed: record_id=%s", record_id)
            result = CommentCheckResult("failed", f"校验失败：{exc}")
        logger.info(
            "finish comment recheck record: record_id=%s status=%s reason=%s",
            record_id,
            result.status,
            result.fail_reason,
        )
        _update_record(record_id, result.status, result.fail_reason)
        if result.status == "login_required":
            logger.warning(
                "stop comment recheck batch because login is required: record_id=%s",
                record_id,
            )
            break


def _load_queued_rows(
    result_ids: list[int] | None,
    task_date: date | None,
    limit: int | None,
) -> list[tuple[int, str, str]]:
    with SessionLocal() as db:
        statement = (
            select(CommentRecheckRecord, AutomationResult)
            .join(AutomationResult, AutomationResult.id == CommentRecheckRecord.automation_result_id)
            .join(DailyTask, DailyTask.id == AutomationResult.task_id)
            .where(CommentRecheckRecord.status.in_(["queued", "pending"]))
            .where(AutomationResult.status == "success")
            .where(AutomationResult.video_link.is_not(None))
            .where(AutomationResult.video_link != "")
            .order_by(CommentRecheckRecord.id.asc())
        )
        if result_ids is not None:
            statement = statement.where(AutomationResult.id.in_(result_ids))
        if task_date is not None:
            statement = statement.where(DailyTask.task_date == task_date)
        if limit is not None:
            statement = statement.limit(limit)

        return [
            (record.id, result.video_link or "", result.comment_content)
            for record, result in db.execute(statement).all()
        ]


def _mark_record_checking(record_id: int) -> None:
    with SessionLocal() as db:
        record = db.get(CommentRecheckRecord, record_id)
        if record is None:
            return
        record.status = "checking"
        record.fail_reason = None
        db.add(record)
        db.commit()


def _update_record(record_id: int, status: str, fail_reason: str | None) -> None:
    with SessionLocal() as db:
        record = db.get(CommentRecheckRecord, record_id)
        if record is None:
            return
        record.status = status
        record.checked_at = now_beijing()
        record.fail_reason = fail_reason
        db.add(record)
        db.commit()
