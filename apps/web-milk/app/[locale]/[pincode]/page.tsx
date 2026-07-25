import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Link } from "@/i18n/navigation";
import { CATEGORY_MESSAGE_KEY, isDairyCategory } from "@/lib/categories";
import { fetchCovers } from "@/lib/directory";
import { fetchMilkHome, milkTypeMeta, priceBannerText, type MilkHome } from "@/lib/milk";

import { CategoryChips } from "./category-chips";
import { CategoryResults } from "./category-results";
import { NotifyMe } from "./notify-me";
import { TypeFilterRow } from "./type-filter-row";
import { VendorResults } from "./vendor-results";

const SITE = "https://milk.in";
export const revalidate = 300;

const PIN_RE = /^\d{6}$/;

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; pincode: string }>;
  searchParams: Promise<{ category?: string }>;
}): Promise<Metadata> {
  const { locale, pincode } = await params;
  setRequestLocale(locale);
  if (!PIN_RE.test(pincode)) return { title: "Milk.in", robots: { index: false, follow: true } };
  const { category } = await searchParams;

  // Category query-param views (D27 Task 13) are thin duplicates of the
  // `/c/{category}` landing pages (Task 12), which own indexing for that
  // content — canonical stays `/{pincode}` (never `/{pincode}?category=`),
  // and the page always self-noindexes regardless of coverage/result count.
  if (category !== undefined && isDairyCategory(category)) {
    const t = await getTranslations({
      locale,
      namespace: `ui.dairyCategories.${CATEGORY_MESSAGE_KEY[category]}`,
    });
    return buildMetadata({
      title: `${t("name")} in ${pincode} — Milk.in`,
      description: t("description"),
      canonical: canonicalUrl(SITE, `/${pincode}`),
      siteName: "Milk.in",
      noIndex: true,
    });
  }

  const data = await fetchMilkHome(pincode);
  const place = data?.location ? `${data.location.district} (${pincode})` : pincode;
  const covered = data?.scope === "covered";
  return buildMetadata({
    title: `Milk in ${place} — Milk.in`,
    description: `Cow, buffalo, A2 & organic milk vendors and brands near ${place}.`,
    canonical: canonicalUrl(SITE, `/${pincode}`),
    siteName: "Milk.in",
    // Thin/empty pincode pages self-noindex until they have real listings.
    noIndex: !covered,
  });
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
  params: Promise<{ locale: string; pincode: string }>;
  searchParams: Promise<{ type?: string; category?: string }>;
}) {
  const { locale, pincode } = await params;
  setRequestLocale(locale);
  if (!PIN_RE.test(pincode)) notFound();
  const { type = "all", category } = await searchParams;

  // ---- Category browse (D27 Task 13) ----
  // An unrecognized `?category=` value is treated as absent, not an error —
  // falls straight through to the normal milk view below. Deliberately does
  // NOT reuse `fetchMilkHome`'s 3-way scope machinery (covered /
  // tn_no_vendors / out_of_area): `/directory/covers` has no such concept,
  // it just returns items or an empty page, so the category view only ever
  // has two states, items or empty (handled inside `CategoryResults`).
  if (category !== undefined && isDairyCategory(category)) {
    const covers = await fetchCovers(pincode, category);
    const t = await getTranslations("ui");
    const categoryLabel = t(`dairyCategories.${CATEGORY_MESSAGE_KEY[category]}.name`);
    return (
      <main
        className="mx-auto flex w-full max-w-[720px] flex-col gap-5 px-4 py-6"
        data-testid="scope-category"
      >
        <h1 className="font-display text-[22px] font-extrabold text-ink">
          {t("categoryBrowse.heading", { category: categoryLabel, place: pincode })}
        </h1>
        <CategoryChips pincode={pincode} active={category} />
        <CategoryResults items={covers?.items ?? []} categoryLabel={categoryLabel} pincode={pincode} />
      </main>
    );
  }

  const data = await fetchMilkHome(pincode, type);
  if (!data) notFound(); // backend unreachable / non-ok — genuine error, not a warm state

  // ---- Warm empty states (features, never error screens) ----
  if (data.scope === "out_of_area") {
    return (
      <main
        className="mx-auto flex w-full max-w-[720px] flex-col gap-3 px-4 py-8"
        data-testid="scope-out-of-area"
      >
        <h1 className="font-display text-[22px] font-extrabold text-ink">
          We&apos;re live in Tamil Nadu right now
        </h1>
        <p className="text-[15px] text-sub">
          {pincode} isn&apos;t in our coverage yet — more areas coming soon. Leave your number and
          we&apos;ll reach out the moment milk vendors arrive.
        </p>
        <NotifyMe pincode={pincode} />
      </main>
    );
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
          No milk vendors in {place} yet
        </h1>
        <p className="text-[15px] text-sub">
          Be the first to know when a dairy lists here.
        </p>
        <NotifyMe pincode={pincode} {...(district ? { district } : {})} />
        {/* D24 will wire a real "list your dairy" onboarding flow — this is a
            warm pointer only, no live link yet. */}
        <p className="text-[13px] text-sub">
          Run a dairy here?{" "}
          <span className="font-bold text-brand-deep">List your dairy on Milk.in</span> — coming
          soon.
        </p>
      </main>
    );
  }

  // ---- Covered ----
  const filteredEmpty = data.vendors.length === 0 && data.brands.length === 0;
  return (
    <main
      className="mx-auto flex w-full max-w-[720px] flex-col gap-5 px-4 py-6"
      data-testid="scope-covered"
    >
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: itemListJsonLd(pincode, data) }}
      />
      <h1 className="font-display text-[22px] font-extrabold text-ink">
        Milk in {data.location?.district ?? pincode}
      </h1>
      <TypeFilterRow pincode={pincode} filters={data.filters} active={type} />
      <CategoryChips pincode={pincode} active={null} />

      {data.price_banner ? (
        <div
          className="rounded-card border border-dashed border-line bg-brand-soft px-3 py-2 text-[13px] text-ink"
          data-testid="price-banner"
        >
          <b>Today in {pincode}:</b> {priceBannerText(data.price_banner)}
        </div>
      ) : null}

      <Link
        href="/post-need"
        prefetch={false}
        className="rounded-card border border-line bg-card px-3 py-3 text-[13px] font-bold text-ink no-underline"
        data-testid="post-need-cta"
      >
        🥛 Post my need — vendors here reply to you{" "}
        <span className="vern font-normal text-sub">· என் தேவை</span>
      </Link>

      {filteredEmpty ? (
        <p className="text-[14px] text-sub" data-testid="filtered-empty">
          No {type === "all" ? "" : `${milkTypeMeta(type).en.toLowerCase()} `}milk listed here
          yet —{" "}
          <Link className="font-bold text-brand-deep" href={`/${pincode}`}>
            see all
          </Link>
          .
        </p>
      ) : (
        <VendorResults vendors={data.vendors} brands={data.brands} pincode={pincode} />
      )}
    </main>
  );
}
