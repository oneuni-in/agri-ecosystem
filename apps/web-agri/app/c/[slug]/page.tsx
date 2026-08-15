import { Eyebrow, Wrap } from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { fetchVerticals, GROUP_STAGE, type VerticalItem } from "@/lib/home";

import { NotifyMeForm } from "./notify-me-form";

/**
 * A-U1 W2 — `/c/[slug]`, the ONE shared vertical landing. The vertical is
 * looked up in the SAME `/catalog/verticals` registry read the grids bind
 * to — an unknown slug is a real 404, never a soft page. ALWAYS noindexed
 * (`buildMetadata({ noIndex: true })`): Soon landings are thin by design,
 * and live verticals' landings are router pages whose real surfaces carry
 * the canonical URLs.
 *
 * Soon verticals: honest copy + a REAL notify-me — POST (via the guest-
 * capable /api/leads BFF proxy) to the backend's `/leads/pincode-interest`,
 * the D23 pincode-interest module (directory/leads_router.py). Its schema
 * `PincodeInterestCreateIn` requires only `pincode` (^\d{6}$); `contact`
 * (≤120 chars) and `milk_type` (≤40) are optional — the form sends
 * {pincode, contact} and omits milk_type (it is milk.in's field).
 *
 * Live verticals: the same page renders a "Go →" door to the real surface.
 */

/** Live vertical slug → its real surface. ROUTING CONFIG, not a category
 * list — the set of verticals (and which are live) still comes from the
 * registry; this only says where a live surface lives today. Unmapped live
 * slugs fall back to "/" (the hub is their surface until they get one). */
const LIVE_ROUTES: Record<string, string> = {
  "farm-tools": "/tools",
  "mandi-prices": "/#mandi",
  weather: "/#weather",
  "govt-schemes": "/#schemes",
  "agri-news": "/",
  knowledge: "/",
  helplines: "/",
};

async function findVertical(slug: string): Promise<VerticalItem | undefined> {
  const verticals = await fetchVerticals();
  return verticals.find((v) => v.slug === slug);
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const vertical = await findVertical(slug);
  const t = await getTranslations("ui.agriHome.soonPage");
  const name = vertical?.name["en"] ?? slug;
  return buildMetadata({
    title: t("metaTitle", { name }),
    description: t("metaDescription", { name }),
    canonical: canonicalUrl("https://agri.in", `/c/${slug}`),
    noIndex: true,
  });
}

export default async function VerticalLandingPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [locale, t, vertical] = await Promise.all([
    getLocale(),
    getTranslations("ui"),
    findVertical(slug),
  ]);
  if (!vertical) notFound();

  const name = vertical.name[locale] ?? vertical.name["en"] ?? vertical.slug;
  const vernacular =
    locale === "ta" ? (vertical.name["en"] ?? "") : (vertical.name["ta"] ?? "");
  const stage = GROUP_STAGE[vertical.group];
  const liveHref = LIVE_ROUTES[vertical.slug] ?? "/";

  return (
    <main className="bg-cream pb-10">
      <Wrap>
        <nav className="mt-3.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
          <Link href="/" prefetch={false} className="tap-target text-brand no-underline">
            {t("agriHome.soonPage.crumbHome")}
          </Link>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <a href="/categories" className="tap-target text-brand no-underline">
            {t("agriHome.soonPage.crumbCategories")}
          </a>
          <span aria-hidden="true" className="text-cream-line">
            ›
          </span>
          <span>{name}</span>
        </nav>

        <div className="mt-2 flex flex-wrap items-start gap-3.5">
          <span
            aria-hidden="true"
            className="flex h-[54px] w-[54px] flex-none items-center justify-center rounded-icon bg-brand-soft text-[26px]"
          >
            {vertical.icon}
          </span>
          <div>
            <Eyebrow>
              {vertical.soon ? t("agriHome.soonPage.eyebrowSoon") : t("agriHome.soonPage.eyebrowLive")}
            </Eyebrow>
            <h1 className="font-display text-[clamp(20px,2.6vw,28px)] font-semibold leading-[1.15]">
              {name}
              {vernacular ? (
                <span className="ml-2 align-middle text-[14px] font-normal text-muted">
                  {vernacular}
                </span>
              ) : null}
            </h1>
          </div>
        </div>

        {vertical.soon ? (
          <>
            {/* Honest copy: the vertical EXISTS (registry entry), its
                surface has not shipped — say so, with the rollout stage. */}
            <p className="mt-4 max-w-[620px] text-[13.5px] leading-relaxed text-sub">
              {stage
                ? t("agriHome.soonPage.bodyStaged", { name, stage })
                : t("agriHome.soonPage.body", { name })}
            </p>
            <NotifyMeForm />
          </>
        ) : (
          <>
            <p className="mt-4 max-w-[620px] text-[13.5px] leading-relaxed text-sub">
              {t("agriHome.soonPage.liveBody", { name })}
            </p>
            <a
              href={liveHref}
              className="mt-4 inline-flex min-h-[44px] items-center rounded-btn bg-brand px-5 text-sm font-bold text-white no-underline"
            >
              {t("agriHome.soonPage.liveCta")} →
            </a>
          </>
        )}
      </Wrap>
    </main>
  );
}
