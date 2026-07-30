/**
 * Business Console URL resolution for `ListBusinessCta` (Task 11, fix round
 * 1 / Finding 2). Split out of the component as pure functions so they can
 * be unit-tested without a DOM/component-testing harness — this app has
 * neither (`apps/web-milk`'s only test file, `lib/taxonomy.test.ts`, is a
 * plain unit test; there is no @testing-library/react or jsdom setup here).
 *
 * `NEXT_PUBLIC_CONSOLE_URL` is inlined into the JS bundle at Next.js build
 * time (the `NEXT_PUBLIC_` convention) — unrecoverable at runtime once
 * shipped. A silent `http://localhost:3002` fallback is fine for local dev,
 * but the wrong failure mode for a production build: it would ship a
 * cross-origin link to the Business Console that resolves to the visitor's
 * OWN machine, i.e. a dead button, with no error anywhere. So a production
 * build with the var unset fails loudly instead — see `resolveConsoleUrl`.
 */
export function resolveConsoleUrl(rawValue: string | undefined, nodeEnv: string | undefined): string {
  if (nodeEnv === "production" && !rawValue) {
    throw new Error(
      "NEXT_PUBLIC_CONSOLE_URL is not set. ListBusinessCta links cross-origin to the " +
        "Business Console (D16 claim/create flow, apps/web-agri/app/business/listings) " +
        "and must not silently fall back to http://localhost:3002 in a production " +
        "build — set NEXT_PUBLIC_CONSOLE_URL at build time.",
    );
  }
  return rawValue ?? "http://localhost:3002";
}

export const CONSOLE_URL = resolveConsoleUrl(process.env.NEXT_PUBLIC_CONSOLE_URL, process.env.NODE_ENV);

/** Strips any trailing slash(es) from `base` before appending the listings
 * path, so a misconfigured `NEXT_PUBLIC_CONSOLE_URL=http://host/` (trailing
 * slash) doesn't produce `http://host//business/listings`. */
export function listingsHref(base: string): string {
  return `${base.replace(/\/+$/, "")}/business/listings`;
}
