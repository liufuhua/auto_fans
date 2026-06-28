from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user
from app.core.exceptions import AppException
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.auth import AdminUserRead, LoginRequest, LoginResponse
from app.schemas.common import ApiResponse, ok
from app.services.auth import authenticate_admin_user, login_admin_user, to_admin_user_read

router = APIRouter(prefix="/auth")


@router.post("/login", response_model=ApiResponse[LoginResponse])
def login(
    payload: LoginRequest, db: Annotated[Session, Depends(get_db)]
) -> ApiResponse[LoginResponse]:
    user = authenticate_admin_user(db, payload.account, payload.password)
    if user is None:
        raise AppException(
            "账号或密码错误", code="INVALID_CREDENTIALS", status_code=status.HTTP_401_UNAUTHORIZED
        )
    if user.status != "active":
        raise AppException(
            "当前账号已被禁用", code="USER_DISABLED", status_code=status.HTTP_403_FORBIDDEN
        )

    return ok(login_admin_user(db, user))


@router.post("/logout", response_model=ApiResponse[None])
def logout(
    _user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    return ok(None)


@router.get("/me", response_model=ApiResponse[AdminUserRead])
def get_me(
    user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[AdminUserRead]:
    return ok(to_admin_user_read(user))
