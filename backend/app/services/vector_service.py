import hashlib
import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class MerchantMemoryMatch:
    category_id: str
    category_name: str
    merchant_clean: str
    score: float


@dataclass
class DocumentSearchMatch:
    document_id: str
    filename: str
    doc_type: str
    excerpt: str
    score: float


@dataclass
class UserFactMatch:
    id: str
    fact: str
    category: str
    score: float | None = None


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

    async def search_documents(
        self, user_id: UUID, query_text: str, top_k: int = 4
    ) -> list[DocumentSearchMatch]: ...

    async def delete_document_chunks(self, user_id: UUID, document_id: UUID) -> None: ...

    async def remember_user_fact(
        self, user_id: UUID, fact: str, category: str = "preference"
    ) -> UserFactMatch: ...

    async def recall_user_facts(
        self, user_id: UUID, query_text: str, top_k: int = 5
    ) -> list[UserFactMatch]: ...

    async def list_user_facts(self, user_id: UUID, limit: int = 30) -> list[UserFactMatch]: ...

    async def delete_user_fact(self, user_id: UUID, fact_id: str) -> None: ...

    async def purge_user_namespaces(self, user_id: UUID) -> None: ...


class UpstashVectorService:
    """Tenant-isolated Upstash Vector service using per-user namespaces.

    Namespaces:
      - `merchant_memory:{user_id}`: self-learning categorization memory
      - `documents:{user_id}`: chunked PDF statements & receipt OCR text for RAG
      - `user_memory:{user_id}`: long-term user financial goals & preferences for Luna
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

    @staticmethod
    def _user_memory_ns(user_id: UUID) -> str:
        return f"user_memory:{user_id}"

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
                    metadata={
                        **metadata,
                        "document_id": str(document_id),
                        "chunk_index": idx,
                        "excerpt": chunk[:600],
                    },
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

    async def search_documents(
        self, user_id: UUID, query_text: str, top_k: int = 4
    ) -> list[DocumentSearchMatch]:
        if not self.enabled or not query_text.strip():
            return []
        try:
            results = await self._index.query(  # type: ignore[union-attr]
                data=query_text.strip(),
                top_k=top_k,
                include_metadata=True,
                include_data=True,
                namespace=self._document_ns(user_id),
            )
            matches: list[DocumentSearchMatch] = []
            for item in results:
                meta = getattr(item, "metadata", None) or {}
                raw_data = getattr(item, "data", None) or meta.get("excerpt", "")
                matches.append(
                    DocumentSearchMatch(
                        document_id=str(meta.get("document_id", item.id)),
                        filename=str(meta.get("filename", "Uploaded Document")),
                        doc_type=str(meta.get("doc_type", "document")),
                        excerpt=str(raw_data)[:600],
                        score=round(float(getattr(item, "score", 0.0)), 3),
                    )
                )
            return matches
        except Exception as exc:  # pragma: no cover
            logger.warning("Upstash Vector document search failed: %s", exc)
            return []

    async def delete_document_chunks(self, user_id: UUID, document_id: UUID) -> None:
        if not self.enabled:
            return
        try:
            await self._index.delete(  # type: ignore[union-attr]
                prefix=f"{document_id}:",
                namespace=self._document_ns(user_id),
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Upstash Vector delete_document_chunks failed: %s", exc)

    async def remember_user_fact(
        self, user_id: UUID, fact: str, category: str = "preference"
    ) -> UserFactMatch:
        fact_id = f"mem-{uuid4().hex[:16]}"
        clean_fact = fact.strip()[:500]
        if self.enabled:
            try:
                from upstash_vector import Vector

                await self._index.upsert(  # type: ignore[union-attr]
                    vectors=[
                        Vector(
                            id=fact_id,
                            data=clean_fact,
                            metadata={"fact": clean_fact, "category": category},
                        )
                    ],
                    namespace=self._user_memory_ns(user_id),
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("Upstash Vector remember_user_fact failed: %s", exc)
        return UserFactMatch(id=fact_id, fact=clean_fact, category=category)

    async def recall_user_facts(
        self, user_id: UUID, query_text: str, top_k: int = 5
    ) -> list[UserFactMatch]:
        if not self.enabled or not query_text.strip():
            return []
        try:
            results = await self._index.query(  # type: ignore[union-attr]
                data=query_text.strip(),
                top_k=top_k,
                include_metadata=True,
                namespace=self._user_memory_ns(user_id),
            )
            out: list[UserFactMatch] = []
            for item in results:
                score = float(getattr(item, "score", 0.0))
                if score < 0.55:
                    continue
                meta = getattr(item, "metadata", None) or {}
                if meta.get("fact"):
                    out.append(
                        UserFactMatch(
                            id=str(item.id),
                            fact=str(meta["fact"]),
                            category=str(meta.get("category", "preference")),
                            score=round(score, 3),
                        )
                    )
            return out
        except Exception as exc:  # pragma: no cover
            logger.warning("Upstash Vector recall_user_facts failed: %s", exc)
            return []

    async def list_user_facts(self, user_id: UUID, limit: int = 30) -> list[UserFactMatch]:
        if not self.enabled:
            return []
        try:
            page = await self._index.range(  # type: ignore[union-attr]
                cursor="0",
                limit=limit,
                include_metadata=True,
                namespace=self._user_memory_ns(user_id),
            )
            vectors = getattr(page, "vectors", []) or []
            out: list[UserFactMatch] = []
            for vec in vectors:
                meta = getattr(vec, "metadata", None) or {}
                if meta.get("fact"):
                    out.append(
                        UserFactMatch(
                            id=str(vec.id),
                            fact=str(meta["fact"]),
                            category=str(meta.get("category", "preference")),
                        )
                    )
            return out
        except Exception as exc:  # pragma: no cover
            logger.warning("Upstash Vector list_user_facts failed: %s", exc)
            return []

    async def delete_user_fact(self, user_id: UUID, fact_id: str) -> None:
        if not self.enabled:
            return
        try:
            await self._index.delete(  # type: ignore[union-attr]
                ids=[fact_id],
                namespace=self._user_memory_ns(user_id),
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Upstash Vector delete_user_fact failed: %s", exc)

    async def purge_user_namespaces(self, user_id: UUID) -> None:
        """Delete all tenant-scoped Upstash Vector namespaces for GDPR-style account deletion."""
        if not self.enabled:
            return
        for ns in (
            self._merchant_ns(user_id),
            self._document_ns(user_id),
            self._user_memory_ns(user_id),
        ):
            try:
                await self._index.delete_namespace(ns)  # type: ignore[union-attr]
            except Exception as exc:  # pragma: no cover
                logger.warning("Upstash Vector purge namespace %s failed: %s", ns, exc)


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
