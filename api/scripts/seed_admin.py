import argparse

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.admin_user import AdminUser


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update a local admin user.")
    parser.add_argument("--phone", default="13800000000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123456")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as db:
        user = db.scalar(
            select(AdminUser).where(
                (AdminUser.phone == args.phone) | (AdminUser.username == args.username)
            )
        )
        if user is None:
            user = AdminUser(
                phone=args.phone,
                username=args.username,
                password_hash=hash_password(args.password),
                status="active",
            )
            db.add(user)
            action = "created"
        else:
            user.phone = args.phone
            user.username = args.username
            user.password_hash = hash_password(args.password)
            user.status = "active"
            action = "updated"

        db.commit()
        print(f"admin user {action}: username={args.username}, phone={args.phone}")


if __name__ == "__main__":
    main()
