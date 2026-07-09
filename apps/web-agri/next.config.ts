import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// Locale comes from the shared request config; catalogs live in @agri/ui.
const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Workspace packages ship TypeScript source (no build step), so Next must
  // compile them alongside the app.
  transpilePackages: ["@agri/ui", "@agri/types", "@agri/auth-client"],
  eslint: {
    // Linting is its own turbo task (`pnpm lint`, --max-warnings 0). Running
    // it again inside `next build` would double the work and hide which task
    // actually failed.
    ignoreDuringBuilds: true,
  },
};

export default withNextIntl(nextConfig);
