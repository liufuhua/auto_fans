from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.admin_user import AdminUser
from app.models.automation_result import AutomationResult
from app.models.comment_bank import CommentBankItem
from app.models.daily_task import DailyTask, DailyTaskItem
from app.models.device import Device
from app.models.doctor import Doctor, DoctorKeyword

DEFAULT_PASSWORD = "admin123456"

MOCK_USERS = [
    {"phone": "13800000000", "username": "admin", "status": "active"},
    {"phone": "13900000000", "username": "运营一号", "status": "active"},
    {"phone": "13700000000", "username": "测试观察员", "status": "disabled"},
]

MOCK_DOCTORS = [
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

MOCK_COMMENTS = [
    {
        "doctor": "张明山",
        "keyword": "脑膜瘤",
        "content": "明山主任真的太牛了，颅底肿瘤这种高难度手术，在您手里稳稳的，专业又靠谱！",
        "status": "unused",
    },
    {
        "doctor": "张明山",
        "keyword": "脑膜瘤",
        "content": "刷到明山主任是福气，看脑膜瘤、听神经瘤就找您，技术顶尖，人还特别有耐心。",
        "status": "used",
        "used_device": "device_01",
        "used_account": "测试账号01",
        "used_at": datetime(2026, 5, 5, 10, 15, tzinfo=UTC),
    },
    {
        "doctor": "张明山",
        "keyword": "听神经瘤",
        "content": "业内公认的听瘤专家，保面、保听做得特别好，患者术后恢复快，太厉害了！",
        "status": "unused",
    },
    {
        "doctor": "赵萌",
        "keyword": "偏瘫神经调控",
        "content": "赵医生在神经调控方向讲得很清楚，给患者和家属很多信心。",
        "status": "unused",
    },
]

MOCK_TASK_ITEMS = [
    {
        "doctor": "张明山",
        "keyword": "听神经瘤",
        "target": 4,
        "claimed": 4,
        "success": 3,
        "failed": 0,
        "status": "running",
    },
    {
        "doctor": "张明山",
        "keyword": "脑膜瘤",
        "target": 5,
        "claimed": 3,
        "success": 2,
        "failed": 1,
        "status": "running",
    },
    {
        "doctor": "赵萌",
        "keyword": "偏瘫神经调控",
        "target": 3,
        "claimed": 1,
        "success": 0,
        "failed": 0,
        "status": "pending",
    },
]


def main() -> None:
    with SessionLocal() as db:
        seed_users(db)
        devices = seed_devices(db)
        doctors, keywords = seed_doctors_and_keywords(db)
        comments = seed_comments(db, doctors, keywords, devices)
        task = seed_daily_task(db, doctors, keywords)
        seed_automation_results(db, task, doctors, keywords, devices, comments)
        db.commit()

    print("mock users seeded")
    print("mock devices seeded: 8")
    print("mock doctors seeded: 张明山, 赵萌")
    print("mock comments seeded: 4")
    print("mock daily task seeded: 2026-05-06")
    print("mock automation results seeded: 2")


def seed_users(db: Session) -> None:
    for item in MOCK_USERS:
        user = db.scalar(
            select(AdminUser).where(
                (AdminUser.phone == item["phone"]) | (AdminUser.username == item["username"])
            )
        )
        if user is None:
            user = AdminUser(
                phone=item["phone"],
                username=item["username"],
                password_hash=hash_password(DEFAULT_PASSWORD),
                status=item["status"],
            )
        else:
            user.phone = item["phone"]
            user.username = item["username"]
            user.status = item["status"]
            if item["username"] == "admin":
                user.password_hash = hash_password(DEFAULT_PASSWORD)
        db.add(user)


def seed_devices(db: Session) -> dict[str, Device]:
    devices: dict[str, Device] = {}
    now = datetime.now(UTC)
    for index in range(1, 9):
        name = f"device_{index:02d}"
        device = db.scalar(select(Device).where(Device.name == name))
        if device is None:
            device = Device(
                name=name, udid=f"emulator-{5554 + (index - 1) * 2}", system_port=8200 + index
            )
        device.udid = f"emulator-{5554 + (index - 1) * 2}"
        device.system_port = 8200 + index
        device.enabled_status = "enabled"
        device.runtime_status = "idle" if index <= 3 else "offline"
        device.last_heartbeat_at = now if index <= 3 else None
        device.remark = "预置 8 台 Android 设备配置"
        db.add(device)
        devices[name] = device
    db.flush()
    return devices


def seed_doctors_and_keywords(
    db: Session,
) -> tuple[dict[str, Doctor], dict[tuple[str, str], DoctorKeyword]]:
    doctors: dict[str, Doctor] = {}
    keywords: dict[tuple[str, str], DoctorKeyword] = {}
    for item in MOCK_DOCTORS:
        doctor = db.scalar(select(Doctor).where(Doctor.name == item["name"]))
        if doctor is None:
            doctor = Doctor(name=item["name"], remark=item["remark"], status="active")
        doctor.remark = item["remark"]
        doctor.status = "active"
        db.add(doctor)
        db.flush()
        doctors[item["name"]] = doctor

        for keyword_text in item["keywords"]:
            keyword = db.scalar(
                select(DoctorKeyword).where(
                    DoctorKeyword.doctor_id == doctor.id,
                    DoctorKeyword.keyword == keyword_text,
                )
            )
            if keyword is None:
                keyword = DoctorKeyword(
                    doctor_id=doctor.id, keyword=keyword_text, remark="", status="active"
                )
            keyword.status = "active"
            db.add(keyword)
            db.flush()
            keywords[(doctor.name, keyword.keyword)] = keyword
    return doctors, keywords


def seed_comments(
    db: Session,
    doctors: dict[str, Doctor],
    keywords: dict[tuple[str, str], DoctorKeyword],
    devices: dict[str, Device],
) -> dict[str, CommentBankItem]:
    comments: dict[str, CommentBankItem] = {}
    for item in MOCK_COMMENTS:
        doctor = doctors[item["doctor"]]
        keyword = keywords[(item["doctor"], item["keyword"])]
        comment = db.scalar(
            select(CommentBankItem).where(
                CommentBankItem.doctor_id == doctor.id,
                CommentBankItem.keyword_id == keyword.id,
                CommentBankItem.content == item["content"],
            )
        )
        if comment is None:
            comment = CommentBankItem(
                doctor_id=doctor.id,
                keyword_id=keyword.id,
                search_word=keyword.keyword,
                content=item["content"],
            )
        comment.status = item["status"]
        comment.used_account = item.get("used_account")
        comment.used_at = item.get("used_at")
        used_device_name = item.get("used_device")
        comment.used_device_id = devices[used_device_name].id if used_device_name else None
        db.add(comment)
        db.flush()
        comments[item["content"]] = comment
    return comments


def seed_daily_task(
    db: Session, doctors: dict[str, Doctor], keywords: dict[tuple[str, str], DoctorKeyword]
) -> DailyTask:
    task = db.scalar(
        select(DailyTask).where(
            DailyTask.task_date == "2026-05-06", DailyTask.created_by == "管理员"
        )
    )
    if task is None:
        task = DailyTask(task_date="2026-05-06", created_by="管理员")
        db.add(task)
        db.flush()
    else:
        for existing_item in list(task.items):
            db.delete(existing_item)
        db.flush()

    task.status = "running"
    task.total_count = 12
    task.success_count = 5
    task.failed_count = 1
    task.stopped_count = 0
    task.started_at = datetime(2026, 5, 6, 9, 5, tzinfo=UTC)
    task.finished_at = None

    for item in MOCK_TASK_ITEMS:
        doctor = doctors[item["doctor"]]
        keyword = keywords[(item["doctor"], item["keyword"])]
        db.add(
            DailyTaskItem(
                task_id=task.id,
                doctor_id=doctor.id,
                keyword_id=keyword.id,
                target_count=item["target"],
                claimed_count=item["claimed"],
                success_count=item["success"],
                failed_count=item["failed"],
                status=item["status"],
            )
        )
    db.flush()
    return task


def seed_automation_results(
    db: Session,
    task: DailyTask,
    doctors: dict[str, Doctor],
    keywords: dict[tuple[str, str], DoctorKeyword],
    devices: dict[str, Device],
    comments: dict[str, CommentBankItem],
) -> None:
    results = [
        {
            "doctor": "张明山",
            "keyword": "脑膜瘤",
            "device": "device_01",
            "publish_account": "测试账号01",
            "comment": "刷到明山主任是福气，看脑膜瘤、听神经瘤就找您，技术顶尖，人还特别有耐心。",
            "video_link": "https://example.com/video/10001",
            "status": "success",
            "fail_reason": None,
            "started_at": datetime(2026, 5, 6, 9, 10, tzinfo=UTC),
            "finished_at": datetime(2026, 5, 6, 9, 13, 20, tzinfo=UTC),
        },
        {
            "doctor": "张明山",
            "keyword": "听神经瘤",
            "device": "device_02",
            "publish_account": "测试账号02",
            "comment": "业内公认的听瘤专家，保面、保听做得特别好，患者术后恢复快，太厉害了！",
            "video_link": "",
            "status": "failed",
            "fail_reason": "评论按钮未找到，疑似页面结构变化",
            "started_at": datetime(2026, 5, 6, 9, 12, tzinfo=UTC),
            "finished_at": datetime(2026, 5, 6, 9, 15, 45, tzinfo=UTC),
        },
    ]
    task_items = {(item.doctor_id, item.keyword_id): item for item in task.items}
    for item in results:
        doctor = doctors[item["doctor"]]
        keyword = keywords[(item["doctor"], item["keyword"])]
        device = devices[item["device"]]
        comment = comments[item["comment"]]
        existing = db.scalar(
            select(AutomationResult).where(
                AutomationResult.task_id == task.id,
                AutomationResult.device_id == device.id,
                AutomationResult.comment_content == item["comment"],
            )
        )
        if existing is None:
            existing = AutomationResult(
                task_id=task.id,
                doctor_id=doctor.id,
                keyword_id=keyword.id,
                device_id=device.id,
                started_at=item["started_at"],
                publish_account=item["publish_account"],
                comment_content=item["comment"],
                status=item["status"],
            )
        task_item = task_items.get((doctor.id, keyword.id))
        existing.task_item_id = task_item.id if task_item else None
        existing.comment_bank_item_id = comment.id
        existing.video_link = item["video_link"]
        existing.status = item["status"]
        existing.fail_reason = item["fail_reason"]
        existing.finished_at = item["finished_at"]
        existing.screenshot_url = ""
        existing.log_url = ""
        db.add(existing)


if __name__ == "__main__":
    main()
