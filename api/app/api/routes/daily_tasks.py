from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user, get_page_params
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.common import ApiResponse, PageParams, PageResult, ok
from app.schemas.daily_task import (
    DailyTaskCreatePayload,
    DailyTaskDeviceDetailsRead,
    DailyTaskDispatchRead,
    DailyTaskItemSortOrderPayload,
    DailyTaskRead,
)
from app.services.daily_tasks import (
    create_daily_task,
    dispatch_daily_task,
    list_daily_task_device_details,
    list_daily_task_options,
    list_daily_tasks,
    reset_daily_task_dispatch,
    stop_daily_task,
    update_daily_task_item_sort_order,
)

router = APIRouter(prefix="/daily-tasks")


@router.get("", response_model=ApiResponse[PageResult[DailyTaskRead]])
def get_daily_tasks(
    page_params: Annotated[PageParams, Depends(get_page_params)],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
    task_date: Annotated[str | None, Query(alias="taskDate")] = None,
    status: Annotated[
        Literal["pending", "running", "completed", "stopped", "exception"] | None, Query()
    ] = None,
) -> ApiResponse[PageResult[DailyTaskRead]]:
    return ok(list_daily_tasks(db, page_params, task_date, status))


@router.get("/options", response_model=ApiResponse[list[DailyTaskRead]])
def get_daily_task_options(
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[list[DailyTaskRead]]:
    return ok(list_daily_task_options(db))


@router.post("", response_model=ApiResponse[DailyTaskRead])
def create_daily_task_item(
    payload: DailyTaskCreatePayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DailyTaskRead]:
    return ok(create_daily_task(db, payload, current_user.username, current_user.id))


@router.put("/{task_id}/items/sort-order", response_model=ApiResponse[DailyTaskRead])
def update_daily_task_item_sort_order_item(
    task_id: int,
    payload: DailyTaskItemSortOrderPayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DailyTaskRead]:
    return ok(update_daily_task_item_sort_order(db, task_id, payload))


@router.post("/{task_id}/dispatch", response_model=ApiResponse[DailyTaskDispatchRead])
def dispatch_daily_task_item(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DailyTaskDispatchRead]:
    return ok(dispatch_daily_task(db, task_id))


@router.post("/{task_id}/dispatch/reset", response_model=ApiResponse[None])
def reset_daily_task_dispatch_item(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    reset_daily_task_dispatch(db, task_id)
    return ok(None)


@router.get("/{task_id}/device-details", response_model=ApiResponse[DailyTaskDeviceDetailsRead])
def get_daily_task_device_details(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[DailyTaskDeviceDetailsRead]:
    return ok(list_daily_task_device_details(db, task_id))


@router.post("/{task_id}/stop", response_model=ApiResponse[None])
def stop_daily_task_item(
    task_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    stop_daily_task(db, task_id)
    return ok(None)
