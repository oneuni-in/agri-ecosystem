"""Thin async Meilisearch v1.13 HTTP client (httpx). Only this module talks to Meili."""

import asyncio
from typing import Any

import httpx

from settings import get_settings

_client: "MeiliClient | None" = None


class MeiliError(RuntimeError):
    pass


class MeiliClient:
    def __init__(self, base_url: str, master_key: str) -> None:
        headers = {"Authorization": f"Bearer {master_key}"} if master_key else {}
        self._http = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10.0)

    async def _request(self, method: str, path: str, json_body: Any | None = None) -> Any:
        resp = await self._http.request(method, path, json=json_body)
        if resp.status_code >= 400:
            raise MeiliError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else None

    async def health(self) -> bool:
        try:
            await self._request("GET", "/health")
            return True
        except (MeiliError, httpx.HTTPError):
            return False

    async def ensure_index(self, uid: str, settings_body: dict[str, Any]) -> None:
        try:
            await self._request("POST", "/indexes", {"uid": uid, "primaryKey": "id"})
        except MeiliError as exc:
            if "index_already_exists" not in str(exc):
                raise
        task = await self._request("PATCH", f"/indexes/{uid}/settings", settings_body)
        await self.wait_for_task(task["taskUid"])

    async def upsert_documents(self, uid: str, docs: list[dict[str, Any]]) -> int:
        task = await self._request("PUT", f"/indexes/{uid}/documents", docs)
        return int(task["taskUid"])

    async def delete_documents(self, uid: str, ids: list[str]) -> int:
        task = await self._request("POST", f"/indexes/{uid}/documents/delete-batch", ids)
        return int(task["taskUid"])

    async def search(self, uid: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/indexes/{uid}/search", body)  # type: ignore[no-any-return]

    async def get_settings(self, uid: str) -> dict[str, Any]:
        return await self._request("GET", f"/indexes/{uid}/settings")  # type: ignore[no-any-return]

    async def delete_index(self, uid: str) -> None:
        try:
            await self._request("DELETE", f"/indexes/{uid}")
        except MeiliError as exc:
            if "index_not_found" not in str(exc):
                raise

    async def wait_for_task(self, task_uid: int, timeout: float = 10.0) -> None:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            task = await self._request("GET", f"/tasks/{task_uid}")
            if task["status"] == "succeeded":
                return
            if task["status"] in ("failed", "canceled"):
                raise MeiliError(f"task {task_uid} {task['status']}: {task.get('error')}")
            if asyncio.get_event_loop().time() > deadline:
                raise MeiliError(f"task {task_uid} timed out")
            await asyncio.sleep(0.05)

    async def aclose(self) -> None:
        await self._http.aclose()


def get_meili() -> MeiliClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = MeiliClient(s.meilisearch_url, s.meilisearch_master_key)
    return _client


def reset_meili() -> None:
    global _client
    _client = None  # old httpx client GC'd; fine for tests
