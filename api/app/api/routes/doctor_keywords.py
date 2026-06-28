from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.common import ApiResponse, ok
from app.schemas.doctor import DoctorKeywordItem, DoctorKeywordPayload
from app.services.doctors import (
    create_doctor_keyword,
    delete_doctor_keyword,
    list_active_doctor_keyword_options,
    list_doctor_keywords,
    set_doctor_keyword_status,
    update_doctor_keyword,
)

doctor_nested_router = APIRouter(prefix="/doctors")
router = APIRouter(prefix="/doctor-keywords")


@doctor_nested_router.get(
    "/{doctor_id}/keywords", response_model=ApiResponse[list[DoctorKeywordItem]]
)
def get_doctor_keywords(
    doctor_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[list[DoctorKeywordItem]]:
    return ok(list_doctor_keywords(db, doctor_id))


@doctor_nested_router.post("/{doctor_id}/keywords", response_model=ApiResponse[DoctorKeywordItem])
def create_doctor_keyword_item(
    doctor_id: int,
    payload: DoctorKeywordPayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DoctorKeywordItem]:
    return ok(create_doctor_keyword(db, doctor_id, payload))


@router.get("/options", response_model=ApiResponse[list[DoctorKeywordItem]])
def get_doctor_keyword_options(
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
    doctor_id: Annotated[int | None, Query(alias="doctorId")] = None,
) -> ApiResponse[list[DoctorKeywordItem]]:
    return ok(list_active_doctor_keyword_options(db, doctor_id))


@router.put("/{keyword_id}", response_model=ApiResponse[DoctorKeywordItem])
def update_doctor_keyword_item(
    keyword_id: int,
    payload: DoctorKeywordPayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DoctorKeywordItem]:
    return ok(update_doctor_keyword(db, keyword_id, payload))


@router.post("/{keyword_id}/enable", response_model=ApiResponse[None])
def enable_doctor_keyword(
    keyword_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    set_doctor_keyword_status(db, keyword_id, "active")
    return ok(None)


@router.post("/{keyword_id}/disable", response_model=ApiResponse[None])
def disable_doctor_keyword(
    keyword_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    set_doctor_keyword_status(db, keyword_id, "disabled")
    return ok(None)


@router.delete("/{keyword_id}", response_model=ApiResponse[None])
def delete_doctor_keyword_item(
    keyword_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    delete_doctor_keyword(db, keyword_id)
    return ok(None)
