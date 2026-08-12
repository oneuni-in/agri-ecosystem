import { citySlug } from "@agri/ui/seo";
import type { MetadataRoute } from "next";

import { fetchBusinessCategories } from "@/lib/categories";
import { fetchCoveredPincodes } from "@/lib/milk";
import { fetchProductCategories } from "@/lib/taxonomy";

const SITE = "https://milk.in";
const MAX_PAGES = 30; // 30 × 100 = 3000 URLs > every TN pincode; hard stop, never infinite

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Backend down ⇒ [] (same fetchProductCategories contract as
  // fetchCoveredPincodes below) ⇒ this list degrades to the static entries
  // above rather than failing the build.
  const [productCategories, businessCategories] = await Promise.all([
    fetchProductCategories("en"),
    fetchBusinessCategories(),
  ]);
  const entries: MetadataRoute.Sitemap = [
    { url: `${SITE}/`, changeFrequency: "daily", priority: 1 },
    ...businessCategories.map((category) => ({
      url: `${SITE}/c/${category.slug}`,
      changeFrequency: "daily" as const,
      priority: 0.8,
    })),
    ...productCategories.map((category) => ({
      url: `${SITE}/p/${category.value}`,
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
