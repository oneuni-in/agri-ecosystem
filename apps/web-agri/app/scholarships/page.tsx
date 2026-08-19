import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { fetchResources } from "@/lib/education";

import { ResourceListCard } from "../colleges/resource-card";

/**
 * Phase 2 — `/scholarships`. ISR, indexed.
 *
 * Plain `WebPage` metadata and NO JSON-LD: schema.org has no honest type for a
 * scholarship, and marking one up as something it is not invites a manual
 * action (spec §6). The same goes for `/exams`.
 */
export const revalidate = 3600;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ui.colleges");
  return buildMetadata({
    title: t("scholarshipsMetaTitle"),
    description: t("scholarshipsMetaDescription"),
    canonical: canonicalUrl("https://agri.in", "/scholarships"),
    siteName: "Agri.in",
  });
}

export default async function ScholarshipsPage() {
  const [t, page] = await Promise.all([
    getTranslations("ui.colleges"),
    fetchResources({ kind: "scholarship", limit: 100 }),
  ]);

  // No scholarships means no page. Unlike /colleges, an empty result here can
  // only mean the dataset is absent -- there is no filter to have narrowed.
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
          <span>{t("scholarshipsCrumb")}</span>
        </nav>

        <Eyebrow className="mt-3">{t("eyebrow")}</Eyebrow>
        <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-extrabold text-ink">
          {t("scholarshipsTitle")}
        </h1>
        <p className="mt-1 max-w-[70ch] text-[13px] text-muted">{t("scholarshipsSub")}</p>

        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {page.items.map((resource) => (
            <ResourceListCard key={resource.slug} resource={resource} labels={labels} />
          ))}
        </div>
      </Wrap>
    </main>
  );
}
