from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.doctor import Doctor
from app.models.doctor_province import DoctorProvince


DOCTOR_PROVINCES: dict[str, list[str]] = {
    "曹迎明": ["北京", "山东", "山西", "河北", "天津", "重庆"],
    "杜志业": ["北京", "山东", "山西", "河北", "天津", "重庆"],
    "范涛": ["北京", "山东", "山西", "河北", "天津", "重庆"],
    "关宇光": ["北京", "山东", "河北", "天津"],
    "姜争": ["北京", "山东", "山西", "河北", "天津", "重庆"],
    "彭俊": ["重庆"],
    "孙卫进": ["北京", "山东", "河北", "天津"],
    "邢云飞": ["山东", "河南"],
    "闫超": ["北京", "山东", "河北", "天津"],
    "张明山": ["北京", "山东", "山西", "河北", "天津", "重庆"],
    "张旭光": ["山东", "河南"],
    "赵萌": ["山东", "河南"],
    "王浩然": ["北京", "山东", "河北", "天津"],
    "张智波": ["重庆"],
    "李云": ["重庆"],
    "李璐华": ["重庆"],
    "高海滨": ["北京", "山东", "河北", "天津"],
}


def replace_doctor_provinces(db: Session) -> tuple[int, list[str]]:
    updated = 0
    missing_doctors: list[str] = []

    for doctor_name, provinces in DOCTOR_PROVINCES.items():
        doctor = db.scalar(select(Doctor).where(Doctor.name == doctor_name))
        if doctor is None:
            missing_doctors.append(doctor_name)
            continue

        db.execute(delete(DoctorProvince).where(DoctorProvince.doctor_id == doctor.id))
        for province in dict.fromkeys(provinces):
            db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        updated += 1

    return updated, missing_doctors


def main() -> None:
    with SessionLocal() as db:
        updated, missing_doctors = replace_doctor_provinces(db)
        db.commit()

    print(f"doctor province rows updated for doctors={updated}")
    if missing_doctors:
        print("missing doctors: " + ", ".join(missing_doctors))


if __name__ == "__main__":
    main()
