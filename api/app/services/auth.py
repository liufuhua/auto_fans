from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.admin_user import AdminUser
from app.schemas.auth import AdminUserRead, LoginResponse

ACTIVE_STATUS = "active"


def to_admin_user_read(user: AdminUser) -> AdminUserRead:
    return AdminUserRead(
        id=user.id,
        phone=user.phone,
        username=user.username,
        is_active=user.status == ACTIVE_STATUS,
        last_login_at=user.last_login_at,
    )


def get_admin_user_by_account(db: Session, account: str) -> AdminUser | None:
    statement = select(AdminUser).where(
        or_(AdminUser.phone == account, AdminUser.username == account)
    )
    return db.scalar(statement)


def get_admin_user_by_id(db: Session, user_id: int) -> AdminUser | None:
    return db.get(AdminUser, user_id)


def authenticate_admin_user(db: Session, account: str, password: str) -> AdminUser | None:
    user = get_admin_user_by_account(db, account)
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def login_admin_user(db: Session, user: AdminUser) -> LoginResponse:
    user.last_login_at = datetime.now(UTC)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return LoginResponse(token=token, user=to_admin_user_read(user))
