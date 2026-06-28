from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.doctor import Doctor

TEST_NAME = "__api_check_doctor__"
UPDATED_NAME = "__api_check_doctor_updated__"


def cleanup_test_doctor() -> None:
    with SessionLocal() as db:
        doctors = db.scalars(
            select(Doctor).where((Doctor.name == TEST_NAME) | (Doctor.name == UPDATED_NAME))
        ).all()
        for doctor in doctors:
            db.delete(doctor)
        db.commit()


def login(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"account": "admin", "password": "admin123456"})
    response.raise_for_status()
    token = response.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    cleanup_test_doctor()
    client = TestClient(app)
    headers = login(client)

    create_response = client.post(
        "/api/doctors",
        json={"name": TEST_NAME, "remark": "医生 API 自检"},
        headers=headers,
    )
    create_response.raise_for_status()
    doctor = create_response.json()["data"]
    doctor_id = doctor["id"]
    print(f"create ok: id={doctor_id}")

    list_response = client.get(
        "/api/doctors",
        params={"keyword": TEST_NAME, "page": 1, "pageSize": 10},
        headers=headers,
    )
    list_response.raise_for_status()
    assert list_response.json()["data"]["total"] >= 1
    print("list ok")

    options_response = client.get("/api/doctors/options", headers=headers)
    options_response.raise_for_status()
    assert any(item["id"] == doctor_id for item in options_response.json()["data"])
    print("options ok")

    update_response = client.put(
        f"/api/doctors/{doctor_id}",
        json={"name": UPDATED_NAME, "remark": "已更新"},
        headers=headers,
    )
    update_response.raise_for_status()
    assert update_response.json()["data"]["name"] == UPDATED_NAME
    print("update ok")

    disable_response = client.post(f"/api/doctors/{doctor_id}/disable", headers=headers)
    disable_response.raise_for_status()
    disabled_options_response = client.get("/api/doctors/options", headers=headers)
    disabled_options_response.raise_for_status()
    assert all(item["id"] != doctor_id for item in disabled_options_response.json()["data"])
    print("disable ok")

    enable_response = client.post(f"/api/doctors/{doctor_id}/enable", headers=headers)
    enable_response.raise_for_status()
    enabled_options_response = client.get("/api/doctors/options", headers=headers)
    enabled_options_response.raise_for_status()
    assert any(item["id"] == doctor_id for item in enabled_options_response.json()["data"])
    print("enable ok")

    delete_response = client.delete(f"/api/doctors/{doctor_id}", headers=headers)
    delete_response.raise_for_status()
    missing_response = client.put(
        f"/api/doctors/{doctor_id}",
        json={"name": UPDATED_NAME, "remark": "不存在"},
        headers=headers,
    )
    assert missing_response.status_code == 404
    print("delete ok")

    cleanup_test_doctor()


if __name__ == "__main__":
    main()
