import path from "node:path";

import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// Locale comes from the shared request config; catalogs live in @agri/ui.
const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Next 15 streams metadata into <body> on dynamically rendered pages;
  // Lighthouse's SEO audits only read <head>. Bots on this list get the
  // blocking in-head variant instead. The list is Next's default set plus
  // Chrome-Lighthouse, so the CI SEO gate (D04) sees what limited bots see;
  // real users and JS-capable crawlers (Googlebot) are unaffected.
  htmlLimitedBots:
    /Chrome-Lighthouse|Mediapartners-Google|Slurp|DuckDuckBot|baiduspider|yandex|sogou|bitlybot|tumblr|vkShare|quora link preview|redditbot|ia_archiver|Bingbot|BingPreview|applebot|facebookexternalhit|facebookcatalog|Twitterbot|LinkedInBot|Slackbot|Discordbot|WhatsApp|SkypeUriPreview/i,
  // NEXT_DIST_DIR lets a production build land somewhere other than
  // `.next`, so it cannot race the dev server writing the same directory
  // (the U2 build-vs-dev trap — a half-overwritten .next 500s on every
  // route and looks exactly like an app bug). Unset in CI and in Docker,
  // where nothing else is using the tree.
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
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
  transpilePackages: [
    "@agri/ui",
    "@agri/types",
    "@agri/auth-client",
    "@agri/observability",
  ],
  // @agri/ui is a barrel of "use client" components; without this, every
  // component in the barrel lands in each app's client graph regardless of
  // use (D21 lighthouse regression: web-milk shipped SponsoredAd it never
  // renders). Rewrites barrel imports to direct module imports at build time.
  experimental: {
    optimizePackageImports: ["@agri/ui"],
    // Issue #45's proven lever, opted into deliberately for agri (the milk
    // note says other apps should not inherit it by default): the home is
    // dynamically rendered (force-dynamic), so build-time critical-CSS can
    // never help it; inlineCss removes both render-blocking stylesheet
    // requests on the CI mobile/3G profile. Same size trade-off as milk
    // (~8 KB inline per document) — accepted for the 0.90 floor (Decision
    // 3: agri holds it from PR one).
    inlineCss: true,
  },
  // AG-U5: /coins, /saved and /notifications moved under the /account shell.
  //
  // THESE REDIRECTS ARE PERMANENT INFRASTRUCTURE, NOT A MIGRATION COURTESY.
  // Do not delete them once "the links are all updated" — the links are not
  // the point. `backend/core/modules/notify/drivers.py` hardcodes
  // `{"url": "/notifications"}` into every web-push payload, and that driver
  // is shared by agri, milk, organic and id — web-id keeps its
  // /notifications at the top level, so the literal cannot simply be
  // repointed here without breaking the other three. Every push already
  // delivered to a device, and every one sent from now on, clicks through to
  // /notifications on this origin. This entry is what makes that land.
  //
  // Permanent (308) rather than temporary: the old paths are not coming back,
  // and a 308 preserves the request method (the AG-A57 note on Next's
  // `permanentRedirect`).
  async redirects() {
    return [
      { source: "/coins", destination: "/account/coins", permanent: true },
      { source: "/saved", destination: "/account/saved", permanent: true },
      { source: "/notifications", destination: "/account/notifications", permanent: true },
    ];
  },
  // Same page-level hardening milk ships (M2 creative threat model): agri's
  // home now renders ad creatives too. Safe subset only; the full img-src
  // allowlist CSP remains the tracked fast-follow.
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
      project: "agri-web-agri",
      silent: true,
      widenClientFileUpload: true,
    })
  : config;
