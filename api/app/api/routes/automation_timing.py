from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.automation_timing import (
    AutomationTimingSettingItem,
    AutomationTimingSettingsPayload,
)
from app.schemas.common import ApiResponse, ok
from app.services.automation_timing import (
    list_automation_timing_settings,
    reset_automation_timing_settings,
    update_automation_timing_settings,
)

router = APIRouter(prefix="/automation/timing-settings")


@router.get("", response_model=ApiResponse[list[AutomationTimingSettingItem]])
def get_timing_settings(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[AutomationTimingSettingItem]]:
    return ok(list_automation_timing_settings(db))


@router.put("", response_model=ApiResponse[list[AutomationTimingSettingItem]])
def update_timing_settings(
    payload: AutomationTimingSettingsPayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[list[AutomationTimingSettingItem]]:
    return ok(update_automation_timing_settings(db, payload))


@router.post("/reset-defaults", response_model=ApiResponse[list[AutomationTimingSettingItem]])
def reset_timing_settings(
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[list[AutomationTimingSettingItem]]:
    return ok(reset_automation_timing_settings(db))
