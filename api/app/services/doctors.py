from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.pinyin import pinyin_initials
from app.models.automation_result import AutomationResult
from app.models.comment_bank import CommentBankItem
from app.models.daily_task import DailyTaskItem
from app.models.device_action import DeviceDoctorActionRecord
from app.models.doctor import Doctor, DoctorKeyword
from app.schemas.common import PageParams, PageResult
from app.schemas.doctor import (
    DoctorItem,
    DoctorKeywordCommentCount,
    DoctorKeywordItem,
    DoctorKeywordPayload,
    DoctorPayload,
    DoctorSortOrderPayload,
)


def to_doctor_item(
    doctor: Doctor,
    remaining_comment_count: int = 0,
    keyword_comment_counts: list[DoctorKeywordCommentCount] | None = None,
) -> DoctorItem:
    return DoctorItem(
        id=doctor.id,
        name=doctor.name,
        real_name=doctor.real_name,
        sort_order=doctor.sort_order,
        remark=doctor.remark,
        status=doctor.status,
        remaining_comment_count=remaining_comment_count,
        keyword_comment_counts=keyword_comment_counts or [],
        created_at=doctor.created_at,
        updated_at=doctor.updated_at,
    )


def _apply_doctor_pinyin_fields(doctor: Doctor) -> None:
    doctor.name_pinyin = pinyin_initials(doctor.name)
    doctor.real_name_pinyin = pinyin_initials(doctor.real_name or doctor.name)


def _remaining_comment_counts(db: Session, doctor_ids: list[int]) -> dict[int, int]:
    if not doctor_ids:
        return {}
    rows = db.execute(
        select(CommentBankItem.doctor_id, func.count(CommentBankItem.id))
        .where(CommentBankItem.doctor_id.in_(doctor_ids))
        .where(CommentBankItem.status == "unused")
        .group_by(CommentBankItem.doctor_id)
    ).all()
    return {doctor_id: count for doctor_id, count in rows}


def _remaining_keyword_comment_counts(db: Session, keyword_ids: list[int]) -> dict[int, int]:
    if not keyword_ids:
        return {}
    rows = db.execute(
        select(CommentBankItem.keyword_id, func.count(CommentBankItem.id))
        .where(CommentBankItem.keyword_id.in_(keyword_ids))
        .where(CommentBankItem.status == "unused")
        .group_by(CommentBankItem.keyword_id)
    ).all()
    return {keyword_id: count for keyword_id, count in rows}


def _keyword_comment_count_items(
    db: Session, doctor_ids: list[int]
) -> dict[int, list[DoctorKeywordCommentCount]]:
    if not doctor_ids:
        return {}

    keywords = db.scalars(
        select(DoctorKeyword)
        .where(DoctorKeyword.doctor_id.in_(doctor_ids))
        .where(DoctorKeyword.status != "deleted")
        .order_by(DoctorKeyword.doctor_id, DoctorKeyword.id.desc())
    ).all()
    counts = _remaining_keyword_comment_counts(db, [keyword.id for keyword in keywords])
    result: dict[int, list[DoctorKeywordCommentCount]] = {doctor_id: [] for doctor_id in doctor_ids}
    for keyword in keywords:
        result.setdefault(keyword.doctor_id, []).append(
            DoctorKeywordCommentCount(
                keyword_id=keyword.id,
                keyword=keyword.keyword,
                remaining_comment_count=counts.get(keyword.id, 0),
            )
        )
    return result


def get_doctor_or_404(db: Session, doctor_id: int) -> Doctor:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None or doctor.status == "deleted":
        raise AppException("医生不存在", code="DOCTOR_NOT_FOUND", status_code=404)
    return doctor


def _apply_doctor_filters(
    statement: Select[tuple[Doctor]], keyword: str | None, status: str | None
) -> Select[tuple[Doctor]]:
    statement = statement.where(Doctor.status != "deleted")
    if keyword:
        keyword_like = f"%{keyword.strip()}%"
        statement = statement.where(
            or_(
                Doctor.name.like(keyword_like),
                Doctor.real_name.like(keyword_like),
                Doctor.remark.like(keyword_like),
            )
        )
    if status:
        statement = statement.where(Doctor.status == status)
    return statement


def list_doctors(
    db: Session,
    page_params: PageParams,
    keyword: str | None,
    status: str | None,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> PageResult[DoctorItem]:
    statement = _apply_doctor_filters(select(Doctor), keyword, status)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    doctors = db.scalars(
        statement.order_by(*_doctor_order_by(sort_by, sort_order))
        .offset((page_params.page - 1) * page_params.page_size)
        .limit(page_params.page_size)
    ).all()
    counts = _remaining_comment_counts(db, [doctor.id for doctor in doctors])
    keyword_counts = _keyword_comment_count_items(db, [doctor.id for doctor in doctors])
    return PageResult(
        items=[
            to_doctor_item(
                doctor,
                counts.get(doctor.id, 0),
                keyword_counts.get(doctor.id, []),
            )
            for doctor in doctors
        ],
        total=total,
    )


def _doctor_order_by(sort_by: str | None, sort_order: str | None) -> list[object]:
    sort_columns = {
        "name": Doctor.name_pinyin,
        "realName": Doctor.real_name_pinyin,
        "status": Doctor.status,
        "createdAt": Doctor.created_at,
        "updatedAt": Doctor.updated_at,
    }
    sort_column = sort_columns.get(sort_by or "")
    if sort_column is None or sort_order not in {"ascending", "descending"}:
        return [Doctor.sort_order.asc(), Doctor.id.asc()]
    direction = sort_column.desc() if sort_order == "descending" else sort_column.asc()
    return [direction, Doctor.sort_order.asc(), Doctor.id.asc()]


def list_active_doctor_options(db: Session) -> list[DoctorItem]:
    doctors = db.scalars(
        select(Doctor)
        .where(Doctor.status == "active")
        .order_by(Doctor.sort_order.asc(), Doctor.id.asc())
    ).all()
    counts = _remaining_comment_counts(db, [doctor.id for doctor in doctors])
    keyword_counts = _keyword_comment_count_items(db, [doctor.id for doctor in doctors])
    return [
        to_doctor_item(doctor, counts.get(doctor.id, 0), keyword_counts.get(doctor.id, []))
        for doctor in doctors
    ]


def ensure_doctor_name_unique(db: Session, name: str, exclude_doctor_id: int | None = None) -> None:
    statement = select(Doctor).where(Doctor.name == name, Doctor.status != "deleted")
    if exclude_doctor_id is not None:
        statement = statement.where(Doctor.id != exclude_doctor_id)
    if db.scalar(statement) is not None:
        raise AppException("医生姓名已存在", code="DOCTOR_NAME_EXISTS", status_code=409)


def _next_doctor_sort_order(db: Session) -> int:
    max_sort_order = db.scalar(
        select(func.max(Doctor.sort_order)).where(Doctor.status != "deleted")
    )
    return (max_sort_order or 0) + 1


def create_doctor(db: Session, payload: DoctorPayload) -> DoctorItem:
    ensure_doctor_name_unique(db, payload.name)
    doctor = Doctor(
        name=payload.name,
        real_name=payload.real_name,
        name_pinyin=pinyin_initials(payload.name),
        real_name_pinyin=pinyin_initials(payload.real_name or payload.name),
        sort_order=_next_doctor_sort_order(db),
        remark=payload.remark,
        status="active",
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return to_doctor_item(doctor)


def update_doctor(db: Session, doctor_id: int, payload: DoctorPayload) -> DoctorItem:
    doctor = get_doctor_or_404(db, doctor_id)
    ensure_doctor_name_unique(db, payload.name, exclude_doctor_id=doctor_id)
    doctor.name = payload.name
    doctor.real_name = payload.real_name
    _apply_doctor_pinyin_fields(doctor)
    doctor.remark = payload.remark
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return to_doctor_item(doctor)


def update_doctor_sort_order(db: Session, payload: DoctorSortOrderPayload) -> None:
    if not payload.items:
        return

    doctor_ids = [item.id for item in payload.items]
    target_doctors = db.scalars(
        select(Doctor).where(Doctor.id.in_(doctor_ids), Doctor.status != "deleted")
    ).all()
    doctors_by_id = {doctor.id: doctor for doctor in target_doctors}
    if len(doctors_by_id) != len(set(doctor_ids)):
        raise AppException("医生不存在", code="DOCTOR_NOT_FOUND", status_code=404)

    all_doctors = db.scalars(
        select(Doctor)
        .where(Doctor.status != "deleted")
        .order_by(Doctor.sort_order.asc(), Doctor.id.asc())
    ).all()

    for item in payload.items:
        doctor = doctors_by_id[item.id]
        all_doctors = [candidate for candidate in all_doctors if candidate.id != doctor.id]
        target_index = min(max(item.sort_order - 1, 0), len(all_doctors))
        all_doctors.insert(target_index, doctor)

    for index, doctor in enumerate(all_doctors, start=1):
        doctor.sort_order = index
        db.add(doctor)
    db.commit()


def set_doctor_status(db: Session, doctor_id: int, status: str) -> DoctorItem:
    doctor = get_doctor_or_404(db, doctor_id)
    doctor.status = status
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return to_doctor_item(doctor)


def _count_rows(db: Session, statement: Select[tuple[object]]) -> int:
    return db.scalar(select(func.count()).select_from(statement.subquery())) or 0


def _raise_if_doctor_referenced(db: Session, doctor_id: int) -> None:
    reference_count = (
        _count_rows(db, select(CommentBankItem.id).where(CommentBankItem.doctor_id == doctor_id))
        + _count_rows(db, select(DailyTaskItem.id).where(DailyTaskItem.doctor_id == doctor_id))
        + _count_rows(db, select(AutomationResult.id).where(AutomationResult.doctor_id == doctor_id))
        + _count_rows(
            db,
            select(DeviceDoctorActionRecord.id).where(
                DeviceDoctorActionRecord.doctor_id == doctor_id
            ),
        )
    )
    if reference_count:
        raise AppException(
            "医生已被评论词库、任务或执行记录引用，不能删除；如需停用请使用禁用",
            code="DOCTOR_IN_USE",
            status_code=409,
        )


def _raise_if_doctor_keyword_referenced(db: Session, keyword_id: int) -> None:
    reference_count = (
        _count_rows(db, select(CommentBankItem.id).where(CommentBankItem.keyword_id == keyword_id))
        + _count_rows(db, select(DailyTaskItem.id).where(DailyTaskItem.keyword_id == keyword_id))
        + _count_rows(db, select(AutomationResult.id).where(AutomationResult.keyword_id == keyword_id))
        + _count_rows(
            db,
            select(DeviceDoctorActionRecord.id).where(
                DeviceDoctorActionRecord.keyword_id == keyword_id
            ),
        )
    )
    if reference_count:
        raise AppException(
            "医生关键词已被评论词库、任务或执行记录引用，不能删除；如需停用请使用禁用",
            code="DOCTOR_KEYWORD_IN_USE",
            status_code=409,
        )


def delete_doctor(db: Session, doctor_id: int) -> None:
    doctor = get_doctor_or_404(db, doctor_id)
    doctor.status = "deleted"
    db.add(doctor)
    db.commit()


def to_doctor_keyword_item(
    keyword: DoctorKeyword, remaining_comment_count: int = 0
) -> DoctorKeywordItem:
    return DoctorKeywordItem(
        id=keyword.id,
        doctor_id=keyword.doctor_id,
        keyword=keyword.keyword,
        remark=keyword.remark,
        status=keyword.status,
        remaining_comment_count=remaining_comment_count,
        created_at=keyword.created_at,
    )


def get_doctor_keyword_or_404(db: Session, keyword_id: int) -> DoctorKeyword:
    keyword = db.get(DoctorKeyword, keyword_id)
    if keyword is None or keyword.status == "deleted":
        raise AppException("医生关键词不存在", code="DOCTOR_KEYWORD_NOT_FOUND", status_code=404)
    return keyword


def list_doctor_keywords(db: Session, doctor_id: int) -> list[DoctorKeywordItem]:
    get_doctor_or_404(db, doctor_id)
    keywords = db.scalars(
        select(DoctorKeyword)
        .where(DoctorKeyword.doctor_id == doctor_id)
        .where(DoctorKeyword.status != "deleted")
        .order_by(DoctorKeyword.id.desc())
    ).all()
    counts = _remaining_keyword_comment_counts(db, [keyword.id for keyword in keywords])
    return [to_doctor_keyword_item(keyword, counts.get(keyword.id, 0)) for keyword in keywords]


def list_active_doctor_keyword_options(
    db: Session, doctor_id: int | None = None
) -> list[DoctorKeywordItem]:
    statement = (
        select(DoctorKeyword)
        .join(Doctor, Doctor.id == DoctorKeyword.doctor_id)
        .where(DoctorKeyword.status == "active")
        .where(Doctor.status == "active")
    )
    if doctor_id:
        statement = statement.where(DoctorKeyword.doctor_id == doctor_id)
    keywords = db.scalars(statement.order_by(DoctorKeyword.id.desc())).all()
    counts = _remaining_keyword_comment_counts(db, [keyword.id for keyword in keywords])
    return [to_doctor_keyword_item(keyword, counts.get(keyword.id, 0)) for keyword in keywords]


def ensure_doctor_keyword_unique(
    db: Session, *, doctor_id: int, keyword: str, exclude_keyword_id: int | None = None
) -> None:
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        raise AppException("关键词不能为空", code="DOCTOR_KEYWORD_REQUIRED", status_code=400)
    statement = select(DoctorKeyword).where(
        DoctorKeyword.doctor_id == doctor_id,
        DoctorKeyword.keyword == normalized_keyword,
        DoctorKeyword.status != "deleted",
    )
    if exclude_keyword_id is not None:
        statement = statement.where(DoctorKeyword.id != exclude_keyword_id)
    if db.scalar(statement) is not None:
        raise AppException("该医生下关键词已存在", code="DOCTOR_KEYWORD_EXISTS", status_code=409)


def create_doctor_keyword(
    db: Session, doctor_id: int, payload: DoctorKeywordPayload
) -> DoctorKeywordItem:
    get_doctor_or_404(db, doctor_id)
    keyword_text = payload.keyword.strip()
    remark_text = payload.remark.strip()
    if not keyword_text:
        raise AppException("关键词不能为空", code="DOCTOR_KEYWORD_REQUIRED", status_code=400)
    existing_keyword = db.scalar(
        select(DoctorKeyword).where(
            DoctorKeyword.doctor_id == doctor_id,
            DoctorKeyword.keyword == keyword_text,
        )
    )
    if existing_keyword is not None:
        if existing_keyword.status == "deleted":
            existing_keyword.status = "active"
            existing_keyword.remark = remark_text
            db.add(existing_keyword)
            db.commit()
            db.refresh(existing_keyword)
            return to_doctor_keyword_item(existing_keyword)
        raise AppException("该医生下关键词已存在", code="DOCTOR_KEYWORD_EXISTS", status_code=409)

    keyword = DoctorKeyword(
        doctor_id=doctor_id,
        keyword=keyword_text,
        remark=remark_text,
        status="active",
    )
    db.add(keyword)
    db.commit()
    db.refresh(keyword)
    return to_doctor_keyword_item(keyword)


def update_doctor_keyword(
    db: Session, keyword_id: int, payload: DoctorKeywordPayload
) -> DoctorKeywordItem:
    keyword = get_doctor_keyword_or_404(db, keyword_id)
    keyword_text = payload.keyword.strip()
    remark_text = payload.remark.strip()
    ensure_doctor_keyword_unique(
        db,
        doctor_id=keyword.doctor_id,
        keyword=keyword_text,
        exclude_keyword_id=keyword_id,
    )
    keyword.keyword = keyword_text
    keyword.remark = remark_text
    db.add(keyword)
    db.commit()
    db.refresh(keyword)
    return to_doctor_keyword_item(keyword)


def set_doctor_keyword_status(db: Session, keyword_id: int, status: str) -> DoctorKeywordItem:
    keyword = get_doctor_keyword_or_404(db, keyword_id)
    keyword.status = status
    db.add(keyword)
    db.commit()
    db.refresh(keyword)
    return to_doctor_keyword_item(keyword)


def delete_doctor_keyword(db: Session, keyword_id: int) -> None:
    keyword = get_doctor_keyword_or_404(db, keyword_id)
    keyword.status = "deleted"
    db.add(keyword)
    db.commit()
