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
  // @agri/ui is a barrel of "use client" components; without this, every
  // component in the barrel lands in each app's client graph regardless of
  // use (D21 lighthouse regression: web-milk shipped SponsoredAd it never
  // renders). Rewrites barrel imports to direct module imports at build time.
  experimental: {
    optimizePackageImports: ["@agri/ui"],
    // Issue #45: every page ships exactly two render-blocking stylesheets
    // (compiled Tailwind + the fonts/design-token CSS from the [locale]
    // layout), ~8 KB transferred (~38 KB raw) total, which Lighthouse
    // estimates at ~1.4s of savings on the CI mobile/3G profile. The
    // pincode landing route (`/[locale]/[city]/[pincode]`) is dynamically
    // rendered (`ƒ`, forced by its own `searchParams` read) and so can
    // never benefit from build-time critical-CSS inlining — that's why
    // D29's `optimizeCss` attempt did nothing for it. `inlineCss` inlines
    // all CSS as `<style>` tags in the document for both static and
    // dynamic rendering, eliminating both blocking requests everywhere.
    // Trade-off accepted: every HTML document now carries the ~8 KB
    // inline instead of one cacheable CSS URL shared across pages — fine
    // at this CSS size; revisit (e.g. critical-CSS extraction) if the
    // bundle grows meaningfully. Scoped to web-milk only for now; other
    // apps should opt in deliberately, not inherit this by default.
    inlineCss: true,
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
      project: "agri-web-milk",
      silent: true,
      widenClientFileUpload: true,
    })
  : config;
