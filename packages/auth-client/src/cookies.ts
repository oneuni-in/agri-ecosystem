/**
 * JWE-sealed httpOnly cookies (the spec's "iron-session or equivalent" -
 * jose was chosen because the back-channel logout verifier needs it anyway).
 * dir + A256GCM with a key derived from the app's session secret; tokens
 * inside the payload therefore never exist in browser-readable form.
 */
import { EncryptJWT, jwtDecrypt } from "jose";

const encoder = new TextEncoder();
const keyCache = new Map<string, Uint8Array>();

async function keyFor(secret: string): Promise<Uint8Array> {
  const cached = keyCache.get(secret);
  if (cached) return cached;
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(secret)));
  keyCache.set(secret, digest);
  return digest;
}

export async function seal(
  payload: Record<string, unknown>,
  secret: string,
  maxAgeSeconds: number,
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  return new EncryptJWT({ ...payload })
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setIssuedAt(now)
    .setExpirationTime(now + maxAgeSeconds)
    .encrypt(await keyFor(secret));
}

export async function unseal<T>(token: string | null, secret: string): Promise<T | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtDecrypt(token, await keyFor(secret));
    return payload as T;
  } catch {
    return null; // tampered, expired, wrong key, garbage - all equal "no session"
  }
}

export function serializeCookie(
  name: string,
  value: string,
  { maxAge, secure }: { maxAge: number; secure: boolean },
): string {
  const parts = [
    `${name}=${value}`,
    `Max-Age=${maxAge}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
  ];
  if (secure) parts.push("Secure");
  return parts.join("; ");
}

export function clearCookie(name: string, secure: boolean): string {
  return serializeCookie(name, "", { maxAge: 0, secure });
}

export function readCookie(header: string | null, name: string): string | null {
  if (!header) return null;
  for (const pair of header.split(";")) {
    const eq = pair.indexOf("=");
    if (eq === -1) continue;
    if (pair.slice(0, eq).trim() === name) return pair.slice(eq + 1).trim();
  }
  return null;
}
