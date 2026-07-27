import { nextConfig } from "@agri/config/eslint/next";

export default [
  ...nextConfig,
  {
    // public/sw.js runs in the ServiceWorkerGlobalScope (D28) — these are
    // real globals there, not undefined browser leaks.
    files: ["public/sw.js"],
    languageOptions: {
      globals: {
        self: "readonly",
        caches: "readonly",
        fetch: "readonly",
        Response: "readonly",
        URL: "readonly",
      },
    },
  },
];
