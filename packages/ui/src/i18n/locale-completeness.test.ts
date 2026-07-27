import { describe, expect, it } from "vitest";

import en from "./messages/en.json";
import hi from "./messages/hi.json";
import ta from "./messages/ta.json";

function flatten(node: unknown, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  if (typeof node === "string") {
    out.set(prefix, node);
    return out;
  }
  if (node && typeof node === "object") {
    for (const [key, value] of Object.entries(node)) {
      for (const [childKey, childValue] of flatten(value, prefix ? `${prefix}.${key}` : key)) {
        out.set(childKey, childValue);
      }
    }
  }
  return out;
}

const catalogs = { en: flatten(en), ta: flatten(ta), hi: flatten(hi) } as const;

describe("locale completeness (D27 non-negotiable #2)", () => {
  it.each(["ta", "hi"] as const)("%s has exactly en's key set", (locale) => {
    expect([...catalogs[locale].keys()].sort()).toEqual([...catalogs.en.keys()].sort());
  });

  it.each(["en", "ta", "hi"] as const)("%s has no empty values", (locale) => {
    const empty = [...catalogs[locale]].filter(([, v]) => v.trim() === "").map(([k]) => k);
    expect(empty).toEqual([]);
  });
});
