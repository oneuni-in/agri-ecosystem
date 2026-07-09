"""Object storage access (MinIO locally, standing in for R2). Client lands later."""

import httpx

from settings import get_settings


async def check_storage() -> bool:
    url = f"{get_settings().minio_endpoint}/minio/health/live"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        return response.status_code == 200
    except httpx.HTTPError:
        return False
