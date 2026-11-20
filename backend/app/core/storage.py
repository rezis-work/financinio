import asyncio
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from app.core.config import get_settings


class StorageBackend(Protocol):
    async def save(self, user_id: UUID, filename: str, data: bytes) -> str:
        """Persist raw bytes and return a storage_key."""
        ...

    async def load(self, storage_key: str) -> bytes:
        """Retrieve raw bytes by storage_key."""
        ...

    async def delete(self, storage_key: str) -> None:
        """Delete object by storage_key."""
        ...


class LocalDiskStorage:
    def __init__(self, base_dir: str) -> None:
        self.base_path = Path(base_dir).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve_safe(self, storage_key: str) -> Path:
        target = (self.base_path / storage_key).resolve()
        if not str(target).startswith(str(self.base_path)):
            raise ValueError("Invalid storage key path traversal detected")
        return target

    async def save(self, user_id: UUID, filename: str, data: bytes) -> str:
        safe_name = Path(filename).name.replace(" ", "_")
        storage_key = f"{user_id}/{uuid4().hex}_{safe_name}"
        target = self._resolve_safe(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return storage_key

    async def load(self, storage_key: str) -> bytes:
        target = self._resolve_safe(storage_key)
        return target.read_bytes()

    async def delete(self, storage_key: str) -> None:
        target = self._resolve_safe(storage_key)
        if target.exists():
            target.unlink()


class S3CompatibleStorage:
    """Async-safe S3-compatible object storage adapter (Fly.io Tigris / AWS S3 / Cloudflare R2)."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region: str = "auto",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.region = region
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self._cached_client = None

    def _client(self):
        if self._cached_client is not None:
            return self._cached_client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError(
                "STORAGE_BACKEND=s3 requires boto3 (`uv add boto3`)."
            ) from exc
        self._cached_client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=Config(s3={"addressing_style": "virtual"}),
        )
        return self._cached_client

    async def save(self, user_id: UUID, filename: str, data: bytes) -> str:
        safe_name = Path(filename).name.replace(" ", "_")
        key = f"users/{user_id}/{uuid4().hex}_{safe_name}"
        await asyncio.to_thread(
            self._client().put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
        )
        return key

    async def load(self, storage_key: str) -> bytes:
        def _get() -> bytes:
            obj = self._client().get_object(Bucket=self.bucket, Key=storage_key)
            return obj["Body"].read()

        return await asyncio.to_thread(_get)

    async def delete(self, storage_key: str) -> None:
        await asyncio.to_thread(
            self._client().delete_object,
            Bucket=self.bucket,
            Key=storage_key,
        )


def get_storage() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == "s3":
        bucket = settings.resolved_s3_bucket
        if not bucket:
            raise RuntimeError(
                "S3_BUCKET or BUCKET_NAME (Tigris) must be configured when STORAGE_BACKEND=s3"
            )
        return S3CompatibleStorage(
            bucket=bucket,
            endpoint_url=settings.resolved_s3_endpoint,
            region=settings.resolved_s3_region,
            access_key_id=settings.resolved_s3_access_key,
            secret_access_key=settings.resolved_s3_secret_key,
        )
    return LocalDiskStorage(settings.local_storage_dir)
