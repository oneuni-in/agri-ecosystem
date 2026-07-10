import { REQUEST_ID_HEADER, apiFetch } from "@agri/observability/api";

// D05 debug page: proves one request id flows app -> API -> JSON log.
// Deliberately outside the Lighthouse matrix (only / and /demo are audited).
export const dynamic = "force-dynamic";

export const metadata = {
  title: "request-id trace",
  robots: { index: false, follow: false },
};

export default async function TracePage() {
  const requestId = crypto.randomUUID();
  let result =
    "API unreachable (is `docker compose -f docker-compose.dev.yml up` running?)";
  try {
    const response = await apiFetch("/health", {
      headers: { [REQUEST_ID_HEADER]: requestId },
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    const echoed = response.headers.get(REQUEST_ID_HEADER);
    result = `HTTP ${response.status} — x-request-id ${
      echoed === requestId ? "echoed by API" : `MISMATCH (${echoed})`
    }`;
  } catch {
    // page must render with the API down (CI builds have no backend)
  }
  return (
    <main className="mx-auto max-w-2xl p-8 font-mono text-sm text-ink">
      <h1 className="mb-4 text-lg font-semibold">request-id trace</h1>
      <p>request_id: {requestId}</p>
      <p>API /health: {result}</p>
      <p className="mt-4 text-sub">
        Verify in the API log: docker compose -f docker-compose.dev.yml logs
        api | grep &lt;request_id&gt;
      </p>
    </main>
  );
}
