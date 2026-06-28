from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.automation_result import AutomationResult
from app.models.comment_bank import CommentBankItem
from app.models.comment_recheck import CommentRecheckRecord
from app.models.daily_task import DailyTask
from app.models.device import Device
from app.models.device_action import DeviceDoctorActionRecord
from app.models.doctor import Doctor

TEST_DOCTOR_NAME = "__api_check_automation_doctor__"
TEST_KEYWORD = "__api_check_automation_keyword__"
TEST_DEVICE_UDID = "__api_check_automation_udid__"
TEST_DEVICE_NAME = "__api_check_automation_device__"
TEST_TASK_DATE = date.today().isoformat()
TEST_NEXT_TASK_DATE = (date.today() + timedelta(days=1)).isoformat()
TEST_PROVINCE = "自动化测试省"


def cleanup_test_data() -> None:
    with SessionLocal() as db:
        devices = db.scalars(select(Device).where(Device.udid == TEST_DEVICE_UDID)).all()
        for device in devices:
            action_records = db.scalars(
                select(DeviceDoctorActionRecord).where(
                    DeviceDoctorActionRecord.device_id == device.id
                )
            ).all()
            for record in action_records:
                db.delete(record)
        db.commit()

    with SessionLocal() as db:
        devices = db.scalars(select(Device).where(Device.udid == TEST_DEVICE_UDID)).all()
        for device in devices:
            results = db.scalars(
                select(AutomationResult).where(AutomationResult.device_id == device.id)
            ).all()
            for result in results:
                recheck_records = db.scalars(
                    select(CommentRecheckRecord).where(
                        CommentRecheckRecord.automation_result_id == result.id
                    )
                ).all()
                for record in recheck_records:
                    db.delete(record)
            db.commit()

            results = db.scalars(
                select(AutomationResult).where(AutomationResult.device_id == device.id)
            ).all()
            for result in results:
                db.delete(result)
            device_comments = db.scalars(
                select(CommentBankItem).where(CommentBankItem.used_device_id == device.id)
            ).all()
            for comment in device_comments:
                db.delete(comment)
            db.delete(device)

        doctors = db.scalars(select(Doctor).where(Doctor.name == TEST_DOCTOR_NAME)).all()
        for doctor in doctors:
            comments = db.scalars(
                select(CommentBankItem).where(CommentBankItem.doctor_id == doctor.id)
            ).all()
            for comment in comments:
                db.delete(comment)

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


def seed_task(client: TestClient, headers: dict[str, str]) -> tuple[int, int, int]:
    doctor_response = client.post(
        "/api/doctors",
        json={
            "name": TEST_DOCTOR_NAME,
            "province": TEST_PROVINCE,
            "remark": "自动化预留接口自检医生",
        },
        headers=headers,
    )
    doctor_response.raise_for_status()
    doctor_id = doctor_response.json()["data"]["id"]

    keyword_response = client.post(
        f"/api/doctors/{doctor_id}/keywords",
        json={"keyword": TEST_KEYWORD, "remark": "自动化预留接口自检关键词"},
        headers=headers,
    )
    keyword_response.raise_for_status()
    keyword_id = keyword_response.json()["data"]["id"]

    with SessionLocal() as db:
        db.add(
            CommentBankItem(
                doctor_id=doctor_id,
                keyword_id=keyword_id,
                search_word=TEST_KEYWORD,
                content="自动化预留接口自检评论内容",
                status="unused",
            )
        )
        db.commit()

    task_response = client.post(
        "/api/daily-tasks",
        json={
            "taskDate": TEST_TASK_DATE,
            "configs": [{"doctorId": doctor_id, "keywordId": keyword_id, "count": 1}],
        },
        headers=headers,
    )
    task_response.raise_for_status()
    task_id = task_response.json()["data"]["id"]
    return doctor_id, keyword_id, task_id


def add_unused_comment(doctor_id: int, keyword_id: int, content: str) -> None:
    with SessionLocal() as db:
        db.add(
            CommentBankItem(
                doctor_id=doctor_id,
                keyword_id=keyword_id,
                search_word=TEST_KEYWORD,
                content=content,
                status="unused",
            )
        )
        db.commit()


def create_task_for_date(
    client: TestClient,
    headers: dict[str, str],
    *,
    task_date: str,
    doctor_id: int,
    keyword_id: int,
) -> int:
    task_response = client.post(
        "/api/daily-tasks",
        json={
            "taskDate": task_date,
            "configs": [{"doctorId": doctor_id, "keywordId": keyword_id, "count": 1}],
        },
        headers=headers,
    )
    task_response.raise_for_status()
    return int(task_response.json()["data"]["id"])


def main() -> None:
    cleanup_test_data()
    client = TestClient(app)
    headers = login(client)
    doctor_id, keyword_id, task_id = seed_task(client, headers)
    print(f"seed task ok: taskId={task_id}")

    heartbeat_response = client.post(
        "/api/automation/devices/heartbeat",
        json={
            "udid": TEST_DEVICE_UDID,
            "deviceName": TEST_DEVICE_NAME,
            "systemPort": 8499,
            "runtimeStatus": "idle",
        },
    )
    heartbeat_response.raise_for_status()
    device_id = heartbeat_response.json()["data"]["deviceId"]
    with SessionLocal() as db:
        device = db.get(Device, device_id)
        assert device is not None
        device.province = TEST_PROVINCE
        db.add(device)
        db.commit()
    print(f"heartbeat ok: deviceId={device_id}")

    claim_response = client.post(
        "/api/automation/tasks/claim",
        json={"udid": TEST_DEVICE_UDID, "publishAccount": "测试账号01"},
    )
    claim_response.raise_for_status()
    claim = claim_response.json()["data"]
    assert claim["hasTask"] is True
    assert any(doctor["doctorId"] == doctor_id for doctor in claim["doctors"])
    print("home-feed claim ok")

    comment_claim_response = client.post(
        "/api/automation/tasks/matched-comment/claim",
        json={
            "udid": TEST_DEVICE_UDID,
            "doctorId": doctor_id,
            "publishAccount": "测试账号01",
        },
    )
    comment_claim_response.raise_for_status()
    comment_claim = comment_claim_response.json()["data"]
    assert comment_claim["taskId"] == 1
    assert comment_claim["doctorId"] == doctor_id
    assert comment_claim["keywordId"] == keyword_id
    comment_bank_item_id = comment_claim["commentBankItemId"]
    print("matched comment claim ok")

    start_response = client.post(
        "/api/automation/tasks/1/start",
        json={
            "udid": TEST_DEVICE_UDID,
            "commentBankItemId": comment_bank_item_id,
            "publishAccount": "测试账号01",
        },
    )
    start_response.raise_for_status()
    result_id = start_response.json()["data"]["resultId"]
    print(f"start ok: resultId={result_id}")

    report_response = client.post(
        "/api/automation/tasks/1/report",
        json={
            "udid": TEST_DEVICE_UDID,
            "resultId": result_id,
            "commentBankItemId": comment_bank_item_id,
            "publishAccount": "测试账号01",
            "status": "success",
            "videoLink": "https://example.com/video/automation",
            "failReason": "",
            "screenshotUrl": "",
            "logUrl": "",
        },
    )
    report_response.raise_for_status()
    assert report_response.json()["data"]["status"] == "success"
    print("report ok")

    results_response = client.get(
        "/api/automation-results",
        params={
            "taskId": 1,
            "deviceId": device_id,
            "status": "success",
            "page": 1,
            "pageSize": 10,
        },
        headers=headers,
    )
    results_response.raise_for_status()
    results = results_response.json()["data"]["items"]
    assert any(item["id"] == result_id for item in results)
    print("automation result visible ok")

    add_unused_comment(doctor_id, keyword_id, "自动化预留接口同日重复评论内容")
    second_comment_claim_response = client.post(
        "/api/automation/tasks/matched-comment/claim",
        json={
            "udid": TEST_DEVICE_UDID,
            "doctorId": doctor_id,
            "publishAccount": "测试账号01",
        },
    )
    second_comment_claim_response.raise_for_status()
    assert second_comment_claim_response.json()["data"]["commentBankItemId"] != comment_bank_item_id
    print("next matched comment claim ok")

    cleanup_test_data()


if __name__ == "__main__":
    main()
