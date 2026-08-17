import { nextConfig } from "@agri/config/eslint/next";

export default [
  ...nextConfig,
  {
    // public/sw.js runs in the ServiceWorkerGlobalScope (A-U3 W2, the
    // single-route helplines worker) — these are real globals there, not
    // undefined browser leaks. Same carve-out web-milk has carried since
    // D28; kept as a per-file block rather than a project-wide global so
    // `self`/`caches` stay undefined everywhere else.
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
