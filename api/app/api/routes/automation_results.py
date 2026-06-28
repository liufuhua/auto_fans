from datetime import date
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user, get_page_params
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.automation_result import AutomationResultItemRead
from app.schemas.common import ApiResponse, PageParams, PageResult, ok
from app.services.automation_results import (
    export_automation_result_summary_by_date_range,
    list_automation_results,
    save_automation_result_summary_to_desktop,
)

router = APIRouter(prefix="/automation-results")


@router.get("/export")
def export_automation_results(
    start_date: Annotated[date, Query(alias="startDate")],
    end_date: Annotated[date, Query(alias="endDate")],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> StreamingResponse:
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    filename = f"医生评论统计表_{start_date.isoformat()}_{end_date.isoformat()}.xlsx"
    encoded_filename = quote(filename)
    return StreamingResponse(
        export_automation_result_summary_by_date_range(db, start_date, end_date),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{encoded_filename}"
            )
        },
    )


@router.post("/export-to-desktop", response_model=ApiResponse[dict[str, str]])
def export_automation_results_to_desktop(
    start_date: Annotated[date, Query(alias="startDate")],
    end_date: Annotated[date, Query(alias="endDate")],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[dict[str, str]]:
    output_path = save_automation_result_summary_to_desktop(db, start_date, end_date)
    return ok({"path": str(output_path)})


@router.get("", response_model=ApiResponse[PageResult[AutomationResultItemRead]])
def get_automation_results(
    page_params: Annotated[PageParams, Depends(get_page_params)],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
    task_id: Annotated[int | None, Query(alias="taskId")] = None,
    doctor_id: Annotated[int | None, Query(alias="doctorId")] = None,
    keyword_id: Annotated[int | None, Query(alias="keywordId")] = None,
    device_id: Annotated[int | None, Query(alias="deviceId")] = None,
    status: Annotated[Literal["success", "failed"] | None, Query()] = None,
    keyword: Annotated[str | None, Query(max_length=100)] = None,
) -> ApiResponse[PageResult[AutomationResultItemRead]]:
    return ok(
        list_automation_results(
            db,
            page_params,
            task_id,
            doctor_id,
            keyword_id,
            device_id,
            status,
            keyword,
        )
    )
