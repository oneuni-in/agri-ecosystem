/**
 * The visitor address this relay is willing to vouch for, or null.
 *
 * Every browser request reaches the API through a relay in this app, so the
 * address the API sees on the socket is always the relay's. The relays used
 * to bridge that gap by copying the inbound `x-forwarded-for` header into the
 * upstream request — which was the bug. `X-Forwarded-For` is not a forbidden
 * header name, so page JavaScript can set it on a same-origin fetch, and the
 * relay passed the claim through untouched. That value keys the backend rate
 * limiter (`ratelimit:{ip}:{path}`) and seeds the daily viewer pseudonym, so
 * anyone who could set it had neither a rate limit nor a stable pseudonym.
 *
 * Putting Cloudflare in front does not fix it on its own: Cloudflare APPENDS
 * the real address to a client-supplied `X-Forwarded-For` rather than
 * replacing it, and the backend reads the leftmost entry — still the
 * attacker's. `CF-Connecting-IP` is the header Cloudflare always sets itself,
 * overwriting whatever arrived, so it is the one worth reading.
 *
 * But only where Cloudflare is actually in front. With no edge, a caller can
 * simply send `CF-Connecting-IP` to this app directly and we would be back to
 * the same bug wearing a different header name — which is why the deployment
 * has to opt in with TRUST_EDGE_CLIENT_IP rather than us sniffing for it.
 *
 * Returning null is a real answer, not a failure: without a trusted edge
 * there is no visitor address anyone can believe at this layer. The backend
 * then falls back to this relay's address and every visitor shares one
 * rate-limit bucket — a throughput limit, not a hole. Per-visitor accounting
 * comes back the moment the edge is declared.
 *
 * Mirrored in apps/web-agri/lib/client-ip.ts; change both.
 */
const EDGE_HEADER = "cf-connecting-ip";

const IPV4 = /^\d{1,3}(?:\.\d{1,3}){3}$/;

function isIpAddress(value: string): boolean {
  if (IPV4.test(value)) {
    // reject 999.1.1.1 and 010.0.0.1: the backend parses this with
    // ipaddress.ip_address and would drop what it cannot read anyway
    return value
      .split(".")
      .every((octet) => Number(octet) <= 255 && String(Number(octet)) === octet);
  }
  // IPv6, deliberately shape-only: the value is Cloudflare's, this is the
  // second line of defence, and the backend validates it properly again
  return value.length <= 45 && value.includes(":") && /^[0-9a-f:.]+$/i.test(value);
}

/** Structural, so both NextRequest.headers and next/headers' readonly bag fit. */
type HeaderBag = { get(name: string): string | null };

export function forwardedClientIp(headers: HeaderBag): string | null {
  if (process.env.TRUST_EDGE_CLIENT_IP !== "true") return null;
  const claimed = headers.get(EDGE_HEADER)?.trim();
  if (!claimed || !isIpAddress(claimed)) return null;
  return claimed;
}
