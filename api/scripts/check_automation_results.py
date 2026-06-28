from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.automation_result import AutomationResult
from app.models.daily_task import DailyTask
from app.models.device import Device
from app.models.doctor import Doctor

TEST_DOCTOR_NAME = "__api_check_result_doctor__"
TEST_KEYWORD = "__api_check_result_keyword__"
TEST_DEVICE_NAME = "__api_check_device__"
TEST_DEVICE_UDID = "__api_check_device_udid__"
TEST_TASK_DATE = "2026-05-06"


def cleanup_test_data() -> None:
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
                    results = db.scalars(
                        select(AutomationResult).where(AutomationResult.task_id == task.id)
                    ).all()
                    for result in results:
                        db.delete(result)
                    db.delete(task)
            db.delete(doctor)
        db.commit()


def login(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"account": "admin", "password": "admin123456"})
    response.raise_for_status()
    token = response.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def seed_result(client: TestClient, headers: dict[str, str]) -> tuple[int, int, int, int, int]:
    doctor_response = client.post(
        "/api/doctors",
        json={"name": TEST_DOCTOR_NAME, "remark": "自动化结果 API 自检医生"},
        headers=headers,
    )
    doctor_response.raise_for_status()
    doctor_id = doctor_response.json()["data"]["id"]

    keyword_response = client.post(
        f"/api/doctors/{doctor_id}/keywords",
        json={"keyword": TEST_KEYWORD, "remark": "自动化结果 API 自检关键词"},
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
            system_port=8299,
            enabled_status="enabled",
            runtime_status="idle",
            remark="自动化结果 API 自检设备",
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
            comment_content="自动化结果 API 自检评论内容",
            video_link="https://example.com/video/check",
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
        result_id = result.id
        device_id = device.id

    return result_id, task_id, doctor_id, keyword_id, device_id


def main() -> None:
    cleanup_test_data()
    client = TestClient(app)
    headers = login(client)
    result_id, task_id, doctor_id, keyword_id, device_id = seed_result(client, headers)
    print(f"seed automation result ok: id={result_id}")

    list_response = client.get(
        "/api/automation-results",
        params={
            "taskId": task_id,
            "doctorId": doctor_id,
            "keywordId": keyword_id,
            "deviceId": device_id,
            "status": "success",
            "keyword": "自检评论",
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
    assert item["taskId"] == task_id
    assert item["taskDate"] == TEST_TASK_DATE
    assert item["doctorName"] == TEST_DOCTOR_NAME
    assert item["keyword"] == TEST_KEYWORD
    assert item["deviceName"] == TEST_DEVICE_NAME
    assert item["videoLink"] == "https://example.com/video/check"
    assert item["status"] == "success"
    print("list/filter ok")

    failed_filter_response = client.get(
        "/api/automation-results",
        params={"status": "failed", "page": 1, "pageSize": 10},
        headers=headers,
    )
    failed_filter_response.raise_for_status()
    assert all(
        item["status"] == "failed" for item in failed_filter_response.json()["data"]["items"]
    )
    print("status filter ok")

    cleanup_test_data()


if __name__ == "__main__":
    main()
