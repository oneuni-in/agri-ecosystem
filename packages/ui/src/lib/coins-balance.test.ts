import { describe, expect, it } from "vitest";

import { fetchCoinsBalance } from "./coins-balance";

type FakeResponse = { status: number; ok: boolean; json: () => Promise<unknown> };

function fakeFetch(response: FakeResponse): typeof fetch {
  return (() => Promise.resolve(response)) as unknown as typeof fetch;
}

describe("fetchCoinsBalance", () => {
  it("returns the balance on a successful response", async () => {
    const fetchImpl = fakeFetch({ status: 200, ok: true, json: () => Promise.resolve({ balance: 250 }) });
    expect(await fetchCoinsBalance("/api/coins/balance", fetchImpl)).toBe(250);
  });

  it("returns null on a 401 (signed out)", async () => {
    const fetchImpl = fakeFetch({ status: 401, ok: false, json: () => Promise.resolve({}) });
    expect(await fetchCoinsBalance("/api/coins/balance", fetchImpl)).toBeNull();
  });

  it("returns null on a non-ok status", async () => {
    const fetchImpl = fakeFetch({ status: 500, ok: false, json: () => Promise.resolve({}) });
    expect(await fetchCoinsBalance("/api/coins/balance", fetchImpl)).toBeNull();
  });

  it("returns null when balance is missing or non-numeric", async () => {
    const missing = fakeFetch({ status: 200, ok: true, json: () => Promise.resolve({}) });
    expect(await fetchCoinsBalance("/api/coins/balance", missing)).toBeNull();

    const nonNumeric = fakeFetch({ status: 200, ok: true, json: () => Promise.resolve({ balance: "250" }) });
    expect(await fetchCoinsBalance("/api/coins/balance", nonNumeric)).toBeNull();
  });

  it("returns null when fetchImpl throws", async () => {
    const fetchImpl = (() => Promise.reject(new Error("network blip"))) as unknown as typeof fetch;
    expect(await fetchCoinsBalance("/api/coins/balance", fetchImpl)).toBeNull();
  });
});
