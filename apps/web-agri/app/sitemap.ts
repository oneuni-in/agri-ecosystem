import type { MetadataRoute } from "next";

import { educationSitemapEntries } from "@/lib/education-sitemap";
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
  const [commodities, education] = await Promise.all([
    fetchCommodities(),
    educationSitemapEntries(),
  ]);

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
    // Phase 2 — the agri-colleges vertical. VERIFIED, ACTIVE institutions
    // only: a `listed` page is noindex, and advertising a self-noindexed page
    // to Google is the same failure this file's comment already warns about
    // for empty commodities. See lib/education-sitemap.ts, which walks the
    // cursor rather than taking one page of 20 out of 772.
    ...education.map((entry) => ({
      url: `${SITE}${entry.path}`,
      // A college changes when a seed PR changes it -- weeks, not days.
      changeFrequency: "monthly" as const,
      priority: entry.path.includes("/", 1) ? 0.6 : 0.8,
      ...(entry.lastModified ? { lastModified: new Date(entry.lastModified) } : {}),
    })),
  ];
}
