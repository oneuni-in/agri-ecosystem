import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { fetchInstitutions, fetchStates } from "@/lib/education";

import { CollegeCard } from "./college-card";
import { CollegeFilters } from "./filters";

/**
 * Phase 2 — `/colleges`, the agri-colleges hub.
 *
 * FILTERING IS SERVER-SIDE, breaking the `/categories` precedent on purpose.
 * That page serializes its whole registry to the client and filters there,
 * which is right for 36 rows and wrong for 772. The SEO a client-side grid
 * would have earned is recovered by the ISR state pages below, which are what
 * rank for "agriculture colleges in Tamil Nadu" — the query the Tamil Nadu
 * depth in this corpus exists to answer.
 *
 * The filters are server-rendered LINKS, following `/directory`: no island, no
 * JS, crawlable, and the URL is the state. `/colleges` carries the 0.90
 * throttled-3G floor with no carve-out, and an island is what spends it.
 *
 * An empty result renders an empty state with the filters still visible — NOT
 * notFound(). Unlike `/schemes`, an empty result here is almost always a
 * too-narrow filter rather than an absent dataset, and 404-ing on a filter
 * combination is hostile.
 */
export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ui.colleges");
  return buildMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    canonical: canonicalUrl("https://agri.in", "/colleges"),
    siteName: "Agri.in",
  });
}

export default async function CollegesPage({
  searchParams,
}: {
  searchParams: Promise<{ gov?: string; trust?: string; q?: string }>;
}) {
  const [t, params] = await Promise.all([
    getTranslations("ui.colleges"),
    searchParams,
  ]);

  // Every filter is validated before it reaches a query string. An
  // unvalidated value goes straight into an API path, and the API's own 422
  // would surface here as an empty list rather than as the mistake it is.
  const gov = params.gov === "true" || params.gov === "false" ? params.gov : undefined;
  const trust = params.trust === "verified" ? "verified" : undefined;
  const q = (params.q ?? "").trim().slice(0, 64) || undefined;

  const [page, states] = await Promise.all([
    fetchInstitutions({
      ...(gov ? { is_government: gov === "true" } : {}),
      ...(trust ? { trust } : {}),
      ...(q ? { q } : {}),
      limit: 24,
    }),
    fetchStates(),
  ]);

  const labels = {
    verified: t("verified"),
    listed: t("listed"),
    government: t("government"),
    private: t("private"),
    established: t("established"),
    kinds: {
      central_agri_university: t("kinds.central_agri_university"),
      state_agri_university: t("kinds.state_agri_university"),
      deemed_university: t("kinds.deemed_university"),
      icar_institute: t("kinds.icar_institute"),
      private_university: t("kinds.private_university"),
      affiliated_college: t("kinds.affiliated_college"),
      constituent_college: t("kinds.constituent_college"),
    },
  };

  return (
    <main className="bg-cream pb-10">
      <Wrap>
        <nav className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
          <Link href="/" prefetch={false} className="tap-target text-brand no-underline">
            {t("crumbHome")}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{t("crumb")}</span>
        </nav>

        <Eyebrow className="mt-3">{t("eyebrow")}</Eyebrow>
        <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-extrabold text-ink">
          {t("title")}
        </h1>
        <p className="mt-1 max-w-[70ch] text-[13px] text-muted">{t("sub")}</p>

        <CollegeFilters
          base="/colleges"
          current={{ gov, trust, q }}
          labels={{
            filterLabel: t("filterLabel"),
            all: t("all"),
            government: t("government"),
            private: t("private"),
            verifiedOnly: t("verifiedOnly"),
            searchLabel: t("searchLabel"),
            searchPlaceholder: t("searchPlaceholder"),
            searchSubmit: t("searchSubmit"),
          }}
        />

        {page.items.length === 0 ? (
          <div className="mt-6 rounded-card border border-cream-line bg-card p-5">
            <p className="text-[13.5px] font-semibold text-ink">{t("emptyTitle")}</p>
            <p className="mt-1 text-[12.5px] text-muted">{t("emptyBody")}</p>
            <Link
              href="/colleges"
              prefetch={false}
              className="tap-target mt-3 inline-flex items-center rounded-pill border border-brand bg-brand px-4 text-[12.5px] font-semibold text-white no-underline"
            >
              {t("clearFilters")}
            </Link>
          </div>
        ) : (
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {page.items.map((college) => (
              <CollegeCard key={college.slug} college={college} labels={labels} />
            ))}
          </div>
        )}

        {/* The state pages are the SEO surface this page delegates to. Only
            states with at least one college are published, so a link here can
            never lead to an empty page. */}
        {states.length > 0 ? (
          <section className="mt-8">
            <h2 className="font-display text-[17px] font-extrabold text-ink">
              {t("byStateTitle")}
            </h2>
            <p className="mt-1 text-[12.5px] text-muted">{t("byStateSub")}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {states.map((state) => (
                <Link
                  key={state.slug}
                  href={`/colleges/state/${state.slug}`}
                  prefetch={false}
                  className="tap-target inline-flex items-center gap-1.5 rounded-pill border border-cream-line bg-card px-3.5 text-[12.5px] font-semibold text-ink no-underline"
                >
                  {state.name}
                  <span className="text-[11px] font-normal text-muted">
                    {state.institution_count}
                  </span>
                </Link>
              ))}
            </div>
          </section>
        ) : null}
      </Wrap>
    </main>
  );
}
