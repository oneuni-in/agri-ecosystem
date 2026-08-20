import path from "node:path";

import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// Locale comes from the shared request config; catalogs live in @agri/ui.
const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  // Page-level hardening, the same safe subset web-agri and web-milk already
  // ship. Deliberately NOT a full policy: no script-src/style-src, so nothing
  // inline breaks, and the full img-src allowlist stays the tracked
  // fast-follow. What these three do buy:
  //   object-src 'none'    - no <object>/<embed> plugin surface
  //   base-uri 'self'      - injected <base> cannot repoint relative URLs
  //   frame-ancestors 'self' - clickjacking: nobody else may frame these pages
  //
  // frame-ancestors is safe here: silent SSO is redirect-based
  // (/api/auth/login?silent=1 -> prompt=none -> redirect back), NOT a hidden
  // iframe, so nothing legitimate frames the identity provider.
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "Content-Security-Policy",
            value: "object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
          },
        ],
      },
    ];
  },
  reactStrictMode: true,
  // D09: the session cookie must be first-party on id.agri.in. In dev the
  // Next server proxies the FastAPI backend so browser, UI and API share one
  // origin; in prod the reverse proxy does the same job at id.agri.in.
  //
  // ONE PREFIX PER SURFACE THIS APP ACTUALLY CALLS, never a catch-all.
  //
  // `/api/id/:path*` used to forward EVERY backend path, which published the
  // whole API at id.agri.in: /metrics (OTP issuance volumes, SMS spend in INR,
  // billing-webhook rejection counts), /health/deep (which internal dependency
  // is down), every /admin/* route and the Razorpay webhook. Authorization
  // still held on each of them, so this was exposed surface rather than a
  // bypass - but none of it is anything this app asks for.
  //
  // The three below cover every call in the app: lib/api.ts's 14 paths are all
  // /auth/* or /identity/*, and the notification bell uses /notify/*. Adding a
  // surface here is a deliberate edit, which is the point.
  //
  // NOT affected by this list, and worth knowing before changing it:
  //   - /authorize is its own entry below (the browser's OAuth redirect).
  //   - /token, /oauth/revoke and JWKS never come through here at all. Every
  //     app reaches those directly via `idInternalOrigin` (= API_BASE_URL),
  //     server to server. Sign-in across milk/agri/organic/admin does not
  //     depend on this rewrite.
  //
  // PROD CAVEAT: the note above says a reverse proxy does this job at
  // id.agri.in. Where that is true, THIS FILE IS NOT THE ENFORCEMENT POINT
  // and the same allowlist has to exist at the proxy.
  async rewrites() {
    const api = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
    return [
      { source: "/api/id/auth/:path*", destination: `${api}/auth/:path*` },
      { source: "/api/id/identity/:path*", destination: `${api}/identity/:path*` },
      { source: "/api/id/notify/:path*", destination: `${api}/notify/:path*` },
      { source: "/authorize", destination: `${api}/authorize` },
    ];
  },
  // Next 15 streams metadata into <body> on dynamically rendered pages;
  // Lighthouse's SEO audits only read <head>. Bots on this list get the
  // blocking in-head variant instead. The list is Next's default set plus
  // Chrome-Lighthouse, so the CI SEO gate (D04) sees what limited bots see;
  // real users and JS-capable crawlers (Googlebot) are unaffected.
  htmlLimitedBots:
    /Chrome-Lighthouse|Mediapartners-Google|Slurp|DuckDuckBot|baiduspider|yandex|sogou|bitlybot|tumblr|vkShare|quora link preview|redditbot|ia_archiver|Bingbot|BingPreview|applebot|facebookexternalhit|facebookcatalog|Twitterbot|LinkedInBot|Slackbot|Discordbot|WhatsApp|SkypeUriPreview/i,
  // Docker image builds (apps/Dockerfile) set NEXT_OUTPUT=standalone to
  // produce the self-contained server. It stays OFF elsewhere: standalone
  // tracing creates symlinks, which Windows dev boxes deny by default
  // (EPERM). Tracing is rooted at the monorepo root so workspace packages
  // (@agri/ui etc.) land inside the bundle.
  ...(process.env.NEXT_OUTPUT === "standalone" && {
    output: "standalone" as const,
    outputFileTracingRoot: path.join(__dirname, "../.."),
  }),
  // Workspace packages ship TypeScript source (no build step), so Next must
  // compile them alongside the app.
  transpilePackages: ["@agri/ui", "@agri/types", "@agri/auth-client", "@agri/observability"],
  // @agri/ui is a barrel of "use client" components; without this, every
  // component in the barrel lands in each app's client graph regardless of
  // use (D21 lighthouse regression: web-milk shipped SponsoredAd it never
  // renders). Rewrites barrel imports to direct module imports at build time.
  experimental: {
    optimizePackageImports: ["@agri/ui"],
  },
  eslint: {
    // Linting is its own turbo task (`pnpm lint`, --max-warnings 0). Running
    // it again inside `next build` would double the work and hide which task
    // actually failed.
    ignoreDuringBuilds: true,
  },
};

const config = withNextIntl(nextConfig);

// Source-map upload is READY BUT INACTIVE: SENTRY_AUTH_TOKEN is a CI secret
// that stays unset until launch prep (docs/runbooks/monitoring.md), so local
// and CI builds skip the wrapper entirely.
export default process.env.SENTRY_AUTH_TOKEN
  ? withSentryConfig(config, {
      ...(process.env.SENTRY_ORG ? { org: process.env.SENTRY_ORG } : {}),
      project: "agri-web-id",
      silent: true,
      widenClientFileUpload: true,
    })
  : config;
