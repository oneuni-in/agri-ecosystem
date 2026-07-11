/**
 * Same-origin calls to the id.agri.in API (Next rewrite -> FastAPI).
 * credentials stay default ("same-origin"): the agri_sid cookie rides along
 * because the rewrite keeps everything one origin. No tokens ever touch JS.
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

export function postJson(path: string, payload: unknown): Promise<JsonBody> {
  return fetch(`/api/id${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  }).then(parse);
}

export function getJson(path: string): Promise<JsonBody> {
  return fetch(`/api/id${path}`).then(parse);
}
