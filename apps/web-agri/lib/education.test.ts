import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchGuide,
  fetchInstitution,
  fetchInstitutions,
  fetchStates,
  qs,
} from "./education";

afterEach(() => vi.unstubAllGlobals());

type FetchLike = (...args: unknown[]) => Promise<unknown>;

function stubFetch(impl: FetchLike) {
  const spy = vi.fn(impl);
  vi.stubGlobal("fetch", spy);
  return spy;
}

describe("F1: a dead engine makes a section absent, never broken", () => {
  it("returns an empty page when the API is unreachable", async () => {
    stubFetch(() => Promise.reject(new Error("ECONNREFUSED")));
    expect(await fetchInstitutions({})).toEqual({ items: [], next_cursor: null });
  });

  it("returns an empty state list when the API is unreachable", async () => {
    stubFetch(() => Promise.reject(new Error("ECONNREFUSED")));
    expect(await fetchStates()).toEqual([]);
  });

  it("returns an empty page on a 5xx rather than throwing", async () => {
    stubFetch(() => Promise.resolve({ ok: false, status: 503 }));
    expect(await fetchInstitutions({})).toEqual({ items: [], next_cursor: null });
  });
});

describe("detail routes distinguish absent from unreachable", () => {
  it("returns null for a 404 institution", async () => {
    stubFetch(() => Promise.resolve({ ok: false, status: 404 }));
    expect(await fetchInstitution("nope")).toBeNull();
  });

  it("does NOT return null for a backend outage", async () => {
    // The distinction is the point. If an outage and a missing slug both came
    // back null, the detail page would notFound() during an incident -- and a
    // college that exists would serve a hard 404 to Google for as long as the
    // backend was down. "Absent" and "unreachable" are different facts.
    stubFetch(() => Promise.resolve({ ok: false, status: 503 }));
    expect(await fetchInstitution("anything")).toBe("unavailable");
  });

  it("treats a thrown fetch as unavailable, not as missing", async () => {
    stubFetch(() => Promise.reject(new Error("ECONNREFUSED")));
    expect(await fetchInstitution("anything")).toBe("unavailable");
  });

  it("applies the same three-way rule to guides", async () => {
    stubFetch(() => Promise.resolve({ ok: false, status: 404 }));
    expect(await fetchGuide("draft-one")).toBeNull();
    stubFetch(() => Promise.resolve({ ok: false, status: 500 }));
    expect(await fetchGuide("draft-one")).toBe("unavailable");
  });
});

describe("query string construction", () => {
  it("omits empty and absent filters", async () => {
    const spy = stubFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [] }) }),
    );
    await fetchInstitutions({ state: "tamil-nadu", kind: undefined, q: "" });

    const url = String(spy.mock.calls[0]?.[0]);
    expect(url).toContain("state=tamil-nadu");
    expect(url).not.toContain("kind=");
    // An empty q= reaches the API as ILIKE '%%', which matches everything and
    // reads as success -- "no filter" silently becoming "whole corpus".
    expect(url).not.toContain("q=");
  });

  it("keeps false, which is a real filter value", () => {
    // is_government=false means "private only". Dropping it as falsy would
    // silently widen the result set to every college.
    expect(qs({ is_government: false })).toBe("?is_government=false");
    expect(qs({ is_government: true })).toBe("?is_government=true");
  });

  it("keeps 0, which is a real limit", () => {
    expect(qs({ limit: 0 })).toBe("?limit=0");
  });

  it("returns an empty string when nothing is set", () => {
    expect(qs({})).toBe("");
    expect(qs({ q: "", cursor: undefined })).toBe("");
  });

  it("encodes a slug that would otherwise break the path", async () => {
    const spy = stubFetch(() => Promise.resolve({ ok: false, status: 404 }));
    await fetchInstitution("a/../../etc");
    expect(String(spy.mock.calls[0]?.[0])).not.toContain("/../");
  });
});
