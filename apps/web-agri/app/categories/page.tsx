import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import Link from "next/link";

import {
  fetchVerticals,
  GROUP_LABEL_KEY,
  GROUP_STAGE,
  GROUP_STYLE,
  groupVerticals,
} from "@/lib/home";

import { CategoriesFilter, type FilterGroup } from "./categories-filter";

/**
 * A-U1 W2 — `/categories`, the A2 PAGE 1 reference screen: every vertical
 * the registry contains, searchable, in the 5 A1 groups. The tile binding
 * is IDENTICAL to the home §6 grid (same registry read, same /c/{slug}
 * hrefs, same tint/soon rules) — tile count MUST equal registry count
 * (AG-A13). Search is a client-side filter over the server-serialized
 * registry rows: no client fetch, and the home search band GETs here with
 * `?q=` as the island's initial value. (Reading `searchParams` makes the
 * route dynamic; the registry fetch itself stays cached in lib/home.)
 */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ui.agriHome.categoriesPage");
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    canonical: canonicalUrl("https://agri.in", "/categories"),
    siteName: "Agri.in",
  });
}

export default async function CategoriesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  const [locale, t, verticals, params] = await Promise.all([
    getLocale(),
    getTranslations("ui"),
    fetchVerticals(),
    searchParams,
  ]);
  const initialQuery = typeof params.q === "string" ? params.q : "";
  const groups = groupVerticals(verticals);
  const liveCount = verticals.filter((v) => !v.soon).length;
  const soonCount = verticals.length - liveCount;

  const filterGroups: FilterGroup[] = groups.map((group) => {
    const style = GROUP_STYLE[group.key];
    const stage = GROUP_STAGE[group.key];
    return {
      key: group.key,
      label: t(`agriHome.categories.groups.${GROUP_LABEL_KEY[group.key]}`),
      count:
        stage === undefined
          ? t("agriHome.categoriesPage.liveCount", { count: group.items.length })
          : t("agriHome.categoriesPage.stageCount", { count: group.items.length, stage }),
      dot: style.dot,
      tint: style.tint,
      items: group.items.map((vertical) => {
        const label = vertical.name[locale] ?? vertical.name["en"] ?? vertical.slug;
        // UX law 1 — EN + mother tongue on every tile, same rule as home §6.
        const vernacular =
          locale === "ta" ? (vertical.name["en"] ?? "") : (vertical.name["ta"] ?? "");
        return {
          slug: vertical.slug,
          icon: vertical.icon,
          label,
          vernacular,
          soon: vertical.soon,
          // EN+TA+HI names + slug: what the search box matches against.
          haystack: [vertical.slug, ...Object.values(vertical.name)]
            .join(" ")
            .toLowerCase(),
        };
      }),
    };
  });

  return (
    <main className="bg-cream pb-10">
      <Wrap>
        <nav className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
          <Link href="/" prefetch={false} className="tap-target text-brand no-underline">
            {t("agriHome.categoriesPage.crumbHome")}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{t("agriHome.categoriesPage.crumb")}</span>
        </nav>

        <div className="mt-2 flex flex-wrap items-start gap-3.5">
          <span
            aria-hidden="true"
            className="flex h-[54px] w-[54px] flex-none items-center justify-center rounded-icon bg-brand-soft text-[26px]"
          >
            🗂️
          </span>
          <div>
            <Eyebrow>{t("agriHome.categoriesPage.eyebrow", { count: verticals.length })}</Eyebrow>
            <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-semibold leading-[1.15]">
              {t("agriHome.categoriesPage.title")}
            </h1>
            {/* live/soon counts FROM the registry read, never literals. */}
            <p className="mt-[3px] text-[12.5px] text-sub">
              {t("agriHome.categoriesPage.sub", { live: liveCount, soon: soonCount })}
            </p>
          </div>
        </div>

        <CategoriesFilter
          groups={filterGroups}
          initialQuery={initialQuery}
          inputLabel={t("agriHome.categoriesPage.searchLabel")}
          placeholder={t("agriHome.categoriesPage.searchPlaceholder")}
          noMatches={t("agriHome.categoriesPage.noMatches")}
          soonLabel={t("agriHome.soon")}
        />

        <p className="mt-3 text-[11.5px] text-muted">
          <b className="font-semibold text-brand-deep">{t("agriHome.soon")}</b>{" "}
          {t("agriHome.categories.note")}
        </p>
      </Wrap>
    </main>
  );
}
