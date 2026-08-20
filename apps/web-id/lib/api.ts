/**
 * Same-origin calls to the id.agri.in API (Next rewrite -> FastAPI).
 * credentials stay default ("same-origin"): the agri_sid cookie rides along
 * because the rewrite keeps everything one origin. No tokens ever touch JS.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    /** Seconds until the caller may retry, from the response's `Retry-After`
     * header; null when the server did not send one. The OTP throttles have
     * always sent it (`OtpRateLimited.retry_after` -> `router.py`), but this
     * client used to build errors from the JSON body alone and drop every
     * header — so a rate-limited screen could not name the wait, and told
     * people to "request a new code" instead, which is the exact action the
     * throttle had just refused. */
    public readonly retryAfter: number | null = null,
  ) {
    super(`${status}: ${detail}`);
  }
}

interface JsonBody {
  [key: string]: unknown;
}

function retryAfterSeconds(response: Response): number | null {
  const raw = response.headers.get("retry-after");
  if (raw === null) return null;
  const seconds = Number(raw);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null;
}

async function parse(response: Response): Promise<JsonBody> {
  const body = (await response.json().catch(() => ({}))) as JsonBody;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      String(body.detail ?? body.error ?? "request_failed"),
      retryAfterSeconds(response),
    );
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

export function patchJson(path: string, payload: unknown): Promise<JsonBody> {
  return fetch(`/api/id${path}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  }).then(parse);
}

export function postForm(path: string, form: FormData): Promise<JsonBody> {
  // no content-type header: the browser sets the multipart boundary
  return fetch(`/api/id${path}`, { method: "POST", body: form }).then(parse);
}
