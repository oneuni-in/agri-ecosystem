/**
 * Node-runtime Sentry init for Next instrumentation. Same inactive-without-DSN
 * contract as client.ts. The type-only import is erased at compile time, so
 * loading this module never pulls the SDK in.
 */
import type { captureRequestError } from "@sentry/nextjs";

function dsn(): string | undefined {
  return process.env.SENTRY_DSN ?? process.env.NEXT_PUBLIC_SENTRY_DSN;
}

export async function registerSentry(): Promise<void> {
  const value = dsn();
  if (!value) return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.init({
    dsn: value,
    release: process.env.RELEASE ?? process.env.NEXT_PUBLIC_RELEASE,
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
  });
}

export async function onRequestError(
  ...args: Parameters<typeof captureRequestError>
): Promise<void> {
  if (!dsn()) return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.captureRequestError(...args);
}
