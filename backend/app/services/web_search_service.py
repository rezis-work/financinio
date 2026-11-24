import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class LiveWebSearchResult:
    answer_text: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    provider_used: str = "none"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_name: str | None = None


def _clean_domain(url: str, fallback_title: str = "") -> str:
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().replace("www.", "")
        if host and "vertexaisearch.cloud.google.com" not in host:
            return host[:64]
    except Exception:
        pass
    if fallback_title and "." in fallback_title and " " not in fallback_title:
        return fallback_title[:64]
    return "web"


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/").split("#")[0]


def sanitize_unverified_markdown_links(answer_text: str, verified_urls: set[str]) -> str:
    """Prevent hallucinated 404 URLs from appearing in markdown replies.

    Keeps links that match a verified URL returned by live web search (exact match or same
    verified domain root), and converts any unverified/fabricated deep URL into plain text.
    """
    if not answer_text:
        return answer_text

    norm_verified = {_normalize_url(u) for u in verified_urls if u}
    verified_domains = {
        urlparse(u).netloc.lower().replace("www.", "") for u in norm_verified if urlparse(u).netloc
    }

    md_link_re = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")

    def _replace(match: re.Match[str]) -> str:
        label = match.group(1)
        raw_url = match.group(2)
        norm = _normalize_url(raw_url)
        if norm in norm_verified:
            return match.group(0)
        # Allow top-level portal homepage links (e.g. https://www.myhome.ge or https://myhome.ge/en)
        parsed = urlparse(raw_url)
        host = parsed.netloc.lower().replace("www.", "")
        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) <= 1 and (not verified_domains or host in verified_domains):
            return match.group(0)
        # Strip fabricated deep link so the user never clicks a fake 404 URL
        return f"**{label}**"

    return md_link_re.sub(_replace, answer_text)


def extract_openai_response_citations(response: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract verified url_citation links and executed queries from OpenAI Responses API output."""
    citations: list[dict[str, Any]] = []
    queries: list[str] = []
    seen_urls: set[str] = set()

    for item in getattr(response, "output", None) or []:
        item_type = getattr(item, "type", None)
        if item_type == "web_search_call":
            action = getattr(item, "action", None)
            q = getattr(action, "query", None) if action is not None else None
            if q and str(q).strip() and str(q).strip() not in queries:
                queries.append(str(q).strip())
            continue

        if item_type == "message":
            for block in getattr(item, "content", None) or []:
                for ann in getattr(block, "annotations", None) or []:
                    if getattr(ann, "type", None) != "url_citation":
                        continue
                    uri = str(getattr(ann, "url", "") or "").strip()
                    title = str(getattr(ann, "title", "") or "").strip()
                    if not uri or uri in seen_urls:
                        continue
                    seen_urls.add(uri)
                    domain = _clean_domain(uri, title)
                    citations.append(
                        {
                            "source": "Web Source",
                            "label": (title or domain)[:120],
                            "url": uri,
                            "domain": domain,
                        }
                    )
                    if len(citations) >= 10:
                        return citations, queries

    return citations, queries


async def run_openai_live_web_search(
    *,
    system_instructions: str,
    conversation_messages: list[dict[str, str]],
) -> LiveWebSearchResult | None:
    """Execute a live web search via OpenAI's Responses API (`web_search` tool)."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    primary_model = settings.llm_model_fast or "gpt-4o-mini"

    attempts: list[tuple[str, dict[str, Any], str]] = [
        (primary_model, {"type": "web_search", "search_context_size": "medium"}, "required"),
        (primary_model, {"type": "web_search_preview", "search_context_size": "medium"}, "auto"),
        ("gpt-4o-mini", {"type": "web_search_preview", "search_context_size": "medium"}, "auto"),
    ]

    last_exc: Exception | None = None
    response: Any = None
    used_model = primary_model

    for model_name, tool_cfg, tool_choice in attempts:
        try:
            response = await client.responses.create(
                model=model_name,
                instructions=system_instructions,
                input=conversation_messages,  # type: ignore[arg-type]
                tools=[tool_cfg],  # type: ignore[list-item]
                tool_choice=tool_choice,  # type: ignore[arg-type]
            )
            used_model = model_name
            break
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "OpenAI live web search attempt failed (model=%s, tool=%s): %s",
                model_name,
                tool_cfg.get("type"),
                exc,
            )

    if response is None:
        if last_exc:
            raise last_exc
        return None

    raw_text = str(getattr(response, "output_text", "") or "").strip()
    web_cits, queries = extract_openai_response_citations(response)
    verified_urls = {str(c["url"]) for c in web_cits if c.get("url")}
    clean_text = sanitize_unverified_markdown_links(raw_text, verified_urls)

    usage = getattr(response, "usage", None)
    prompt_toks = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
    comp_toks = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
    total_toks = int(getattr(usage, "total_tokens", prompt_toks + comp_toks) or 0) if usage else 0

    return LiveWebSearchResult(
        answer_text=clean_text,
        citations=web_cits,
        search_queries=queries,
        provider_used="openai_web_search",
        prompt_tokens=prompt_toks,
        completion_tokens=comp_toks,
        total_tokens=total_toks,
        model_name=used_model,
    )
