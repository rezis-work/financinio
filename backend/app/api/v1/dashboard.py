from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard_service import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    months: int = Query(default=6, ge=1, le=24),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummaryResponse:
    return await get_dashboard_summary(db, current_user, months=months)


@router.get("/system-status")
async def system_status(
    current_user: User = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    return {
        "database": "neon_postgres" if settings.is_postgres else "sqlite_dev",
        "storage_backend": settings.storage_backend,
        "upstash_vector_connected": settings.upstash_configured,
        "llm_provider": settings.llm_provider,
        "llm_model_fast": settings.llm_model_fast,
        "llm_model_vision": settings.llm_model_vision,
        "llm_configured": settings.llm_configured,
        "langsmith_tracing": settings.langsmith_configured,
        "langsmith_project": settings.langchain_project,
    }
