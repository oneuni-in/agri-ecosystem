import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { fetchResources, type ResourceCard } from "@/lib/education";

import { ResourceListCard } from "../colleges/resource-card";

/**
 * Phase 2 — `/exams`. ISR, indexed.
 *
 * COVERS BOTH ENTRANCE AND RECRUITMENT EXAMS. Someone looking for NABARD
 * Grade A and someone looking for ICAR AIEEA want different halves of the same
 * page, so it is grouped by category with real headings rather than mixed into
 * one list. Spec §11 owner action 3 records the both-kinds reading as an
 * assumption, not a settled decision — flagged again in the PR body.
 *
 * No JSON-LD, for the same reason as /scholarships: schema.org has no honest
 * type for an exam listing.
 */
export const revalidate = 3600;

const ORDER = ["entrance", "recruitment", "language_test"] as const;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ui.colleges");
  return buildMetadata({
    title: t("examsMetaTitle"),
    description: t("examsMetaDescription"),
    canonical: canonicalUrl("https://agri.in", "/exams"),
    siteName: "Agri.in",
  });
}

export default async function ExamsPage() {
  const [t, page] = await Promise.all([
    getTranslations("ui.colleges"),
    fetchResources({ kind: "exam", limit: 100 }),
  ]);

  if (page.items.length === 0) notFound();

  const labels = {
    checked: t("checkedOn"),
    opens: t("opens"),
    closes: t("closes"),
    levels: {
      diploma: t("levels.diploma"),
      ug: t("levels.ug"),
      pg: t("levels.pg"),
      phd: t("levels.phd"),
    },
  };

  const grouped = new Map<string, ResourceCard[]>();
  for (const exam of page.items) {
    const key = exam.category ?? "other";
    grouped.set(key, [...(grouped.get(key) ?? []), exam]);
  }
  // Known categories in a deliberate order, then anything the data grew that
  // this page has not been taught about -- rendered rather than dropped.
  const sections = [
    ...ORDER.filter((key) => grouped.has(key)),
    ...[...grouped.keys()].filter((key) => !ORDER.includes(key as (typeof ORDER)[number])),
  ];

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
          <span>{t("examsCrumb")}</span>
        </nav>

        <Eyebrow className="mt-3">{t("eyebrow")}</Eyebrow>
        <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-extrabold text-ink">
          {t("examsTitle")}
        </h1>
        <p className="mt-1 max-w-[70ch] text-[13px] text-muted">{t("examsSub")}</p>

        {sections.map((category) => (
          <section key={category} className="mt-7">
            <h2 className="font-display text-[17px] font-extrabold text-ink">
              {t(`examCategories.${category}`)}
            </h2>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {(grouped.get(category) ?? []).map((exam) => (
                <ResourceListCard key={exam.slug} resource={exam} labels={labels} />
              ))}
            </div>
          </section>
        ))}
      </Wrap>
    </main>
  );
}
