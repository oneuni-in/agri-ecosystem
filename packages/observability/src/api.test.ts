import { afterEach, describe, expect, it, vi } from "vitest";

import { REQUEST_ID_HEADER, apiFetch, apiUrl } from "./api";

describe("apiFetch", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("stamps a request id when none is given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok"));
    vi.stubGlobal("fetch", fetchMock);
    await apiFetch("/health");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toBe(apiUrl("/health"));
    const rid = new Headers(init.headers).get(REQUEST_ID_HEADER);
    expect(rid).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("preserves a caller-supplied request id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok"));
    vi.stubGlobal("fetch", fetchMock);
    await apiFetch("/health", {
      headers: { [REQUEST_ID_HEADER]: "trace-me-12345" },
    });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get(REQUEST_ID_HEADER)).toBe(
      "trace-me-12345",
    );
  });
});
