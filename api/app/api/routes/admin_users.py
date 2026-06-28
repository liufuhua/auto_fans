from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user, get_page_params
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.admin_user import (
    AdminUserCreate,
    AdminUserItem,
    AdminUserResetPassword,
    AdminUserUpdate,
)
from app.schemas.common import ApiResponse, PageParams, PageResult, ok
from app.services.admin_users import (
    create_admin_user,
    list_admin_users,
    reset_admin_user_password,
    set_admin_user_status,
    update_admin_user,
)

router = APIRouter(prefix="/admin-users")


@router.get("", response_model=ApiResponse[PageResult[AdminUserItem]])
def get_admin_users(
    page_params: Annotated[PageParams, Depends(get_page_params)],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
    keyword: Annotated[str | None, Query(max_length=64)] = None,
    status: Annotated[Literal["active", "disabled"] | None, Query()] = None,
) -> ApiResponse[PageResult[AdminUserItem]]:
    return ok(list_admin_users(db, page_params, keyword, status))


@router.post("", response_model=ApiResponse[AdminUserItem])
def create_user(
    payload: AdminUserCreate,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[AdminUserItem]:
    return ok(create_admin_user(db, payload))


@router.put("/{user_id}", response_model=ApiResponse[AdminUserItem])
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[AdminUserItem]:
    return ok(update_admin_user(db, user_id, payload))


@router.post("/{user_id}/enable", response_model=ApiResponse[None])
def enable_user(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    set_admin_user_status(db, user_id, "active", current_user.id)
    return ok(None)


@router.post("/{user_id}/disable", response_model=ApiResponse[None])
def disable_user(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    set_admin_user_status(db, user_id, "disabled", current_user.id)
    return ok(None)


@router.post("/{user_id}/reset-password", response_model=ApiResponse[None])
def reset_password(
    user_id: int,
    payload: AdminUserResetPassword,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    reset_admin_user_password(db, user_id, payload.password)
    return ok(None)
