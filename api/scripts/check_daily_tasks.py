from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.comment_bank import CommentBankItem
from app.models.daily_task import DailyTask
from app.models.doctor import Doctor

TEST_DOCTOR_NAME = "__api_check_daily_task_doctor__"
TEST_KEYWORD = "__api_check_daily_task_keyword__"
TEST_TASK_DATE = "2026-05-06"


def cleanup_test_data() -> None:
    with SessionLocal() as db:
        doctors = db.scalars(select(Doctor).where(Doctor.name == TEST_DOCTOR_NAME)).all()
        for doctor in doctors:
            db.query(CommentBankItem).filter(CommentBankItem.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
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


def main() -> None:
    cleanup_test_data()
    client = TestClient(app)
    headers = login(client)

    doctor_response = client.post(
        "/api/doctors",
        json={"name": TEST_DOCTOR_NAME, "remark": "每日任务 API 自检医生"},
        headers=headers,
    )
    doctor_response.raise_for_status()
    doctor_id = doctor_response.json()["data"]["id"]

    keyword_response = client.post(
        f"/api/doctors/{doctor_id}/keywords",
        json={"keyword": TEST_KEYWORD, "remark": "每日任务 API 自检关键词"},
        headers=headers,
    )
    keyword_response.raise_for_status()
    keyword_id = keyword_response.json()["data"]["id"]
    print(f"seed doctor/keyword ok: doctorId={doctor_id}, keywordId={keyword_id}")

    with SessionLocal() as db:
        db.add_all(
            [
                CommentBankItem(
                    doctor_id=doctor_id,
                    keyword_id=keyword_id,
                    search_word=TEST_KEYWORD,
                    content="daily task remaining comment 1",
                    status="unused",
                ),
                CommentBankItem(
                    doctor_id=doctor_id,
                    keyword_id=keyword_id,
                    search_word=TEST_KEYWORD,
                    content="daily task remaining comment 2",
                    status="unused",
                ),
                CommentBankItem(
                    doctor_id=doctor_id,
                    keyword_id=keyword_id,
                    search_word=TEST_KEYWORD,
                    content="daily task used comment",
                    status="used",
                ),
            ]
        )
        db.commit()

    create_response = client.post(
        "/api/daily-tasks",
        json={
            "taskDate": TEST_TASK_DATE,
            "configs": [{"doctorId": doctor_id, "keywordId": keyword_id, "count": 3}],
        },
        headers=headers,
    )
    create_response.raise_for_status()
    task = create_response.json()["data"]
    task_id = task["id"]
    assert task["totalCount"] == 3
    assert task["items"][0]["doctorName"] == TEST_DOCTOR_NAME
    assert task["items"][0]["keyword"] == TEST_KEYWORD
    assert task["items"][0]["remainingCommentCount"] == 2
    print(f"create daily task ok: id={task_id}")

    list_response = client.get(
        "/api/daily-tasks",
        params={"taskDate": TEST_TASK_DATE, "page": 1, "pageSize": 10},
        headers=headers,
    )
    list_response.raise_for_status()
    listed_task = next(item for item in list_response.json()["data"]["items"] if item["id"] == task_id)
    assert listed_task["items"][0]["remainingCommentCount"] == 2
    print("list ok")

    options_response = client.get("/api/daily-tasks/options", headers=headers)
    options_response.raise_for_status()
    option_task = next(item for item in options_response.json()["data"] if item["id"] == task_id)
    assert option_task["items"][0]["remainingCommentCount"] == 2
    print("options ok")

    stop_response = client.post(f"/api/daily-tasks/{task_id}/stop", headers=headers)
    stop_response.raise_for_status()
    stopped_list_response = client.get(
        "/api/daily-tasks",
        params={"taskDate": TEST_TASK_DATE, "status": "stopped", "page": 1, "pageSize": 10},
        headers=headers,
    )
    stopped_list_response.raise_for_status()
    stopped_task = next(
        item for item in stopped_list_response.json()["data"]["items"] if item["id"] == task_id
    )
    assert stopped_task["status"] == "stopped"
    assert stopped_task["stoppedCount"] == 3
    assert stopped_task["items"][0]["status"] == "stopped"
    print("stop ok")

    cleanup_test_data()


if __name__ == "__main__":
    main()
