import { Eyebrow, MandiCard, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl, datasetJsonLd, JsonLd, shouldNoIndex } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { fetchCommodities, fetchCommodity, pick, type MarketPrice } from "@/lib/mandi";

/**
 * A-U2 W3 — `/mandi/[commodity]`, the commodity × market page.
 *
 * One payload drives everything here: the lead card's 30-day trend, the
 * multi-market compare table, and the Dataset JSON-LD. The backend 404s a
 * commodity with no servable rows, so this page never exists empty — and
 * `shouldNoIndex` keeps a single-market page out of the index until it
 * has something worth indexing.
 *
 * ISR: `revalidate` matches the data's real cadence. Mandi prices move
 * once a day, and the as-of stamp travels IN the payload, so a cached
 * page is still honest about its own age.
 */
export const revalidate = 3600;

/** Pre-render the commodities that have data; anything else is rendered
 * on demand and 404s if the backend says it has no rows. */
export async function generateStaticParams(): Promise<{ commodity: string }[]> {
  const commodities = await fetchCommodities();
  return commodities.map((c) => ({ commodity: c.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ commodity: string }>;
}): Promise<Metadata> {
  const { commodity } = await params;
  const detail = await fetchCommodity(commodity);
  if (!detail) {
    return buildMetadata({
      title: "Mandi prices · agri.in",
      canonical: canonicalUrl("https://agri.in", `/mandi/${commodity}`),
      noIndex: true,
    });
  }
  const name = detail.name["en"] ?? detail.slug;
  const markets = detail.markets.length;
  return buildMetadata({
    title: `${name} price today — ${markets} ${markets === 1 ? "market" : "markets"} · agri.in`,
    description:
      `Today's ${name} mandi price from Agmarknet (${detail.as_of}), across ` +
      `${markets} Tamil Nadu ${markets === 1 ? "market" : "markets"}, with a 30-day trend.`,
    canonical: canonicalUrl("https://agri.in", `/mandi/${detail.slug}`),
    siteName: "agri.in",
    // A page with one market and one observation is thin. It stays out of
    // the index until at least two markets report — the data grows into
    // being indexable rather than being advertised before it is useful.
    noIndex: shouldNoIndex(detail.markets.length, 2),
  });
}

function tone(change: number): "up" | "down" | "flat" {
  if (change > 0) return "up";
  if (change < 0) return "down";
  return "flat";
}

function changeText(change: number, unit: string): string {
  if (change === 0) return "—";
  return `${change > 0 ? "▲" : "▼"} ₹${Math.abs(change)}/${unit}`;
}

export default async function CommodityPage({
  params,
}: {
  params: Promise<{ commodity: string }>;
}) {
  const { commodity } = await params;
  const [detail, locale] = await Promise.all([fetchCommodity(commodity), getLocale()]);
  if (!detail) notFound();

  const name = pick(locale, detail.name);
  const [lead, ...rest] = detail.markets;

  return (
    <Wrap>
      {/* Dataset JSON-LD: these ARE a published dataset, and saying so
          honestly (with the source named) is the whole point. */}
      <JsonLd
        data={datasetJsonLd({
          name: `${detail.name["en"] ?? detail.slug} mandi prices — Tamil Nadu`,
          description:
            `Daily minimum, maximum and modal prices for ` +
            `${detail.name["en"] ?? detail.slug} across ${detail.markets.length} ` +
            `Tamil Nadu markets, as published by Agmarknet (${detail.source}). ` +
            `Latest observation ${detail.as_of}.`,
          url: canonicalUrl("https://agri.in", `/mandi/${detail.slug}`),
        })}
      />

      <section className="pb-8 pt-6" aria-label={`${name} mandi prices`}>
        <Eyebrow>MARKET DATA · {detail.source.toUpperCase()}</Eyebrow>
        <h1 className="mb-1 font-display text-2xl font-extrabold">
          <span aria-hidden="true">{detail.emoji} </span>
          {name}
        </h1>
        {/* Source + as-of are DATA. The page never claims freshness it
            does not have. */}
        <p className="mb-4 text-[12px] text-muted" data-testid="commodity-stamp">
          {detail.source} · {detail.as_of}
          {detail.note ? ` · ${pick(locale, detail.note)}` : ""}
        </p>

        {lead ? (
          <div className="mb-6 max-w-[320px]">
            <MandiCard
              data-testid="commodity-lead-card"
              emoji={detail.emoji}
              name={name}
              market={lead.market}
              price={`₹${lead.price}/${detail.unit}`}
              change={changeText(lead.change, detail.unit)}
              tone={tone(lead.change)}
              spark={[...lead.series_30d]}
              range={`30-day: ₹${lead.range_low}–${lead.range_high}`}
            />
          </div>
        ) : null}

        {/* Multi-market compare — the additive table this page exists for.
            Rendered only when a second market has reported: a one-row
            "comparison" compares nothing. */}
        {rest.length > 0 ? (
          <section aria-label="Compare markets" data-testid="compare-table">
            <h2 className="mb-2 font-display text-lg font-bold">Compare markets</h2>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[13px]">
                <thead>
                  <tr className="border-b border-line text-left text-[11px] text-muted">
                    <th className="py-2 pr-3 font-medium">Market</th>
                    <th className="py-2 pr-3 font-medium">District</th>
                    <th className="py-2 pr-3 font-medium">Price</th>
                    <th className="py-2 pr-3 font-medium">Change</th>
                    <th className="py-2 font-medium">As of</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.markets.map((m: MarketPrice) => (
                    <tr key={m.market_slug} className="border-b border-line-soft">
                      <td className="py-2 pr-3">{m.market}</td>
                      <td className="py-2 pr-3 text-muted">{m.district}</td>
                      <td className="py-2 pr-3 font-medium">
                        ₹{m.price}/{detail.unit}
                      </td>
                      <td className={`py-2 pr-3 text-${tone(m.change)}`}>
                        {changeText(m.change, detail.unit)}
                      </td>
                      {/* Per-row as-of: markets report on different days,
                          and a stale row must say so rather than borrow
                          the page's freshest date. */}
                      <td className="py-2 text-muted">{m.as_of}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}
      </section>
    </Wrap>
  );
}
