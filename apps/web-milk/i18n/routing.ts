import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "ta", "hi"],
  defaultLocale: "en",
  // "/" stays the canonical English URL (Lighthouse audits it; D23 static
  // fix must hold). ta/hi live under /ta /hi with hreflang alternates.
  localePrefix: "as-needed",
  // Every page already emits its own absolute-URL <link rel="canonical"> +
  // <link rel="alternate" hreflang> via @agri/ui/seo's buildMetadata (fixed
  // to the production origin). Leaving next-intl's default `alternateLinks`
  // on ALSO emits an HTTP `Link` header built from the request's own origin
  // - identical in prod (both resolve to milk.in) but a real conflict under
  // any other host (localhost during Lighthouse audits, staging): Lighthouse's
  // canonical audit sees hreflang entries for both origins and fails
  // "points to another hreflang location". Disabling it here leaves a single
  // hreflang source of truth (the metadata one) in every environment.
  alternateLinks: false,
});
