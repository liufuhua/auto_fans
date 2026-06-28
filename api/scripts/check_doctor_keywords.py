from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.doctor import Doctor

TEST_DOCTOR_NAME = "__api_check_keyword_doctor__"
TEST_KEYWORD = "__api_check_keyword__"
UPDATED_KEYWORD = "__api_check_keyword_updated__"


def cleanup_test_data() -> None:
    with SessionLocal() as db:
        doctors = db.scalars(select(Doctor).where(Doctor.name == TEST_DOCTOR_NAME)).all()
        for doctor in doctors:
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
        json={"name": TEST_DOCTOR_NAME, "remark": "关键词 API 自检医生"},
        headers=headers,
    )
    doctor_response.raise_for_status()
    doctor_id = doctor_response.json()["data"]["id"]
    print(f"doctor create ok: id={doctor_id}")

    create_response = client.post(
        f"/api/doctors/{doctor_id}/keywords",
        json={"keyword": TEST_KEYWORD, "remark": "关键词 API 自检"},
        headers=headers,
    )
    create_response.raise_for_status()
    keyword_item = create_response.json()["data"]
    keyword_id = keyword_item["id"]
    assert keyword_item["doctorId"] == doctor_id
    print(f"keyword create ok: id={keyword_id}")

    list_response = client.get(f"/api/doctors/{doctor_id}/keywords", headers=headers)
    list_response.raise_for_status()
    assert any(item["id"] == keyword_id for item in list_response.json()["data"])
    print("keyword list ok")

    options_response = client.get(
        "/api/doctor-keywords/options", params={"doctorId": doctor_id}, headers=headers
    )
    options_response.raise_for_status()
    assert any(item["id"] == keyword_id for item in options_response.json()["data"])
    print("keyword options ok")

    update_response = client.put(
        f"/api/doctor-keywords/{keyword_id}",
        json={"keyword": UPDATED_KEYWORD, "remark": "已更新"},
        headers=headers,
    )
    update_response.raise_for_status()
    assert update_response.json()["data"]["keyword"] == UPDATED_KEYWORD
    print("keyword update ok")

    disable_response = client.post(f"/api/doctor-keywords/{keyword_id}/disable", headers=headers)
    disable_response.raise_for_status()
    disabled_options_response = client.get(
        "/api/doctor-keywords/options", params={"doctorId": doctor_id}, headers=headers
    )
    disabled_options_response.raise_for_status()
    assert all(item["id"] != keyword_id for item in disabled_options_response.json()["data"])
    print("keyword disable ok")

    enable_response = client.post(f"/api/doctor-keywords/{keyword_id}/enable", headers=headers)
    enable_response.raise_for_status()
    enabled_options_response = client.get(
        "/api/doctor-keywords/options", params={"doctorId": doctor_id}, headers=headers
    )
    enabled_options_response.raise_for_status()
    assert any(item["id"] == keyword_id for item in enabled_options_response.json()["data"])
    print("keyword enable ok")

    delete_response = client.delete(f"/api/doctor-keywords/{keyword_id}", headers=headers)
    delete_response.raise_for_status()
    missing_response = client.put(
        f"/api/doctor-keywords/{keyword_id}",
        json={"keyword": UPDATED_KEYWORD, "remark": "不存在"},
        headers=headers,
    )
    assert missing_response.status_code == 404
    print("keyword delete ok")

    cleanup_test_data()


if __name__ == "__main__":
    main()
