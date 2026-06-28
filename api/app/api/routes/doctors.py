from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user, get_page_params
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.common import ApiResponse, PageParams, PageResult, ok
from app.schemas.doctor import DoctorItem, DoctorPayload, DoctorSortOrderPayload
from app.services.doctors import (
    create_doctor,
    delete_doctor,
    list_active_doctor_options,
    list_doctors,
    set_doctor_status,
    update_doctor,
    update_doctor_sort_order,
)

router = APIRouter(prefix="/doctors")


@router.get("", response_model=ApiResponse[PageResult[DoctorItem]])
def get_doctors(
    page_params: Annotated[PageParams, Depends(get_page_params)],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
    keyword: Annotated[str | None, Query(max_length=64)] = None,
    status: Annotated[Literal["active", "disabled"] | None, Query()] = None,
    sort_by: Annotated[
        Literal["name", "realName", "status", "createdAt", "updatedAt"] | None,
        Query(alias="sortBy"),
    ] = None,
    sort_order: Annotated[
        Literal["ascending", "descending"] | None, Query(alias="sortOrder")
    ] = None,
) -> ApiResponse[PageResult[DoctorItem]]:
    return ok(list_doctors(db, page_params, keyword, status, sort_by, sort_order))


@router.get("/options", response_model=ApiResponse[list[DoctorItem]])
def get_doctor_options(
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[list[DoctorItem]]:
    return ok(list_active_doctor_options(db))


@router.post("", response_model=ApiResponse[DoctorItem])
def create_doctor_item(
    payload: DoctorPayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DoctorItem]:
    return ok(create_doctor(db, payload))


@router.put("/sort-order", response_model=ApiResponse[None])
def update_doctor_sort_order_item(
    payload: DoctorSortOrderPayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    update_doctor_sort_order(db, payload)
    return ok(None)


@router.put("/{doctor_id}", response_model=ApiResponse[DoctorItem])
def update_doctor_item(
    doctor_id: int,
    payload: DoctorPayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DoctorItem]:
    return ok(update_doctor(db, doctor_id, payload))


@router.post("/{doctor_id}/enable", response_model=ApiResponse[None])
def enable_doctor(
    doctor_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    set_doctor_status(db, doctor_id, "active")
    return ok(None)


@router.post("/{doctor_id}/disable", response_model=ApiResponse[None])
def disable_doctor(
    doctor_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    set_doctor_status(db, doctor_id, "disabled")
    return ok(None)


@router.delete("/{doctor_id}", response_model=ApiResponse[None])
def delete_doctor_item(
    doctor_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    delete_doctor(db, doctor_id)
    return ok(None)
