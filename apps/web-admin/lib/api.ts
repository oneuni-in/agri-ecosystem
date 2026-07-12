/**
 * Same-origin calls to /api/admin/* (the BFF proxy). Access tokens live ~15
 * minutes; on a 401 we ask /api/auth/me to rotate the session cookie, then
 * retry exactly once.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
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
    throw new ApiError(response.status, String(body.detail ?? body.error ?? "request_failed"));
  }
  return body;
}

async function request(path: string, init?: RequestInit): Promise<JsonBody> {
  const url = `/api/admin${path}`;
  const first = await fetch(url, init);
  if (first.status !== 401) return parse(first);
  await fetch("/api/auth/me"); // rotates a stale session cookie
  return parse(await fetch(url, init));
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

export function deleteJson(path: string): Promise<JsonBody> {
  return request(path, { method: "DELETE" });
}
