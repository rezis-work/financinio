from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.checkpointer import checkpointer_manager
from app.ai.observability import configure_langsmith_env
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import engine
from app.models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_langsmith_env()

    # Auto-create tables in local SQLite dev mode; in Neon Postgres use `alembic upgrade head`
    if not settings.is_postgres and settings.app_env != "production":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    await checkpointer_manager.startup()
    try:
        yield
    finally:
        await checkpointer_manager.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        description="AI-powered Personal Finance & Wealth platform (FastAPI + LangChain + LangGraph + LangSmith)",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["Health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
