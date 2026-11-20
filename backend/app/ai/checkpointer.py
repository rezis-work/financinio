import logging
from contextlib import AsyncExitStack

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CheckpointerManager:
    """Manages LangGraph checkpointer lifecycle (Neon Postgres in prod, MemorySaver in dev/test)."""

    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self._saver: BaseCheckpointSaver = MemorySaver()

    @property
    def saver(self) -> BaseCheckpointSaver:
        return self._saver

    async def startup(self) -> None:
        settings = get_settings()
        if not settings.is_postgres:
            self._saver = MemorySaver()
            return
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            conn_str = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
            conn_str = conn_str.replace("postgres://", "postgresql://")
            saver = await self._stack.enter_async_context(
                AsyncPostgresSaver.from_conn_string(conn_str)
            )
            await saver.setup()
            self._saver = saver
            logger.info("LangGraph AsyncPostgresSaver connected to PostgreSQL (Neon).")
        except Exception as exc:
            logger.warning(
                "Could not initialize AsyncPostgresSaver (%s); falling back to MemorySaver.", exc
            )
            self._saver = MemorySaver()

    async def shutdown(self) -> None:
        await self._stack.aclose()


checkpointer_manager = CheckpointerManager()
