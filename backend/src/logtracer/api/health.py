"""GET /api/health: liveness and basic configuration check."""

from fastapi import APIRouter
from pydantic import BaseModel

from logtracer import __version__
from logtracer.core.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    log_root_found: bool
    db_found: bool


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=__version__,
        log_root_found=settings.log_root.is_dir(),
        db_found=settings.db_path.is_file(),
    )
