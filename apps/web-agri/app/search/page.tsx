import { Badge, Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import { LOC_COOKIE } from "@agri/ui";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { cookies } from "next/headers";
import Link from "next/link";

import { pick } from "@/lib/content";
import { searchAgri, type SearchHit } from "@/lib/directory";
import { resolveHomePincode } from "@/lib/home";

/**
 * A-U3 W3 — `/search`, the home band's real destination. Closes AG-A5.
 *
 * A-U1 pointed the band at `/categories` and said so out loud, because
 * "web-agri has NO /search route" was true at the time and inventing a
 * results page would have been worse than the redirect. This is that
 * page, and the band now posts here.
 *
 * NO new search engine (build prompt §W3). This renders the existing D19
 * `/search` facade, with `site=agri` pinned server-side so a crafted URL
 * cannot show another vertical's index under agri.in's chrome.
 *
 * `noindex`: a results page is a query, not a document. Letting Google
 * index arbitrary `?q=` URLs is how a site accumulates thousands of thin
 * pages that compete with the real ones.
 */
export const dynamic = "force-dynamic";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}): Promise<Metadata> {
  const t = await getTranslations("ui.searchPage");
  const q = (await searchParams).q?.trim();
  return buildMetadata({
    title: q ? t("metaTitleQuery", { q }) : t("metaTitle"),
    canonical: canonicalUrl("https://agri.in", "/search"),
    siteName: "Agri.in",
    noIndex: true,
  });
}

function hitHref(hit: SearchHit): string {
  // A product's own page is its business's page — products have no
  // standalone route on agri.in yet, and linking to one that 404s would
  // be worse than landing the reader one level up.
  return hit.kind === "product" && hit.business_slug
    ? `/directory/businesses/${hit.business_slug}`
    : `/directory/businesses/${hit.slug}`;
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; kind?: string }>;
}) {
  const [t, locale, params, cookieStore] = await Promise.all([
    getTranslations("ui.searchPage"),
    getLocale(),
    searchParams,
    cookies(),
  ]);
  const q = (params.q ?? "").trim();
  // The SAME location the header pill and the home row use, so a result
  // set matches the pincode the chip is showing (AG-A5's second half).
  const pincode = resolveHomePincode(cookieStore.get(LOC_COOKIE)?.value);
  const kind =
    params.kind === "business" || params.kind === "product"
      ? params.kind
      : undefined;

  const page = q
    ? await searchAgri({ q, pincode, ...(kind ? { kind } : {}), limit: 24 })
    : { items: [], next_cursor: null };

  return (
    <main className="bg-cream pb-10">
      <Wrap>
        <nav className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
          <Link
            href="/"
            prefetch={false}
            className="tap-target text-brand no-underline"
          >
            {t("crumbHome")}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{t("crumb")}</span>
        </nav>

        <Eyebrow className="mt-3">{t("eyebrow")}</Eyebrow>
        <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-extrabold text-ink">
          {q ? t("titleQuery", { q }) : t("title")}
        </h1>

        {/* Re-search from the results page. Same GET form as the home
            band, so back/forward and bookmarking all behave. */}
        <form
          action="/search"
          method="get"
          className="mt-3 flex max-w-[620px] gap-2"
        >
          <label htmlFor="q" className="sr-only">
            {t("inputLabel")}
          </label>
          <input
            id="q"
            name="q"
            type="search"
            defaultValue={q}
            placeholder={t("placeholder")}
            className="min-h-[44px] min-w-0 flex-1 rounded-btn border border-cream-line bg-card px-3.5 text-[15px] text-ink"
          />
          <button
            type="submit"
            className="min-h-[44px] rounded-btn bg-brand px-5 text-sm font-semibold text-white"
          >
            {t("cta")}
          </button>
        </form>

        <p className="mt-2 text-[12px] text-muted">
          {q
            ? t("resultCount", { count: page.items.length, pincode })
            : t("promptForQuery")}
        </p>

        {q && page.items.length === 0 ? (
          // An honest zero. No "did you mean", no padding with unrelated
          // rows — a search that found nothing says so.
          <p className="mt-5 rounded-card border border-cream-line bg-card p-5 text-[13px] text-muted">
            {t("noResults", { q })}
          </p>
        ) : null}

        {page.items.length > 0 ? (
          <ul className="mt-4 grid list-none gap-2.5 p-0 md:grid-cols-2 lg:grid-cols-3">
            {page.items.map((hit) => (
              <li key={hit.id}>
                <Link
                  href={hitHref(hit)}
                  prefetch={false}
                  className="flex h-full flex-col gap-1.5 rounded-card border border-cream-line bg-card p-4 no-underline transition-shadow hover:shadow-lift"
                >
                  <div className="flex flex-wrap items-center gap-1.5">
                    {hit.verified ? (
                      <Badge variant="verified">{t("verified")}</Badge>
                    ) : null}
                    <span className="rounded-pill bg-brand-soft px-2 py-0.5 text-[10px] font-semibold text-brand-deep">
                      {t(`kinds.${hit.kind}`)}
                    </span>
                  </div>
                  <h2 className="text-[15px] font-extrabold leading-[1.3] text-ink">
                    {hit.name}
                  </h2>
                  {hit.business_name ? (
                    <p className="text-[12px] text-muted">
                      {hit.business_name}
                    </p>
                  ) : null}
                  {hit.description ? (
                    <p className="line-clamp-2 text-[12.5px] leading-[1.5] text-muted">
                      {pick(locale, hit.description)}
                    </p>
                  ) : null}
                  <p className="mt-auto flex flex-wrap items-center gap-1.5 pt-1 text-[11.5px] text-muted">
                    {hit.district ? <span>{hit.district}</span> : null}
                    {hit.price_display ? (
                      <>
                        <span aria-hidden="true">·</span>
                        <span className="font-semibold text-ink">
                          {hit.price_display}
                        </span>
                      </>
                    ) : null}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        ) : null}

        {/* No sponsored slot on this page. Milk injects sponsored results
            into its list via M3.B, but no agri sponsored-results slot is
            registered, so nothing is injected — the honesty rule, same as
            the home's §10 row. */}
      </Wrap>
    </main>
  );
}
