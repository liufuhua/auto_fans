from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user, get_page_params
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.comment_recheck import (
    CommentRecheckLoginStatusRead,
    CommentRecheckItemRead,
    ConfirmCommentRecheckLoginPayload,
    StartCommentRecheckPayload,
    StartCommentRecheckResponse,
)
from app.schemas.common import ApiResponse, PageParams, PageResult, ok
from app.services.comment_recheck import (
    list_comment_recheck_items,
    start_comment_recheck,
    start_comment_recheck_by_date_range,
    start_today_comment_recheck,
)
from app.services.douyin_playwright_session import douyin_playwright_session_manager

router = APIRouter(prefix="/comment-results/recheck")


@router.get("", response_model=ApiResponse[PageResult[CommentRecheckItemRead]])
def get_comment_recheck_items(
    page_params: Annotated[PageParams, Depends(get_page_params)],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
    doctor_id: Annotated[int | None, Query(alias="doctorId")] = None,
    keyword_id: Annotated[int | None, Query(alias="keywordId")] = None,
    status: Annotated[
        Literal[
            "not_checked",
            "queued",
            "checking",
            "exists",
            "missing",
            "failed",
            "login_required",
            "captcha_required",
    ]
        | None,
        Query(),
    ] = None,
    keyword: Annotated[str | None, Query(max_length=100)] = None,
    start_date: Annotated[date | None, Query(alias="startDate")] = None,
    end_date: Annotated[date | None, Query(alias="endDate")] = None,
) -> ApiResponse[PageResult[CommentRecheckItemRead]]:
    return ok(
        list_comment_recheck_items(
            db,
            page_params,
            doctor_id,
            keyword_id,
            status,
            keyword,
            start_date,
            end_date,
        )
    )


@router.get("/login-status", response_model=ApiResponse[CommentRecheckLoginStatusRead])
def get_comment_recheck_login_status(
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[CommentRecheckLoginStatusRead]:
    return ok(douyin_playwright_session_manager.get_login_status())


@router.post("/login-session", response_model=ApiResponse[CommentRecheckLoginStatusRead])
def create_comment_recheck_login_session(
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[CommentRecheckLoginStatusRead]:
    return ok(douyin_playwright_session_manager.create_login_session())


@router.get("/login-qr")
def get_comment_recheck_login_qr(
    session_id: Annotated[str, Query(alias="sessionId")],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> FileResponse:
    qr_path = douyin_playwright_session_manager.get_qr_path(session_id)
    return FileResponse(qr_path, media_type="image/png", filename="douyin-login-qr.png")


@router.post("/confirm-login", response_model=ApiResponse[CommentRecheckLoginStatusRead])
def confirm_comment_recheck_login(
    payload: ConfirmCommentRecheckLoginPayload,
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[CommentRecheckLoginStatusRead]:
    return ok(douyin_playwright_session_manager.confirm_login(payload.session_id))


@router.post("", response_model=ApiResponse[StartCommentRecheckResponse])
def start_comment_recheck_items(
    payload: StartCommentRecheckPayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[StartCommentRecheckResponse]:
    return ok(start_comment_recheck(db, payload.ids))


@router.post("/today", response_model=ApiResponse[StartCommentRecheckResponse])
def start_today_comment_recheck_items(
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[StartCommentRecheckResponse]:
    return ok(start_today_comment_recheck(db))


@router.post("/by-date", response_model=ApiResponse[StartCommentRecheckResponse])
def start_comment_recheck_by_date_items(
    task_date: Annotated[date, Query(alias="taskDate")],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[StartCommentRecheckResponse]:
    return ok(start_today_comment_recheck(db, task_date))


@router.post("/by-date-range", response_model=ApiResponse[StartCommentRecheckResponse])
def start_comment_recheck_by_date_range_items(
    start_date: Annotated[date, Query(alias="startDate")],
    end_date: Annotated[date, Query(alias="endDate")],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[StartCommentRecheckResponse]:
    return ok(start_comment_recheck_by_date_range(db, start_date, end_date))
