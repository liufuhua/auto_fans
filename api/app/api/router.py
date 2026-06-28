from fastapi import APIRouter

from app.api.routes import (
    admin_users,
    auth,
    automation,
    automation_results,
    automation_timing,
    comment_bank,
    comment_recheck,
    daily_tasks,
    devices,
    doctor_keywords,
    doctor_provinces,
    doctors,
    health,
)

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(admin_users.router, tags=["admin-users"])
api_router.include_router(doctors.router, tags=["doctors"])
api_router.include_router(doctor_keywords.doctor_nested_router, tags=["doctor-keywords"])
api_router.include_router(doctor_keywords.router, tags=["doctor-keywords"])
api_router.include_router(doctor_provinces.router, tags=["doctor-provinces"])
api_router.include_router(comment_bank.router, tags=["comment-bank"])
api_router.include_router(daily_tasks.router, tags=["daily-tasks"])
api_router.include_router(devices.router, tags=["devices"])
api_router.include_router(automation_results.router, tags=["automation-results"])
api_router.include_router(automation_timing.router, tags=["automation-timing"])
api_router.include_router(comment_recheck.router, tags=["comment-recheck"])
api_router.include_router(automation.router, tags=["automation"])
api_router.include_router(health.router, tags=["health"])
