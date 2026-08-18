import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { fetchInstitutions, fetchStates } from "@/lib/education";

import { CollegeCard } from "../../college-card";

/**
 * Phase 2 — `/colleges/state/[state]`, ISR.
 *
 * These pages are the SEO surface `/colleges` delegates to: they are what rank
 * for "agriculture colleges in Tamil Nadu", which is the query the TN depth in
 * this corpus exists to answer.
 *
 * THE SLUG VOCABULARY COMES FROM THE API. `geo.states` has no slug column, so
 * something has to turn "Tamil Nadu" into a URL segment — and `citySlug()`
 * from @agri/ui, which web-milk uses for its city segments, is deliberately
 * NOT that thing here. It normalizes NFKD and strips diacritics where the
 * backend's `state_slug` does not; two implementations on opposite sides of an
 * HTTP boundary is how a link 404s against the page it points at. The API
 * publishes the vocabulary and this page consumes it.
 *
 * `/education/states` returns only states with at least one college, so
 * generateStaticParams cannot produce a thin empty page — 5 UTs have none.
 */
export const revalidate = 3600;

export async function generateStaticParams() {
  return (await fetchStates()).map((state) => ({ state: state.slug }));
}

async function resolve(slug: string) {
  return (await fetchStates()).find((state) => state.slug === slug);
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ state: string }>;
}): Promise<Metadata> {
  const [t, { state }] = await Promise.all([
    getTranslations("ui.colleges"),
    params,
  ]);
  const facet = await resolve(state);
  // An unknown segment 404s in the component below; the metadata for that
  // render must still be noindex, or a soft-404 gets indexed.
  if (!facet) {
    return buildMetadata({
      title: t("metaTitle"),
      canonical: canonicalUrl("https://agri.in", "/colleges"),
      siteName: "Agri.in",
      noIndex: true,
    });
  }

  return buildMetadata({
    title: t("stateMetaTitle", { state: facet.name }),
    description: t("stateMetaDescription", {
      state: facet.name,
      count: facet.institution_count,
    }),
    canonical: canonicalUrl("https://agri.in", `/colleges/state/${facet.slug}`),
    siteName: "Agri.in",
  });
}

export default async function StateCollegesPage({
  params,
}: {
  params: Promise<{ state: string }>;
}) {
  const [t, { state }] = await Promise.all([
    getTranslations("ui.colleges"),
    params,
  ]);

  const facet = await resolve(state);
  // An unknown segment is genuinely unknown, not a slugify disagreement --
  // which is exactly what makes this 404 safe rather than a guess.
  if (!facet) notFound();

  const page = await fetchInstitutions({ state: facet.slug, limit: 48 });

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
          <Link
            href="/colleges"
            prefetch={false}
            className="tap-target text-brand no-underline"
          >
            {t("crumb")}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{facet.name}</span>
        </nav>

        <Eyebrow className="mt-3">{t("eyebrow")}</Eyebrow>
        <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-extrabold text-ink">
          {t("stateTitle", { state: facet.name })}
        </h1>
        <p className="mt-1 max-w-[70ch] text-[13px] text-muted">
          {t("stateSub", { state: facet.name, count: facet.institution_count })}
        </p>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {page.items.map((college) => (
            <CollegeCard key={college.slug} college={college} labels={labels} />
          ))}
        </div>
      </Wrap>
    </main>
  );
}
