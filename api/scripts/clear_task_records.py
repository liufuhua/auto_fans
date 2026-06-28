from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


STATEMENTS = [
    (
        "comment_recheck_records",
        "DELETE FROM comment_recheck_records",
    ),
    (
        "device_doctor_action_records",
        "DELETE FROM device_doctor_action_records",
    ),
    (
        "automation_results",
        "DELETE FROM automation_results",
    ),
    (
        "daily_task_items",
        "DELETE FROM daily_task_items",
    ),
    (
        "daily_tasks",
        "DELETE FROM daily_tasks",
    ),
]

RESET_COMMENT_BANK_SQL = """
UPDATE comment_bank_items
SET
    status = 'unused',
    used_device_id = NULL,
    used_account = NULL,
    used_task_id = NULL,
    used_at = NULL
WHERE used_task_id IS NOT NULL OR status = 'used'
"""


def scalar_int(connection, sql: str) -> int:
    return int(connection.execute(text(sql)).scalar_one())


def main() -> None:
    with engine.begin() as connection:
        before = {
            "daily_tasks": scalar_int(connection, "SELECT COUNT(*) FROM daily_tasks"),
            "daily_task_items": scalar_int(connection, "SELECT COUNT(*) FROM daily_task_items"),
            "automation_results": scalar_int(connection, "SELECT COUNT(*) FROM automation_results"),
            "comment_recheck_records": scalar_int(
                connection, "SELECT COUNT(*) FROM comment_recheck_records"
            ),
            "device_doctor_action_records": scalar_int(
                connection, "SELECT COUNT(*) FROM device_doctor_action_records"
            ),
            "used_comment_bank_items": scalar_int(
                connection,
                "SELECT COUNT(*) FROM comment_bank_items "
                "WHERE used_task_id IS NOT NULL OR status = 'used'",
            ),
        }

        released_comments = connection.execute(text(RESET_COMMENT_BANK_SQL)).rowcount
        deleted: dict[str, int] = {"released_comment_bank_items": int(released_comments or 0)}
        for name, sql in STATEMENTS:
            deleted[name] = int(connection.execute(text(sql)).rowcount or 0)

        after = {
            "daily_tasks": scalar_int(connection, "SELECT COUNT(*) FROM daily_tasks"),
            "daily_task_items": scalar_int(connection, "SELECT COUNT(*) FROM daily_task_items"),
            "automation_results": scalar_int(connection, "SELECT COUNT(*) FROM automation_results"),
            "comment_recheck_records": scalar_int(
                connection, "SELECT COUNT(*) FROM comment_recheck_records"
            ),
            "device_doctor_action_records": scalar_int(
                connection, "SELECT COUNT(*) FROM device_doctor_action_records"
            ),
            "used_comment_bank_items": scalar_int(
                connection,
                "SELECT COUNT(*) FROM comment_bank_items "
                "WHERE used_task_id IS NOT NULL OR status = 'used'",
            ),
        }

    print("before:", before)
    print("deleted:", deleted)
    print("after:", after)


if __name__ == "__main__":
    main()
