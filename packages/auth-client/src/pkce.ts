/**
 * RFC 7636 PKCE material. Runs on the Node runtime of Next route handlers -
 * webcrypto globals only, no node:crypto import, so vitest and any future
 * edge runtime agree.
 */
const encoder = new TextEncoder();

function base64url(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("base64url");
}

export function generateVerifier(): string {
  return base64url(crypto.getRandomValues(new Uint8Array(32)));
}

export async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(verifier));
  return base64url(new Uint8Array(digest));
}

export function generateState(): string {
  return base64url(crypto.getRandomValues(new Uint8Array(16)));
}
