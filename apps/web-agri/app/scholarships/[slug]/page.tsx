import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { fetchResource, fetchResources } from "@/lib/education";

import { ResourceDetailBody } from "../../colleges/resource-detail";

/**
 * Phase 2 — `/scholarships/[slug]`. ISR, indexed.
 *
 * generateStaticParams reads the same gated list the index does, so an
 * archived resource can never be pre-rendered.
 */
export const revalidate = 3600;

export async function generateStaticParams() {
  const page = await fetchResources({ kind: "scholarship", limit: 100 });
  return page.items.map((item) => ({ slug: item.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const [t, { slug }] = await Promise.all([getTranslations("ui.colleges"), params]);
  const resource = await fetchResource(slug);

  if (resource === null || resource === "unavailable") {
    return buildMetadata({
      title: t("scholarshipsMetaTitle"),
      canonical: canonicalUrl("https://agri.in", "/scholarships"),
      siteName: "Agri.in",
      noIndex: true,
    });
  }

  return buildMetadata({
    title: resource.name.en ?? slug,
    description: resource.benefit ?? t("scholarshipsMetaDescription"),
    canonical: canonicalUrl("https://agri.in", `/scholarships/${resource.slug}`),
    siteName: "Agri.in",
  });
}

export default async function ResourcePage({ params }: { params: Promise<{ slug: string }> }) {
  const [t, { slug }] = await Promise.all([getTranslations("ui.colleges"), params]);
  const resource = await fetchResource(slug);

  // An outage must not become a 404 for a page that exists.
  if (resource === "unavailable" || resource === null) {
    if (resource === null) notFound();
    return (
      <main className="bg-cream pb-10">
        <div className="mx-auto mt-8 max-w-[70ch] px-4">
          <p className="text-[13.5px] font-semibold text-ink">{t("unavailableTitle")}</p>
          <p className="mt-1 text-[12.5px] text-muted">{t("unavailableBody")}</p>
        </div>
      </main>
    );
  }

  return (
    <ResourceDetailBody
      resource={resource}
      labels={{
        crumbHome: t("crumbHome"),
        crumb: t("scholarshipsCrumb"),
        crumbHref: "/scholarships",
        eyebrow: t("eyebrow"),
        provider: t("provider"),
        eligibility: t("eligibility"),
        benefit: t("benefit"),
        opens: t("opens"),
        closes: t("closes"),
        session: t("session"),
        checked: t("checkedOn"),
        officialLink: t("officialLink"),
        levels: {
          diploma: t("levels.diploma"),
          ug: t("levels.ug"),
          pg: t("levels.pg"),
          phd: t("levels.phd"),
        },
      }}
    />
  );
}
