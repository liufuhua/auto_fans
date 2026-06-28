from datetime import date
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook
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

TEST_DOCTOR_NAME = "__api_check_integration_doctor__"
TEST_KEYWORD = "__api_check_integration_keyword__"
TEST_DEVICE_NAME = "__api_check_integration_device__"
TEST_DEVICE_UDID = "__api_check_integration_udid__"
TEST_TASK_DATE = date.today().isoformat()


def cleanup() -> None:
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
                records = db.scalars(
                    select(CommentRecheckRecord).where(
                        CommentRecheckRecord.automation_result_id == result.id
                    )
                ).all()
                for record in records:
                    db.delete(record)
            db.commit()

            results = db.scalars(
                select(AutomationResult).where(AutomationResult.device_id == device.id)
            ).all()
            for result in results:
                db.delete(result)
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


def build_excel() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["搜索词", "评论内容"])
    sheet.append([TEST_KEYWORD, "接口联调评论内容"])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def main() -> None:
    cleanup()
    client = TestClient(app)
    headers = login(client)
    print("login ok")

    me_response = client.get("/api/auth/me", headers=headers)
    me_response.raise_for_status()
    print("auth/me ok")

    users_response = client.get(
        "/api/admin-users", params={"page": 1, "pageSize": 10}, headers=headers
    )
    users_response.raise_for_status()
    print("admin users ok")

    doctor_response = client.post(
        "/api/doctors",
        json={"name": TEST_DOCTOR_NAME, "remark": "接口联调医生"},
        headers=headers,
    )
    doctor_response.raise_for_status()
    doctor_id = doctor_response.json()["data"]["id"]

    keyword_response = client.post(
        f"/api/doctors/{doctor_id}/keywords",
        json={"keyword": TEST_KEYWORD, "remark": "接口联调关键词"},
        headers=headers,
    )
    keyword_response.raise_for_status()
    keyword_id = keyword_response.json()["data"]["id"]
    print("doctor/keyword ok")

    import_response = client.post(
        "/api/comment-bank/import-excel",
        data={"doctorId": str(doctor_id)},
        files={
            "file": (
                "comments.xlsx",
                build_excel(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=headers,
    )
    import_response.raise_for_status()
    assert import_response.json()["data"]["imported"] == 1
    print("comment bank import ok")

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
    print("daily task ok")

    device_response = client.post(
        "/api/devices",
        json={
            "name": TEST_DEVICE_NAME,
            "udid": TEST_DEVICE_UDID,
            "systemPort": 8599,
            "remark": "接口联调设备",
        },
        headers=headers,
    )
    device_response.raise_for_status()
    device_id = device_response.json()["data"]["id"]
    print("device management ok")

    claim_response = client.post(
        "/api/automation/tasks/claim",
        json={"udid": TEST_DEVICE_UDID, "publishAccount": "测试账号01"},
    )
    claim_response.raise_for_status()
    claim = claim_response.json()["data"]
    assert claim["hasTask"] is True

    start_response = client.post(
        f"/api/automation/tasks/{claim['taskItemId']}/start",
        json={
            "udid": TEST_DEVICE_UDID,
            "commentBankItemId": claim["commentBankItemId"],
            "publishAccount": "测试账号01",
        },
    )
    start_response.raise_for_status()
    result_id = start_response.json()["data"]["resultId"]

    report_response = client.post(
        f"/api/automation/tasks/{claim['taskItemId']}/report",
        json={
            "udid": TEST_DEVICE_UDID,
            "resultId": result_id,
            "commentBankItemId": claim["commentBankItemId"],
            "publishAccount": "测试账号01",
            "status": "success",
            "videoLink": "https://example.com/video/integration",
            "failReason": "",
            "screenshotUrl": "",
            "logUrl": "",
        },
    )
    report_response.raise_for_status()
    print("automation flow ok")

    results_response = client.get(
        "/api/automation-results",
        params={
            "taskId": task_id,
            "deviceId": device_id,
            "status": "success",
            "page": 1,
            "pageSize": 10,
        },
        headers=headers,
    )
    results_response.raise_for_status()
    assert results_response.json()["data"]["total"] >= 1
    print("automation results ok")

    recheck_response = client.get(
        "/api/comment-results/recheck",
        params={"doctorId": doctor_id, "keywordId": keyword_id, "page": 1, "pageSize": 10},
        headers=headers,
    )
    recheck_response.raise_for_status()
    assert recheck_response.json()["data"]["total"] >= 1
    print("comment recheck list ok")

    cleanup()


if __name__ == "__main__":
    main()
