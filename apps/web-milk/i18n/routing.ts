import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "ta", "hi"],
  defaultLocale: "en",
  // "/" stays the canonical English URL (Lighthouse audits it; D23 static
  // fix must hold). ta/hi live under /ta /hi with hreflang alternates.
  localePrefix: "as-needed",
});
