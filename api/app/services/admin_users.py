from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.security import hash_password
from app.models.admin_user import AdminUser
from app.schemas.admin_user import AdminUserCreate, AdminUserItem, AdminUserUpdate
from app.schemas.common import PageParams, PageResult


def to_admin_user_item(user: AdminUser) -> AdminUserItem:
    return AdminUserItem.model_validate(user)


def get_admin_user_or_404(db: Session, user_id: int) -> AdminUser:
    user = db.get(AdminUser, user_id)
    if user is None:
        raise AppException("后台用户不存在", code="ADMIN_USER_NOT_FOUND", status_code=404)
    return user


def _apply_admin_user_filters(
    statement: Select[tuple[AdminUser]], keyword: str | None, status: str | None
) -> Select[tuple[AdminUser]]:
    if keyword:
        keyword_like = f"%{keyword.strip()}%"
        statement = statement.where(
            or_(AdminUser.phone.like(keyword_like), AdminUser.username.like(keyword_like))
        )
    if status:
        statement = statement.where(AdminUser.status == status)
    return statement


def list_admin_users(
    db: Session, page_params: PageParams, keyword: str | None, status: str | None
) -> PageResult[AdminUserItem]:
    statement = _apply_admin_user_filters(select(AdminUser), keyword, status)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    users = db.scalars(
        statement.order_by(AdminUser.id.desc())
        .offset((page_params.page - 1) * page_params.page_size)
        .limit(page_params.page_size)
    ).all()
    return PageResult(items=[to_admin_user_item(user) for user in users], total=total)


def ensure_admin_user_unique(
    db: Session, *, phone: str, username: str, exclude_user_id: int | None = None
) -> None:
    statement = select(AdminUser).where(
        or_(AdminUser.phone == phone, AdminUser.username == username)
    )
    if exclude_user_id is not None:
        statement = statement.where(AdminUser.id != exclude_user_id)
    existing = db.scalar(statement)
    if existing is None:
        return
    if existing.phone == phone:
        raise AppException("手机号已存在", code="ADMIN_USER_PHONE_EXISTS", status_code=409)
    raise AppException("用户名称已存在", code="ADMIN_USER_USERNAME_EXISTS", status_code=409)


def create_admin_user(db: Session, payload: AdminUserCreate) -> AdminUserItem:
    ensure_admin_user_unique(db, phone=payload.phone, username=payload.username)
    user = AdminUser(
        phone=payload.phone,
        username=payload.username,
        password_hash=hash_password(payload.password),
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return to_admin_user_item(user)


def update_admin_user(db: Session, user_id: int, payload: AdminUserUpdate) -> AdminUserItem:
    user = get_admin_user_or_404(db, user_id)
    ensure_admin_user_unique(
        db, phone=payload.phone, username=payload.username, exclude_user_id=user_id
    )
    user.phone = payload.phone
    user.username = payload.username
    db.add(user)
    db.commit()
    db.refresh(user)
    return to_admin_user_item(user)


def set_admin_user_status(
    db: Session, user_id: int, status: str, current_user_id: int
) -> AdminUserItem:
    user = get_admin_user_or_404(db, user_id)
    if user.id == current_user_id and status == "disabled":
        raise AppException("不能禁用当前登录账号", code="CANNOT_DISABLE_SELF", status_code=400)
    user.status = status
    db.add(user)
    db.commit()
    db.refresh(user)
    return to_admin_user_item(user)


def reset_admin_user_password(db: Session, user_id: int, password: str) -> None:
    user = get_admin_user_or_404(db, user_id)
    user.password_hash = hash_password(password)
    db.add(user)
    db.commit()
