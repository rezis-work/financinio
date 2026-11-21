from typing import Any

from fastapi import HTTPException, status
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import AIUsageEvent, User


def enforce_ai_quota(user: User) -> None:
    """Block AI execution with HTTP 402 if a standard user has exhausted their fixed token cap."""
    if user.has_unlimited_ai:
        return
    if user.ai_tokens_used >= user.ai_token_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"AI token limit reached ({user.ai_tokens_used:,} / {user.ai_token_limit:,} tokens). "
                "Ask an administrator to increase your limit or grant Unlimited Full Access."
            ),
        )


class TokenMeterCallbackHandler(AsyncCallbackHandler):
    """Captures exact LLM prompt/completion token usage across all LangChain/LangGraph nodes."""

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.model_name: str | None = None

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        # 1. Standard LangChain llm_output token_usage (OpenAI / Anthropic)
        llm_out = response.llm_output or {}
        if isinstance(llm_out, dict):
            if llm_out.get("model_name"):
                self.model_name = str(llm_out["model_name"])
            usage = llm_out.get("token_usage") or llm_out.get("usage")
            if isinstance(usage, dict):
                pt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                ct = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
                tt = int(usage.get("total_tokens") or (pt + ct))
                if tt > 0:
                    self.prompt_tokens += pt
                    self.completion_tokens += ct
                    self.total_tokens += tt
                    return

        # 2. Modern LangChain ChatGeneration message.usage_metadata (Gemini / OpenAI / Anthropic)
        for gen_list in response.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                meta = getattr(msg, "usage_metadata", None) if msg is not None else None
                if isinstance(meta, dict):
                    pt = int(meta.get("input_tokens") or 0)
                    ct = int(meta.get("output_tokens") or 0)
                    tt = int(meta.get("total_tokens") or (pt + ct))
                    self.prompt_tokens += pt
                    self.completion_tokens += ct
                    self.total_tokens += tt


async def record_ai_usage(
    db: AsyncSession,
    *,
    user: User,
    feature: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int | None = None,
    model_name: str | None = None,
    fallback_text: str = "",
) -> int:
    """Persist an AIUsageEvent and atomically increment user.ai_tokens_used."""
    settings = get_settings()
    tot = total_tokens if total_tokens is not None else (prompt_tokens + completion_tokens)
    if tot <= 0 and fallback_text:
        # Conservative fallback estimate when provider omits usage metadata or heuristic runs
        est_comp = max(1, len(fallback_text) // 4)
        prompt_tokens = max(prompt_tokens, est_comp // 2)
        completion_tokens = max(completion_tokens, est_comp)
        tot = prompt_tokens + completion_tokens

    if tot <= 0:
        return 0

    event = AIUsageEvent(
        user_id=user.id,
        feature=feature,
        provider=settings.llm_provider,
        model=(model_name or settings.llm_model_fast)[:64],
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=tot,
    )
    db.add(event)
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(ai_tokens_used=User.ai_tokens_used + tot)
    )
    await db.commit()
    await db.refresh(user)
    return tot
