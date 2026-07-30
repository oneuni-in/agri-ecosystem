import { describe, expect, it } from "vitest";

import { categoriesFromSchema, categoryIcon } from "./taxonomy";

const schema = {
  vertical_slug: "milk",
  version: 2,
  fields: [
    {
      key: "category",
      type: "enum",
      options: ["milk", "ghee"],
      option_meta: {
        milk: { label: { en: "Milk", ta: "பால்", hi: "दूध" }, icon: "milk" },
        ghee: { label: { en: "Ghee", ta: "நெய்", hi: "घी" }, icon: "ghee" },
      },
    },
    { key: "fat_percent", type: "number" },
  ],
};

describe("categoriesFromSchema", () => {
  it("reads values, labels and icons out of the schema", () => {
    expect(categoriesFromSchema(schema, "en")).toEqual([
      { value: "milk", label: "Milk", vern: "பால்", icon: "🥛" },
      { value: "ghee", label: "Ghee", vern: "நெய்", icon: "🍯" },
    ]);
  });

  it("renders the requested locale as the primary label", () => {
    const [milk] = categoriesFromSchema(schema, "hi");
    expect(milk?.label).toBe("दूध");
  });

  it("falls back to en when the locale is missing from a label", () => {
    const partial = {
      fields: [
        {
          key: "category",
          type: "enum",
          options: ["khoa"],
          option_meta: { khoa: { label: { en: "Khoa" }, icon: "khoa" } },
        },
      ],
    };
    expect(categoriesFromSchema(partial, "ta")[0]?.label).toBe("Khoa");
  });

  it("NON-NEGOTIABLE 1: a value added to the schema needs no code change", () => {
    const withNewValue = {
      fields: [
        {
          key: "category",
          type: "enum",
          options: ["milk", "shrikhand"],
          option_meta: {
            milk: { label: { en: "Milk", ta: "பால்" }, icon: "milk" },
            shrikhand: { label: { en: "Shrikhand", ta: "ஸ்ரீகண்ட்" }, icon: "shrikhand" },
          },
        },
      ],
    };
    const result = categoriesFromSchema(withNewValue, "ta");
    expect(result.map((c) => c.value)).toEqual(["milk", "shrikhand"]);
    expect(result[1]?.label).toBe("ஸ்ரீகண்ட்"); // label ships from the schema
    expect(result[1]?.icon).toBe("🥛"); // unknown icon key → documented fallback
  });

  it("uses the option value when an option carries no metadata at all", () => {
    const bare = { fields: [{ key: "category", type: "enum", options: ["lassi"] }] };
    expect(categoriesFromSchema(bare, "en")).toEqual([
      { value: "lassi", label: "lassi", vern: "", icon: "🧋" },
    ]);
  });

  it("returns nothing when the schema has no category field", () => {
    expect(categoriesFromSchema({ fields: [{ key: "fat_percent" }] }, "en")).toEqual([]);
  });

  it("survives a malformed payload rather than throwing", () => {
    expect(categoriesFromSchema(null, "en")).toEqual([]);
    expect(categoriesFromSchema({ fields: "nope" }, "en")).toEqual([]);
  });
});

describe("categoryIcon", () => {
  it("maps known keys", () => {
    expect(categoryIcon("paneer")).toBe("🧀");
  });

  it("falls back for unknown keys", () => {
    expect(categoryIcon("not-a-real-key")).toBe("🥛");
  });
});
