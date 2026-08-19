import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { fetchGuides } from "@/lib/education";

import { GuideIndexBody } from "../colleges/guide-index";

/**
 * Phase 2 — `/study-abroad`, an index of `kind=foreign_study` guides. ISR, indexed.
 */
export const revalidate = 3600;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ui.colleges");
  return buildMetadata({
    title: t("studyAbroadMetaTitle"),
    description: t("studyAbroadMetaDescription"),
    canonical: canonicalUrl("https://agri.in", "/study-abroad"),
    siteName: "Agri.in",
  });
}

export default async function GuideIndexPage() {
  const [t, guides] = await Promise.all([
    getTranslations("ui.colleges"),
    fetchGuides({ kind: "foreign_study" }),
  ]);

  if (guides.length === 0) notFound();

  return (
    <GuideIndexBody
      guides={guides}
      labels={{
        crumbHome: t("crumbHome"),
        crumb: t("studyAbroadCrumb"),
        eyebrow: t("eyebrow"),
        title: t("studyAbroadTitle"),
        sub: t("studyAbroadSub"),
        checked: t("checkedOn"),
      }}
    />
  );
}
