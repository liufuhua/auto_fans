from datetime import date

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.comment_bank import CommentBankItem
from app.models.daily_task import DailyTask, DailyTaskItem
from app.models.device import Device
from app.models.device_task_pool import DeviceTaskPoolItem
from app.models.doctor import Doctor, DoctorKeyword
from app.models.doctor_province import DoctorProvince
from app.services.daily_tasks import dispatch_daily_task


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
            for task in db.scalars(select(DailyTask)).all():
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
        try:
            assert pool_item.device_id == devices[1].id
        finally:
            for cleanup_task in [task, existing_task]:
                db.query(DeviceTaskPoolItem).filter(
                    DeviceTaskPoolItem.task_id == cleanup_task.id
                ).delete(synchronize_session=False)
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


def test_daily_task_dispatch_only_uses_enabled_online_devices() -> None:
    doctor_name = "__pytest_dispatch_online_doctor__"
    keyword_text = "__pytest_dispatch_online_keyword__"
    province = "__pytest_online_province__"
    task_date = date(2026, 6, 26)
    device_specs = [
        ("__pytest_dispatch_online_idle__", "enabled", "idle"),
        ("__pytest_dispatch_online_offline__", "enabled", "offline"),
        ("__pytest_dispatch_online_exception__", "enabled", "exception"),
        ("__pytest_dispatch_online_disabled__", "disabled", "idle"),
    ]

    with SessionLocal() as db:
        cleanup_doctor = db.scalar(select(Doctor).where(Doctor.name == doctor_name))
        if cleanup_doctor is not None:
            db.query(DeviceTaskPoolItem).filter(
                DeviceTaskPoolItem.doctor_id == cleanup_doctor.id
            ).delete(synchronize_session=False)
            db.query(CommentBankItem).filter(CommentBankItem.doctor_id == cleanup_doctor.id).delete(
                synchronize_session=False
            )
            db.query(DoctorProvince).filter(DoctorProvince.doctor_id == cleanup_doctor.id).delete(
                synchronize_session=False
            )
            for task in db.scalars(select(DailyTask)).all():
                if any(item.doctor_id == cleanup_doctor.id for item in task.items):
                    db.delete(task)
            db.delete(cleanup_doctor)
        db.query(Device).filter(
            Device.udid.in_([udid for udid, _enabled, _runtime in device_specs])
        ).delete(synchronize_session=False)
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        db.add_all([doctor, keyword])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        devices = [
            Device(
                name=f"pytest online {index}",
                udid=udid,
                system_port=19400 + index,
                enabled_status=enabled_status,
                runtime_status=runtime_status,
                province=province,
                remark="",
            )
            for index, (udid, enabled_status, runtime_status) in enumerate(device_specs, start=1)
        ]
        db.add_all(devices)
        db.flush()
        task = DailyTask(
            task_date=task_date,
            status="pending",
            total_count=4,
            success_count=0,
            failed_count=0,
            stopped_count=0,
            created_by="pytest",
            items=[
                DailyTaskItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    sort_order=1,
                    target_count=4,
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
                    content=f"online dispatch comment {index}",
                    status="unused",
                )
                for index in range(1, 5)
            ]
        )
        db.commit()
        db.refresh(task)

        dispatch_daily_task(db, task.id)

        pool_items = db.scalars(
            select(DeviceTaskPoolItem).where(DeviceTaskPoolItem.task_id == task.id)
        ).all()
        try:
            assert [item.device_id for item in pool_items] == [devices[0].id]
            assert task.items[0].dispatched_count == 1
        finally:
            db.query(DeviceTaskPoolItem).filter(DeviceTaskPoolItem.task_id == task.id).delete(
                synchronize_session=False
            )
            db.delete(db.get(DailyTask, task.id))
            db.query(CommentBankItem).filter(CommentBankItem.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
            db.query(DoctorProvince).filter(DoctorProvince.doctor_id == doctor.id).delete(
                synchronize_session=False
            )
            for device in devices:
                db.delete(db.get(Device, device.id))
            db.delete(db.get(Doctor, doctor.id))
            db.commit()
