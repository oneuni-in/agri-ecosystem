"""Object storage access (MinIO locally, standing in for R2).

D11 shipped put_object (avatars); D16 adds get_object for auth-gated
evidence serving. Bytes are fully in memory (5 MiB cap upstream in
shared.media). The minio client is sync - calls run in a worker thread.
Bucket auto-creation is a dev convenience; prod buckets are provisioned.
"""

import asyncio
import io
from urllib.parse import urlparse

import httpx
from minio import Minio

from settings import get_settings

_client: Minio | None = None


class StorageError(RuntimeError):
    """Object storage is unreachable or rejected the write."""


def reset_storage() -> None:
    global _client
    _client = None


def get_storage_client() -> Minio:
    global _client
    if _client is None:
        settings = get_settings()
        parsed = urlparse(settings.minio_endpoint)
        _client = Minio(
            parsed.netloc,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=parsed.scheme == "https",
        )
    return _client


async def put_object(key: str, data: bytes, content_type: str) -> None:
    def _put() -> None:
        client = get_storage_client()
        bucket = get_settings().minio_bucket
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(
            bucket, key, io.BytesIO(data), length=len(data), content_type=content_type
        )

    try:
        await asyncio.to_thread(_put)
    except Exception as exc:
        raise StorageError("object storage write failed") from exc


async def get_object(key: str) -> bytes:
    """Read a stored object fully into memory (evidence docs are <= 5 MiB)."""

    def _get() -> bytes:
        client = get_storage_client()
        response = client.get_object(get_settings().minio_bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    try:
        return await asyncio.to_thread(_get)
    except Exception as exc:
        raise StorageError("object storage read failed") from exc


async def check_storage() -> bool:
    url = f"{get_settings().minio_endpoint}/minio/health/live"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        return response.status_code == 200
    except httpx.HTTPError:
        return False
