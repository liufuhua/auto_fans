from alembic.config import Config
from alembic.script import ScriptDirectory
from datetime import date, datetime
from sqlalchemy import select, text

from app.db.session import SessionLocal
from scripts import (
    check_admin_users,
    check_auth,
    check_automation,
    check_comment_bank,
    check_daily_tasks,
    check_integration,
)
from app.models.comment_bank import CommentBankItem
from app.models.daily_task import DailyTask, DailyTaskItem
from app.models.automation_result import AutomationResult
from app.models.device import Device
from app.models.device_task_pool import DeviceTaskPoolItem
from app.models.doctor import Doctor, DoctorKeyword
from app.models.doctor_province import DoctorProvince
from app.schemas.common import PageParams
from app.schemas.doctor import DoctorSortOrderPayload, DoctorSortOrderUpdate
from app.services.comment_recheck import (
    list_comment_recheck_items,
    list_comment_recheck_result_ids_by_date_range,
)
from app.services.doctors import list_doctors, update_doctor_sort_order
from app.services.daily_tasks import dispatch_daily_task, to_daily_task_read


def test_login_auth_and_disabled_user_guard() -> None:
    check_auth.main()


def test_admin_users_api_pagination_and_password_reset() -> None:
    check_admin_users.main()


def test_comment_bank_excel_import_and_delete() -> None:
    check_comment_bank.main()


def test_daily_task_database_write_flow() -> None:
    check_daily_tasks.main()


def test_daily_task_item_includes_remaining_comment_count() -> None:
    doctor_name = "__pytest_remaining_comment_count_doctor__"
    keyword_text = "__pytest_remaining_comment_count_keyword__"

    with SessionLocal() as db:
        existing_doctors = db.scalars(select(Doctor).where(Doctor.name == doctor_name)).all()
        for doctor in existing_doctors:
            db.query(CommentBankItem).filter(CommentBankItem.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
            tasks = db.scalars(select(DailyTask)).all()
            for task in tasks:
                if any(item.doctor_id == doctor.id for item in task.items):
                    db.delete(task)
            db.delete(doctor)
        db.commit()

        doctor = Doctor(name=doctor_name, remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        task = DailyTask(
            task_date=date(2026, 6, 18),
            status="pending",
            total_count=3,
            success_count=0,
            failed_count=0,
            stopped_count=0,
            created_by="pytest",
            items=[
                DailyTaskItem(
                    doctor_id=0,
                    keyword_id=0,
                    target_count=3,
                    claimed_count=0,
                    success_count=0,
                    failed_count=0,
                    status="pending",
                )
            ],
        )
        db.add_all([doctor, keyword])
        db.flush()
        task.items[0].doctor_id = doctor.id
        task.items[0].keyword_id = keyword.id
        db.add(task)
        db.flush()
        db.add_all(
            [
                CommentBankItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    search_word=keyword_text,
                    content="remaining comment 1",
                    status="unused",
                ),
                CommentBankItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    search_word=keyword_text,
                    content="remaining comment 2",
                    status="unused",
                ),
                CommentBankItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    search_word=keyword_text,
                    content="already used comment",
                    status="used",
                ),
            ]
        )
        db.commit()
        db.refresh(task)

        result = to_daily_task_read(db, task).model_dump(by_alias=True)

        assert result["items"][0]["remainingCommentCount"] == 2

        db.query(CommentBankItem).filter(CommentBankItem.doctor_id == doctor.id).delete(
            synchronize_session=False
        )
        db.delete(task)
        db.delete(keyword)
        db.delete(doctor)
        db.commit()


def test_daily_task_dispatch_creates_device_task_pool() -> None:
    doctor_name = "__pytest_dispatch_doctor__"
    keyword_text = "__pytest_dispatch_keyword__"
    province = "__pytest_dispatch_province__"
    udid_1 = "__pytest_dispatch_udid_1__"
    udid_2 = "__pytest_dispatch_udid_2__"

    with SessionLocal() as db:
        existing_doctors = db.scalars(select(Doctor).where(Doctor.name == doctor_name)).all()
        for doctor in existing_doctors:
            db.query(DeviceTaskPoolItem).filter(DeviceTaskPoolItem.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
            db.query(CommentBankItem).filter(CommentBankItem.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
            db.query(DoctorProvince).filter(DoctorProvince.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
            tasks = db.scalars(select(DailyTask)).all()
            for task in tasks:
                if any(item.doctor_id == doctor.id for item in task.items):
                    db.delete(task)
            db.delete(doctor)
        db.query(Device).filter(Device.udid.in_([udid_1, udid_2])).delete(
            synchronize_session=False
        )
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        db.add_all([doctor, keyword])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        devices = [
            Device(
                name="pytest dispatch 1",
                udid=udid_1,
                system_port=19201,
                enabled_status="enabled",
                runtime_status="idle",
                province=province,
                remark="",
            ),
            Device(
                name="pytest dispatch 2",
                udid=udid_2,
                system_port=19202,
                enabled_status="enabled",
                runtime_status="idle",
                province=province,
                remark="",
            ),
        ]
        db.add_all(devices)
        db.flush()
        task = DailyTask(
            task_date=date(2026, 6, 25),
            status="pending",
            total_count=2,
            success_count=0,
            failed_count=0,
            stopped_count=0,
            created_by="pytest",
            items=[
                DailyTaskItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    sort_order=1,
                    target_count=2,
                    claimed_count=0,
                    dispatched_count=0,
                    success_count=0,
                    failed_count=0,
                    status="pending",
                )
            ],
        )
        db.add(task)
        db.flush()
        db.add_all(
            [
                CommentBankItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    search_word=keyword_text,
                    content="dispatch comment 1",
                    status="unused",
                ),
                CommentBankItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    search_word=keyword_text,
                    content="dispatch comment 2",
                    status="unused",
                ),
            ]
        )
        db.commit()
        db.refresh(task)

        result = dispatch_daily_task(db, task.id)

        pool_items = db.scalars(
            select(DeviceTaskPoolItem).where(DeviceTaskPoolItem.task_id == task.id)
        ).all()
        db.refresh(task)
        assert result.dispatch_status == "dispatched"
        assert result.pool_item_count == 2
        assert len(pool_items) == 2
        assert {item.device_id for item in pool_items} == {devices[0].id, devices[1].id}
        assert all(item.status == "pending" for item in pool_items)
        assert task.items[0].dispatched_count == 2
        comments = db.scalars(
            select(CommentBankItem).where(CommentBankItem.doctor_id == doctor.id)
        ).all()
        assert {comment.status for comment in comments} == {"unused"}

        db.query(DeviceTaskPoolItem).filter(DeviceTaskPoolItem.task_id == task.id).delete(
            synchronize_session=False
        )
        db.query(CommentBankItem).filter(CommentBankItem.doctor_id == doctor.id).delete(
            synchronize_session=False
        )
        db.query(DoctorProvince).filter(DoctorProvince.doctor_id == doctor.id).delete(
            synchronize_session=False
        )
        db.delete(db.get(DailyTask, task.id))
        for device in devices:
            db.delete(db.get(Device, device.id))
        db.delete(db.get(Doctor, doctor.id))
        db.commit()


def test_daily_task_dispatch_prefers_device_with_fewer_assigned_tasks() -> None:
    doctor_name = "__pytest_dispatch_balance_doctor__"
    keyword_text = "__pytest_dispatch_balance_keyword__"
    existing_doctor_name = "__pytest_dispatch_balance_existing_doctor__"
    existing_keyword_text = "__pytest_dispatch_balance_existing_keyword__"
    province = "__pytest_bal_province__"
    udid_1 = "__pytest_dispatch_balance_udid_1__"
    udid_2 = "__pytest_dispatch_balance_udid_2__"
    task_date = date(2026, 6, 26)

    with SessionLocal() as db:
        cleanup_doctors = db.scalars(
            select(Doctor).where(Doctor.name.in_([doctor_name, existing_doctor_name]))
        ).all()
        for doctor in cleanup_doctors:
            db.query(DeviceTaskPoolItem).filter(DeviceTaskPoolItem.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
            db.query(CommentBankItem).filter(CommentBankItem.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
            db.query(DoctorProvince).filter(DoctorProvince.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
            tasks = db.scalars(select(DailyTask)).all()
            for task in tasks:
                if any(item.doctor_id == doctor.id for item in task.items):
                    db.delete(task)
            db.delete(doctor)
        db.query(Device).filter(Device.udid.in_([udid_1, udid_2])).delete(
            synchronize_session=False
        )
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        existing_doctor = Doctor(
            name=existing_doctor_name, real_name="", remark="", status="active"
        )
        existing_keyword = DoctorKeyword(
            keyword=existing_keyword_text,
            remark="",
            status="active",
            doctor=existing_doctor,
        )
        db.add_all([doctor, keyword, existing_doctor, existing_keyword])
        db.flush()
        db.add_all(
            [
                DoctorProvince(doctor_id=doctor.id, province=province),
                DoctorProvince(doctor_id=existing_doctor.id, province=province),
            ]
        )
        devices = [
            Device(
                name="pytest balance 1",
                udid=udid_1,
                system_port=19301,
                enabled_status="enabled",
                runtime_status="idle",
                province=province,
                remark="",
            ),
            Device(
                name="pytest balance 2",
                udid=udid_2,
                system_port=19302,
                enabled_status="enabled",
                runtime_status="idle",
                province=province,
                remark="",
            ),
        ]
        db.add_all(devices)
        db.flush()

        existing_task = DailyTask(
            task_date=task_date,
            status="pending",
            total_count=1,
            success_count=0,
            failed_count=0,
            stopped_count=0,
            created_by="pytest",
            dispatch_status="dispatched",
            items=[
                DailyTaskItem(
                    doctor_id=existing_doctor.id,
                    keyword_id=existing_keyword.id,
                    sort_order=1,
                    target_count=1,
                    claimed_count=0,
                    dispatched_count=1,
                    success_count=0,
                    failed_count=0,
                    status="pending",
                )
            ],
        )
        task = DailyTask(
            task_date=task_date,
            status="pending",
            total_count=1,
            success_count=0,
            failed_count=0,
            stopped_count=0,
            created_by="pytest",
            items=[
                DailyTaskItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    sort_order=1,
                    target_count=1,
                    claimed_count=0,
                    dispatched_count=0,
                    success_count=0,
                    failed_count=0,
                    status="pending",
                )
            ],
        )
        db.add_all([existing_task, task])
        db.flush()
        db.add_all(
            [
                CommentBankItem(
                    doctor_id=existing_doctor.id,
                    keyword_id=existing_keyword.id,
                    search_word=existing_keyword_text,
                    content="existing dispatch comment",
                    status="unused",
                ),
                CommentBankItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    search_word=keyword_text,
                    content="new dispatch comment",
                    status="unused",
                ),
            ]
        )
        db.flush()
        existing_comment = db.scalar(
            select(CommentBankItem).where(CommentBankItem.doctor_id == existing_doctor.id)
        )
        db.add(
            DeviceTaskPoolItem(
                task_id=existing_task.id,
                task_item_id=existing_task.items[0].id,
                device_id=devices[0].id,
                doctor_id=existing_doctor.id,
                keyword_id=existing_keyword.id,
                comment_bank_item_id=existing_comment.id,
                pool_round=1,
                pool_order=1,
                status="pending",
            )
        )
        db.commit()
        db.refresh(task)

        dispatch_daily_task(db, task.id)

        pool_item = db.scalar(
            select(DeviceTaskPoolItem).where(DeviceTaskPoolItem.task_id == task.id)
        )
        assert pool_item.device_id == devices[1].id

        for cleanup_task in [task, existing_task]:
            db.query(DeviceTaskPoolItem).filter(DeviceTaskPoolItem.task_id == cleanup_task.id).delete(
                synchronize_session=False
            )
            db.delete(db.get(DailyTask, cleanup_task.id))
        db.query(CommentBankItem).filter(
            CommentBankItem.doctor_id.in_([doctor.id, existing_doctor.id])
        ).delete(synchronize_session=False)
        db.query(DoctorProvince).filter(
            DoctorProvince.doctor_id.in_([doctor.id, existing_doctor.id])
        ).delete(synchronize_session=False)
        for device in devices:
            db.delete(db.get(Device, device.id))
        db.delete(db.get(Doctor, doctor.id))
        db.delete(db.get(Doctor, existing_doctor.id))
        db.commit()


def test_doctor_sort_order_moves_item_to_target_position_and_compacts_order() -> None:
    prefix = "__pytest_sort_order_doctor__"

    with SessionLocal() as db:
        existing_doctors = db.scalars(select(Doctor).where(Doctor.name.like(f"{prefix}%"))).all()
        for doctor in existing_doctors:
            db.delete(doctor)
        db.commit()

        first = Doctor(name=f"{prefix}_first", remark="", status="active", sort_order=10)
        second = Doctor(name=f"{prefix}_second", remark="", status="active", sort_order=20)
        third = Doctor(name=f"{prefix}_third", remark="", status="active", sort_order=30)
        fourth = Doctor(name=f"{prefix}_fourth", remark="", status="active", sort_order=40)
        fifth = Doctor(name=f"{prefix}_fifth", remark="", status="active", sort_order=50)
        db.add_all([first, second, third, fourth, fifth])
        db.commit()

        update_doctor_sort_order(
            db,
            DoctorSortOrderPayload(
                items=[DoctorSortOrderUpdate(id=third.id, sort_order=100)]
            ),
        )

        result = list_doctors(db, PageParams(page=1, pageSize=10), prefix, None)

        assert [doctor.name for doctor in result.items] == [
            f"{prefix}_first",
            f"{prefix}_second",
            f"{prefix}_fourth",
            f"{prefix}_fifth",
            f"{prefix}_third",
        ]

        for doctor in [first, second, third, fourth, fifth]:
            db.delete(db.get(Doctor, doctor.id))
        db.commit()


def test_comment_recheck_date_range_selects_only_eligible_results() -> None:
    prefix = "__pytest_recheck_range__"

    with SessionLocal() as db:
        existing_doctors = db.scalars(select(Doctor).where(Doctor.name.like(f"{prefix}%"))).all()
        for doctor in existing_doctors:
            db.query(AutomationResult).filter(AutomationResult.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
            db.query(CommentBankItem).filter(CommentBankItem.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
            tasks = db.scalars(select(DailyTask)).all()
            for task in tasks:
                if any(item.doctor_id == doctor.id for item in task.items):
                    db.delete(task)
            db.delete(doctor)
        db.query(Device).filter(Device.name.like(f"{prefix}%")).delete(synchronize_session=False)
        db.commit()

        doctor = Doctor(name=f"{prefix}_doctor", remark="", status="active")
        keyword = DoctorKeyword(keyword=f"{prefix}_keyword", remark="", status="active", doctor=doctor)
        device = Device(
            name=f"{prefix}_device",
            udid=f"{prefix}_udid",
            system_port=18301,
            enabled_status="enabled",
            runtime_status="offline",
            province="",
            remark="",
        )
        db.add_all([doctor, keyword, device])
        db.flush()

        tasks = [
            DailyTask(task_date=date(2026, 6, 7), status="completed", total_count=1, created_by="pytest"),
            DailyTask(task_date=date(2026, 6, 8), status="completed", total_count=3, created_by="pytest"),
            DailyTask(task_date=date(2026, 6, 9), status="completed", total_count=1, created_by="pytest"),
            DailyTask(task_date=date(2026, 6, 10), status="completed", total_count=1, created_by="pytest"),
        ]
        db.add_all(tasks)
        db.flush()

        result_before_range = AutomationResult(
            task_id=tasks[0].id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            device_id=device.id,
            publish_account="account",
            comment_content="comment",
            video_link="https://example.com/before",
            status="success",
            started_at=datetime(2026, 6, 7, 10, 0, 0),
        )
        eligible_result = AutomationResult(
            task_id=tasks[1].id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            device_id=device.id,
            publish_account="account",
            comment_content="comment",
            video_link="https://example.com/eligible",
            status="success",
            started_at=datetime(2026, 6, 8, 10, 0, 0),
        )
        failed_result = AutomationResult(
            task_id=tasks[1].id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            device_id=device.id,
            publish_account="account",
            comment_content="comment",
            video_link="https://example.com/failed",
            status="failed",
            started_at=datetime(2026, 6, 8, 10, 0, 0),
        )
        no_video_result = AutomationResult(
            task_id=tasks[2].id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            device_id=device.id,
            publish_account="account",
            comment_content="comment",
            video_link="",
            status="success",
            started_at=datetime(2026, 6, 9, 10, 0, 0),
        )
        result_after_range = AutomationResult(
            task_id=tasks[3].id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            device_id=device.id,
            publish_account="account",
            comment_content="comment",
            video_link="https://example.com/after",
            status="success",
            started_at=datetime(2026, 6, 10, 10, 0, 0),
        )
        db.add_all([
            result_before_range,
            eligible_result,
            failed_result,
            no_video_result,
            result_after_range,
        ])
        db.commit()

        result_ids = list_comment_recheck_result_ids_by_date_range(
            db, date(2026, 6, 8), date(2026, 6, 9)
        )
        page_result = list_comment_recheck_items(
            db,
            PageParams(page=1, pageSize=50),
            None,
            None,
            None,
            None,
            date(2026, 6, 8),
            date(2026, 6, 9),
        )

        assert result_ids == [eligible_result.id]
        assert [item.id for item in page_result.items] == [eligible_result.id]

        db.query(AutomationResult).filter(AutomationResult.doctor_id == doctor.id).delete(
            synchronize_session=False
        )
        for task in tasks:
            db.delete(db.get(DailyTask, task.id))
        db.delete(db.get(Device, device.id))
        db.delete(db.get(DoctorKeyword, keyword.id))
        db.delete(db.get(Doctor, doctor.id))
        db.commit()


def test_automation_transaction_flow_updates_result_and_progress() -> None:
    check_automation.main()


def test_full_api_integration_smoke() -> None:
    check_integration.main()


def test_alembic_database_revision_is_at_head() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1

    with SessionLocal() as db:
        current_revision = db.scalar(
            select(text("version_num")).select_from(text("alembic_version"))
        )

    assert current_revision == heads[0]
