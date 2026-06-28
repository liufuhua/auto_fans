from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    with engine.connect() as connection:
        database_name = connection.execute(text("SELECT DATABASE()")).scalar_one()
        charset = connection.execute(
            text(
                "SELECT DEFAULT_CHARACTER_SET_NAME "
                "FROM information_schema.SCHEMATA "
                "WHERE SCHEMA_NAME = DATABASE()"
            )
        ).scalar_one()
        print(f"database={database_name}")
        print(f"charset={charset}")


if __name__ == "__main__":
    main()
