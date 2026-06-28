from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_admin_user
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.common import ApiResponse, ok
from app.schemas.region_relation import RegionRelationItem, RegionRelationPayload
from app.services.region_relations import (
    list_region_options,
    list_region_relations,
    reset_region_relations,
    update_region_relation,
)

router = APIRouter(prefix="/region-relations")


@router.get("", response_model=ApiResponse[list[RegionRelationItem]])
def get_region_relations(
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[list[RegionRelationItem]]:
    return ok(list_region_relations(db))


@router.get("/options", response_model=ApiResponse[list[str]])
def get_region_options(
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[list[str]]:
    return ok(list_region_options(db))


@router.put("/{region_id}", response_model=ApiResponse[RegionRelationItem])
def update_region_relation_item(
    region_id: int,
    payload: RegionRelationPayload,
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[RegionRelationItem]:
    return ok(update_region_relation(db, region_id, payload))


@router.post("/reset-defaults", response_model=ApiResponse[list[RegionRelationItem]])
def reset_region_relation_items(
    db: Annotated[Session, Depends(get_db)],
    _current_user: Annotated[AdminUser, Depends(get_current_active_admin_user)],
) -> ApiResponse[list[RegionRelationItem]]:
    return ok(reset_region_relations(db))
