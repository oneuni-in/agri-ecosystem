import { expect, test } from "@playwright/test";

// web-organic is already one of this suite's webServer entries (port 3001);
// its /api/coins and /api/notify proxies share the exact forward() pattern
// hardened in this change across all 8 catch-all routes (D14 A5).
//
// These assertions encode a discovery made during D14 Task 6's TDD, verified
// independently via curl, Node http.request, a raw TCP socket, and this same
// Playwright request fixture: Next.js 15's App Router normalizes literal and
// percent-encoded (%2e) dot-segments in the request pathname BEFORE route
// matching and BEFORE populating [...path]'s params.path - so no genuine
// HTTP request can currently deliver a "." or ".." element into the array
// the route's own guard checks. The guard (reject any "."/".."/"" segment,
// added to all 8 files) still exists and fires correctly if params.path
// ever DOES contain one - it is defense-in-depth for a source Next itself
// doesn't normalize (a future code path, or a Next version/config change),
// not the primary mitigation for these specific HTTP payloads.
//
// If this test ever starts failing (i.e. any of these stop matching), that
// is a signal Next's front-door normalization changed and the manual guard's
// HTTP-reachability needs re-verifying - see docs/security/sprint1-audit.md
// A5 for the full analysis.
const ORIGIN = "http://localhost:3001";

test.describe("Next.js front-door normalization neutralizes dot-segment traversal (D14 A5)", () => {
  test("encoded .. collapses out of the path before route matching -> Next's own 404", async ({
    request,
  }) => {
    const res = await request.get(`${ORIGIN}/api/coins/%2e%2e/%2e%2e/admin/rules`);
    expect(res.status()).toBe(404);
  });

  test("encoded .. on the notify proxy also collapses -> Next's own 404", async ({ request }) => {
    const res = await request.get(`${ORIGIN}/api/notify/%2e%2e/%2e%2e/admin/rules`);
    expect(res.status()).toBe(404);
  });

  test("single-dot segment collapses harmlessly, guard doesn't fire, falls through to auth check", async ({
    request,
  }) => {
    const res = await request.get(`${ORIGIN}/api/coins/./balance`);
    expect(res.status()).toBe(401);
    const body = await res.json();
    expect(body.detail).toBe("unauthenticated");
  });
});
