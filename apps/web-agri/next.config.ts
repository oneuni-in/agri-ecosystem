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
