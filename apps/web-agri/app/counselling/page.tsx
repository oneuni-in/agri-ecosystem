import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { fetchGuides } from "@/lib/education";

import { GuideIndexBody } from "../colleges/guide-index";

/**
 * Phase 2 — `/counselling`, an index of `kind=counselling` guides. ISR, indexed.
 */
export const revalidate = 3600;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("ui.colleges");
  return buildMetadata({
    title: t("counsellingMetaTitle"),
    description: t("counsellingMetaDescription"),
    canonical: canonicalUrl("https://agri.in", "/counselling"),
    siteName: "Agri.in",
  });
}

export default async function GuideIndexPage() {
  const [t, guides] = await Promise.all([
    getTranslations("ui.colleges"),
    fetchGuides({ kind: "counselling" }),
  ]);

  if (guides.length === 0) notFound();

  return (
    <GuideIndexBody
      guides={guides}
      labels={{
        crumbHome: t("crumbHome"),
        crumb: t("counsellingCrumb"),
        eyebrow: t("eyebrow"),
        title: t("counsellingTitle"),
        sub: t("counsellingSub"),
        checked: t("checkedOn"),
      }}
    />
  );
}
