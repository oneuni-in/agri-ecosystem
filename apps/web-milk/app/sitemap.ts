import type { MetadataRoute } from "next";

import { DAIRY_CATEGORIES } from "@/lib/categories";

const SITE = "https://milk.in";

// Curated launch pincodes (Coimbatore metro). Full covered-pincode
// enumeration + per-pincode landing detail lands D28.
const LAUNCH_PINCODES = ["641001", "641002", "641004", "641012", "641045"];

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${SITE}/`, changeFrequency: "daily", priority: 1 },
    ...LAUNCH_PINCODES.map((p) => ({
      url: `${SITE}/${p}`,
      changeFrequency: "daily" as const,
      priority: 0.8,
    })),
    ...DAIRY_CATEGORIES.map((category) => ({
      url: `${SITE}/c/${category}`,
      changeFrequency: "daily" as const,
      priority: 0.8,
    })),
  ];
}
