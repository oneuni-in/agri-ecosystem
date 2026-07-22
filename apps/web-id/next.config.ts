import path from "node:path";

import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// Locale comes from the shared request config; catalogs live in @agri/ui.
const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // D09: the session cookie must be first-party on id.agri.in. In dev the
  // Next server proxies the FastAPI backend so browser, UI and API share one
  // origin; in prod the reverse proxy does the same job at id.agri.in.
  async rewrites() {
    const api = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
    return [
      { source: "/api/id/:path*", destination: `${api}/:path*` },
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
