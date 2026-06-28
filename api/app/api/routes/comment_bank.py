from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user, get_page_params
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.comment_bank import (
    CommentBankBatchDeletePayload,
    CommentBankBatchDeleteResponse,
    CommentBankImportResponse,
    CommentBankItemRead,
)
from app.schemas.common import ApiResponse, PageParams, PageResult, ok
from app.services.comment_bank import (
    batch_delete_comment_bank_items,
    delete_comment_bank_item,
    import_comment_bank_excel,
    list_comment_bank_items,
)

router = APIRouter(prefix="/comment-bank")


@router.get("", response_model=ApiResponse[PageResult[CommentBankItemRead]])
def get_comment_bank(
    page_params: Annotated[PageParams, Depends(get_page_params)],
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
    doctor_id: Annotated[int | None, Query(alias="doctorId")] = None,
    keyword_id: Annotated[int | None, Query(alias="keywordId")] = None,
    status: Annotated[Literal["unused", "used"] | None, Query()] = None,
    keyword: Annotated[str | None, Query(max_length=100)] = None,
) -> ApiResponse[PageResult[CommentBankItemRead]]:
    return ok(list_comment_bank_items(db, page_params, doctor_id, keyword_id, status, keyword))


@router.delete("/{item_id}", response_model=ApiResponse[None])
def delete_comment(
    item_id: int,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[None]:
    delete_comment_bank_item(db, item_id)
    return ok(None)


@router.post("/batch-delete", response_model=ApiResponse[CommentBankBatchDeleteResponse])
def batch_delete_comments(
    payload: CommentBankBatchDeletePayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[CommentBankBatchDeleteResponse]:
    deleted = batch_delete_comment_bank_items(db, payload.ids)
    return ok(CommentBankBatchDeleteResponse(deleted=deleted))


@router.post("/import-excel", response_model=ApiResponse[CommentBankImportResponse])
async def import_excel(
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
    doctor_id: Annotated[int, Form(alias="doctorId")],
    file: Annotated[UploadFile, File()],
) -> ApiResponse[CommentBankImportResponse]:
    file_bytes = await file.read()
    return ok(import_comment_bank_excel(db, doctor_id, file_bytes))
