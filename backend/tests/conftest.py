import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_storage_dep, get_vector_dep
from app.core.database import get_db
from app.core.storage import LocalDiskStorage
from app.main import create_app
from app.models import Base
from app.services.vector_service import (
    DocumentSearchMatch,
    MerchantMemoryMatch,
    UserFactMatch,
)


class InMemoryVectorService:
    """Deterministic fake Upstash Vector backend for fast offline testing."""

    def __init__(self) -> None:
        self.merchant_memory: dict[tuple[str, str], MerchantMemoryMatch] = {}
        self.document_chunks: list[dict] = []
        self.user_facts: dict[str, dict[str, UserFactMatch]] = {}

    async def lookup_merchant_memory(
        self, user_id: UUID, query_text: str, min_score: float = 0.85
    ) -> MerchantMemoryMatch | None:
        q = query_text.lower()
        for (uid, raw_key), match in self.merchant_memory.items():
            if uid == str(user_id) and raw_key in q:
                if match.score >= min_score:
                    return match
        return None

    async def upsert_merchant_memory(
        self,
        user_id: UUID,
        merchant_raw: str,
        merchant_clean: str,
        category_id: str,
        category_name: str,
    ) -> None:
        key = (str(user_id), merchant_raw.lower().strip())
        self.merchant_memory[key] = MerchantMemoryMatch(
            category_id=category_id,
            category_name=category_name,
            merchant_clean=merchant_clean,
            score=0.96,
        )

    async def upsert_document_chunks(
        self,
        user_id: UUID,
        document_id: UUID,
        chunks: list[str],
        metadata: dict,
    ) -> None:
        self.document_chunks.append(
            {"user_id": str(user_id), "document_id": str(document_id), "chunks": chunks, **metadata}
        )

    async def search_documents(
        self, user_id: UUID, query_text: str, top_k: int = 4
    ) -> list[DocumentSearchMatch]:
        q = query_text.lower()
        matches: list[DocumentSearchMatch] = []
        for entry in self.document_chunks:
            if entry["user_id"] != str(user_id):
                continue
            for chunk in entry["chunks"]:
                if any(w in chunk.lower() for w in q.split() if len(w) > 3):
                    matches.append(
                        DocumentSearchMatch(
                            document_id=entry["document_id"],
                            filename=entry.get("filename", "doc.pdf"),
                            doc_type=entry.get("doc_type", "receipt"),
                            excerpt=chunk[:400],
                            score=0.92,
                        )
                    )
        return matches[:top_k]

    async def remember_user_fact(
        self, user_id: UUID, fact: str, category: str = "preference"
    ) -> UserFactMatch:
        uid = str(user_id)
        bucket = self.user_facts.setdefault(uid, {})
        fid = f"mem-{len(bucket) + 1}"
        item = UserFactMatch(id=fid, fact=fact.strip(), category=category, score=1.0)
        bucket[fid] = item
        return item

    async def recall_user_facts(
        self, user_id: UUID, query_text: str, top_k: int = 5
    ) -> list[UserFactMatch]:
        return list(self.user_facts.get(str(user_id), {}).values())[:top_k]

    async def list_user_facts(self, user_id: UUID, limit: int = 30) -> list[UserFactMatch]:
        return list(self.user_facts.get(str(user_id), {}).values())[:limit]

    async def delete_user_fact(self, user_id: UUID, fact_id: str) -> None:
        self.user_facts.get(str(user_id), {}).pop(fact_id, None)


@pytest_asyncio.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def fake_vector() -> InMemoryVectorService:
    return InMemoryVectorService()


@pytest_asyncio.fixture
async def client(
    test_db_session: AsyncSession, fake_vector: InMemoryVectorService
) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    tmp_dir = tempfile.mkdtemp(prefix="financinio_test_uploads_")
    storage = LocalDiskStorage(tmp_dir)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_dep] = lambda: storage
    app.dependency_overrides[get_vector_dep] = lambda: fake_vector

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup temp uploads dir
    for p in sorted(Path(tmp_dir).rglob("*"), reverse=True):
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            p.rmdir()
    Path(tmp_dir).rmdir()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@financinio.app",
            "password": "StrongPassword123!",
            "full_name": "Alice Mercer",
            "base_currency": "USD",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
