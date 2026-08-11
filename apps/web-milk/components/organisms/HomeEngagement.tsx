import { RatingStars, ReviewCard, Section, StatBand, StatCell } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { statVisible, type HomeData, type ReviewItem } from "@/lib/home";

/**
 * §8b — stats band. Every number is a real aggregate computed server-side in
 * `homeStats()` from sources already on the page (the covers()-backed blend,
 * the D28 coverage feed, D18 rating aggregates). Nothing is client-computed
 * from a full list, and nothing is invented: a stat with no honest source is
 * not rendered at all, and any cell can be switched off with
 * `HOME_HIDDEN_STATS` rather than faked (§16).
 *
 * The reference count-up is deliberately NOT reproduced: it animates from 0
 * on scroll, which needs a client island above the fold and repaints text
 * mid-scroll. The numbers are server-rendered and final.
 */
export async function StatsBand({ stats }: { stats: Record<string, number> }) {
  const t = await getTranslations("ui.home.stats");
  const cells = (["verifiedVendors", "coveredPincodes", "sellers", "reviews"] as const)
    .filter((key) => statVisible(key) && stats[key] !== undefined && stats[key] > 0)
    .map((key) => ({ key, value: stats[key] as number, label: t(key) }));
  if (cells.length === 0) return null;
  return (
    <StatBand label={t("verifiedVendors")} data-testid="stats-band" className="mt-5">
      {cells.map((cell, index) => (
        <StatCell
          key={cell.key}
          value={cell.value.toLocaleString("en-IN")}
          label={cell.label}
          first={index === 0}
        />
      ))}
    </StatBand>
  );
}

/** §8c — static i18n content component (one of the four U1 allows). */
export async function HowItWorks() {
  const t = await getTranslations("ui.home.how");
  return (
    <Section title={t("title")}>
      <div className="grid gap-3 md:grid-cols-3">
        {(["s1", "s2", "s3"] as const).map((step, index) => (
          <div
            key={step}
            className="rounded-card border border-cream-line bg-card p-4 text-center"
          >
            <span
              aria-hidden="true"
              className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-pill bg-brand-soft font-display text-base font-extrabold text-brand-deep"
            >
              {index + 1}
            </span>
            <b className="block text-[13px] font-semibold text-ink">{t(`${step}.t`)}</b>
            <small className="text-[11px] text-muted">{t(`${step}.d`)}</small>
          </div>
        ))}
      </div>
    </Section>
  );
}

/**
 * §8d — reviews strip. Composed in `fetchHomeData()` from D18's per-business
 * endpoint, which only ever returns APPROVED rows to a public caller: a
 * pending or rejected review can never reach this component. Empty → the
 * whole section is hidden, per the spec.
 *
 * Review bodies are locale-keyed JSONB; we render the reader's locale when the
 * author wrote in it and fall back to whatever they did write, so a Tamil
 * review still shows on `/en` in Tamil rather than vanishing.
 */
export async function ReviewsStrip({
  reviews,
  locale,
}: {
  reviews: ReviewItem[];
  locale: string;
}) {
  if (reviews.length === 0) return null;
  const t = await getTranslations("ui.home.reviews");
  return (
    <Section title={t("title")} see={t("coinsNudge")} seeHref="/post-need">
      <div className="grid gap-2.5 md:grid-cols-3">
        {reviews.slice(0, 3).map((review) => {
          const body = review.body[locale] ?? Object.values(review.body)[0] ?? "";
          return (
            <ReviewCard
              key={review.id}
              data-testid="home-review"
              stars={<RatingStars value={String(review.rating)} />}
              body={body}
              attribution={
                // `.tap-target`: an 11px attribution line is a ~12px-tall
                // link — §1.5's overlay gives it the 44px hit area without
                // growing the card.
                <Link
                  href={`/directory/businesses/${review.business.slug}`}
                  className="tap-target text-muted no-underline"
                >
                  {review.business.name}
                </Link>
              }
            />
          );
        })}
      </div>
    </Section>
  );
}

/**
 * §8e — popular near you. Generated from the REAL covered-geo feed (the same
 * D28 source the sitemap uses), so every chip is an existing ISR city/pincode
 * landing page. Nothing hardcoded: a newly covered pincode appears here on the
 * next revalidate.
 */
export async function PopularNearYou({ covered }: { covered: HomeData["coveredPincodes"] }) {
  if (covered.length === 0) return null;
  const t = await getTranslations("ui.home.popular");
  // One chip per district (the city page), most-covered districts first.
  const byDistrict = new Map<string, string>();
  for (const item of covered) {
    if (!byDistrict.has(item.district)) byDistrict.set(item.district, item.pincode);
  }
  const cities = [...byDistrict.entries()].slice(0, 9);
  return (
    <Section title={t("title")}>
      <div className="flex flex-wrap gap-2">
        {cities.map(([district, pincode]) => (
          <Link
            key={district}
            href={`/${district.toLowerCase().replace(/\s+/g, "-")}/${pincode}`}
            // min-h 44 (was py-2 ≈ 36px): the §1.5 floor. inline-flex keeps
            // the pill's text vertically centred in the taller box.
            className="inline-flex min-h-[44px] items-center rounded-pill border border-cream-line bg-card px-4 text-[12px] text-ink no-underline"
          >
            {t("milkIn", { place: district })}
          </Link>
        ))}
      </div>
    </Section>
  );
}
