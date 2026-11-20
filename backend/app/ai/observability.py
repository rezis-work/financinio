import hashlib
import os
import re
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from app.core.config import get_settings

_CARD_OR_ACCOUNT_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def configure_langsmith_env() -> None:
    """Ensure LangSmith environment variables are exported for LangChain/LangGraph auto-tracing."""
    settings = get_settings()
    if settings.langsmith_configured:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key or ""
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    else:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")


def redact_pii(text: str) -> str:
    """Mask long card/account numbers before sending text into trace metadata or logs."""
    return _CARD_OR_ACCOUNT_RE.sub("[REDACTED_NUMBER]", text)


def pseudonymize_user_id(user_id: UUID | str) -> str:
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:16]


def build_langgraph_config(
    *,
    thread_id: str,
    user_id: UUID | str,
    feature: str,
    extra_metadata: dict | None = None,
) -> RunnableConfig:
    """Construct a LangGraph RunnableConfig with LangSmith tags & pseudonymized metadata."""
    settings = get_settings()
    user_hash = pseudonymize_user_id(user_id)
    metadata = {
        "app": settings.app_name,
        "env": settings.app_env,
        "feature": feature,
        "user_hash": user_hash,
        "llm_provider": settings.llm_provider,
        **(extra_metadata or {}),
    }
    tags = [
        f"env:{settings.app_env}",
        f"feature:{feature}",
        f"provider:{settings.llm_provider}",
    ]
    return RunnableConfig(
        configurable={"thread_id": thread_id},
        tags=tags,
        metadata=metadata,
        run_name=f"financinio.{feature}",
    )
