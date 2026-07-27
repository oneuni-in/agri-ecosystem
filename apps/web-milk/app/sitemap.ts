import { citySlug } from "@agri/ui/seo";
import type { MetadataRoute } from "next";

import { DAIRY_CATEGORIES } from "@/lib/categories";
import { fetchCoveredPincodes } from "@/lib/milk";

const SITE = "https://milk.in";
const MAX_PAGES = 30; // 30 × 100 = 3000 URLs > every TN pincode; hard stop, never infinite

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries: MetadataRoute.Sitemap = [
    { url: `${SITE}/`, changeFrequency: "daily", priority: 1 },
    ...DAIRY_CATEGORIES.map((category) => ({
      url: `${SITE}/c/${category}`,
      changeFrequency: "daily" as const,
      priority: 0.8,
    })),
  ];
  // Covered (indexable) pincodes only — thin pages self-noindex and must
  // never be advertised here. Backend down ⇒ static entries only (CI builds).
  let cursor: string | undefined;
  for (let i = 0; i < MAX_PAGES; i++) {
    const page = await fetchCoveredPincodes(cursor);
    if (!page) break;
    entries.push(
      ...page.items.map((p) => ({
        url: `${SITE}/${citySlug(p.district)}/${p.pincode}`,
        changeFrequency: "daily" as const,
        priority: 0.8,
      })),
    );
    if (!page.next_cursor) break;
    cursor = page.next_cursor;
  }
  return entries;
}
