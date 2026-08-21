import { NextResponse, type NextRequest } from "next/server";

/**
 * Structural auth gate for the admin console, mirroring the one web-agri
 * ships for the business console and web-milk for its account pages.
 *
 * The console had per-page gates only. Every page that matters carries one
 * today, so nothing was exposed - but nothing CAUGHT a page that forgot. Two
 * route files already have no `getServerUser()` call (`claims`, `reviews`);
 * they are bare `redirect("/ops")` stubs, so they leak nothing, and that is
 * exactly how this decays: the next page added under app/ inherits no gate
 * and no failure. This is the backstop, not the authority.
 *
 * PRESENCE-ONLY, deliberately. The session cookie is a JWE sealed with a
 * server secret; verifying it here would duplicate the BFF and drift from it.
 * A stale or forged cookie passes this check and is refused one hop later by
 * `auth.getServerUser()` on the page (and by the BFF for any /api call), which
 * is the same two-step web-agri uses. What this adds is that a guest bounces
 * to login from the FIRST byte of any console URL, carrying the path they
 * asked for, instead of rendering a shell whose data calls then 401.
 *
 * `admin_session` = auth-client's `${clientId.replace("web-", "")}_session`
 * for clientId "web-admin" (packages/auth-client/src/config.ts).
 */
const SESSION_COOKIE = "admin_session";

export function middleware(request: NextRequest): NextResponse {
  if (!request.cookies.has(SESSION_COOKIE)) {
    const login = new URL("/api/auth/login", request.url);
    login.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  // Everything except the API routes and Next's own assets.
  //
  // `api` MUST stay excluded, and not only to avoid a redirect loop through
  // /api/auth/login: the /api/admin proxy answers an unauthenticated call with
  // 401 `{"detail":"unauthenticated"}`, which is what a fetch() expects.
  // Redirecting it to an HTML login page instead would turn a clean 401 into a
  // parse error at the caller.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
