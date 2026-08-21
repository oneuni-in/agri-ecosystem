/**
 * Business Console origin, for W5's business half.
 *
 * Mirrors apps/web-milk/lib/console.ts deliberately — same var, same
 * fail-loud rule — rather than inventing a second convention for the same
 * cross-origin link.
 *
 * `NEXT_PUBLIC_CONSOLE_URL` is inlined at build time, so it is unrecoverable
 * once shipped. A silent localhost fallback is right for dev and exactly
 * wrong for production: it would ship a "claim my shop" button that resolves
 * to the visitor's OWN machine — a dead button, with nothing logged anywhere.
 * A production build with the var unset fails loudly instead.
 */
export function resolveConsoleUrl(
  rawValue: string | undefined,
  nodeEnv: string | undefined,
): string {
  if (nodeEnv === "production" && !rawValue) {
    throw new Error(
      "NEXT_PUBLIC_CONSOLE_URL is not set. The /account farm-or-business section links " +
        "cross-origin to the Business Console (D16 claim/create flow, " +
        "apps/web-agri/app/business/listings) and must not silently fall back to " +
        "http://localhost:3002 in a production build — set NEXT_PUBLIC_CONSOLE_URL at build time.",
    );
  }
  return rawValue ?? "http://localhost:3002";
}

export const CONSOLE_URL = resolveConsoleUrl(
  process.env.NEXT_PUBLIC_CONSOLE_URL,
  process.env.NODE_ENV,
);

/** Strips trailing slashes so a misconfigured `.../` cannot produce `//`. */
export function listingsHref(base: string): string {
  return `${base.replace(/\/+$/, "")}/business/listings`;
}
