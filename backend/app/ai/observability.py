import hashlib
import os
import re
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.runnables import RunnableConfig

from app.core.config import get_settings

_CARD_OR_ACCOUNT_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


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
    """Mask card/account numbers, SSNs, IBANs, and emails before logging or trace metadata."""
    redacted = _CARD_OR_ACCOUNT_RE.sub("[REDACTED_NUMBER]", text)
    redacted = _SSN_RE.sub("[REDACTED_SSN]", redacted)
    redacted = _IBAN_RE.sub("[REDACTED_IBAN]", redacted)
    redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    return redacted


def sanitize_metadata(data: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, str):
            clean[k] = redact_pii(v)
        elif isinstance(v, dict):
            clean[k] = sanitize_metadata(v)
        else:
            clean[k] = v
    return clean


def pseudonymize_user_id(user_id: UUID | str) -> str:
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:16]


class PIIRedactingCallbackHandler(AsyncCallbackHandler):
    """Lightweight LangChain callback ensuring custom trace metadata never leaks raw PII."""

    async def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        meta = kwargs.get("metadata")
        if isinstance(meta, dict):
            for k, v in list(meta.items()):
                if isinstance(v, str):
                    meta[k] = redact_pii(v)


def build_langgraph_config(
    *,
    thread_id: str,
    user_id: UUID | str,
    feature: str,
    extra_metadata: dict | None = None,
) -> RunnableConfig:
    """Construct a LangGraph RunnableConfig with LangSmith tags, PII redaction & pseudonymized user hash."""
    settings = get_settings()
    user_hash = pseudonymize_user_id(user_id)
    metadata = sanitize_metadata(
        {
            "app": settings.app_name,
            "env": settings.app_env,
            "feature": feature,
            "user_hash": user_hash,
            "llm_provider": settings.llm_provider,
            **(extra_metadata or {}),
        }
    )
    tags = [
        f"env:{settings.app_env}",
        f"feature:{feature}",
        f"provider:{settings.llm_provider}",
    ]
    return RunnableConfig(
        configurable={"thread_id": thread_id},
        tags=tags,
        metadata=metadata,
        callbacks=[PIIRedactingCallbackHandler()],
        run_name=f"financinio.{feature}",
    )
