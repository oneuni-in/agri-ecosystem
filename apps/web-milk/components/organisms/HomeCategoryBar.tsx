import { CategoryBar, CategoryBarLink } from "@agri/ui";
import { getTranslations } from "next-intl/server";

import type { ProductCategory } from "@/lib/taxonomy";

/**
 * Organism (U1 §5): the home category bar.
 *
 * Every entry comes from the D17 vertical registry — `fetchProductCategories`
 * reads `GET /catalog/verticals/milk/schema`. Nothing here enumerates
 * categories, so adding a schema value lights up a link with zero code
 * (NON-NEGOTIABLE 1). The full value set is rendered; the bar scrolls rather
 * than truncating, which is why there is no "All N ›" link — milk.in has no
 * all-categories index route, and the reference's truncation exists only
 * because a static mock cannot scroll.
 *
 * A server component: no client JS, no hydration island, so it costs the LCP
 * path nothing beyond its markup. Renders nothing when the taxonomy is
 * unavailable (backend down at build time) — the page still builds and
 * self-heals at the next revalidate.
 */
export async function HomeCategoryBar({ categories }: { categories: ProductCategory[] }) {
  if (categories.length === 0) return null;
  const t = await getTranslations("ui.categoryBar");
  return (
    <CategoryBar
      label={t("label")}
      filters={
        // §5: the two attribute filters are pinned right on desktop and are
        // NOT part of the bar below 1024px — there they live as filter chips
        // on the results pages, which already own that state (D23).
        //
        // They point at /search (the one route that filters without a
        // pincode) rather than at `?type=` on the results page: `?type=` is
        // scoped to `/{city}/{pincode}`, and home is ISR — it cannot read the
        // visitor's location cookie server-side without going dynamic and
        // losing the Lighthouse budget. Pass 2 rewires these to the shared
        // D23 chip state alongside the §5c milk-type chips.
        <>
          <CategoryBarLink href="/search?q=home%20delivery">{t("homeDelivery")}</CategoryBarLink>
          <CategoryBarLink href="/search?q=organic">{t("organic")}</CategoryBarLink>
        </>
      }
    >
      <CategoryBarLink href="/" active>
        {t("all")}
      </CategoryBarLink>
      {categories.map((category) => (
        <CategoryBarLink key={category.value} href={`/p/${category.value}`}>
          {category.label}
        </CategoryBarLink>
      ))}
    </CategoryBar>
  );
}
