from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.automation import (
    AutomationDeviceConfigResponse,
    AutomationRuntimePayload,
    AutomationRuntimeResponse,
    AutomationServiceStatusResponse,
    ClaimMatchedDoctorCommentPayload,
    ClaimMatchedDoctorCommentResponse,
    ClaimTaskPayload,
    ClaimTaskResponse,
    DeviceHeartbeatPayload,
    DeviceHeartbeatResponse,
    ReportTaskPayload,
    ReportTaskResponse,
    StartTaskPayload,
    StartTaskResponse,
)
from app.schemas.common import ApiResponse, ok
from app.services.automation import (
    auto_stop_runtime,
    claim_matched_doctor_comment,
    claim_task,
    get_runtime_state,
    heartbeat_device,
    list_enabled_device_configs,
    report_task,
    start_runtime,
    start_task,
    stop_runtime,
)
from app.services.system_services import get_service_status

router = APIRouter(prefix="/automation")


@router.get("/runtime", response_model=ApiResponse[AutomationRuntimeResponse])
def runtime_state(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AutomationRuntimeResponse]:
    return ok(get_runtime_state(db))


@router.get("/runtime/services", response_model=ApiResponse[AutomationServiceStatusResponse])
def runtime_services(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AutomationServiceStatusResponse]:
    return ok(AutomationServiceStatusResponse.model_validate(get_service_status(db)))


@router.post("/runtime/start", response_model=ApiResponse[AutomationRuntimeResponse])
def start_business(
    payload: AutomationRuntimePayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[AutomationRuntimeResponse]:
    return ok(start_runtime(db, payload))


@router.post("/runtime/stop", response_model=ApiResponse[AutomationRuntimeResponse])
def stop_business(
    payload: AutomationRuntimePayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[AutomationRuntimeResponse]:
    return ok(stop_runtime(db, payload))


@router.post("/runtime/auto-stop", response_model=ApiResponse[AutomationRuntimeResponse])
def auto_stop_business(
    payload: AutomationRuntimePayload,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[AutomationRuntimeResponse]:
    return ok(auto_stop_runtime(db, payload))


@router.post("/devices/heartbeat", response_model=ApiResponse[DeviceHeartbeatResponse])
def heartbeat(
    payload: DeviceHeartbeatPayload,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DeviceHeartbeatResponse]:
    return ok(heartbeat_device(db, payload))


@router.get("/devices/configs", response_model=ApiResponse[list[AutomationDeviceConfigResponse]])
def device_configs(
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[AutomationDeviceConfigResponse]]:
    return ok(list_enabled_device_configs(db))


@router.post("/tasks/claim", response_model=ApiResponse[ClaimTaskResponse])
def claim(
    payload: ClaimTaskPayload,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ClaimTaskResponse]:
    return ok(claim_task(db, payload))


@router.post(
    "/tasks/matched-comment/claim",
    response_model=ApiResponse[ClaimMatchedDoctorCommentResponse],
)
def claim_matched_comment(
    payload: ClaimMatchedDoctorCommentPayload,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ClaimMatchedDoctorCommentResponse]:
    return ok(claim_matched_doctor_comment(db, payload))


@router.post("/tasks/{task_item_id}/start", response_model=ApiResponse[StartTaskResponse])
def start(
    task_item_id: int,
    payload: StartTaskPayload,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[StartTaskResponse]:
    return ok(start_task(db, task_item_id, payload))


@router.post("/tasks/{task_item_id}/report", response_model=ApiResponse[ReportTaskResponse])
def report(
    task_item_id: int,
    payload: ReportTaskPayload,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ReportTaskResponse]:
    return ok(report_task(db, task_item_id, payload))
