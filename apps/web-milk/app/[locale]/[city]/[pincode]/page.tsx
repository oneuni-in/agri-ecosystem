import { Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl, citySlug } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound, permanentRedirect } from "next/navigation";

import { ListBusinessCta } from "@/components/molecules/ListBusinessCta";
import { MilkTypeChips } from "@/components/organisms/MilkTypeChips";
import { PriceTicker } from "@/components/organisms/PriceTicker";
import { Link } from "@/i18n/navigation";
import { fetchSponsoredListings } from "@/lib/ads";
import { CATEGORY_MESSAGE_KEY, isDairyCategory } from "@/lib/categories";
import { fetchCovers } from "@/lib/directory";
import { fetchReviewSignals } from "@/lib/home";
import { fetchMilkHome, milkTypeMeta, priceBannerText, type MilkHome } from "@/lib/milk";
import { fetchMilkTypes } from "@/lib/taxonomy";

import { CategoryChips } from "./category-chips";
import { CategoryResults } from "./category-results";
import { LastSeenWriter } from "./last-seen-writer";
import { NotifyMe } from "./notify-me";
import { OutOfArea } from "./out-of-area";
import { RecommendedRail } from "./recommended-rail";
import { VendorResults } from "./vendor-results";

const SITE = "https://milk.in";
export const revalidate = 300;

const PIN_RE = /^\d{6}$/;

type Params = Promise<{ locale: string; city: string; pincode: string }>;

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<{ category?: string; product_category?: string }>;
}): Promise<Metadata> {
  const { locale, city, pincode } = await params;
  setRequestLocale(locale);
  if (!PIN_RE.test(pincode)) return { title: "Milk.in", robots: { index: false, follow: true } };
  const { category, product_category } = await searchParams;

  const data = await fetchMilkHome(pincode);
  // Canonical always carries the CORRECT city slug (the page 301s wrong-city
  // URLs, but metadata must never advertise the mistyped variant).
  const canonicalCity = data?.location ? citySlug(data.location.district) : city;
  const path = `/${canonicalCity}/${pincode}`;

  // Category query-param views (D27 Task 13) are thin duplicates of the
  // `/c/{category}` landing pages, which own indexing for that content —
  // canonical stays the plain landing URL and the view self-noindexes.
  if (category !== undefined && isDairyCategory(category)) {
    const t = await getTranslations({
      locale,
      namespace: `ui.dairyCategories.${CATEGORY_MESSAGE_KEY[category]}`,
    });
    return buildMetadata({
      title: `${t("name")} in ${pincode} — Milk.in`,
      description: t("description"),
      canonical: canonicalUrl(SITE, path),
      siteName: "Milk.in",
      noIndex: true,
    });
  }

  const place = data?.location ? `${data.location.district} (${pincode})` : pincode;
  const covered = data?.scope === "covered";
  // `?product_category=` views (Task 10) are thin filtered duplicates of this
  // page, same treatment as `?category=` above — canonical stays the bare
  // `/{city}/{pincode}` and the view self-noindexes.
  const isProductCategoryFiltered =
    product_category !== undefined && product_category !== "all";
  return {
    ...buildMetadata({
      title: `Milk in ${place} — Milk.in`,
      description: `Cow, buffalo, A2 & organic milk vendors and brands near ${place}.`,
      canonical: canonicalUrl(SITE, path),
      siteName: "Milk.in",
      // Thin/empty pincode pages self-noindex until they have real listings.
      noIndex: !covered || isProductCategoryFiltered,
    }),
    // hreflang: default-locale URL is canonical; ta/hi are prefixed (D27
    // pattern — metadata is the single hreflang source, alternateLinks off).
    alternates: {
      canonical: canonicalUrl(SITE, path),
      languages: {
        en: `${SITE}${path}`,
        ta: `${SITE}/ta${path}`,
        hi: `${SITE}/hi${path}`,
        "x-default": `${SITE}${path}`,
      },
    },
  };
}

/** ItemList of LocalBusiness — hand-built (no itemList builder in @agri/ui/seo,
 * see apps/web-agri/app/directory/businesses/[slug]/page.tsx for the
 * hand-built-JSON-LD precedent this follows). `<` escaped so listing content
 * can never close the script tag. */
function itemListJsonLd(pincode: string, data: MilkHome): string {
  const cards = [...data.vendors, ...data.brands];
  const graph = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: `Milk vendors in ${data.location?.district ?? pincode}`,
    itemListElement: cards.map((c, i) => ({
      "@type": "ListItem",
      position: i + 1,
      item: {
        "@type": "LocalBusiness",
        name: c.name,
        url: canonicalUrl(SITE, `/directory/businesses/${c.slug}`),
        ...(data.location
          ? {
              address: {
                "@type": "PostalAddress",
                addressLocality: data.location.district,
                addressRegion: data.location.state ?? "Tamil Nadu",
                postalCode: pincode,
                addressCountry: "IN",
              },
            }
          : {}),
      },
    })),
  };
  return JSON.stringify(graph).replaceAll("<", "\\u003c");
}

export default async function PincodePage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: Promise<{ type?: string; category?: string; product_category?: string }>;
}) {
  const { locale, city, pincode } = await params;
  setRequestLocale(locale);
  if (!PIN_RE.test(pincode)) notFound();
  const { type = "all", category, product_category } = await searchParams;
  const base = `/${city}/${pincode}`;

  // ---- Category browse (D27 Task 13) ----
  // An unrecognized `?category=` value is treated as absent, not an error —
  // falls straight through to the normal milk view below. Deliberately does
  // NOT reuse `fetchMilkHome`'s 3-way scope machinery (covered /
  // tn_no_vendors / out_of_area): `/directory/covers` has no such concept,
  // it just returns items or an empty page, so the category view only ever
  // has two states, items or empty (handled inside `CategoryResults`) — but
  // a `fetchCovers` null (backend unreachable / non-ok) is a genuine error,
  // not a warm empty state, same distinction `fetchMilkHome`'s `!data` check
  // makes below for the milk view.
  if (category !== undefined && isDairyCategory(category)) {
    const covers = await fetchCovers(pincode, category);
    if (!covers) notFound();
    // M3.B render-layer injection: sponsored cards never touch covers.items
    // or its cursor - CategoryResults splices them into the RENDERED grid.
    const sponsored = await fetchSponsoredListings({ pincode, category, locale });
    const t = await getTranslations("ui");
    const categoryLabel = t(`dairyCategories.${CATEGORY_MESSAGE_KEY[category]}.name`);
    return (
      <main className="bg-cream" data-testid="scope-category">
        <Wrap className="flex flex-col gap-5 py-6">
          <h1 className="font-display text-[22px] font-extrabold text-ink">
            {t("categoryBrowse.heading", { category: categoryLabel, place: pincode })}
          </h1>
          <CategoryChips base={base} active={category} />
          <CategoryResults
            items={covers.items}
            categoryLabel={categoryLabel}
            base={base}
            sponsored={sponsored}
          />
        </Wrap>
      </main>
    );
  }

  const data = await fetchMilkHome(pincode, type, product_category);
  if (!data) notFound(); // backend unreachable / non-ok — genuine error, not a warm state

  // Wrong (or stale) city slug → 301 to the canonical URL, preserving the
  // filter query — duplicate-content defence for the indexed landing pages.
  if (data.location) {
    const canonicalCity = citySlug(data.location.district);
    if (canonicalCity && city !== canonicalCity) {
      const qs = new URLSearchParams();
      if (type !== "all") qs.set("type", type);
      if (category !== undefined) qs.set("category", category);
      if (product_category !== undefined) qs.set("product_category", product_category);
      const suffix = qs.size > 0 ? `?${qs.toString()}` : "";
      permanentRedirect(`/${canonicalCity}/${pincode}${suffix}`);
    }
  }

  const t = await getTranslations("ui.results");

  // ---- Warm empty states (features, never error screens) ----
  if (data.scope === "out_of_area") {
    return <OutOfArea pincode={pincode} />;
  }
  if (data.scope === "tn_no_vendors") {
    const district = data.location?.district;
    const place = district ? `${district} (${pincode})` : pincode;
    return (
      <main
        className="mx-auto flex w-full max-w-[720px] flex-col gap-3 px-4 py-8"
        data-testid="scope-tn-no-vendors"
      >
        <h1 className="font-display text-[22px] font-extrabold text-ink">
          {t("noVendorsTitle", { place })}
        </h1>
        <p className="text-[15px] text-sub">{t("noVendorsBody")}</p>
        <NotifyMe pincode={pincode} {...(district ? { district } : {})} />
        <ListBusinessCta />
      </main>
    );
  }

  // ---- Covered ----
  const filteredEmpty = data.vendors.length === 0 && data.brands.length === 0;
  // The SAME shared paths the home vendor grid renders from (U1b Group A):
  // localised D17 type labels, D18 review summaries for every card on the
  // page, and M3.B sponsored listings fetched server-side and injected at
  // the render layer only - data.vendors/data.brands (and the JSON-LD built
  // from them) stay pristine.
  const [milkTypes, { ratings }, sponsored] = await Promise.all([
    fetchMilkTypes(locale),
    fetchReviewSignals([...data.vendors, ...data.brands, ...data.recommended]),
    filteredEmpty
      ? Promise.resolve([])
      : fetchSponsoredListings({
          pincode,
          category: product_category && product_category !== "all" ? product_category : null,
          locale,
        }),
  ]);
  const typeLabels = Object.fromEntries(milkTypes.map((m) => [m.value, m.label]));

  return (
    <main className="bg-cream" data-testid="scope-covered">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: itemListJsonLd(pincode, data) }}
      />
      <Wrap className="flex flex-col gap-5 py-6">
        <h1 className="font-display text-[22px] font-extrabold text-ink">
          {t("title", { place: data.location?.district ?? pincode })}
        </h1>
        <div className="flex flex-col gap-1.5">
          <MilkTypeChips
            filters={data.filters}
            milkTypes={milkTypes}
            base={base}
            active={type}
            testId="type-filter-row"
          />
          <CategoryChips base={base} active={null} />
        </div>

        {data.price_banner ? (
          <>
            <PriceTicker home={data} milkTypes={milkTypes} />
            <LastSeenWriter
              pincode={pincode}
              district={data.location?.district ?? null}
              banner={priceBannerText(data.price_banner)}
            />
          </>
        ) : null}

        <Link
          href="/post-need"
          prefetch={false}
          className="rounded-card border border-cream-line bg-card px-3 py-3 text-[13px] font-bold text-ink no-underline"
          data-testid="post-need-cta"
        >
          {t("postNeed")}
          {locale === "en" ? (
            // The reference's designed Tamil accent — /en only; ta/hi carry
            // the fully translated line above instead.
            <span className="vern font-normal text-sub"> · என் தேவை</span>
          ) : null}
        </Link>

        {!filteredEmpty ? (
          <RecommendedRail
            cards={data.recommended}
            pincode={pincode}
            ratings={ratings}
            typeLabels={typeLabels}
          />
        ) : null}

        {filteredEmpty ? (
          <p className="text-[14px] text-sub" data-testid="filtered-empty">
            {type === "all"
              ? t("filteredEmptyAll")
              : t("filteredEmpty", {
                  type: typeLabels[type] ?? milkTypeMeta(type).en.toLowerCase(),
                })}{" "}
            <Link className="font-bold text-brand-deep" href={base}>
              {t("seeAll")}
            </Link>
            .
          </p>
        ) : (
          <VendorResults
            vendors={data.vendors}
            brands={data.brands}
            pincode={pincode}
            sponsored={sponsored}
            ratings={ratings}
            typeLabels={typeLabels}
          />
        )}
      </Wrap>
    </main>
  );
}
