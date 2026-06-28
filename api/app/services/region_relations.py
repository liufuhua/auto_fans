from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.region_relation import RegionRelation
from app.schemas.region_relation import RegionRelationItem, RegionRelationPayload

DEFAULT_REGION_NEIGHBORS: dict[str, list[str]] = {
    "北京": ["天津", "河北"],
    "天津": ["北京", "河北"],
    "河北": ["北京", "天津", "山西", "河南", "山东", "内蒙古", "辽宁"],
    "山西": ["河北", "河南", "陕西", "内蒙古"],
    "内蒙古": ["黑龙江", "吉林", "辽宁", "河北", "山西", "陕西", "宁夏", "甘肃"],
    "辽宁": ["吉林", "内蒙古", "河北"],
    "吉林": ["黑龙江", "辽宁", "内蒙古"],
    "黑龙江": ["吉林", "内蒙古"],
    "上海": ["江苏", "浙江"],
    "江苏": ["山东", "安徽", "浙江", "上海"],
    "浙江": ["上海", "江苏", "安徽", "江西", "福建"],
    "安徽": ["江苏", "浙江", "江西", "湖北", "河南", "山东"],
    "福建": ["浙江", "江西", "广东", "台湾"],
    "江西": ["浙江", "福建", "广东", "湖南", "湖北", "安徽"],
    "山东": ["河北", "河南", "安徽", "江苏"],
    "河南": ["河北", "山西", "陕西", "湖北", "安徽", "山东"],
    "湖北": ["河南", "安徽", "江西", "湖南", "重庆", "陕西"],
    "湖南": ["湖北", "江西", "广东", "广西", "贵州", "重庆"],
    "广东": ["福建", "江西", "湖南", "广西", "海南", "香港", "澳门"],
    "广西": ["广东", "湖南", "贵州", "云南", "海南"],
    "海南": ["广东", "广西"],
    "重庆": ["四川", "陕西", "湖北", "湖南", "贵州"],
    "四川": ["重庆", "贵州", "云南", "西藏", "青海", "甘肃", "陕西"],
    "贵州": ["重庆", "四川", "云南", "广西", "湖南"],
    "云南": ["四川", "贵州", "广西", "西藏"],
    "西藏": ["新疆", "青海", "四川", "云南"],
    "陕西": ["内蒙古", "山西", "河南", "湖北", "重庆", "四川", "甘肃", "宁夏"],
    "甘肃": ["新疆", "青海", "四川", "陕西", "宁夏", "内蒙古"],
    "青海": ["新疆", "西藏", "四川", "甘肃"],
    "宁夏": ["内蒙古", "陕西", "甘肃"],
    "新疆": ["西藏", "青海", "甘肃"],
    "香港": ["广东"],
    "澳门": ["广东"],
    "台湾": ["福建"],
}


def list_region_relations(db: Session) -> list[RegionRelationItem]:
    ensure_default_region_relations(db)
    rows = db.scalars(select(RegionRelation).order_by(RegionRelation.id.asc())).all()
    return [_to_region_relation_item(row) for row in rows]


def list_region_options(db: Session) -> list[str]:
    ensure_default_region_relations(db)
    return list(db.scalars(select(RegionRelation.region).order_by(RegionRelation.id.asc())).all())


def get_related_regions(db: Session, region: str) -> set[str]:
    normalized_region = region.strip()
    if not normalized_region:
        return set()
    ensure_default_region_relations(db)
    relation = db.scalar(select(RegionRelation).where(RegionRelation.region == normalized_region))
    if relation is None:
        return {normalized_region}
    try:
        neighbors = json.loads(relation.neighbors)
    except json.JSONDecodeError:
        neighbors = []
    if not isinstance(neighbors, list):
        neighbors = []
    return {normalized_region, *[str(item).strip() for item in neighbors if str(item).strip()]}


def update_region_relation(
    db: Session, region_id: int, payload: RegionRelationPayload
) -> RegionRelationItem:
    ensure_default_region_relations(db)
    relation = db.get(RegionRelation, region_id)
    if relation is None:
        raise AppException("地区关联不存在", code="REGION_RELATION_NOT_FOUND", status_code=404)

    all_regions = set(list_region_options(db))
    neighbors = []
    for neighbor in payload.neighbors:
        normalized = neighbor.strip()
        if not normalized or normalized == relation.region or normalized in neighbors:
            continue
        if normalized not in all_regions:
            raise AppException(
                f"无效关联地区：{normalized}", code="REGION_NEIGHBOR_INVALID", status_code=400
            )
        neighbors.append(normalized)

    relation.neighbors = json.dumps(neighbors, ensure_ascii=False)
    db.add(relation)
    db.commit()
    db.refresh(relation)
    return _to_region_relation_item(relation)


def reset_region_relations(db: Session) -> list[RegionRelationItem]:
    existing = {row.region: row for row in db.scalars(select(RegionRelation)).all()}
    now = datetime.now(UTC)
    for region, neighbors in DEFAULT_REGION_NEIGHBORS.items():
        relation = existing.get(region)
        if relation is None:
            relation = RegionRelation(region=region, neighbors="[]")
        relation.neighbors = json.dumps(neighbors, ensure_ascii=False)
        relation.updated_at = now
        db.add(relation)
    db.commit()
    return list_region_relations(db)


def ensure_default_region_relations(db: Session) -> None:
    existing_count = db.scalar(select(RegionRelation.id).limit(1))
    if existing_count is not None:
        return
    for region, neighbors in DEFAULT_REGION_NEIGHBORS.items():
        db.add(
            RegionRelation(
                region=region,
                neighbors=json.dumps(neighbors, ensure_ascii=False),
            )
        )
    db.commit()


def _to_region_relation_item(row: RegionRelation) -> RegionRelationItem:
    try:
        neighbors = json.loads(row.neighbors)
    except json.JSONDecodeError:
        neighbors = []
    if not isinstance(neighbors, list):
        neighbors = []
    return RegionRelationItem(
        id=row.id,
        region=row.region,
        neighbors=[str(item) for item in neighbors],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
