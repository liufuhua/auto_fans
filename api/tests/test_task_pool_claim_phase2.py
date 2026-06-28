import logging
from datetime import date

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.automation_runtime import AutomationRuntime
from app.models.automation_result import AutomationResult
from app.models.automation_timing import AutomationTimingSetting
from app.models.comment_bank import CommentBankItem
from app.models.daily_task import DailyTask, DailyTaskItem
from app.models.device import Device
from app.models.device_action import DeviceDoctorActionRecord
from app.models.device_task_pool import DeviceTaskPoolItem
from app.models.doctor import Doctor, DoctorKeyword
from app.models.doctor_province import DoctorProvince
from app.schemas.automation import ClaimTaskPayload
from app.schemas.automation import ReportTaskPayload
from app.schemas.automation import StartTaskPayload
from app.services.automation import RUNTIME_SINGLETON_ID, claim_task, report_task, start_task
from app.services.automation_timing import ensure_default_timing_settings
from app.services.daily_tasks import reset_daily_task_dispatch, stop_daily_task


def _claim_reason(response) -> str | None:
    return response.model_dump(by_alias=True).get("reason")


def _set_runtime_status(db, status: str) -> str | None:
    runtime = db.get(AutomationRuntime, RUNTIME_SINGLETON_ID)
    original_status = runtime.business_status if runtime is not None else None
    if runtime is None:
        runtime = AutomationRuntime(id=RUNTIME_SINGLETON_ID, business_status=status)
    else:
        runtime.business_status = status
    db.add(runtime)
    db.flush()
    return original_status


def _restore_runtime_status(db, original_status: str | None) -> None:
    runtime = db.get(AutomationRuntime, RUNTIME_SINGLETON_ID)
    if runtime is None or original_status is None:
        return
    runtime.business_status = original_status
    db.add(runtime)


def _set_daily_limit_for_test(db, limit: int) -> float | None:
    ensure_default_timing_settings(db)
    timing = db.scalar(
        select(AutomationTimingSetting).where(
            AutomationTimingSetting.key == "single_device_daily_task_limit"
        )
    )
    original_limit = timing.max_seconds if timing is not None else None
    if timing is not None:
        timing.max_seconds = limit
        db.add(timing)
    return original_limit


def _restore_daily_limit(db, original_limit: float | None) -> None:
    if original_limit is None:
        return
    timing = db.scalar(
        select(AutomationTimingSetting).where(
            AutomationTimingSetting.key == "single_device_daily_task_limit"
        )
    )
    if timing is not None:
        timing.max_seconds = original_limit
        db.add(timing)


def _cleanup_reason_test_data(db, doctor_name: str, udids: list[str]) -> None:
    doctors = db.scalars(select(Doctor).where(Doctor.name == doctor_name)).all()
    for doctor in doctors:
        db.query(DeviceTaskPoolItem).filter(DeviceTaskPoolItem.doctor_id == doctor.id).delete(
            synchronize_session=False
        )
        db.query(DeviceDoctorActionRecord).filter(
            DeviceDoctorActionRecord.doctor_id == doctor.id
        ).delete(synchronize_session=False)
        db.query(AutomationResult).filter(AutomationResult.doctor_id == doctor.id).delete(
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
    db.query(Device).filter(Device.udid.in_(udids)).delete(synchronize_session=False)


def test_claim_task_only_claims_current_devices_pool_item() -> None:
    r859_udid = "R8594XIBXWXWKRVO"
    vivo_udid = "Y9IRZHNR4XNRYDPJ"
    doctor_name = "__pytest_task_pool_claim_doctor__"
    keyword_text = "__pytest_task_pool_claim_keyword__"
    province = "__pytest_pool_claim__"

    with SessionLocal() as db:
        ensure_default_timing_settings(db)
        timing = db.scalar(
            select(AutomationTimingSetting).where(
                AutomationTimingSetting.key == "single_device_daily_task_limit"
            )
        )
        original_limit = timing.max_seconds if timing is not None else None

        r859_device = db.scalar(select(Device).where(Device.udid == r859_udid))
        vivo_device = db.scalar(select(Device).where(Device.udid == vivo_udid))
        assert r859_device is not None, f"test device not found: {r859_udid}"
        assert vivo_device is not None, f"test device not found: {vivo_udid}"

        original_device_state = {
            r859_device.id: {
                "province": r859_device.province,
                "runtime_status": r859_device.runtime_status,
            },
            vivo_device.id: {
                "province": vivo_device.province,
                "runtime_status": vivo_device.runtime_status,
            },
        }

        cleanup_doctors = db.scalars(select(Doctor).where(Doctor.name == doctor_name)).all()
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
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="phase2", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        db.add_all([doctor, keyword])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))

        r859_device.province = province
        vivo_device.province = province
        r859_device.runtime_status = "idle"
        vivo_device.runtime_status = "idle"
        if timing is not None:
            timing.max_seconds = 9999
            db.add(timing)

        task = DailyTask(
            task_date=date.today(),
            status="pending",
            total_count=2,
            success_count=0,
            failed_count=0,
            stopped_count=0,
            created_by="pytest",
            dispatch_status="dispatched",
            items=[
                DailyTaskItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    sort_order=1,
                    target_count=2,
                    claimed_count=0,
                    dispatched_count=2,
                    success_count=0,
                    failed_count=0,
                    status="pending",
                )
            ],
        )
        db.add(task)
        db.flush()

        r859_comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="task pool comment for R8594",
            status="unused",
        )
        vivo_comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="task pool comment for vivo",
            status="unused",
        )
        db.add_all([r859_comment, vivo_comment])
        db.flush()

        r859_pool_item = DeviceTaskPoolItem(
            task_id=task.id,
            task_item_id=task.items[0].id,
            device_id=r859_device.id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            comment_bank_item_id=r859_comment.id,
            pool_round=1,
            pool_order=1,
            status="pending",
        )
        vivo_pool_item = DeviceTaskPoolItem(
            task_id=task.id,
            task_item_id=task.items[0].id,
            device_id=vivo_device.id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            comment_bank_item_id=vivo_comment.id,
            pool_round=1,
            pool_order=2,
            status="pending",
        )
        db.add_all([r859_pool_item, vivo_pool_item])
        db.commit()

        try:
            r859_response = claim_task(
                db,
                ClaimTaskPayload(udid=r859_udid, publishAccount="pytest-r859"),
            )
            db.refresh(r859_pool_item)
            db.refresh(vivo_pool_item)

            assert r859_response.has_task is True
            assert any(item.doctor_id == doctor.id for item in r859_response.doctors)
            assert r859_response.comment_bank_item_id is None
            assert r859_pool_item.status == "pending"
            assert r859_pool_item.claimed_at is None
            assert vivo_pool_item.status == "pending"
            assert vivo_pool_item.claimed_at is None

            vivo_response = claim_task(
                db,
                ClaimTaskPayload(udid=vivo_udid, publishAccount="pytest-vivo"),
            )
            db.refresh(vivo_pool_item)

            assert vivo_response.has_task is True
            assert any(item.doctor_id == doctor.id for item in vivo_response.doctors)
            assert vivo_response.comment_bank_item_id is None
            assert vivo_pool_item.status == "pending"
            assert vivo_pool_item.claimed_at is None
        finally:
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
            db.delete(db.get(DoctorKeyword, keyword.id))
            db.delete(db.get(Doctor, doctor.id))
            for device in [r859_device, vivo_device]:
                original = original_device_state[device.id]
                device.province = original["province"]
                device.runtime_status = original["runtime_status"]
                db.add(device)
            if timing is not None and original_limit is not None:
                timing.max_seconds = original_limit
                db.add(timing)
            db.commit()


def test_claim_task_returns_device_pool_empty_when_device_has_no_pending_pool_item() -> None:
    doctor_name = "__pytest_pool_empty_doctor__"
    keyword_text = "__pytest_pool_empty_keyword__"
    province = "__pytest_empty__"
    target_udid = "__pytest_pool_empty_target__"
    other_udid = "__pytest_pool_empty_other__"

    with SessionLocal() as db:
        original_runtime_status = _set_runtime_status(db, "running")
        original_limit = _set_daily_limit_for_test(db, 9999)
        _cleanup_reason_test_data(db, doctor_name, [target_udid, other_udid])
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        target_device = Device(
            name="pytest pool empty target",
            udid=target_udid,
            system_port=19401,
            enabled_status="enabled",
            runtime_status="idle",
            province=province,
            remark="",
        )
        other_device = Device(
            name="pytest pool empty other",
            udid=other_udid,
            system_port=19402,
            enabled_status="enabled",
            runtime_status="idle",
            province=province,
            remark="",
        )
        db.add_all([doctor, keyword, target_device, other_device])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))

        task = DailyTask(
            task_date=date.today(),
            status="pending",
            dispatch_status="dispatched",
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
                    claimed_count=1,
                    dispatched_count=1,
                    success_count=0,
                    failed_count=0,
                    status="pending",
                )
            ],
        )
        db.add(task)
        db.flush()
        comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="pool item belongs to another device",
            status="unused",
        )
        db.add(comment)
        db.flush()
        db.add(
            DeviceTaskPoolItem(
                task_id=task.id,
                task_item_id=task.items[0].id,
                device_id=other_device.id,
                doctor_id=doctor.id,
                keyword_id=keyword.id,
                comment_bank_item_id=comment.id,
                pool_round=1,
                pool_order=1,
                status="pending",
            )
        )
        db.commit()

        try:
            response = claim_task(
                db,
                ClaimTaskPayload(udid=target_udid, publishAccount="pytest-empty"),
            )

            assert response.has_task is True
            assert response.reason is None
            assert any(item.doctor_id == doctor.id for item in response.doctors)
            assert response.comment_bank_item_id is None
            db.refresh(comment)
            assert comment.status == "unused"
            assert comment.used_device_id is None
            assert comment.used_task_id is None
        finally:
            _cleanup_reason_test_data(db, doctor_name, [target_udid, other_udid])
            _restore_runtime_status(db, original_runtime_status)
            _restore_daily_limit(db, original_limit)
            db.commit()


def test_claim_task_returns_not_dispatched_when_today_task_has_no_dispatch_pool() -> None:
    doctor_name = "__pytest_not_dispatched_doctor__"
    keyword_text = "__pytest_not_dispatched_keyword__"
    province = "__pytest_notdisp__"
    udid = "__pytest_not_dispatched_device__"

    with SessionLocal() as db:
        original_runtime_status = _set_runtime_status(db, "running")
        original_limit = _set_daily_limit_for_test(db, 9999)
        _cleanup_reason_test_data(db, doctor_name, [udid])
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        device = Device(
            name="pytest not dispatched device",
            udid=udid,
            system_port=19403,
            enabled_status="enabled",
            runtime_status="idle",
            province=province,
            remark="",
        )
        db.add_all([doctor, keyword, device])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        task = DailyTask(
            task_date=date.today(),
            status="pending",
            dispatch_status="not_dispatched",
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
                    claimed_count=1,
                    dispatched_count=0,
                    success_count=0,
                    failed_count=0,
                    status="pending",
                )
            ],
        )
        db.add(task)
        db.flush()
        comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="not dispatched dynamic fallback must not use this comment",
            status="unused",
        )
        db.add(comment)
        db.commit()

        try:
            response = claim_task(db, ClaimTaskPayload(udid=udid, publishAccount="pytest-notdisp"))

            assert response.has_task is True
            assert response.reason is None
            assert any(item.doctor_id == doctor.id for item in response.doctors)
            assert response.comment_bank_item_id is None
            db.refresh(comment)
            assert comment.status == "unused"
            assert comment.used_device_id is None
            assert comment.used_task_id is None
        finally:
            _cleanup_reason_test_data(db, doctor_name, [udid])
            _restore_runtime_status(db, original_runtime_status)
            _restore_daily_limit(db, original_limit)
            db.commit()


def test_claim_task_returns_task_completed_when_devices_pool_items_are_terminal() -> None:
    doctor_name = "__pytest_pool_completed_doctor__"
    keyword_text = "__pytest_pool_completed_keyword__"
    province = "__pytest_done__"
    udid = "__pytest_pool_completed_device__"

    with SessionLocal() as db:
        original_runtime_status = _set_runtime_status(db, "running")
        original_limit = _set_daily_limit_for_test(db, 9999)
        _cleanup_reason_test_data(db, doctor_name, [udid])
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        device = Device(
            name="pytest pool completed device",
            udid=udid,
            system_port=19404,
            enabled_status="enabled",
            runtime_status="idle",
            province=province,
            remark="",
        )
        db.add_all([doctor, keyword, device])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        task = DailyTask(
            task_date=date.today(),
            status="running",
            dispatch_status="dispatched",
            total_count=1,
            success_count=1,
            failed_count=0,
            stopped_count=0,
            created_by="pytest",
            items=[
                DailyTaskItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    sort_order=1,
                    target_count=1,
                    claimed_count=1,
                    dispatched_count=1,
                    success_count=1,
                    failed_count=0,
                    status="completed",
                )
            ],
        )
        db.add(task)
        db.flush()
        comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="already completed pool comment",
            status="used",
        )
        db.add(comment)
        db.flush()
        db.add(
            DeviceTaskPoolItem(
                task_id=task.id,
                task_item_id=task.items[0].id,
                device_id=device.id,
                doctor_id=doctor.id,
                keyword_id=keyword.id,
                comment_bank_item_id=comment.id,
                pool_round=1,
                pool_order=1,
                status="success",
            )
        )
        db.commit()

        try:
            response = claim_task(db, ClaimTaskPayload(udid=udid, publishAccount="pytest-done"))

            assert response.has_task is True
            assert response.reason is None
            assert any(item.doctor_id == doctor.id for item in response.doctors)
            assert response.comment_bank_item_id is None
        finally:
            _cleanup_reason_test_data(db, doctor_name, [udid])
            _restore_runtime_status(db, original_runtime_status)
            _restore_daily_limit(db, original_limit)
            db.commit()


def test_start_task_marks_claimed_pool_item_running_and_links_result() -> None:
    doctor_name = "__pytest_start_pool_doctor__"
    keyword_text = "__pytest_start_pool_keyword__"
    province = "__pytest_start__"
    udid = "__pytest_start_pool_device__"

    with SessionLocal() as db:
        original_runtime_status = _set_runtime_status(db, "running")
        original_limit = _set_daily_limit_for_test(db, 9999)
        _cleanup_reason_test_data(db, doctor_name, [udid])
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        device = Device(
            name="pytest start pool device",
            udid=udid,
            system_port=19405,
            enabled_status="enabled",
            runtime_status="idle",
            province=province,
            remark="",
        )
        db.add_all([doctor, keyword, device])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        task = DailyTask(
            task_date=date.today(),
            status="running",
            dispatch_status="dispatched",
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
                    claimed_count=1,
                    dispatched_count=1,
                    success_count=0,
                    failed_count=0,
                    status="running",
                )
            ],
        )
        db.add(task)
        db.flush()
        comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="claimed comment for start task",
            status="used",
            used_device_id=device.id,
            used_account="pytest-start",
            used_task_id=task.id,
        )
        db.add(comment)
        db.flush()
        pool_item = DeviceTaskPoolItem(
            task_id=task.id,
            task_item_id=task.items[0].id,
            device_id=device.id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            comment_bank_item_id=comment.id,
            pool_round=1,
            pool_order=1,
            status="claimed",
        )
        db.add(pool_item)
        db.commit()

        try:
            response = start_task(
                db,
                task.items[0].id,
                StartTaskPayload(
                    udid=udid,
                    commentBankItemId=comment.id,
                    publishAccount="pytest-start",
                ),
            )
            db.refresh(pool_item)

            assert response.status == "running"
            assert pool_item.status == "running"
            assert pool_item.started_at is not None
            assert pool_item.result_id == response.result_id
        finally:
            _cleanup_reason_test_data(db, doctor_name, [udid])
            _restore_runtime_status(db, original_runtime_status)
            _restore_daily_limit(db, original_limit)
            db.commit()


def test_report_task_marks_running_pool_item_success(caplog) -> None:
    doctor_name = "__pytest_report_pool_doctor__"
    keyword_text = "__pytest_report_pool_keyword__"
    province = "__pytest_report__"
    udid = "__pytest_report_pool_device__"

    with SessionLocal() as db:
        original_runtime_status = _set_runtime_status(db, "running")
        original_limit = _set_daily_limit_for_test(db, 9999)
        _cleanup_reason_test_data(db, doctor_name, [udid])
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        device = Device(
            name="pytest report pool device",
            udid=udid,
            system_port=19406,
            enabled_status="enabled",
            runtime_status="running",
            province=province,
            remark="",
        )
        db.add_all([doctor, keyword, device])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        task = DailyTask(
            task_date=date.today(),
            status="running",
            dispatch_status="dispatched",
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
                    claimed_count=1,
                    dispatched_count=1,
                    success_count=0,
                    failed_count=0,
                    status="running",
                )
            ],
        )
        db.add(task)
        db.flush()
        item = task.items[0]
        comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="running comment for report task",
            status="used",
            used_device_id=device.id,
            used_account="pytest-report",
            used_task_id=task.id,
        )
        db.add(comment)
        db.flush()
        result = AutomationResult(
            task_id=task.id,
            task_item_id=item.id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            device_id=device.id,
            comment_bank_item_id=comment.id,
            publish_account="pytest-report",
            comment_content=comment.content,
            status="running",
            started_at=date.today(),
        )
        db.add(result)
        db.flush()
        pool_item = DeviceTaskPoolItem(
            task_id=task.id,
            task_item_id=item.id,
            device_id=device.id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            comment_bank_item_id=comment.id,
            pool_round=1,
            pool_order=1,
            status="running",
            result_id=result.id,
        )
        db.add(pool_item)
        db.commit()

        try:
            with caplog.at_level(logging.INFO, logger="app.services.automation"):
                response = report_task(
                    db,
                    item.id,
                    ReportTaskPayload(
                        udid=udid,
                        resultId=result.id,
                        commentBankItemId=comment.id,
                        publishAccount="pytest-report",
                        status="success",
                        videoLink="https://v.douyin.com/pytest/",
                        resultSummary="pytest success",
                    ),
                )
            db.refresh(pool_item)

            assert response.status == "success"
            assert pool_item.status == "success"
            assert pool_item.finished_at is not None
            assert pool_item.result_id == response.result_id
            assert pool_item.fail_reason is None
            assert (
                "report task pool item updated: "
                f"pool_item_id={pool_item.id} device_id={device.id} "
                f"task_item_id={item.id} comment_bank_item_id={comment.id} status=success"
            ) in caplog.text
        finally:
            _cleanup_reason_test_data(db, doctor_name, [udid])
            _restore_runtime_status(db, original_runtime_status)
            _restore_daily_limit(db, original_limit)
            db.commit()


def test_report_task_marks_running_pool_item_failed_with_reason() -> None:
    doctor_name = "__pytest_report_pool_failed_doctor__"
    keyword_text = "__pytest_report_pool_failed_keyword__"
    province = "__pytest_repfail__"
    udid = "__pytest_report_pool_failed_device__"

    with SessionLocal() as db:
        original_runtime_status = _set_runtime_status(db, "running")
        original_limit = _set_daily_limit_for_test(db, 9999)
        _cleanup_reason_test_data(db, doctor_name, [udid])
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        device = Device(
            name="pytest report failed pool device",
            udid=udid,
            system_port=19407,
            enabled_status="enabled",
            runtime_status="running",
            province=province,
            remark="",
        )
        db.add_all([doctor, keyword, device])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        task = DailyTask(
            task_date=date.today(),
            status="running",
            dispatch_status="dispatched",
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
                    claimed_count=1,
                    dispatched_count=1,
                    success_count=0,
                    failed_count=0,
                    status="running",
                )
            ],
        )
        db.add(task)
        db.flush()
        item = task.items[0]
        comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="running failed comment for report task",
            status="used",
            used_device_id=device.id,
            used_account="pytest-report-failed",
            used_task_id=task.id,
        )
        db.add(comment)
        db.flush()
        result = AutomationResult(
            task_id=task.id,
            task_item_id=item.id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            device_id=device.id,
            comment_bank_item_id=comment.id,
            publish_account="pytest-report-failed",
            comment_content=comment.content,
            status="running",
            started_at=date.today(),
        )
        db.add(result)
        db.flush()
        pool_item = DeviceTaskPoolItem(
            task_id=task.id,
            task_item_id=item.id,
            device_id=device.id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            comment_bank_item_id=comment.id,
            pool_round=1,
            pool_order=1,
            status="running",
            result_id=result.id,
        )
        db.add(pool_item)
        db.commit()

        try:
            response = report_task(
                db,
                item.id,
                ReportTaskPayload(
                    udid=udid,
                    resultId=result.id,
                    commentBankItemId=comment.id,
                    publishAccount="pytest-report-failed",
                    status="failed",
                    failReason="pytest failed reason",
                ),
            )
            db.refresh(pool_item)

            assert response.status == "failed"
            assert pool_item.status == "failed"
            assert pool_item.finished_at is not None
            assert pool_item.result_id == response.result_id
            assert pool_item.fail_reason == "pytest failed reason"
        finally:
            _cleanup_reason_test_data(db, doctor_name, [udid])
            _restore_runtime_status(db, original_runtime_status)
            _restore_daily_limit(db, original_limit)
            db.commit()


def test_report_task_completes_dispatched_task_when_all_pool_items_terminal_even_below_target() -> None:
    doctor_name = "__pytest_pool_completion_below_target_doctor__"
    keyword_text = "__pytest_pool_completion_below_target_keyword__"
    province = "__pytest_pool_done__"
    udid = "__pytest_pool_completion_below_target_device__"

    with SessionLocal() as db:
        original_runtime_status = _set_runtime_status(db, "running")
        original_limit = _set_daily_limit_for_test(db, 9999)
        _cleanup_reason_test_data(db, doctor_name, [udid])
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        device = Device(
            name="pytest pool completion below target device",
            udid=udid,
            system_port=19408,
            enabled_status="enabled",
            runtime_status="running",
            province=province,
            remark="",
        )
        db.add_all([doctor, keyword, device])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        task = DailyTask(
            task_date=date.today(),
            status="running",
            dispatch_status="dispatched",
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
                    claimed_count=1,
                    dispatched_count=1,
                    success_count=0,
                    failed_count=0,
                    status="running",
                )
            ],
        )
        db.add(task)
        db.flush()
        item = task.items[0]
        comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="pool completion below target comment",
            status="used",
            used_device_id=device.id,
            used_account="pytest-pool-completion",
            used_task_id=task.id,
        )
        db.add(comment)
        db.flush()
        result = AutomationResult(
            task_id=task.id,
            task_item_id=item.id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            device_id=device.id,
            comment_bank_item_id=comment.id,
            publish_account="pytest-pool-completion",
            comment_content=comment.content,
            status="running",
            started_at=date.today(),
        )
        db.add(result)
        db.flush()
        db.add(
            DeviceTaskPoolItem(
                task_id=task.id,
                task_item_id=item.id,
                device_id=device.id,
                doctor_id=doctor.id,
                keyword_id=keyword.id,
                comment_bank_item_id=comment.id,
                pool_round=1,
                pool_order=1,
                status="running",
                result_id=result.id,
            )
        )
        db.commit()

        try:
            report_task(
                db,
                item.id,
                ReportTaskPayload(
                    udid=udid,
                    resultId=result.id,
                    commentBankItemId=comment.id,
                    publishAccount="pytest-pool-completion",
                    status="success",
                    videoLink="https://v.douyin.com/pool-completion/",
                ),
            )
            db.refresh(task)
            db.refresh(item)

            assert item.status == "completed"
            assert task.status == "completed"
            assert task.finished_at is not None
        finally:
            _cleanup_reason_test_data(db, doctor_name, [udid])
            _restore_runtime_status(db, original_runtime_status)
            _restore_daily_limit(db, original_limit)
            db.commit()


def test_report_task_keeps_dispatched_task_running_when_pool_item_still_active() -> None:
    doctor_name = "__pytest_pool_completion_active_doctor__"
    keyword_text = "__pytest_pool_completion_active_keyword__"
    province = "__pytest_pool_active__"
    udid = "__pytest_pool_completion_active_device__"

    with SessionLocal() as db:
        original_runtime_status = _set_runtime_status(db, "running")
        original_limit = _set_daily_limit_for_test(db, 9999)
        _cleanup_reason_test_data(db, doctor_name, [udid])
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        device = Device(
            name="pytest pool completion active device",
            udid=udid,
            system_port=19409,
            enabled_status="enabled",
            runtime_status="running",
            province=province,
            remark="",
        )
        db.add_all([doctor, keyword, device])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        task = DailyTask(
            task_date=date.today(),
            status="running",
            dispatch_status="dispatched",
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
                    claimed_count=1,
                    dispatched_count=2,
                    success_count=0,
                    failed_count=0,
                    status="running",
                )
            ],
        )
        db.add(task)
        db.flush()
        item = task.items[0]
        running_comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="pool active running comment",
            status="used",
            used_device_id=device.id,
            used_account="pytest-pool-active",
            used_task_id=task.id,
        )
        pending_comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="pool active pending comment",
            status="unused",
        )
        db.add_all([running_comment, pending_comment])
        db.flush()
        result = AutomationResult(
            task_id=task.id,
            task_item_id=item.id,
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            device_id=device.id,
            comment_bank_item_id=running_comment.id,
            publish_account="pytest-pool-active",
            comment_content=running_comment.content,
            status="running",
            started_at=date.today(),
        )
        db.add(result)
        db.flush()
        db.add_all(
            [
                DeviceTaskPoolItem(
                    task_id=task.id,
                    task_item_id=item.id,
                    device_id=device.id,
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    comment_bank_item_id=running_comment.id,
                    pool_round=1,
                    pool_order=1,
                    status="running",
                    result_id=result.id,
                ),
                DeviceTaskPoolItem(
                    task_id=task.id,
                    task_item_id=item.id,
                    device_id=device.id,
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    comment_bank_item_id=pending_comment.id,
                    pool_round=1,
                    pool_order=2,
                    status="pending",
                ),
            ]
        )
        db.commit()

        try:
            report_task(
                db,
                item.id,
                ReportTaskPayload(
                    udid=udid,
                    resultId=result.id,
                    commentBankItemId=running_comment.id,
                    publishAccount="pytest-pool-active",
                    status="success",
                    videoLink="https://v.douyin.com/pool-active/",
                ),
            )
            db.refresh(task)
            db.refresh(item)

            assert item.status == "running"
            assert task.status == "running"
            assert task.finished_at is None
        finally:
            _cleanup_reason_test_data(db, doctor_name, [udid])
            _restore_runtime_status(db, original_runtime_status)
            _restore_daily_limit(db, original_limit)
            db.commit()


def test_stop_daily_task_cancels_pending_and_claimed_pool_items_but_keeps_running() -> None:
    doctor_name = "__pytest_stop_pool_doctor__"
    keyword_text = "__pytest_stop_pool_keyword__"
    province = "__pytest_stop_pool__"
    udids = [
        "__pytest_stop_pool_pending_device__",
        "__pytest_stop_pool_claimed_device__",
        "__pytest_stop_pool_running_device__",
        "__pytest_stop_pool_success_device__",
        "__pytest_stop_pool_failed_device__",
    ]

    with SessionLocal() as db:
        _cleanup_reason_test_data(db, doctor_name, udids)
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        db.add_all([doctor, keyword])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        devices = [
            Device(
                name=f"pytest stop pool {index}",
                udid=udid,
                system_port=19500 + index,
                enabled_status="enabled",
                runtime_status="idle",
                province=province,
                remark="",
            )
            for index, udid in enumerate(udids, start=1)
        ]
        db.add_all(devices)
        db.flush()
        task = DailyTask(
            task_date=date.today(),
            status="running",
            dispatch_status="dispatched",
            total_count=5,
            success_count=1,
            failed_count=1,
            stopped_count=0,
            created_by="pytest",
            items=[
                DailyTaskItem(
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    sort_order=1,
                    target_count=5,
                    claimed_count=3,
                    dispatched_count=5,
                    success_count=1,
                    failed_count=1,
                    status="running",
                )
            ],
        )
        db.add(task)
        db.flush()
        item = task.items[0]
        comments = [
            CommentBankItem(
                doctor_id=doctor.id,
                keyword_id=keyword.id,
                search_word=keyword_text,
                content=f"stop pool comment {index}",
                status="used" if status in {"claimed", "running", "success", "failed"} else "unused",
                used_device_id=devices[index - 1].id
                if status in {"claimed", "running", "success", "failed"}
                else None,
                used_account="pytest-stop" if status in {"claimed", "running", "success", "failed"} else None,
                used_task_id=task.id if status in {"claimed", "running", "success", "failed"} else None,
            )
            for index, status in enumerate(["pending", "claimed", "running", "success", "failed"], start=1)
        ]
        db.add_all(comments)
        db.flush()
        statuses = ["pending", "claimed", "running", "success", "failed"]
        for index, status in enumerate(statuses, start=1):
            db.add(
                DeviceTaskPoolItem(
                    task_id=task.id,
                    task_item_id=item.id,
                    device_id=devices[index - 1].id,
                    doctor_id=doctor.id,
                    keyword_id=keyword.id,
                    comment_bank_item_id=comments[index - 1].id,
                    pool_round=1,
                    pool_order=index,
                    status=status,
                )
            )
        db.commit()

        try:
            stop_daily_task(db, task.id)

            pool_statuses = db.scalars(
                select(DeviceTaskPoolItem.status)
                .where(DeviceTaskPoolItem.task_id == task.id)
                .order_by(DeviceTaskPoolItem.pool_order.asc())
            ).all()
            db.refresh(task)
            db.refresh(item)

            assert pool_statuses == ["cancelled", "cancelled", "running", "success", "failed"]
            assert task.status == "stopped"
            assert task.finished_at is not None
            assert item.status == "stopped"
        finally:
            _cleanup_reason_test_data(db, doctor_name, udids)
            db.commit()


def test_reset_daily_task_dispatch_clears_pending_pool_items_and_dispatch_counts() -> None:
    doctor_name = "__pytest_reset_dispatch_pool_doctor__"
    keyword_text = "__pytest_reset_dispatch_pool_keyword__"
    province = "__pytest_reset_pool__"
    udid = "__pytest_reset_dispatch_pool_device__"

    with SessionLocal() as db:
        _cleanup_reason_test_data(db, doctor_name, [udid])
        db.commit()

        doctor = Doctor(name=doctor_name, real_name="", remark="", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        device = Device(
            name="pytest reset dispatch pool device",
            udid=udid,
            system_port=19510,
            enabled_status="enabled",
            runtime_status="idle",
            province=province,
            remark="",
        )
        db.add_all([doctor, keyword, device])
        db.flush()
        db.add(DoctorProvince(doctor_id=doctor.id, province=province))
        task = DailyTask(
            task_date=date.today(),
            status="pending",
            dispatch_status="dispatched",
            dispatch_error="pytest warning",
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
                    dispatched_count=1,
                    success_count=0,
                    failed_count=0,
                    status="pending",
                )
            ],
        )
        db.add(task)
        db.flush()
        item = task.items[0]
        comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content="reset dispatch pool comment",
            status="unused",
        )
        db.add(comment)
        db.flush()
        db.add(
            DeviceTaskPoolItem(
                task_id=task.id,
                task_item_id=item.id,
                device_id=device.id,
                doctor_id=doctor.id,
                keyword_id=keyword.id,
                comment_bank_item_id=comment.id,
                pool_round=1,
                pool_order=1,
                status="pending",
            )
        )
        db.commit()

        try:
            reset_daily_task_dispatch(db, task.id)

            pool_count = (
                db.scalar(
                    select(DeviceTaskPoolItem.id).where(DeviceTaskPoolItem.task_id == task.id)
                )
                is not None
            )
            db.refresh(task)
            db.refresh(item)
            db.refresh(comment)

            assert pool_count is False
            assert task.dispatch_status == "not_dispatched"
            assert task.dispatch_started_at is None
            assert task.dispatch_finished_at is None
            assert task.dispatch_error is None
            assert item.dispatched_count == 0
            assert item.status == "pending"
            assert comment.status == "unused"
        finally:
            _cleanup_reason_test_data(db, doctor_name, [udid])
            db.commit()
