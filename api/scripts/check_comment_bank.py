from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.comment_bank import CommentBankItem
from app.models.doctor import Doctor

TEST_DOCTOR_NAME = "__api_check_comment_doctor__"
TEST_KEYWORD = "__api_check_comment_keyword__"
UNMATCHED_KEYWORD = "__api_check_unmatched_keyword__"


def cleanup_test_data() -> None:
    with SessionLocal() as db:
        doctors = db.scalars(select(Doctor).where(Doctor.name == TEST_DOCTOR_NAME)).all()
        for doctor in doctors:
            comment_items = db.scalars(
                select(CommentBankItem).where(CommentBankItem.doctor_id == doctor.id)
            ).all()
            for item in comment_items:
                db.delete(item)
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
    sheet.append([TEST_KEYWORD, "这是一条应该导入的评论"])
    sheet.append([UNMATCHED_KEYWORD, "这是一条应该跳过的评论"])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def main() -> None:
    cleanup_test_data()
    client = TestClient(app)
    headers = login(client)

    doctor_response = client.post(
        "/api/doctors",
        json={"name": TEST_DOCTOR_NAME, "remark": "评论词库 API 自检医生"},
        headers=headers,
    )
    doctor_response.raise_for_status()
    doctor_id = doctor_response.json()["data"]["id"]

    keyword_response = client.post(
        f"/api/doctors/{doctor_id}/keywords",
        json={"keyword": TEST_KEYWORD, "remark": "评论词库 API 自检关键词"},
        headers=headers,
    )
    keyword_response.raise_for_status()
    keyword_id = keyword_response.json()["data"]["id"]
    print(f"seed doctor/keyword ok: doctorId={doctor_id}, keywordId={keyword_id}")

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
    import_result = import_response.json()["data"]
    assert import_result == {"imported": 1, "skipped": 1}
    print("import excel ok")

    list_response = client.get(
        "/api/comment-bank",
        params={"doctorId": doctor_id, "keywordId": keyword_id, "page": 1, "pageSize": 10},
        headers=headers,
    )
    list_response.raise_for_status()
    list_payload = list_response.json()["data"]
    assert list_payload["total"] == 1
    item = list_payload["items"][0]
    assert item["doctorId"] == doctor_id
    assert item["keywordId"] == keyword_id
    assert item["keyword"] == TEST_KEYWORD
    assert item["status"] == "unused"
    print("list ok")

    delete_response = client.delete(f"/api/comment-bank/{item['id']}", headers=headers)
    delete_response.raise_for_status()
    missing_delete_response = client.delete(f"/api/comment-bank/{item['id']}", headers=headers)
    assert missing_delete_response.status_code == 404
    print("delete ok")

    cleanup_test_data()


if __name__ == "__main__":
    main()
