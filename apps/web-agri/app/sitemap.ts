import type { MetadataRoute } from "next";

import { fetchCommodities } from "@/lib/mandi";

/**
 * A-U2 W3 — agri.in's sitemap.
 *
 * The commodity entries come from the SAME read the pages do
 * (`/market/commodities`), which returns only commodities that have
 * servable prices. That is the whole safety property: a page with no data
 * is never advertised here, so the sitemap cannot point Google at a
 * self-noindexed thin page.
 *
 * Backend down ⇒ `fetchCommodities()` returns [] ⇒ the sitemap degrades
 * to its static entries rather than failing the build (the milk sitemap's
 * contract, ported).
 */
const SITE = "https://agri.in";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const commodities = await fetchCommodities();

  return [
    { url: `${SITE}/`, changeFrequency: "daily", priority: 1 },
    { url: `${SITE}/categories`, changeFrequency: "weekly", priority: 0.7 },
    { url: `${SITE}/tools`, changeFrequency: "monthly", priority: 0.6 },
    {
      url: `${SITE}/mandi`,
      changeFrequency: "daily",
      priority: 0.8,
    },
    ...commodities.map((c) => ({
      url: `${SITE}/mandi/${c.slug}`,
      // Prices republish daily, so the pages genuinely change daily.
      changeFrequency: "daily" as const,
      priority: 0.8,
      // The newest ingested day, not the build time: an honest
      // lastModified is the one the data carries.
      ...(c.as_of ? { lastModified: new Date(c.as_of) } : {}),
    })),
  ];
}
