from datetime import date

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.automation_result import AutomationResult
from app.models.comment_bank import CommentBankItem
from app.models.daily_task import DailyTask
from app.models.device import Device
from app.models.device_action import DeviceDoctorActionRecord
from app.models.doctor import Doctor, DoctorKeyword
from app.schemas.automation import (
    ClaimMatchedDoctorCommentPayload,
    ClaimTaskPayload,
    ReportTaskPayload,
    StartTaskPayload,
)
from app.services.automation import (
    HOME_FEED_TASK_ID,
    claim_matched_doctor_comment,
    claim_task,
    report_task,
    start_task,
)


def _cleanup_home_feed_test_data(db, doctor_names: list[str], udids: list[str]) -> None:
    doctors = db.scalars(select(Doctor).where(Doctor.name.in_(doctor_names))).all()
    for doctor in doctors:
        db.query(DeviceDoctorActionRecord).filter(
            DeviceDoctorActionRecord.doctor_id == doctor.id
        ).delete(synchronize_session=False)
        db.query(AutomationResult).filter(AutomationResult.doctor_id == doctor.id).delete(
            synchronize_session=False
        )
        db.query(CommentBankItem).filter(CommentBankItem.doctor_id == doctor.id).delete(
            synchronize_session=False
        )
        for keyword in list(doctor.keywords):
            db.delete(keyword)
        db.delete(doctor)
    db.query(Device).filter(Device.udid.in_(udids)).delete(synchronize_session=False)
    db.commit()


def test_claim_task_returns_active_doctors_for_home_feed_matching() -> None:
    udid = "__pytest_home_feed_claim_udid__"
    active_doctor_name = "__pytest_home_feed_active_doctor__"
    deleted_doctor_name = "__pytest_home_feed_deleted_doctor__"

    with SessionLocal() as db:
        _cleanup_home_feed_test_data(db, [active_doctor_name, deleted_doctor_name], [udid])
        db.add(
            Device(
                name="pytest home feed device",
                udid=udid,
                system_port=4961,
                enabled_status="enabled",
                runtime_status="idle",
            )
        )
        active_doctor = Doctor(name=active_doctor_name, real_name="active", status="active")
        deleted_doctor = Doctor(name=deleted_doctor_name, real_name="deleted", status="deleted")
        db.add_all([active_doctor, deleted_doctor])
        db.commit()

        try:
            response = claim_task(
                db,
                ClaimTaskPayload(udid=udid, publishAccount="pytest-home-feed"),
            )

            assert response.has_task is True
            doctors = response.model_dump(by_alias=True)["doctors"]
            doctor_names = {doctor["doctorName"] for doctor in doctors}
            assert active_doctor_name in doctor_names
            assert deleted_doctor_name not in doctor_names
        finally:
            _cleanup_home_feed_test_data(db, [active_doctor_name, deleted_doctor_name], [udid])


def test_claim_matched_doctor_comment_claims_unused_comment() -> None:
    udid = "__pytest_home_feed_comment_udid__"
    doctor_name = "__pytest_home_feed_comment_doctor__"
    keyword_text = "__pytest_home_feed_comment_keyword__"
    comment_content = "__pytest_home_feed_comment_content__"

    with SessionLocal() as db:
        _cleanup_home_feed_test_data(db, [doctor_name], [udid])
        device = Device(
            name="pytest home feed comment device",
            udid=udid,
            system_port=4962,
            enabled_status="enabled",
            runtime_status="idle",
        )
        doctor = Doctor(name=doctor_name, real_name="comment", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        db.add_all([device, doctor, keyword])
        db.flush()
        comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content=comment_content,
            status="unused",
        )
        db.add(comment)
        db.commit()

        try:
            response = claim_matched_doctor_comment(
                db,
                ClaimMatchedDoctorCommentPayload(
                    udid=udid,
                    doctorId=doctor.id,
                    publishAccount="pytest-home-feed",
                ),
            )
            data = response.model_dump(by_alias=True)

            assert data["taskId"] == 1
            assert data["doctorId"] == doctor.id
            assert data["doctorName"] == doctor_name
            assert data["keywordId"] == keyword.id
            assert data["keyword"] == keyword_text
            assert data["commentBankItemId"] == comment.id
            assert data["commentContent"] == comment_content

            db.refresh(comment)
            db.refresh(device)
            assert comment.status == "used"
            assert comment.used_device_id == device.id
            assert comment.used_account == "pytest-home-feed"
            assert device.runtime_status == "running"
        finally:
            _cleanup_home_feed_test_data(db, [doctor_name], [udid])


def test_home_feed_start_and_report_store_result_under_task_1() -> None:
    udid = "__pytest_home_feed_report_udid__"
    doctor_name = "__pytest_home_feed_report_doctor__"
    keyword_text = "__pytest_home_feed_report_keyword__"
    comment_content = "__pytest_home_feed_report_content__"

    with SessionLocal() as db:
        _cleanup_home_feed_test_data(db, [doctor_name], [udid])
        if db.get(DailyTask, HOME_FEED_TASK_ID) is None:
            db.add(
                DailyTask(
                    id=HOME_FEED_TASK_ID,
                    task_date=date.today(),
                    status="running",
                    total_count=0,
                    success_count=0,
                    failed_count=0,
                    stopped_count=0,
                    created_by="pytest-home-feed",
                )
            )
        device = Device(
            name="pytest home feed report device",
            udid=udid,
            system_port=4963,
            enabled_status="enabled",
            runtime_status="idle",
        )
        doctor = Doctor(name=doctor_name, real_name="report", status="active")
        keyword = DoctorKeyword(keyword=keyword_text, remark="", status="active", doctor=doctor)
        db.add_all([device, doctor, keyword])
        db.flush()
        comment = CommentBankItem(
            doctor_id=doctor.id,
            keyword_id=keyword.id,
            search_word=keyword_text,
            content=comment_content,
            status="unused",
        )
        db.add(comment)
        db.commit()

        try:
            claimed = claim_matched_doctor_comment(
                db,
                ClaimMatchedDoctorCommentPayload(
                    udid=udid,
                    doctorId=doctor.id,
                    publishAccount="pytest-home-feed",
                ),
            )
            start_response = start_task(
                db,
                HOME_FEED_TASK_ID,
                StartTaskPayload(
                    udid=udid,
                    commentBankItemId=claimed.comment_bank_item_id,
                    publishAccount="pytest-home-feed",
                ),
            )
            report_response = report_task(
                db,
                HOME_FEED_TASK_ID,
                ReportTaskPayload(
                    udid=udid,
                    resultId=start_response.result_id,
                    commentBankItemId=claimed.comment_bank_item_id,
                    publishAccount="pytest-home-feed",
                    status="success",
                    videoLink="https://v.douyin.com/pytest-home-feed/",
                    resultSummary="home feed report ok",
                ),
            )

            result = db.get(AutomationResult, report_response.result_id)
            assert result is not None
            assert result.task_id == HOME_FEED_TASK_ID
            assert result.task_item_id is None
            assert result.doctor_id == doctor.id
            assert result.keyword_id == keyword.id
            assert result.comment_bank_item_id == comment.id
            assert result.comment_content == comment_content
            assert result.publish_account == "pytest-home-feed"
            assert result.video_link == "https://v.douyin.com/pytest-home-feed/"
            assert result.status == "success"
            assert result.result_summary == "home feed report ok"

            db.refresh(comment)
            db.refresh(device)
            assert comment.status == "used"
            assert comment.used_task_id == HOME_FEED_TASK_ID
            assert device.runtime_status == "idle"
        finally:
            _cleanup_home_feed_test_data(db, [doctor_name], [udid])
