from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.admin_user import AdminUser


def main() -> None:
    client = TestClient(app)

    login_response = client.post(
        "/api/auth/login",
        json={"account": "admin", "password": "admin123456"},
    )
    login_response.raise_for_status()
    login_payload = login_response.json()["data"]
    token = login_payload["token"]
    print(f"login ok: user={login_payload['user']['username']}")

    me_response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    me_response.raise_for_status()
    me_payload = me_response.json()["data"]
    print(f"me ok: id={me_payload['id']}, isActive={me_payload['isActive']}")

    logout_response = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    logout_response.raise_for_status()
    print("logout ok")

    invalid_token_response = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"})
    assert invalid_token_response.status_code == 401
    print("invalid token ok: 401")

    with SessionLocal() as db:
        user = db.get(AdminUser, me_payload["id"])
        assert user is not None
        try:
            user.status = "disabled"
            db.add(user)
            db.commit()

            disabled_response = client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
            assert disabled_response.status_code == 403
            print("disabled user ok: 403")
        finally:
            user.status = "active"
            db.add(user)
            db.commit()


if __name__ == "__main__":
    main()
