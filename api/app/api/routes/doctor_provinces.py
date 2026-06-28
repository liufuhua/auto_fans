from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user, get_page_params
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.common import ApiResponse, PageParams, PageResult, ok
from app.schemas.doctor_province import DoctorProvinceItem, DoctorProvincePayload
from app.services.doctor_provinces import (
    list_doctor_provinces,
    list_province_options,
    update_doctor_provinces,
)

router = APIRouter(prefix="/doctor-provinces")


@router.get("", response_model=ApiResponse[PageResult[DoctorProvinceItem]])
def get_doctor_provinces(
    page_params: Annotated[PageParams, Depends(get_page_params)],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
    keyword: Annotated[str | None, Query(max_length=64)] = None,
) -> ApiResponse[PageResult[DoctorProvinceItem]]:
    return ok(list_doctor_provinces(db, page_params, keyword))


@router.get("/options", response_model=ApiResponse[list[str]])
def get_province_options(
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[list[str]]:
    return ok(list_province_options())


@router.put("/{doctor_id}", response_model=ApiResponse[DoctorProvinceItem])
def update_doctor_province_item(
    doctor_id: int,
    payload: DoctorProvincePayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DoctorProvinceItem]:
    return ok(update_doctor_provinces(db, doctor_id, payload))
