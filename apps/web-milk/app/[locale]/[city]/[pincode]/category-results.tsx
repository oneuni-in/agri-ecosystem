import { Card, EmptyState, injectSponsored, type ServedAd, SponsoredListingCard } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import type { CoversItem } from "@/lib/directory";

/** Backend sentinel (`covers.py` `UNLOCATABLE_M`) for "neither the business
 * nor a branch resolves a location" — `distance_m` hits this exact value
 * rather than being null, so callers compare instead of null-checking. */
const UNLOCATABLE_M = 1_000_000_000;

/**
 * Results grid for the covers-based category browse view (D27 Task 13).
 * Deliberately simple vs. `VendorResults`/`VendorCard` (no map, no
 * call/WhatsApp actions, no verified badge) — this is a thin, noindexed
 * query-param view whose only job is "here are N businesses in this
 * category near you, tap through to their profile"; richer per-vertical
 * card content is Task 14+ territory.
 */
export async function CategoryResults({
  items,
  categoryLabel,
  base,
  sponsored = [],
}: {
  items: CoversItem[];
  categoryLabel: string;
  base: string; // canonical page path, e.g. /coimbatore/641001 (D28)
  /** M3.B sponsored listings - render-layer injection at positions 1 and 6;
   * `items` (and the covers cursor upstream) are never touched. */
  sponsored?: ServedAd[];
}) {
  const t = await getTranslations("ui");

  if (items.length === 0) {
    return (
      <EmptyState
        icon="🔎"
        title={t("categoryBrowse.empty")}
        action={
          <Link
            className="font-bold text-brand-deep no-underline"
            href={base}
            data-testid="category-empty-back"
          >
            {t("categoryBrowse.allMilk")}
          </Link>
        }
      />
    );
  }

  return (
    <ul className="grid gap-3 sm:grid-cols-2" data-testid="category-results">
      {injectSponsored(items, sponsored).map((entry) =>
        entry.kind === "sponsored" ? (
          <li key={`s-${entry.ad.placement_id}`}>
            <SponsoredListingCard ad={entry.ad} />
          </li>
        ) : (
          <li key={entry.item.id}>
            <Card
              hover
              className="flex h-full flex-col gap-1.5 p-4"
              data-testid={`category-result-${entry.item.slug}`}
            >
              <Link
                href={`/directory/businesses/${entry.item.slug}`}
                className="flex flex-col gap-1.5 no-underline"
              >
                <h3 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">
                  {entry.item.name}
                </h3>
                <p className="text-[12.5px] text-sub">{categoryLabel}</p>
                {entry.item.distance_m < UNLOCATABLE_M ? (
                  <p className="text-[12.5px] text-sub">
                    {t("brandPage.kmAway", { km: (entry.item.distance_m / 1000).toFixed(1) })}
                  </p>
                ) : null}
              </Link>
            </Card>
          </li>
        ),
      )}
    </ul>
  );
}
