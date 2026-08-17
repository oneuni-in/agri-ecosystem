import { Badge, Eyebrow, LOC_COOKIE, RatingStars, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { cookies } from "next/headers";
import Link from "next/link";

import { pick } from "@/lib/content";
import {
  distanceLabel,
  fetchActiveCategories,
  fetchCoverage,
  type CoverageItem,
} from "@/lib/directory";
import { fetchReviewSignals, resolveHomePincode } from "@/lib/home";

/**
 * A-U3 W3 — `/directory`, the hub. Closes AG-A6.
 *
 * Browse agri businesses by category × pincode using the EXISTING E1
 * coverage read — no new directory engine (build prompt §W3). The home's
 * §10 row is the same read with a smaller limit, which is deliberate:
 * one engine, one notion of "covers this pincode", one distance rule.
 *
 * SPONSORED PINS. There are none, and their absence is the feature. Milk
 * injects sponsored listings into a list through its M3.B slot; no agri
 * sponsored-listing slot is registered, so there is nothing to inject and
 * this page renders organic-only. When a slot and a real campaign exist,
 * the injection point is `injectSponsored` from @agri/ui and every
 * injected card carries the "Sponsored" label — until then, a labelled
 * placeholder would be advertising inventory that does not exist.
 *
 * Category chips come from `/directory/categories/active`, so a chip can
 * never lead to an empty list: an active category has businesses by
 * definition.
 */
export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ui.directoryPage");
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    canonical: canonicalUrl("https://agri.in", "/directory"),
    siteName: "Agri.in",
  });
}

export default async function DirectoryPage({
  searchParams,
}: {
  searchParams: Promise<{ category?: string; pin?: string }>;
}) {
  const [t, locale, params, cookieStore] = await Promise.all([
    getTranslations("ui.directoryPage"),
    getLocale(),
    searchParams,
    cookies(),
  ]);

  // ?pin= wins over the cookie so a shared link shows the sender's area,
  // but it is validated first — an unvalidated pincode goes straight into
  // an API path.
  const fromQuery = /^\d{6}$/.test(params.pin ?? "") ? params.pin : undefined;
  const pincode =
    fromQuery ?? resolveHomePincode(cookieStore.get(LOC_COOKIE)?.value);
  const category = /^[a-z0-9-]{1,40}$/.test(params.category ?? "")
    ? params.category
    : undefined;

  const [categories, coverage] = await Promise.all([
    fetchActiveCategories(),
    fetchCoverage({ pincode, ...(category ? { category } : {}), limit: 24 }),
  ]);
  // Ratings for the visible page only — the same D18 signals seam the
  // home row uses (the engine serves approved reviews only).
  const { ratings } = await fetchReviewSignals(
    coverage.items as CoverageItem[],
    0,
  );

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
          {t("title", { pincode })}
        </h1>
        <p className="mt-1 max-w-[70ch] text-[13px] text-muted">{t("sub")}</p>

        {/* Server-rendered filter links, like /knowledge: no island, works
            with JS off, crawlable, and the URL is the state. */}
        <div
          className="mt-4 flex flex-wrap gap-2"
          role="navigation"
          aria-label={t("filterLabel")}
        >
          <Link
            href="/directory"
            prefetch={false}
            aria-current={category ? undefined : "page"}
            className={`tap-target inline-flex items-center rounded-pill border px-3.5 text-[12.5px] font-semibold no-underline ${
              category
                ? "border-cream-line bg-card text-ink"
                : "border-brand bg-brand text-white"
            }`}
          >
            {t("all")}
          </Link>
          {categories.map((entry) => (
            <Link
              key={entry.slug}
              href={`/directory?category=${entry.slug}`}
              prefetch={false}
              aria-current={category === entry.slug ? "page" : undefined}
              className={`tap-target inline-flex items-center gap-1.5 rounded-pill border px-3.5 text-[12.5px] font-semibold no-underline ${
                category === entry.slug
                  ? "border-brand bg-brand text-white"
                  : "border-cream-line bg-card text-ink"
              }`}
            >
              {pick(locale, entry.name)}
              {/* The count is from data — the chip cannot claim a number
                  the list will not deliver. */}
              <span className="opacity-70">{entry.business_count}</span>
            </Link>
          ))}
        </div>

        {coverage.items.length === 0 ? (
          <p className="mt-5 rounded-card border border-cream-line bg-card p-5 text-[13px] text-muted">
            {t("empty", { pincode })}
          </p>
        ) : (
          <ul className="mt-5 grid list-none gap-2.5 p-0 md:grid-cols-2 lg:grid-cols-3">
            {coverage.items.map((item) => {
              const km = distanceLabel(item.distance_m);
              const rating = ratings[item.id];
              return (
                <li key={item.id}>
                  <Link
                    href={`/directory/businesses/${item.slug}?pin=${pincode}`}
                    prefetch={false}
                    data-testid={`hub-directory-${item.slug}`}
                    className="flex h-full flex-col gap-1.5 rounded-card border border-cream-line bg-card p-4 no-underline transition-shadow hover:shadow-lift"
                  >
                    {item.verification_status === "verified" ? (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant="verified">{t("verified")}</Badge>
                      </div>
                    ) : null}
                    <h2 className="text-[15px] font-extrabold leading-[1.3] text-ink">
                      {item.name}
                    </h2>
                    <p className="flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
                      {rating?.rating_avg ? (
                        <>
                          <RatingStars value={rating.rating_avg} />
                          <span>({rating.rating_count})</span>
                          {km ? <span aria-hidden="true">·</span> : null}
                        </>
                      ) : null}
                      {km ? <span>{km}</span> : null}
                    </p>
                    {/* Contact is NOT here. Numbers never travel in list
                        payloads — the profile page runs D18's capped,
                        fail-closed reveal flow. */}
                    <span className="mt-auto pt-1 text-[12px] font-semibold text-brand-deep">
                      {t("viewProfile")} →
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Wrap>
    </main>
  );
}
