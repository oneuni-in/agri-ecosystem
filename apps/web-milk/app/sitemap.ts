import type { MetadataRoute } from "next";

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
  ];
}
