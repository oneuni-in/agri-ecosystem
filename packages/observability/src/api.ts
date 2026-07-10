/**
 * Backend API fetch helper. Stamps x-request-id (uuid) so one id traces
 * app -> API -> log; the backend echoes it on the response
 * (backend/core/shared/request_context.py).
 */
export const REQUEST_ID_HEADER = "x-request-id";

export function apiUrl(path: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return new URL(path, base).toString();
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!headers.has(REQUEST_ID_HEADER)) {
    headers.set(REQUEST_ID_HEADER, crypto.randomUUID());
  }
  return fetch(apiUrl(path), { ...init, headers });
}
