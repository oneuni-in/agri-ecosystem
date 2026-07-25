import { Card, EmptyState } from "@agri/ui";
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
  pincode,
}: {
  items: CoversItem[];
  categoryLabel: string;
  pincode: string;
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
            href={`/${pincode}`}
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
      {items.map((item) => (
        <li key={item.id}>
          <Card
            hover
            className="flex h-full flex-col gap-1.5 p-4"
            data-testid={`category-result-${item.slug}`}
          >
            <Link
              href={`/directory/businesses/${item.slug}`}
              className="flex flex-col gap-1.5 no-underline"
            >
              <h3 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">{item.name}</h3>
              <p className="text-[12.5px] text-sub">{categoryLabel}</p>
              {item.distance_m < UNLOCATABLE_M ? (
                <p className="text-[12.5px] text-sub">
                  {t("brandPage.kmAway", { km: (item.distance_m / 1000).toFixed(1) })}
                </p>
              ) : null}
            </Link>
          </Card>
        </li>
      ))}
    </ul>
  );
}
