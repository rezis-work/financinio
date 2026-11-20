from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import get_settings


def get_chat_model(
    tier: Literal["fast", "vision"] = "fast",
    temperature: float = 0.0,
) -> BaseChatModel | None:
    """Provider-agnostic LangChain chat model factory.

    Supports Google Gemini (`google_genai`), OpenAI (`openai`), and Anthropic (`anthropic`)
    purely via `.env` settings. Returns `None` if the selected provider has no API key
    configured, allowing deterministic/heuristic fallbacks in local dev & tests.
    """
    settings = get_settings()
    model_name = settings.llm_model_fast if tier == "fast" else settings.llm_model_vision

    if settings.llm_provider == "google_genai":
        if not settings.google_api_key:
            return None
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=settings.google_api_key,
            temperature=temperature,
        )

    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            return None
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            api_key=settings.openai_api_key,
            temperature=temperature,
        )

    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            return None
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model_name,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
        )

    return None
