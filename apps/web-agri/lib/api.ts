/**
 * Same-origin calls to the `/api/leads/*` and `/api/directory/*` BFF proxies
 * (D18 inbox + my-inquiries pages). Mirrors apps/web-admin/lib/api.ts's
 * 401-retry-once helper: access tokens live ~15 minutes; on a 401 we ask
 * /api/auth/me to rotate the session cookie, then retry exactly once.
 * Callers pass the full proxy path (e.g. "/api/leads/inbox?...") since the
 * two proxies share no common prefix.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly detailData?: unknown,
  ) {
    super(`${status}: ${detail}`);
  }
}

interface JsonBody {
  [key: string]: unknown;
}

async function parse(response: Response): Promise<JsonBody> {
  const body = (await response.json().catch(() => ({}))) as JsonBody;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      String(body.detail ?? body.error ?? "request_failed"),
      body.detail,
    );
  }
  return body;
}

async function request(path: string, init?: RequestInit): Promise<JsonBody> {
  const first = await fetch(path, init);
  if (first.status !== 401) return parse(first);
  await fetch("/api/auth/me"); // rotates a stale session cookie
  return parse(await fetch(path, init));
}

export function getJson(path: string): Promise<JsonBody> {
  return request(path);
}

export function postJson(path: string, payload?: unknown): Promise<JsonBody> {
  return request(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  });
}

export function putJson(path: string, payload?: unknown): Promise<JsonBody> {
  return request(path, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  });
}

export function patchJson(path: string, payload?: unknown): Promise<JsonBody> {
  return request(path, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  });
}

export function deleteJson(path: string): Promise<JsonBody> {
  return request(path, { method: "DELETE" });
}
