from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.automation_result import AutomationResult
from app.models.comment_recheck import CommentRecheckRecord
from app.models.daily_task import DailyTask
from app.models.device import Device
from app.models.doctor import Doctor

TEST_DOCTOR_NAME = "__api_check_recheck_doctor__"
TEST_KEYWORD = "__api_check_recheck_keyword__"
TEST_DEVICE_NAME = "__api_check_recheck_device__"
TEST_DEVICE_UDID = "__api_check_recheck_device_udid__"
TEST_TASK_DATE = "2026-05-06"


def cleanup_test_data() -> None:
    with SessionLocal() as db:
        devices = db.scalars(select(Device).where(Device.udid == TEST_DEVICE_UDID)).all()
        for device in devices:
            results = db.scalars(
                select(AutomationResult).where(AutomationResult.device_id == device.id)
            ).all()
            for result in results:
                records = db.scalars(
                    select(CommentRecheckRecord).where(
                        CommentRecheckRecord.automation_result_id == result.id
                    )
                ).all()
                for record in records:
                    db.delete(record)
        db.commit()

    with SessionLocal() as db:
        devices = db.scalars(select(Device).where(Device.udid == TEST_DEVICE_UDID)).all()
        for device in devices:
            results = db.scalars(
                select(AutomationResult).where(AutomationResult.device_id == device.id)
            ).all()
            for result in results:
                db.delete(result)
            db.delete(device)

        doctors = db.scalars(select(Doctor).where(Doctor.name == TEST_DOCTOR_NAME)).all()
        for doctor in doctors:
            tasks = db.scalars(select(DailyTask)).all()
            for task in tasks:
                if any(item.doctor_id == doctor.id for item in task.items):
                    db.delete(task)
            db.delete(doctor)
        db.commit()


def login(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"account": "admin", "password": "admin123456"})
    response.raise_for_status()
    token = response.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def seed_recheckable_result(client: TestClient, headers: dict[str, str]) -> tuple[int, int, int]:
    doctor_response = client.post(
        "/api/doctors",
        json={"name": TEST_DOCTOR_NAME, "remark": "评论复检 API 自检医生"},
        headers=headers,
    )
    doctor_response.raise_for_status()
    doctor_id = doctor_response.json()["data"]["id"]

    keyword_response = client.post(
        f"/api/doctors/{doctor_id}/keywords",
        json={"keyword": TEST_KEYWORD, "remark": "评论复检 API 自检关键词"},
        headers=headers,
    )
    keyword_response.raise_for_status()
    keyword_id = keyword_response.json()["data"]["id"]

    task_response = client.post(
        "/api/daily-tasks",
        json={
            "taskDate": TEST_TASK_DATE,
            "configs": [{"doctorId": doctor_id, "keywordId": keyword_id, "count": 1}],
        },
        headers=headers,
    )
    task_response.raise_for_status()
    task = task_response.json()["data"]
    task_id = task["id"]
    task_item_id = task["items"][0]["id"]

    with SessionLocal() as db:
        device = Device(
            name=TEST_DEVICE_NAME,
            udid=TEST_DEVICE_UDID,
            system_port=8399,
            enabled_status="enabled",
            runtime_status="idle",
            remark="评论复检 API 自检设备",
        )
        db.add(device)
        db.commit()
        db.refresh(device)

        result = AutomationResult(
            task_id=task_id,
            task_item_id=task_item_id,
            doctor_id=doctor_id,
            keyword_id=keyword_id,
            device_id=device.id,
            publish_account="测试账号01",
            comment_content="评论复检 API 自检评论内容",
            video_link="https://example.com/video/recheck",
            status="success",
            fail_reason=None,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            screenshot_url="",
            log_url="",
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        return result.id, doctor_id, keyword_id


def main() -> None:
    cleanup_test_data()
    client = TestClient(app)
    headers = login(client)
    result_id, doctor_id, keyword_id = seed_recheckable_result(client, headers)
    print(f"seed recheckable result ok: id={result_id}")

    list_response = client.get(
        "/api/comment-results/recheck",
        params={
            "doctorId": doctor_id,
            "keywordId": keyword_id,
            "status": "not_checked",
            "keyword": "复检 API",
            "page": 1,
            "pageSize": 10,
        },
        headers=headers,
    )
    list_response.raise_for_status()
    payload = list_response.json()["data"]
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["id"] == result_id
    assert item["automationResultId"] == result_id
    assert item["status"] == "not_checked"
    assert item["videoLink"] == "https://example.com/video/recheck"
    print("list not_checked ok")

    start_response = client.post(
        "/api/comment-results/recheck",
        json={"ids": [result_id]},
        headers=headers,
    )
    start_response.raise_for_status()
    start_payload = start_response.json()["data"]
    assert start_payload["submitted"] in {0, 1}
    if start_payload["loginRequired"]:
        assert start_payload["submitted"] == 0
        assert start_payload["skipped"] == 1
        print("start recheck requires douyin login ok")
        cleanup_test_data()
        return
    assert start_payload["submitted"] == 1

    started_list_response = client.get(
        "/api/comment-results/recheck",
        params={"status": "queued", "page": 1, "pageSize": 10},
        headers=headers,
    )
    started_list_response.raise_for_status()
    assert any(
        row["automationResultId"] == result_id
        for row in started_list_response.json()["data"]["items"]
    )
    print("start recheck ok")

    cleanup_test_data()


if __name__ == "__main__":
    main()
