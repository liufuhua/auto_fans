from typing import Annotated

from fastapi import Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.security import decode_access_token, is_token_error
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.auth import TokenPayload
from app.schemas.common import PageParams
from app.services.auth import get_admin_user_by_id

bearer_scheme = HTTPBearer(auto_error=False)


def get_page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> PageParams:
    return PageParams(page=page, pageSize=page_size)


def get_current_admin_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> AdminUser:
    if credentials is None or not credentials.credentials:
        raise AppException(
            "登录已失效，请重新登录", code="UNAUTHORIZED", status_code=status.HTTP_401_UNAUTHORIZED
        )

    try:
        payload = TokenPayload.model_validate(decode_access_token(credentials.credentials))
    except Exception as exc:
        if is_token_error(exc):
            raise AppException(
                "登录已失效，请重新登录",
                code="TOKEN_INVALID",
                status_code=status.HTTP_401_UNAUTHORIZED,
            ) from exc
        raise

    if payload.type != "access":
        raise AppException(
            "登录已失效，请重新登录", code="TOKEN_INVALID", status_code=status.HTTP_401_UNAUTHORIZED
        )

    try:
        user_id = int(payload.sub)
    except ValueError as exc:
        raise AppException("登录已失效，请重新登录", code="TOKEN_INVALID", status_code=401) from exc

    user = get_admin_user_by_id(db, user_id)
    if user is None:
        raise AppException("登录已失效，请重新登录", code="TOKEN_INVALID", status_code=401)
    return user


def get_current_active_admin_user(
    user: Annotated[AdminUser, Depends(get_current_admin_user)],
) -> AdminUser:
    if user.status != "active":
        raise AppException(
            "当前账号已被禁用", code="USER_DISABLED", status_code=status.HTTP_403_FORBIDDEN
        )
    return user
