from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select


ROOT_DIR = Path(__file__).resolve().parents[1]
API_DIR = ROOT_DIR / "api"
sys.path.insert(0, str(API_DIR))


def _load_api_env() -> None:
    env_path = API_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_api_env()

from app.db.session import SessionLocal  # noqa: E402
from app.models.automation_result import AutomationResult  # noqa: E402
from app.models.comment_recheck import CommentRecheckRecord  # noqa: E402
from app.models.daily_task import DailyTask  # noqa: E402
from app.services.comment_recheck_browser import run_comment_rechecks_for_results  # noqa: E402


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc


def _configure_browser(args: argparse.Namespace) -> None:
    if args.chrome_debugger_address:
        os.environ["CHROME_DEBUGGER_ADDRESS"] = args.chrome_debugger_address
    if args.chrome_user_data_dir:
        os.environ["CHROME_USER_DATA_DIR"] = args.chrome_user_data_dir
    if args.chrome_profile_directory:
        os.environ["CHROME_PROFILE_DIRECTORY"] = args.chrome_profile_directory
    if args.headed:
        os.environ["CHROME_HEADLESS"] = "false"


def _has_logged_in_browser_config() -> bool:
    return any(
        os.getenv(name, "").strip()
        for name in ("CHROME_DEBUGGER_ADDRESS", "CHROME_USER_DATA_DIR")
    )


def reset_recheck_records(task_date: date) -> list[int]:
    with SessionLocal() as db:
        result_ids = list(
            db.scalars(
                select(AutomationResult.id)
                .join(DailyTask, DailyTask.id == AutomationResult.task_id)
                .where(DailyTask.task_date == task_date)
                .where(AutomationResult.status == "success")
                .where(AutomationResult.video_link.is_not(None))
                .where(AutomationResult.video_link != "")
                .order_by(AutomationResult.id.desc())
            ).all()
        )
        if not result_ids:
            db.commit()
            return []

        records = db.scalars(
            select(CommentRecheckRecord).where(
                CommentRecheckRecord.automation_result_id.in_(result_ids)
            )
        ).all()
        record_by_result_id = {record.automation_result_id: record for record in records}

        for result_id in result_ids:
            record = record_by_result_id.get(result_id)
            if record is None:
                db.add(CommentRecheckRecord(automation_result_id=result_id, status="pending"))
                continue
            record.status = "pending"
            record.checked_at = None
            record.fail_reason = None
            db.add(record)

        db.commit()
        return result_ids


def print_summary(task_date: date) -> None:
    with SessionLocal() as db:
        rows = db.execute(
            select(CommentRecheckRecord.status, CommentRecheckRecord.id)
            .join(AutomationResult, AutomationResult.id == CommentRecheckRecord.automation_result_id)
            .join(DailyTask, DailyTask.id == AutomationResult.task_id)
            .where(DailyTask.task_date == task_date)
        ).all()

    counts: dict[str, int] = {}
    for status, _record_id in rows:
        counts[status] = counts.get(status, 0) + 1
    print("校验结果汇总:", counts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run comment recheck for a single task date.")
    parser.add_argument("--date", type=_parse_date, default=date(2026, 6, 8))
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--no-reset", action="store_true")
    parser.add_argument("--allow-anonymous", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--chrome-debugger-address", default="")
    parser.add_argument("--chrome-user-data-dir", default="")
    parser.add_argument("--chrome-profile-directory", default="")
    args = parser.parse_args()

    _configure_browser(args)
    if args.no_reset:
        with SessionLocal() as db:
            result_ids = list(
                db.scalars(
                    select(AutomationResult.id)
                    .join(DailyTask, DailyTask.id == AutomationResult.task_id)
                    .join(
                        CommentRecheckRecord,
                        CommentRecheckRecord.automation_result_id == AutomationResult.id,
                    )
                    .where(DailyTask.task_date == args.date)
                    .where(CommentRecheckRecord.status == "pending")
                    .order_by(AutomationResult.id.desc())
                    .limit(args.limit)
                ).all()
            )
    else:
        result_ids = reset_recheck_records(args.date)

    result_ids = result_ids[: args.limit]
    print(f"{args.date} 待校验结果数: {len(result_ids)}")
    if not result_ids:
        return

    if not args.allow_anonymous and not _has_logged_in_browser_config():
        print(
            "已完成重置，但未配置已登录浏览器环境，停止执行浏览器校验，"
            "避免把登录后才可见的评论误判为未找到。\n"
            "可选方式：\n"
            "1. 使用已登录 Chrome profile：--chrome-user-data-dir <User Data目录> "
            "--chrome-profile-directory <Profile目录名>\n"
            "2. 连接已打开的调试 Chrome：--chrome-debugger-address 127.0.0.1:9222\n"
            "临时允许匿名测试可加 --allow-anonymous，但结果不可靠。"
        )
        raise SystemExit(2)

    run_comment_rechecks_for_results(result_ids, limit=args.limit, task_date=args.date)
    print_summary(args.date)


if __name__ == "__main__":
    main()
