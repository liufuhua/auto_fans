import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.admin_user import AdminUser
from app.models.device import Device
from app.models.doctor import Doctor, DoctorKeyword

DEFAULT_ADMIN = {
    "phone": "13800000000",
    "username": "admin",
    "password": "admin123456",
}

DEFAULT_DEVICES = [
    {
        "name": f"device_{index:02d}",
        "udid": f"android_device_{index:02d}",
        "system_port": 8200 + index,
    }
    for index in range(1, 9)
]

SAMPLE_DOCTORS = [
    {
        "name": "张明山",
        "remark": "颅底肿瘤、脑膜瘤、听神经瘤方向",
        "keywords": ["听神经瘤", "脑膜瘤"],
    },
    {
        "name": "赵萌",
        "remark": "神经调控相关测试医生",
        "keywords": ["偏瘫神经调控"],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize local development data.")
    parser.add_argument(
        "--with-samples", action="store_true", help="Seed sample doctors and keywords."
    )
    parser.add_argument("--admin-phone", default=DEFAULT_ADMIN["phone"])
    parser.add_argument("--admin-username", default=DEFAULT_ADMIN["username"])
    parser.add_argument("--admin-password", default=DEFAULT_ADMIN["password"])
    return parser.parse_args()


def upsert_admin(db: Session, phone: str, username: str, password: str) -> str:
    user = db.scalar(
        select(AdminUser).where((AdminUser.phone == phone) | (AdminUser.username == username))
    )
    if user is None:
        user = AdminUser(
            phone=phone,
            username=username,
            password_hash=hash_password(password),
            status="active",
        )
        db.add(user)
        return "created"

    user.phone = phone
    user.username = username
    user.password_hash = hash_password(password)
    user.status = "active"
    db.add(user)
    return "updated"


def upsert_devices(db: Session) -> tuple[int, int]:
    created = 0
    updated = 0
    for item in DEFAULT_DEVICES:
        device = db.scalar(select(Device).where(Device.udid == item["udid"]))
        if device is None:
            device = Device(
                name=item["name"],
                udid=item["udid"],
                system_port=item["system_port"],
                enabled_status="enabled",
                runtime_status="offline",
                remark="初始化设备配置，请替换为真实 ADB UDID",
            )
            db.add(device)
            created += 1
            continue

        device.name = item["name"]
        device.system_port = item["system_port"]
        device.enabled_status = "enabled"
        device.remark = device.remark or "初始化设备配置，请替换为真实 ADB UDID"
        db.add(device)
        updated += 1
    return created, updated


def upsert_sample_doctors(db: Session) -> tuple[int, int]:
    doctor_count = 0
    keyword_count = 0
    for item in SAMPLE_DOCTORS:
        doctor = db.scalar(select(Doctor).where(Doctor.name == item["name"]))
        if doctor is None:
            doctor = Doctor(name=item["name"], remark=item["remark"], status="active")
            db.add(doctor)
            db.flush()
            doctor_count += 1
        else:
            doctor.remark = item["remark"]
            doctor.status = "active"
            db.add(doctor)

        for keyword_text in item["keywords"]:
            keyword = db.scalar(
                select(DoctorKeyword).where(
                    DoctorKeyword.doctor_id == doctor.id,
                    DoctorKeyword.keyword == keyword_text,
                )
            )
            if keyword is None:
                db.add(
                    DoctorKeyword(
                        doctor_id=doctor.id,
                        keyword=keyword_text,
                        remark="初始化示例关键词",
                        status="active",
                    )
                )
                keyword_count += 1
            else:
                keyword.status = "active"
                db.add(keyword)
    return doctor_count, keyword_count


def main() -> None:
    args = parse_args()
    with SessionLocal() as db:
        admin_action = upsert_admin(db, args.admin_phone, args.admin_username, args.admin_password)
        device_created, device_updated = upsert_devices(db)
        sample_message = "sample doctors skipped"
        if args.with_samples:
            doctor_created, keyword_created = upsert_sample_doctors(db)
            sample_message = (
                f"sample doctors created={doctor_created}, "
                f"sample keywords created={keyword_created}"
            )

        db.commit()

    print(f"admin {admin_action}: username={args.admin_username}, phone={args.admin_phone}")
    print(f"devices created={device_created}, updated={device_updated}")
    print(sample_message)


if __name__ == "__main__":
    main()
