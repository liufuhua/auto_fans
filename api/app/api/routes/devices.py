from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user, get_page_params
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.common import ApiResponse, PageParams, PageResult, ok
from app.schemas.device import DeviceItem, DevicePayload
from app.services.devices import (
    create_device,
    list_device_options,
    list_devices,
    refresh_device_public_ip,
    set_device_enabled_status,
    update_device,
)

router = APIRouter(prefix="/devices")


@router.get("", response_model=ApiResponse[PageResult[DeviceItem]])
def get_devices(
    page_params: Annotated[PageParams, Depends(get_page_params)],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
    keyword: Annotated[str | None, Query(max_length=100)] = None,
    enabled_status: Annotated[
        Literal["enabled", "disabled"] | None, Query(alias="enabledStatus")
    ] = None,
    runtime_status: Annotated[
        Literal["offline", "idle", "running", "exception"] | None, Query(alias="runtimeStatus")
    ] = None,
) -> ApiResponse[PageResult[DeviceItem]]:
    return ok(list_devices(db, page_params, keyword, enabled_status, runtime_status))


@router.get("/options", response_model=ApiResponse[list[DeviceItem]])
def get_device_options(
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[list[DeviceItem]]:
    return ok(list_device_options(db))


@router.post("", response_model=ApiResponse[DeviceItem])
def create_device_item(
    payload: DevicePayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DeviceItem]:
    return ok(create_device(db, payload))


@router.put("/{device_id}", response_model=ApiResponse[DeviceItem])
def update_device_item(
    device_id: int,
    payload: DevicePayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DeviceItem]:
    return ok(update_device(db, device_id, payload))


@router.post("/{device_id}/enable", response_model=ApiResponse[None])
def enable_device(
    device_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    set_device_enabled_status(db, device_id, "enabled")
    return ok(None)


@router.post("/{device_id}/disable", response_model=ApiResponse[None])
def disable_device(
    device_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    set_device_enabled_status(db, device_id, "disabled")
    return ok(None)


@router.post("/{device_id}/refresh-ip", response_model=ApiResponse[DeviceItem])
def refresh_device_ip(
    device_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DeviceItem]:
    return ok(refresh_device_public_ip(db, device_id))
