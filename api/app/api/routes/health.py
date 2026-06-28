from fastapi import APIRouter

from app.schemas.common import ApiResponse, ok

router = APIRouter()


@router.get("/health", response_model=ApiResponse[dict[str, str]])
def health_check() -> ApiResponse[dict[str, str]]:
    return ok({"status": "ok"})
