import nextPlugin from "@next/eslint-plugin-next";
import tseslint from "typescript-eslint";

import { baseConfig } from "./base.js";

/**
 * Flat config for the five Next.js apps.
 * Every Next rule is escalated to "error" — `pnpm lint` runs with
 * --max-warnings 0, so a warning would fail the build anyway; making it
 * explicit keeps the failure message honest about severity.
 */
const nextRules = {
  ...nextPlugin.configs.recommended.rules,
  ...nextPlugin.configs["core-web-vitals"].rules,
};

export const nextConfig = tseslint.config(
  ...baseConfig,
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    plugins: {
      "@next/next": nextPlugin,
    },
    rules: Object.fromEntries(
      Object.keys(nextRules).map((rule) => [rule, "error"]),
    ),
  },
);

export default nextConfig;
