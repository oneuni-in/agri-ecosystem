import {
  BigCtaGrid,
  BigCtaTile,
  Card,
  EarnCard,
  EcoPill,
  EcoStrip,
  Eyebrow,
  LOC_COOKIE,
  Section,
  StoryCard,
  TrustPillar,
  WaveDivider,
  Wrap,
} from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { cookies } from "next/headers";
import Link from "next/link";
import { Suspense } from "react";

import { SARKARI_LINKS } from "@/data/sarkari";
import { resolveHomePincode } from "@/lib/home";

import { HeaderLocation } from "./header-location";
import {
  CalendarBlock,
  CategoryGrid,
  DirectoryRow,
  HeroAd,
  HelplineBand,
  KnowledgeBlock,
  MandiBlock,
  ReviewsStrip,
  SchemesBlock,
  StatsBandSection,
  TodayLead,
  WeatherBlock,
  type HouseCopy,
} from "./home-sections";
import {
  CalendarSkeleton,
  CategoryGridSkeleton,
  DirectorySkeleton,
  HelplinesSkeleton,
  KnowledgeSkeleton,
  MandiSkeleton,
  ReviewsSkeleton,
  SchemesSkeleton,
  StatsSkeleton,
  WeatherSkeleton,
} from "./home-skeletons";
import { MandiAlertCard } from "./mandi-alert-card";

const SITE = "https://agri.in";

/**
 * The route stays dynamic because it renders the VISITOR's pincode from their
 * `agri_loc` cookie. `dynamic = "force-dynamic"` is deliberately GONE: reading
 * `cookies()` already makes the route dynamic, while force-dynamic ALSO
 * downgrades every fetch default to no-store — which quietly defeated the
 * revalidate windows the reads declare. The windows now live in one place
 * (`lib/home-data.ts`) and actually apply.
 */
export function generateMetadata(): Metadata {
  return buildMetadata({
    title: "Agri.in — all of Indian agriculture, one place",
    description:
      "Mandi prices, weather, government schemes, verified agri businesses, equipment and expert help near you — in English, Tamil and Hindi.",
    canonical: canonicalUrl(SITE, "/"),
    siteName: "Agri.in",
  });
}

/** WebSite + Organization + FAQPage — milk's hand-built JSON-LD precedent.
 * `<` is escaped so the payload can never close the script tag. */
function homeJsonLd(faq: { q: string; a: string }[]): string {
  const graph = {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "WebSite", name: "Agri.in", url: SITE },
      { "@type": "Organization", name: "Agri.in", url: SITE },
      {
        "@type": "FAQPage",
        mainEntity: faq.map((item) => ({
          "@type": "Question",
          name: item.q,
          acceptedAnswer: { "@type": "Answer", text: item.a },
        })),
      },
    ],
  };
  return JSON.stringify(graph).replaceAll("<", "\\u003c");
}

/** §10c — the four calculator entry cards; hrefs anchor into /tools. */
const TOOL_CARDS = [
  { key: "emi", icon: "🚜", href: "/tools#emi" },
  { key: "seed", icon: "🌱", href: "/tools#seed-rate" },
  { key: "fert", icon: "🧪", href: "/tools#fertilizer" },
  { key: "spray", icon: "💧", href: "/tools#spray" },
] as const;

/**
 * Below-fold sections keep A-U1's content-visibility budget: the browser skips
 * layout and paint for what is off-screen, which is the only reason a document
 * this tall was ever affordable. The W0 refactor moved the sections into
 * components and briefly lost these classes — TBT rose immediately, which is
 * how we found out. It belongs on the WRAPPER, not inside the section, so the
 * skeleton and the streamed content both get it.
 */
function BelowFold({ children }: { children: React.ReactNode }) {
  return (
    <div className="[content-visibility:auto] [contain-intrinsic-size:auto_600px]">
      {children}
    </div>
  );
}

/**
 * The agri.in home — A1 FINAL v4 (docs/design-reference/agri/
 * agri_home_desktop_v1.html; §-numbers below are that file's), bound to REAL
 * engines only, with no mock rows anywhere.
 *
 * A-U4 W0 changed HOW this page is delivered, not what it says.
 *
 * Before: one `Promise.all` over eight reads, then a single 1,066-element
 * document. Nothing painted until the slowest read returned — measured
 * server-response 900 ms on `/` against 60 ms on `/categories`, with FCP
 * 2.0–2.6 s and five of five Lighthouse runs under the 0.90 floor. The
 * distributions, and the finding that pre-A-U3 measured identically (so A-U3
 * inherited this rather than caused it), are recorded in
 * `docs/qa/agri-perf-a1.md`.
 *
 * After: this function awaits ONE cheap thing — the translation catalogue,
 * which touches no network — and returns immediately. Everything that reads an
 * engine sits behind its own `<Suspense>` and streams into a reserved box.
 * Above the fold that means the header, hero and search band paint from the
 * first flush; below it, a slow section costs only itself instead of the page.
 *
 * Two rules for anyone adding to this page (W2/W3 add coins and notifications
 * here):
 *   - a section that reads an engine goes in `home-sections.tsx` behind its
 *     own boundary, never inline in this shell;
 *   - its read goes in `lib/home-data.ts` with a declared cache window, so the
 *     `cache()` dedupe holds and boundaries cannot fan out duplicate calls.
 */
export default async function HomePage() {
  // The ONLY await in the shell. `getTranslations` is an in-process catalogue
  // read; the pincode comes from a cookie. No engine is touched here, which is
  // what lets the shell flush before any of them answer.
  const [t, cookieStore] = await Promise.all([getTranslations("ui"), cookies()]);
  const pincode = resolveHomePincode(cookieStore.get(LOC_COOKIE)?.value);

  const faq = (["1", "2", "3", "4", "5", "6"] as const).map((n) => ({
    q: t(`agriHome.faq.q${n}`),
    a: t(`agriHome.faq.a${n}`),
  }));

  // Resolved here, in the shell, so the hero's LCP text can be rendered
  // synchronously by the Suspense fallback — see HouseHero's note.
  const house: HouseCopy = {
    title: t("agriHome.hero.houseTitle"),
    cta: t("agriHome.hero.houseCta"),
  };

  return (
    <main className="bg-cream pb-6">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: homeJsonLd(faq) }}
      />

      {/* §2b severe strip + §3 TODAY strip — ABOVE THE FOLD, so it is AWAITED
          here, not streamed. W0 measured the alternative: behind a boundary the
          strip swaps in after first paint and moves the hero under it, which
          put CLS at 0.103 on two of five runs against a 0.003 baseline. Above
          the fold, "renders first" and "streams" are opposites. */}
      <TodayLead pincode={pincode} />

      {/* §4 — full-bleed hero ad, D21 slot agri_home_hero_xl (config-only
          onboarding; engine untouched). The box reserves the seeded creative
          ratio (1600×420) so loading, empty and full all occupy the same
          space — zero CLS. The WaveDivider closes the hero into the cream page
          exactly as A1 draws it. */}
      <div className="relative">
        {/* AWAITED, not streamed, and this one is the sharpest lesson of W0.
            Lighthouse measures the house-hero <b> as the LCP element. Behind a
            Suspense boundary the fallback paints it early — and then React
            REPLACES it when the serve resolves, so the largest paint is
            recorded at the swap, not the first paint: LCP went 2830-3383ms ->
            3415-3748ms. Streaming the LCP element cannot help, because the
            swap IS the paint being measured. The serve is a ~30ms local read;
            it belongs on first byte. */}
        <HeroAd pincode={pincode} house={house} />
        <WaveDivider />
      </div>

      <Wrap>
        {/* §5 — search band. Gradient with a solid token underlay (never a
            bg-* class beside a gradient through cn() — tw-merge drops it).
            Fully static, so it is part of the first flush: the search box is
            usable before any engine has answered. The mic is an entry stub —
            A1 ships it inert too, and a dead mic button is honest where a fake
            transcript would not be. */}
        <section className="mt-3.5 rounded-band [background-color:var(--brand)] bg-band-gradient px-5 pb-7 pt-[26px] text-center text-white">
          <h1 className="font-display text-[clamp(19px,2.4vw,27px)] font-semibold">
            {t("agriHome.search.title")}
          </h1>
          <p className="mb-4 mt-1.5 text-[13px] text-brand-soft">
            {t("agriHome.search.sub")}
          </p>
          <form
            action="/search"
            method="get"
            className="mx-auto flex max-w-[620px] items-center gap-2.5 rounded-[14px] bg-card p-1.5 pl-4"
          >
            <label htmlFor="q" className="sr-only">
              {t("agriHome.search.inputLabel")}
            </label>
            <input
              id="q"
              name="q"
              type="search"
              placeholder={t("agriHome.search.placeholder")}
              className="min-w-0 flex-1 border-0 bg-transparent text-[15px] font-medium text-ink focus:outline-none"
            />
            <button
              type="button"
              aria-label={t("search.micLabel")}
              className="tap-target px-1 text-[17px] text-brand"
            >
              🎙️
            </button>
            <button
              type="submit"
              className="inline-flex min-h-[44px] items-center rounded-btn bg-brand px-[18px] text-sm font-medium text-white"
            >
              {t("agriHome.search.cta")}
            </button>
          </form>
          {/* The ONE location control pattern (D19): the same LiveLocationPill
              wrapper the header renders, bound to /api/identity/location. */}
          <div className="mt-3 inline-flex">
            <HeaderLocation />
          </div>
        </section>

        {/* ── below the fold: every data-bearing section streams ──────────── */}

        {/* §6 — category grid: 36 verticals, 5 groups, rendered FROM
            GET /catalog/verticals (zero hardcoded category lists). */}
        <BelowFold>
          <Suspense fallback={<CategoryGridSkeleton />}>
            <CategoryGrid />
          </Suspense>
        </BelowFold>

        {/* §6b ticker + §7 price cards. */}
        <BelowFold>
          <Suspense fallback={<MandiSkeleton />}>
            <MandiBlock pincode={pincode} />
          </Suspense>
        </BelowFold>

        {/* §7b — kharif calendar. */}
        <BelowFold>
          <Suspense fallback={<CalendarSkeleton />}>
            <CalendarBlock pincode={pincode} />
          </Suspense>
        </BelowFold>

        {/* §8 — weather. */}
        <BelowFold>
          <Suspense fallback={<WeatherSkeleton />}>
            <WeatherBlock pincode={pincode} />
          </Suspense>
        </BelowFold>

        {/* §9 — schemes spotlight + deadlines bar. */}
        <BelowFold>
          <Suspense fallback={<SchemesSkeleton />}>
            <SchemesBlock pincode={pincode} />
          </Suspense>
        </BelowFold>

        {/* §9b — sarkari services hub: REAL and flag-independent, and STATIC —
            deep links to OFFICIAL portals only (data/sarkari.ts, checked by
            scripts/check-sarkari-links.mjs — AG-A11). We link, we never fetch
            or store anyone's records (DPDP). Domain + verified stamp render
            from the data file, so no boundary is needed. */}
        <section
          aria-label={t("agriHome.sarkari.title")}
          className="pb-2 pt-[22px] [content-visibility:auto] [contain-intrinsic-size:auto_600px]"
        >
          <Eyebrow>{t("agriHome.sarkari.eyebrow")}</Eyebrow>
          <h2 className="mb-3.5 font-display text-xl font-extrabold">
            {t("agriHome.sarkari.title")}
          </h2>
          <div className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-3">
            {SARKARI_LINKS.map((link) => (
              <a
                key={link.key}
                data-testid="sarkari-link"
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-[11px] rounded-card border border-cream-line bg-card px-3.5 py-3 no-underline transition-[transform,box-shadow] duration-150 hover:-translate-y-0.5 hover:shadow-lift motion-reduce:transition-none motion-reduce:hover:translate-y-0"
              >
                <span
                  aria-hidden="true"
                  className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-[10px] bg-brand-soft text-base"
                >
                  {link.icon}
                </span>
                <span className="min-w-0">
                  <b className="block text-[12.5px] font-medium text-ink">
                    {t(`agriHome.sarkari.${link.key}.title`)}
                  </b>
                  <small className="mt-px block text-[10px] leading-normal text-muted">
                    {t(`agriHome.sarkari.${link.key}.sub`)}
                  </small>
                  <span className="mt-[3px] inline-block text-[9.5px] font-medium text-brand">
                    {link.domain} ↗ · ✓ {link.verified_on}
                  </span>
                </span>
              </a>
            ))}
          </div>
        </section>

        {/* §10 — directory row: businesses covering the visitor's pincode,
            nearest first, from the public covers() read. Organic only: no agri
            sponsored-listing slot is registered, so nothing is injected until a
            real campaign can serve (honesty rule). */}
        <BelowFold>
          <Suspense fallback={<DirectorySkeleton />}>
            <DirectoryRow pincode={pincode} />
          </Suspense>
        </BelowFold>

        {/* §10a2 — how agri.in works (static i18n). */}
        <Section
          title={t("agriHome.how.title")}
          className="[content-visibility:auto] [contain-intrinsic-size:auto_600px]"
        >
          <div className="grid gap-3 md:grid-cols-3">
            {(["s1", "s2", "s3"] as const).map((step, index) => (
              <div
                key={step}
                className="rounded-card border border-cream-line bg-card p-4 text-center"
              >
                <span
                  aria-hidden="true"
                  className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-pill bg-brand-soft font-display text-base font-extrabold text-brand-deep"
                >
                  {index + 1}
                </span>
                <b className="block text-[13px] font-semibold text-ink">
                  {t(`agriHome.how.${step}.t`)}
                </b>
                <small className="text-[11px] text-muted">
                  {t(`agriHome.how.${step}.d`)}
                </small>
              </div>
            ))}
          </div>
        </Section>

        {/* §10b equipment showcase: /catalog/verticals/{slug}/products has no
            agri schema yet → no products can exist → section ABSENT. */}

        {/* §11 — knowledge + news, from the E6 content engine. APPROVED items
            only: the backend gate means anything rendered here was passed by a
            human, and the section is absent when nothing has been approved. */}
        <BelowFold>
          <Suspense fallback={<KnowledgeSkeleton />}>
            <KnowledgeBlock />
          </Suspense>
        </BelowFold>

        {/* §10c — farm calculators entry (A1 .tools-grid): REAL doors into
            /tools, the client-side offline calculators. Static. */}
        <section
          aria-label={t("agriHome.toolsRow.title")}
          className="pb-2 pt-[22px] [content-visibility:auto] [contain-intrinsic-size:auto_600px]"
        >
          <Eyebrow>{t("agriHome.toolsRow.eyebrow")}</Eyebrow>
          <div className="mb-3.5 flex items-baseline justify-between gap-2.5">
            <h2 className="font-display text-xl font-extrabold">
              {t("agriHome.toolsRow.title")}
            </h2>
            <a
              href="/tools"
              className="tap-target text-[13px] font-bold text-brand-deep no-underline"
            >
              {t("agriHome.toolsRow.all")}
            </a>
          </div>
          <div className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
            {TOOL_CARDS.map((tool) => (
              <a
                key={tool.key}
                href={tool.href}
                className="block rounded-card border border-cream-line bg-card px-[15px] py-[13px] no-underline transition-[transform,box-shadow] duration-150 hover:-translate-y-0.5 hover:shadow-lift motion-reduce:transition-none motion-reduce:hover:translate-y-0"
              >
                <span aria-hidden="true" className="text-xl">
                  {tool.icon}
                </span>
                <b className="mt-1.5 block text-[12px] font-medium text-ink">
                  {t(`agriHome.toolsRow.${tool.key}.title`)}
                </b>
                <small className="mt-0.5 block text-[10px] leading-[1.45] text-muted">
                  {t(`agriHome.toolsRow.${tool.key}.sub`)}
                </small>
                <span className="mt-[7px] inline-block text-[10.5px] font-medium text-brand">
                  {t("agriHome.toolsRow.calc")}
                </span>
              </a>
            ))}
          </div>
        </section>

        {/* §11b/§11c — Q&A + events are Stage D surfaces: honest Soon cards
            (door to the /c/ landing), never fake threads or events. */}
        <Section
          title={t("agriHome.community.title")}
          className="[content-visibility:auto] [contain-intrinsic-size:auto_600px]"
        >
          <div className="grid gap-2.5 md:grid-cols-2">
            {(
              [
                { href: "/c/forum-qa", icon: "💬", key: "qa" },
                { href: "/c/events-webinars", icon: "🎪", key: "events" },
              ] as const
            ).map((item) => (
              <a key={item.key} href={item.href} className="no-underline">
                <Card hover className="relative flex items-start gap-3 p-4">
                  <span
                    aria-hidden="true"
                    className="absolute right-2 top-2 rounded-pill bg-cream-deep px-2 py-0.5 text-[9px] font-medium text-sub"
                  >
                    {t("agriHome.soon")}
                  </span>
                  <span aria-hidden="true" className="text-2xl">
                    {item.icon}
                  </span>
                  <span>
                    <b className="block text-[13.5px] font-semibold text-ink">
                      {t(`agriHome.community.${item.key}Title`)}
                    </b>
                    <small className="text-[11px] leading-relaxed text-sub">
                      {t(`agriHome.community.${item.key}Sub`)}
                    </small>
                  </span>
                </Card>
              </a>
            ))}
          </div>
        </Section>

        {/* §12 — Ask-AI band. A-U4 W1 gives this a real destination: /ask,
            which serves the chat when `agri_ai` is ON and an honest
            not-yet state when it is OFF. One route, both states — so this
            CTA never becomes a lie in either direction, and the flag flip
            needs no change here. id="ask" anchors the bottom-nav mic. */}
        <section
          id="ask"
          aria-label={t("agriHome.ask.title")}
          className="mt-5 rounded-band [background-color:var(--brand-deep)] bg-cta-gradient px-6 py-[22px] text-white"
        >
          <div className="flex flex-wrap items-center gap-3.5">
            <span aria-hidden="true" className="text-[30px]">
              🤖
            </span>
            <div className="min-w-0 flex-1">
              <b className="block font-display text-[17px] font-semibold">
                {t("agriHome.ask.title")}
              </b>
              <p className="mt-0.5 text-[12px] text-brand-soft-2">
                {t("agriHome.ask.sub")}
              </p>
            </div>
            <Link
              href="/ask"
              prefetch={false}
              className="inline-flex min-h-[44px] items-center rounded-pill bg-accent px-[18px] text-[13.5px] font-bold text-accent-ink no-underline"
            >
              {t("agriHome.ask.cta")}
            </Link>
          </div>
          <p className="mt-2.5 text-[10.5px] text-brand-soft-2">
            {t("agriHome.ask.note")}
          </p>
        </section>

        {/* §13 — helpline band from the E5 dataset. Name, number, tel: link and
            the per-number source+date stamp ALL render from the row. */}
        <BelowFold>
          <Suspense fallback={<HelplinesSkeleton />}>
            <HelplineBand />
          </Suspense>
        </BelowFold>

        {/* §13b live activity feed: agri_live_feed flag is OFF and no feed
            endpoint exists → ABSENT (events are never fabricated). */}

        {/* §14 — stats band, REAL numbers only. */}
        <BelowFold>
          <Suspense fallback={<StatsSkeleton />}>
            <StatsBandSection pincode={pincode} />
          </Suspense>
        </BelowFold>

        {/* §14b — trust pillars (static i18n) + the success story, which is
            marked ILLUSTRATIVE in copy and carries NO number chips in prod. */}
        <Section
          title={t("agriHome.pillars.title")}
          className="pb-0 [content-visibility:auto] [contain-intrinsic-size:auto_600px]"
        >
          <Eyebrow className="-mt-3">{t("agriHome.pillars.eyebrow")}</Eyebrow>
          <div className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
            <TrustPillar
              icon="🆓"
              tint="green"
              title={t("agriHome.pillars.p1t")}
              sub={t("agriHome.pillars.p1d")}
            />
            <TrustPillar
              icon="✅"
              tint="aqua"
              title={t("agriHome.pillars.p2t")}
              sub={t("agriHome.pillars.p2d")}
            />
            <TrustPillar
              icon="📊"
              tint="blue"
              title={t("agriHome.pillars.p3t")}
              sub={t("agriHome.pillars.p3d")}
            />
            <TrustPillar
              icon="🔒"
              tint="cream"
              title={t("agriHome.pillars.p4t")}
              sub={t("agriHome.pillars.p4d")}
            />
          </div>
          <StoryCard
            className="mt-3"
            quote={t("agriHome.story.quote")}
            who={
              <>
                <span
                  aria-hidden="true"
                  className="flex h-[34px] w-[34px] items-center justify-center rounded-full bg-accent font-semibold text-brand-deep"
                >
                  {t("agriHome.story.initial")}
                </span>
                <span>
                  <b className="text-white">{t("agriHome.story.name")}</b> ·{" "}
                  {t("agriHome.story.context")}
                </span>
              </>
            }
          />
        </Section>

        {/* §15 — reviews strip: approved-only D18 rows composed from the
            businesses on this page. */}
        <BelowFold>
          <Suspense fallback={<ReviewsSkeleton />}>
            <ReviewsStrip pincode={pincode} />
          </Suspense>
        </BelowFold>

        {/* §15b — earn AgriCoins. DECISION: the coins engine exposes no public
            rules endpoint (only authed /coins/balance·history·referral-code),
            so the cards carry i18n copy WITHOUT amounts — the coin glyph fills
            EarnCard's amount slot; real numbers arrive when a rules read
            exists. Never invent amounts. (W2 revisits this.) */}
        <Section
          title={t("agriHome.earn.title")}
          className="pb-0 [content-visibility:auto] [contain-intrinsic-size:auto_600px]"
        >
          <Eyebrow className="-mt-3">{t("agriHome.earn.eyebrow")}</Eyebrow>
          <div className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
            {(
              [
                { icon: "⭐", key: "e1" },
                { icon: "🎪", key: "e2" },
                { icon: "🤝", key: "e3" },
                { icon: "📅", key: "e4" },
              ] as const
            ).map((item) => (
              <EarnCard
                key={item.key}
                icon={item.icon}
                title={t(`agriHome.earn.${item.key}t`)}
                sub={t(`agriHome.earn.${item.key}d`)}
                amount="🪙"
              />
            ))}
          </div>
        </Section>

        {/* §16 popular searches: OMITTED this pass — chips may only link routes
            that resolve. Returns with the search facade. */}

        {/* §17 — big CTA tiles. */}
        <BigCtaGrid className="mt-5">
          <BigCtaTile
            icon="🎙️"
            gradient="brand"
            title={t("agriHome.cta.needTitle")}
            sub={t("agriHome.cta.needSub")}
            cta={t("agriHome.cta.needCta")}
            href="/account/inquiries"
          />
          <BigCtaTile
            icon="🏪"
            gradient="gold"
            title={t("agriHome.cta.listTitle")}
            sub={t("agriHome.cta.listSub")}
            cta={t("agriHome.cta.listCta")}
            href="/business"
          />
        </BigCtaGrid>

        {/* §18 — mandi-alert opt-in: honest door to /notifications. */}
        <div className="mt-5">
          <MandiAlertCard pincode={pincode} />
        </div>

        {/* §19 PWA band: arrives with W4's PWA pass. */}

        {/* §20 — FAQ; the same strings are emitted as FAQPage JSON-LD above. */}
        <Section
          title={t("agriHome.faq.title")}
          className="[content-visibility:auto] [contain-intrinsic-size:auto_600px]"
        >
          <div className="flex flex-col gap-2">
            {faq.map((item) => (
              <details
                key={item.q}
                className="rounded-btn border border-cream-line bg-card px-4"
              >
                <summary className="cursor-pointer list-none py-3.5 text-[13px] font-semibold text-ink">
                  {item.q}
                </summary>
                <div className="pb-3.5 text-[12px] leading-relaxed text-sub">
                  {item.a}
                </div>
              </details>
            ))}
          </div>
        </Section>

        {/* §20b — weekly digest, SOON state (no reader counts, no live
            subscription): the notify-me control is disabled until the real
            subscription lands. */}
        <section
          aria-label={t("agriHome.digest.title")}
          className="mt-5 flex flex-wrap items-center gap-4 rounded-band border border-brand-soft-2 bg-brand-soft p-5"
        >
          <span aria-hidden="true" className="text-[28px]">
            📩
          </span>
          <div className="min-w-0 flex-1">
            <b className="block font-display text-base font-semibold text-brand-deep">
              {t("agriHome.digest.title")}{" "}
              <span className="ml-1 rounded-pill bg-cream-deep px-2 py-0.5 align-middle text-[9px] font-medium text-sub">
                {t("agriHome.soon")}
              </span>
            </b>
            <p className="mt-0.5 text-[11.5px] text-sub">{t("agriHome.digest.sub")}</p>
          </div>
          <button
            type="button"
            disabled
            aria-disabled="true"
            className="inline-flex min-h-[44px] items-center rounded-btn bg-brand px-4 text-[12.5px] font-bold text-white opacity-60"
          >
            🔔 {t("agriHome.digest.cta")}
          </button>
        </section>

        {/* §21 — family strip: agri (you are here, not a link) · milk ·
            organic · coins. */}
        <Section
          title={t("agriHome.family.title")}
          className="pb-0 [content-visibility:auto] [contain-intrinsic-size:auto_600px]"
        >
          <EcoStrip>
            <span className="min-w-[210px] shrink-0 rounded-card bg-brand px-[18px] py-3.5 text-white">
              <b className="block font-display text-[17px] font-extrabold">🌾 agri.in</b>
              <small className="text-xs opacity-90">{t("agriHome.family.here")}</small>
            </span>
            <EcoPill
              href="https://milk.in"
              gradient="milk"
              title="🥛 milk.in"
              sub={t("agriHome.family.milk")}
            />
            <EcoPill
              href="https://theorganic.in"
              gradient="organic"
              title="🌿 theorganic.in"
              sub={t("agriHome.family.organic")}
            />
            <EcoPill
              href="/notifications"
              gradient="coins"
              title="🪙 AgriCoins"
              sub={t("agriHome.family.coins")}
            />
          </EcoStrip>
        </Section>
      </Wrap>
    </main>
  );
}
