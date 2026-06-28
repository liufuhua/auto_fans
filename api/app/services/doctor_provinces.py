from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.doctor import Doctor
from app.models.doctor_province import DoctorProvince
from app.schemas.common import PageParams, PageResult
from app.schemas.doctor_province import DoctorProvinceItem, DoctorProvincePayload

CHINA_PROVINCES = [
    "北京",
    "天津",
    "河北",
    "山西",
    "内蒙古",
    "辽宁",
    "吉林",
    "黑龙江",
    "上海",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "广西",
    "海南",
    "重庆",
    "四川",
    "贵州",
    "云南",
    "西藏",
    "陕西",
    "甘肃",
    "青海",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
    "台湾",
]


def _doctor_province_maps(
    db: Session, doctor_ids: set[int]
) -> tuple[dict[int, list[str]], dict[int, datetime | None]]:
    if not doctor_ids:
        return {}, {}

    rows = db.execute(
        select(DoctorProvince)
        .where(DoctorProvince.doctor_id.in_(doctor_ids))
        .order_by(DoctorProvince.doctor_id.asc(), DoctorProvince.id.asc())
    ).scalars()
    provinces_by_doctor_id: dict[int, list[str]] = {}
    updated_at_by_doctor_id: dict[int, datetime | None] = {}
    for row in rows:
        provinces_by_doctor_id.setdefault(row.doctor_id, []).append(row.province)
        current_updated_at = updated_at_by_doctor_id.get(row.doctor_id)
        if current_updated_at is None or row.updated_at > current_updated_at:
            updated_at_by_doctor_id[row.doctor_id] = row.updated_at

    return provinces_by_doctor_id, updated_at_by_doctor_id


def _to_doctor_province_item(
    doctor: Doctor,
    provinces_by_doctor_id: dict[int, list[str]],
    updated_at_by_doctor_id: dict[int, datetime | None],
) -> DoctorProvinceItem:
    return DoctorProvinceItem(
        doctor_id=doctor.id,
        doctor_name=doctor.name,
        provinces=provinces_by_doctor_id.get(doctor.id, []),
        updated_at=updated_at_by_doctor_id.get(doctor.id),
    )


def list_doctor_provinces(
    db: Session, page_params: PageParams, keyword: str | None
) -> PageResult[DoctorProvinceItem]:
    statement = select(Doctor).where(Doctor.status == "active")
    if keyword:
        statement = statement.where(Doctor.name.like(f"%{keyword}%"))

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    doctors = db.scalars(
        statement.order_by(Doctor.id.desc())
        .offset((page_params.page - 1) * page_params.page_size)
        .limit(page_params.page_size)
    ).all()

    doctor_ids = {doctor.id for doctor in doctors}
    provinces_by_doctor_id, updated_at_by_doctor_id = _doctor_province_maps(db, doctor_ids)
    return PageResult(
        items=[
            _to_doctor_province_item(doctor, provinces_by_doctor_id, updated_at_by_doctor_id)
            for doctor in doctors
        ],
        total=total,
    )


def update_doctor_provinces(
    db: Session, doctor_id: int, payload: DoctorProvincePayload
) -> DoctorProvinceItem:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None or doctor.status != "active":
        raise AppException("医生不存在", code="DOCTOR_NOT_FOUND", status_code=404)

    db.execute(delete(DoctorProvince).where(DoctorProvince.doctor_id == doctor_id))
    for province in payload.provinces:
        db.add(DoctorProvince(doctor_id=doctor_id, province=province))
    db.commit()

    provinces_by_doctor_id, updated_at_by_doctor_id = _doctor_province_maps(db, {doctor_id})
    return _to_doctor_province_item(doctor, provinces_by_doctor_id, updated_at_by_doctor_id)


def list_province_options() -> list[str]:
    return CHINA_PROVINCES
