from collections.abc import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def normalize_async_database_url(url: str) -> tuple[str, dict]:
    """Normalize Neon/Postgres URLs for SQLAlchemy asyncpg compatibility.

    Neon connection strings often arrive as `postgresql://...` with
    `sslmode=require` and `channel_binding=require`. SQLAlchemy + asyncpg expects
    `postgresql+asyncpg://...` and passes SSL via connect_args instead of `sslmode`.
    """
    connect_args: dict = {}
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]

    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        query_items = dict(parse_qsl(parts.query))
        sslmode = query_items.pop("sslmode", None)
        query_items.pop("channel_binding", None)
        if sslmode in {"require", "verify-ca", "verify-full"}:
            connect_args["ssl"] = "require"
        new_query = urlencode(query_items)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

    return url, connect_args


def create_engine_and_sessionmaker(
    database_url: str | None = None,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    settings = get_settings()
    raw_url = database_url or settings.database_url
    url, connect_args = normalize_async_database_url(raw_url)

    engine_kwargs: dict = {
        "echo": False,
        "pool_pre_ping": True,
        "connect_args": connect_args,
    }
    if url.startswith("postgresql+asyncpg://"):
        engine_kwargs["pool_size"] = 5
        engine_kwargs["max_overflow"] = 10

    engine = create_async_engine(url, **engine_kwargs)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return engine, session_factory


engine, AsyncSessionLocal = create_engine_and_sessionmaker()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
