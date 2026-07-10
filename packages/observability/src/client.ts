/**
 * Browser Sentry init. READY BUT INACTIVE: NEXT_PUBLIC_SENTRY_DSN is inlined
 * at build time, so without it the guard is constant-false and the bundler
 * drops the dynamic import chunk — zero client bytes, which keeps the D04
 * Lighthouse perf gate honest. Activation: docs/runbooks/monitoring.md.
 */
export function initSentryClient(): void {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;
  void import("@sentry/nextjs").then((Sentry) => {
    Sentry.init({
      dsn,
      release: process.env.NEXT_PUBLIC_RELEASE,
      tracesSampleRate: 0.1,
      sendDefaultPii: false,
    });
  });
}
