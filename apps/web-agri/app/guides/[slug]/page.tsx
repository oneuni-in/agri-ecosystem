import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { fetchGuide, fetchGuides } from "@/lib/education";

/**
 * Phase 2 — `/guides/[slug]`, the canonical detail for every guide kind.
 *
 * One detail route for counselling, study-abroad and general guides; the two
 * index pages link into it. `generateStaticParams` reads `fetchGuides()`,
 * which returns published guides only, so a draft can never be pre-rendered —
 * and the API 404s a draft identically to a slug that was never used, so
 * `null` is the only missing case this page has to handle.
 *
 * `steps` render in order, because the order IS the guide: counselling rounds
 * happen in sequence and a shuffled list is actively misleading.
 */
export const revalidate = 3600;

export async function generateStaticParams() {
  return (await fetchGuides()).map((guide) => ({ slug: guide.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const [t, { slug }] = await Promise.all([getTranslations("ui.colleges"), params]);
  const guide = await fetchGuide(slug);

  if (guide === null || guide === "unavailable") {
    return buildMetadata({
      title: t("counsellingMetaTitle"),
      canonical: canonicalUrl("https://agri.in", "/counselling"),
      siteName: "Agri.in",
      noIndex: true,
    });
  }

  return buildMetadata({
    title: guide.title.en ?? slug,
    description: guide.summary.en ?? t("counsellingMetaDescription"),
    canonical: canonicalUrl("https://agri.in", `/guides/${guide.slug}`),
    siteName: "Agri.in",
  });
}

export default async function GuidePage({ params }: { params: Promise<{ slug: string }> }) {
  const [t, { slug }] = await Promise.all([getTranslations("ui.colleges"), params]);
  const guide = await fetchGuide(slug);

  if (guide === "unavailable") {
    return (
      <main className="bg-cream pb-10">
        <Wrap>
          <div className="mt-8 rounded-card border border-cream-line bg-card p-5">
            <p className="text-[13.5px] font-semibold text-ink">{t("unavailableTitle")}</p>
            <p className="mt-1 text-[12.5px] text-muted">{t("unavailableBody")}</p>
          </div>
        </Wrap>
      </main>
    );
  }
  if (guide === null) notFound();

  const backHref = guide.kind === "foreign_study" ? "/study-abroad" : "/counselling";
  const backLabel =
    guide.kind === "foreign_study" ? t("studyAbroadCrumb") : t("counsellingCrumb");

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
          <Link href={backHref} prefetch={false} className="tap-target text-brand no-underline">
            {backLabel}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{guide.title.en ?? guide.slug}</span>
        </nav>

        <Eyebrow className="mt-3">{t("eyebrow")}</Eyebrow>
        <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-extrabold text-ink">
          {guide.title.en ?? guide.slug}
        </h1>

        {guide.summary.en ? (
          <p className="mt-2 max-w-[70ch] text-[13px] leading-[1.6] text-ink">
            {guide.summary.en}
          </p>
        ) : null}

        {/* Prominent, not a footnote. Counselling dates going stale and
            misleading is a named risk in spec §12, and this is its mitigation:
            a reader can see how old the guide is before acting on it. */}
        <p className="mt-3 text-[12px] text-muted">
          {t("checkedOn")} {guide.last_verified_at}
        </p>

        {guide.steps.length > 0 ? (
          <ol className="mt-6 grid gap-3">
            {guide.steps.map((step, index) => (
              <li
                key={step.title ?? index}
                className="rounded-card border border-cream-line bg-card p-4"
              >
                <h2 className="text-[14.5px] font-extrabold text-ink">
                  <span className="text-muted">{index + 1}. </span>
                  {step.title}
                </h2>
                {step.body ? (
                  <p className="mt-1.5 text-[13px] leading-[1.6] text-ink">{step.body}</p>
                ) : null}
                {step.links && step.links.length > 0 ? (
                  <ul className="mt-2 grid gap-1">
                    {step.links.map((link) => (
                      <li key={link}>
                        <a
                          href={link}
                          rel="nofollow noopener"
                          className="text-[12.5px] text-brand no-underline"
                        >
                          {new URL(link).hostname.replace(/^www\./, "")}
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ol>
        ) : null}

        {guide.official_links.length > 0 ? (
          <section className="mt-7">
            <h2 className="font-display text-[16px] font-extrabold text-ink">
              {t("officialLinks")}
            </h2>
            <ul className="mt-2 grid gap-1">
              {guide.official_links.map((link) => (
                <li key={link}>
                  <a
                    href={link}
                    rel="nofollow noopener"
                    className="text-[12.5px] text-brand no-underline"
                  >
                    {link}
                  </a>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </Wrap>
    </main>
  );
}
