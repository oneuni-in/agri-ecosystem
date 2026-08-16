import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl, shouldNoIndex } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale } from "next-intl/server";
import Link from "next/link";

import { fetchCommodities, pick } from "@/lib/mandi";

/**
 * A-U2 W3 — `/mandi`, the commodity index.
 *
 * Lists only commodities that HAVE prices: the backend omits the empty
 * ones, so this page never advertises a door that opens onto nothing.
 * When the whole set is empty (a fresh database, or an ingest that has
 * never run) the page still renders — with its empty state and a
 * self-noindex, because a thin page must not be indexed while it is thin
 * (Execution Schedule §0.6, `shouldNoIndex`).
 */
export const revalidate = 3600;

export async function generateMetadata(): Promise<Metadata> {
  const commodities = await fetchCommodities();
  return buildMetadata({
    title: "Mandi prices by commodity · agri.in",
    description:
      "Daily mandi prices from Agmarknet for Tamil Nadu markets — per commodity, " +
      "with 30-day trends and a market-by-market comparison.",
    canonical: canonicalUrl("https://agri.in", "/mandi"),
    siteName: "agri.in",
    noIndex: shouldNoIndex(commodities.length),
  });
}

export default async function MandiIndexPage() {
  const [commodities, locale] = await Promise.all([fetchCommodities(), getLocale()]);

  return (
    <Wrap>
      <section className="pb-8 pt-6" aria-label="Mandi prices by commodity">
        <Eyebrow>MARKET DATA · AGMARKNET</Eyebrow>
        <h1 className="mb-1 font-display text-2xl font-extrabold">Mandi prices · சந்தை விலை</h1>

        {commodities.length === 0 ? (
          // Same honest empty state the home shows: no market data yet,
          // said plainly, rather than a grid of placeholder cards.
          <p className="mt-3 text-[13px] text-muted" data-testid="mandi-index-empty">
            No market data yet. Prices appear here as the daily Agmarknet pull ingests them.
          </p>
        ) : (
          <>
            <p className="mb-4 text-[13px] text-muted">
              {commodities.length} commodities · prices as published by Agmarknet
            </p>
            <ul className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
              {commodities.map((c) => (
                <li key={c.slug}>
                  <Link
                    href={`/mandi/${c.slug}`}
                    data-testid="commodity-link"
                    className="tap-target block rounded-card border border-line bg-card p-3 no-underline"
                  >
                    <span className="text-[20px]" aria-hidden="true">
                      {c.emoji}
                    </span>
                    <b className="mt-1 block text-[13px]">{pick(locale, c.name)}</b>
                    {/* Both stamps are DATA: how many markets reported, and
                        the day they reported for. Never hardcoded. */}
                    <small className="block text-[11px] text-muted">
                      {c.market_count} {c.market_count === 1 ? "market" : "markets"} · {c.as_of}
                    </small>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </Wrap>
  );
}
