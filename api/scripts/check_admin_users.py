from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.admin_user import AdminUser

TEST_PHONE = "13699999999"
TEST_USERNAME = "__api_check_user__"
TEST_PASSWORD = "check123456"
UPDATED_USERNAME = "__api_check_user_updated__"
UPDATED_PASSWORD = "check654321"


def cleanup_test_user() -> None:
    with SessionLocal() as db:
        users = db.scalars(
            select(AdminUser).where(
                (AdminUser.phone == TEST_PHONE)
                | (AdminUser.username == TEST_USERNAME)
                | (AdminUser.username == UPDATED_USERNAME)
            )
        ).all()
        for user in users:
            db.delete(user)
        db.commit()


def login(client: TestClient, account: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"account": account, "password": password})
    response.raise_for_status()
    return response.json()["data"]["token"]


def main() -> None:
    cleanup_test_user()
    client = TestClient(app)
    admin_token = login(client, "admin", "admin123456")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    create_response = client.post(
        "/api/admin-users",
        json={"phone": TEST_PHONE, "username": TEST_USERNAME, "password": TEST_PASSWORD},
        headers=admin_headers,
    )
    create_response.raise_for_status()
    created_user = create_response.json()["data"]
    user_id = created_user["id"]
    print(f"create ok: id={user_id}")

    list_response = client.get(
        "/api/admin-users",
        params={"keyword": TEST_USERNAME, "page": 1, "pageSize": 10},
        headers=admin_headers,
    )
    list_response.raise_for_status()
    assert list_response.json()["data"]["total"] >= 1
    print("list ok")

    update_response = client.put(
        f"/api/admin-users/{user_id}",
        json={"phone": TEST_PHONE, "username": UPDATED_USERNAME},
        headers=admin_headers,
    )
    update_response.raise_for_status()
    assert update_response.json()["data"]["username"] == UPDATED_USERNAME
    print("update ok")

    reset_response = client.post(
        f"/api/admin-users/{user_id}/reset-password",
        json={"password": UPDATED_PASSWORD},
        headers=admin_headers,
    )
    reset_response.raise_for_status()
    user_token = login(client, UPDATED_USERNAME, UPDATED_PASSWORD)
    print("reset password ok")

    disable_response = client.post(f"/api/admin-users/{user_id}/disable", headers=admin_headers)
    disable_response.raise_for_status()
    disabled_me_response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert disabled_me_response.status_code == 403
    print("disable ok")

    enable_response = client.post(f"/api/admin-users/{user_id}/enable", headers=admin_headers)
    enable_response.raise_for_status()
    enabled_me_response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {user_token}"}
    )
    enabled_me_response.raise_for_status()
    print("enable ok")

    cleanup_test_user()


if __name__ == "__main__":
    main()
