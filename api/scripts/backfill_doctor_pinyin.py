from sqlalchemy import select

from app.core.pinyin import pinyin_initials
from app.db.session import SessionLocal
from app.models.doctor import Doctor


def main() -> None:
    with SessionLocal() as db:
        doctors = db.scalars(select(Doctor)).all()
        for doctor in doctors:
            doctor.name_pinyin = pinyin_initials(doctor.name)
            doctor.real_name_pinyin = pinyin_initials(doctor.real_name or doctor.name)
            db.add(doctor)
        db.commit()
        print(f"updated doctor pinyin fields: {len(doctors)}")


if __name__ == "__main__":
    main()
