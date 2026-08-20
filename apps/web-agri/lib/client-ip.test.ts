/**
 * A visitor must not be able to nominate its own address.
 *
 * The relays used to copy the inbound `x-forwarded-for` straight into the
 * request they make to the API. `X-Forwarded-For` is not a forbidden header
 * name, so page JavaScript can set it on a same-origin fetch — which handed
 * every caller the value that keys the backend rate limiter and seeds the
 * daily viewer pseudonym. Cloudflare does not save us either: it APPENDS to a
 * client-supplied header, and the backend reads the leftmost entry.
 *
 * So: never read `x-forwarded-for`, and read the edge header only where the
 * deployment has actually declared an edge. Without one there is no
 * trustworthy visitor address at this layer, and saying so is the honest
 * answer — the backend then falls back to the relay's own address.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { forwardedClientIp } from "./client-ip";

const head = (init: Record<string, string>): Headers => new Headers(init);

describe("forwardedClientIp", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns null when no trusted edge is declared", () => {
    vi.stubEnv("TRUST_EDGE_CLIENT_IP", "");
    expect(forwardedClientIp(head({ "cf-connecting-ip": "203.0.113.9" }))).toBeNull();
  });

  it("never reads x-forwarded-for, which page JavaScript can set", () => {
    vi.stubEnv("TRUST_EDGE_CLIENT_IP", "true");
    expect(forwardedClientIp(head({ "x-forwarded-for": "1.2.3.4" }))).toBeNull();
  });

  it("uses the edge-set address once the edge is declared", () => {
    vi.stubEnv("TRUST_EDGE_CLIENT_IP", "true");
    expect(forwardedClientIp(head({ "cf-connecting-ip": "203.0.113.9" }))).toBe("203.0.113.9");
  });

  it("ignores a visitor's x-forwarded-for even alongside a real edge header", () => {
    vi.stubEnv("TRUST_EDGE_CLIENT_IP", "true");
    const value = forwardedClientIp(
      head({ "cf-connecting-ip": "203.0.113.9", "x-forwarded-for": "1.2.3.4" }),
    );
    expect(value).toBe("203.0.113.9");
  });

  it("rejects an edge value that is not an address", () => {
    vi.stubEnv("TRUST_EDGE_CLIENT_IP", "true");
    expect(forwardedClientIp(head({ "cf-connecting-ip": "not-an-ip" }))).toBeNull();
    expect(forwardedClientIp(head({ "cf-connecting-ip": "10.0.0.1, 9.9.9.9" }))).toBeNull();
    expect(forwardedClientIp(head({ "cf-connecting-ip": "999.1.1.1" }))).toBeNull();
  });

  it("accepts IPv6, which is most of mobile India", () => {
    vi.stubEnv("TRUST_EDGE_CLIENT_IP", "true");
    expect(forwardedClientIp(head({ "cf-connecting-ip": "2001:db8::1" }))).toBe("2001:db8::1");
  });

  it("returns null when the edge header is absent", () => {
    vi.stubEnv("TRUST_EDGE_CLIENT_IP", "true");
    expect(forwardedClientIp(head({}))).toBeNull();
  });
});
