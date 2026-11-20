import hashlib
import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class MerchantMemoryMatch:
    category_id: str
    category_name: str
    merchant_clean: str
    score: float


class VectorMemoryBackend(Protocol):
    async def lookup_merchant_memory(
        self, user_id: UUID, query_text: str, min_score: float = 0.85
    ) -> MerchantMemoryMatch | None: ...

    async def upsert_merchant_memory(
        self,
        user_id: UUID,
        merchant_raw: str,
        merchant_clean: str,
        category_id: str,
        category_name: str,
    ) -> None: ...

    async def upsert_document_chunks(
        self,
        user_id: UUID,
        document_id: UUID,
        chunks: list[str],
        metadata: dict,
    ) -> None: ...


class UpstashVectorService:
    """Tenant-isolated Upstash Vector service using per-user namespaces.

    Namespaces:
      - `merchant_memory:{user_id}`: self-learning categorization memory
      - `documents:{user_id}`: chunked PDF statements & receipt OCR text for RAG
    """

    def __init__(self, rest_url: str | None, rest_token: str | None) -> None:
        self._enabled = bool(rest_url and rest_token)
        self._index = None
        if self._enabled:
            from upstash_vector import AsyncIndex

            self._index = AsyncIndex(url=rest_url, token=rest_token)

    @property
    def enabled(self) -> bool:
        return self._enabled and self._index is not None

    @staticmethod
    def _merchant_ns(user_id: UUID) -> str:
        return f"merchant_memory:{user_id}"

    @staticmethod
    def _document_ns(user_id: UUID) -> str:
        return f"documents:{user_id}"

    async def lookup_merchant_memory(
        self, user_id: UUID, query_text: str, min_score: float = 0.85
    ) -> MerchantMemoryMatch | None:
        if not self.enabled or not query_text.strip():
            return None
        try:
            results = await self._index.query(  # type: ignore[union-attr]
                data=query_text.strip(),
                top_k=1,
                include_metadata=True,
                namespace=self._merchant_ns(user_id),
            )
            if not results:
                return None
            top = results[0]
            score = float(getattr(top, "score", 0.0))
            meta = getattr(top, "metadata", None) or {}
            if score >= min_score and meta.get("category_id"):
                return MerchantMemoryMatch(
                    category_id=str(meta["category_id"]),
                    category_name=str(meta.get("category_name", "")),
                    merchant_clean=str(meta.get("merchant_clean", "")),
                    score=score,
                )
        except Exception as exc:  # pragma: no cover - network fallback
            logger.warning("Upstash Vector lookup failed (falling back): %s", exc)
        return None

    async def upsert_merchant_memory(
        self,
        user_id: UUID,
        merchant_raw: str,
        merchant_clean: str,
        category_id: str,
        category_name: str,
    ) -> None:
        if not self.enabled:
            return
        try:
            from upstash_vector import Vector

            vec_id = hashlib.sha256(
                f"{user_id}:{merchant_raw.lower().strip()}".encode()
            ).hexdigest()[:32]
            text = f"{merchant_raw} | {merchant_clean}".strip()
            await self._index.upsert(  # type: ignore[union-attr]
                vectors=[
                    Vector(
                        id=vec_id,
                        data=text,
                        metadata={
                            "category_id": category_id,
                            "category_name": category_name,
                            "merchant_clean": merchant_clean,
                            "merchant_raw": merchant_raw[:160],
                        },
                    )
                ],
                namespace=self._merchant_ns(user_id),
            )
        except Exception as exc:  # pragma: no cover - network fallback
            logger.warning("Upstash Vector merchant upsert failed: %s", exc)

    async def upsert_document_chunks(
        self,
        user_id: UUID,
        document_id: UUID,
        chunks: list[str],
        metadata: dict,
    ) -> None:
        if not self.enabled or not chunks:
            return
        try:
            from upstash_vector import Vector

            vectors = [
                Vector(
                    id=f"{document_id}:{idx}",
                    data=chunk[:2000],
                    metadata={**metadata, "document_id": str(document_id), "chunk_index": idx},
                )
                for idx, chunk in enumerate(chunks[:100])
                if chunk.strip()
            ]
            if vectors:
                await self._index.upsert(  # type: ignore[union-attr]
                    vectors=vectors,
                    namespace=self._document_ns(user_id),
                )
        except Exception as exc:  # pragma: no cover - network fallback
            logger.warning("Upstash Vector document chunk upsert failed: %s", exc)


_vector_service_singleton: UpstashVectorService | None = None


def get_vector_service() -> UpstashVectorService:
    global _vector_service_singleton
    if _vector_service_singleton is None:
        settings = get_settings()
        _vector_service_singleton = UpstashVectorService(
            rest_url=settings.upstash_vector_rest_url,
            rest_token=settings.upstash_vector_rest_token,
        )
    return _vector_service_singleton
