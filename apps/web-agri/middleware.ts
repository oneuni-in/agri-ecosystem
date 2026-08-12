import { NextResponse, type NextRequest } from "next/server";

/**
 * Structural auth gate for the Business Console (the D26 fast-follow
 * promised "before D27", closed here in U2 Group A).
 *
 * Presence-only on purpose: the session cookie is a JWE sealed with a
 * server secret, and the middleware does NOT try to verify it — the BFF and
 * each page's `auth.getServerUser()` gate stay authoritative. What this
 * fixes is the structural hole D26 left when the layout-level gate was
 * removed (it redirected with a dead `next=/business`): a guest now bounces
 * to login from the FIRST byte of any console URL, carrying the exact
 * path+query they asked for, and returns there after auth. A stale/garbage
 * cookie passes here and is caught by the page gate — one hop later, same
 * destination, no loop.
 *
 * `agri_session` = auth-client's `${clientId.replace("web-", "")}_session`
 * for clientId "web-agri" (packages/auth-client/src/config.ts).
 */
const SESSION_COOKIE = "agri_session";

export function middleware(request: NextRequest): NextResponse {
  if (!request.cookies.has(SESSION_COOKIE)) {
    const login = new URL("/api/auth/login", request.url);
    login.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/business/:path*"],
};
