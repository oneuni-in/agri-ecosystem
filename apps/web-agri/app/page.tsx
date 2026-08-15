import {
  AdCarousel,
  Badge,
  BigCtaGrid,
  BigCtaTile,
  Card,
  CategoryGroup,
  CategoryTile,
  CountUp,
  EarnCard,
  EcoPill,
  EcoStrip,
  EmptyState,
  Eyebrow,
  LOC_COOKIE,
  RatingStars,
  ReviewCard,
  Reveal,
  Section,
  StatBand,
  StatCell,
  StoryCard,
  TrustPillar,
  WaveDivider,
  Wrap,
} from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { cookies } from "next/headers";

import { HELPLINES } from "@/data/helplines";
import { HOME_HERO_SLOT, serveAds } from "@/lib/ads";
import {
  fetchDirectoryRow,
  fetchReviewSignals,
  fetchToday,
  fetchVerticals,
  groupVerticals,
  resolveHomePincode,
  UNLOCATABLE_M,
  type VerticalGroupKey,
} from "@/lib/home";

import { HeaderLocation } from "./header-location";
import { MandiAlertCard } from "./mandi-alert-card";

const SITE = "https://agri.in";

// Per-request: the page renders the VISITOR's pincode (their `agri_loc`
// cookie) — same contract as milk's U1 home.
export const dynamic = "force-dynamic";

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

/** §6 — A1 `.vg-dot` colour per group + the tile icon-disc tint. */
const GROUP_STYLE: Record<VerticalGroupKey, { dot: string; tint: "green" | "sand" | "aqua" | "lilac" | "peach" }> = {
  essentials: { dot: "bg-brand-deep", tint: "green" },
  inputs: { dot: "bg-coins-fg", tint: "sand" },
  services: { dot: "bg-down", tint: "aqua" },
  community: { dot: "bg-brand", tint: "lilac" },
  "buy-sell": { dot: "bg-sponsored-fg", tint: "peach" },
};

const GROUP_LABEL_KEY: Record<VerticalGroupKey, string> = {
  essentials: "essentials",
  inputs: "inputs",
  services: "services",
  community: "community",
  "buy-sell": "buySell",
};

/**
 * The agri.in home — A-U1 CP2, assembled per the A1 FINAL v4 reference
 * (docs/design-reference/agri/agri_home_desktop_v1.html; §-numbers below are
 * that file's) and bound to REAL engines only. The `agri_today` flag is OFF:
 * every flag-gated section (§2b/§3/§6b/§7/§7b/§8/§9) is ABSENT from the DOM
 * — see `fetchToday()` — and every other data-bearing section renders from a
 * live public read or renders nothing. No mock rows anywhere.
 */
export default async function HomePage() {
  const locale = await getLocale();
  const pincode = resolveHomePincode((await cookies()).get(LOC_COOKIE)?.value);

  const [today, verticals, directory, heroAds, t] = await Promise.all([
    fetchToday(),
    fetchVerticals(),
    fetchDirectoryRow(pincode),
    // Served on the SERVER: the hero is the LCP element, and a client fetch
    // delays its image until after hydration (milk's measured 2372ms lesson).
    serveAds(HOME_HERO_SLOT, { pincode, locale }, 5),
    getTranslations("ui"),
  ]);
  // §10 rating meta + §15 strip come from the SAME D18 signals seam milk
  // proved (approved-only is the engine's own guarantee).
  const { ratings, reviews } = await fetchReviewSignals(directory, 2);

  const faq = (["1", "2", "3", "4", "5", "6"] as const).map((n) => ({
    q: t(`agriHome.faq.q${n}`),
    a: t(`agriHome.faq.a${n}`),
  }));
  const groups = groupVerticals(verticals);
  const reviewCount = Object.values(ratings).reduce((sum, r) => sum + r.rating_count, 0);
  const helplineStampDate = HELPLINES[0]?.verified_on ?? "";
  const helplineSources = [...new Set(HELPLINES.map((h) => h.source))].join(" · ");

  return (
    <main className="bg-cream pb-6">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: homeJsonLd(faq) }} />

      {/* §2b severe strip · §3 TODAY strip · §6b mandi ticker · §7 mandi
          cards · §7b kharif calendar · §8 weather+tip · §9 schemes+deadlines:
          agri_today is OFF, fetchToday() is null → these sections are ABSENT
          from the DOM (assert node count, not visibility). Their shapes ship
          in /demo; A-U2 binds them here without touching the composites.
          Rendering the (null) payload keeps the binding point explicit. */}
      {today}

      {/* §4 — full-bleed hero ad, D21 slot agri_home_hero_xl (config-only
          onboarding; engine untouched). The box reserves the seeded creative
          ratio (1600×420, scripts/seed_sample_media.py) so loading, empty and
          full all occupy the same space — zero CLS. The WaveDivider closes
          the hero into the cream page exactly as A1 draws it. */}
      <div className="relative">
        <AdCarousel
          slotKey={HOME_HERO_SLOT}
          initialAds={heroAds}
          heightClass="aspect-[1600/420]"
          badgeClassName="right-3 top-3"
          sponsoredLabel={t("badges.sponsored")}
          arrows={{ prevLabel: t("heroAd.prev"), nextLabel: t("heroAd.next") }}
          fallback={
            // House fallback (first-party door, not a served creative — no
            // badge, no beacons; milk's HouseAdCard rule).
            <a
              href="/business"
              className="flex h-full w-full flex-col items-center justify-center gap-2 [background-color:var(--brand-deep)] bg-cta-gradient text-white no-underline"
            >
              <b className="font-display text-xl font-semibold">{t("agriHome.hero.houseTitle")}</b>
              <span className="rounded-pill bg-accent px-4 py-2 text-[13px] font-bold text-accent-ink">
                {t("agriHome.hero.houseCta")}
              </span>
            </a>
          }
        />
        <WaveDivider />
      </div>

      <Wrap>
        {/* §5 — search band. Gradient with a solid token underlay (never a
            bg-* class beside a gradient through cn() — tw-merge drops it).
            DECISION: web-agri has NO /search route and /directory has no
            index page accepting a query (verified: app/ contains only
            account/api/business/demo/directory/[slug]/notifications). The
            form targets /categories — this work package's CP3 surface, whose
            client-side filter reads ?q — rather than a fabricated results
            page. The mic is an entry stub (A1 ships it inert too). */}
        <section className="mt-3.5 rounded-band [background-color:var(--brand)] bg-band-gradient px-5 pb-7 pt-[26px] text-center text-white">
          <h1 className="font-display text-[clamp(19px,2.4vw,27px)] font-semibold">
            {t("agriHome.search.title")}
          </h1>
          <p className="mb-4 mt-1.5 text-[13px] text-brand-soft">{t("agriHome.search.sub")}</p>
          <form
            action="/categories"
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

        {/* §6 — category grid: 36 verticals, 5 groups, rendered FROM
            GET /catalog/verticals (zero hardcoded category lists). Tile hrefs
            are the /c/{slug} landing routes — they land in CP3 (this work
            package) as the vertical's real surface or its honest noindexed
            coming-soon page. */}
        <Section
          title={t("agriHome.categories.title")}
          className="pb-0"
        >
          <Eyebrow className="-mt-3">{t("agriHome.categories.eyebrow")}</Eyebrow>
          {groups.map((group) => {
            const style = GROUP_STYLE[group.key];
            return (
              <Reveal key={group.key}>
                <CategoryGroup
                  label={
                    <>
                      <span
                        aria-hidden="true"
                        className={`h-2.5 w-2.5 flex-shrink-0 rounded-[3px] ${style.dot}`}
                      />
                      {t(`agriHome.categories.groups.${GROUP_LABEL_KEY[group.key]}`)} (
                      {group.items.length})
                    </>
                  }
                >
                  {group.items.map((vertical, index) => {
                    const label = vertical.name[locale] ?? vertical.name["en"] ?? vertical.slug;
                    // UX law 1: EN + mother tongue on every tile. name.ta is
                    // the vernacular line; on /ta itself (where the label IS
                    // Tamil) the English name takes that slot instead of
                    // duplicating.
                    const vernacular =
                      locale === "ta" ? (vertical.name["en"] ?? "") : (vertical.name["ta"] ?? "");
                    return (
                      // A1 staggered pop-in: the wrapper joins the group's
                      // Reveal (hidden until the group intersects, pops with
                      // i×45ms delay); under reduced motion / no JS the tile
                      // is simply visible.
                      <div
                        key={vertical.slug}
                        style={{ animationDelay: `${index * 45}ms` }}
                        className="group-data-[in=false]/reveal:opacity-0 group-data-[in=true]/reveal:animate-pop motion-reduce:!animate-none motion-reduce:!opacity-100"
                      >
                        <CategoryTile
                          href={`/c/${vertical.slug}`}
                          icon={vertical.icon}
                          label={label}
                          vernacular={vernacular}
                          tint={style.tint}
                          soon={vertical.soon}
                          soonLabel={t("agriHome.soon")}
                        />
                      </div>
                    );
                  })}
                </CategoryGroup>
              </Reveal>
            );
          })}
          <p className="mt-2.5 text-[11.5px] text-muted">
            <b className="font-semibold text-brand-deep">{t("agriHome.soon")}</b>{" "}
            {t("agriHome.categories.note")}
          </p>
        </Section>

        {/* §10 — directory row: businesses covering the visitor's pincode,
            nearest first, from the public covers() read. Organic only: milk
            injects sponsored listings via its M3.B slot, but no agri
            sponsored-listing slot is registered — nothing is injected until a
            real campaign can serve (honesty rule). Call/WhatsApp are doors to
            the profile page, where D18's capped, fail-closed contact-reveal
            flow lives — numbers are never in list payloads. */}
        <Section title={t("agriHome.directory.title")} className="pb-0" >
          <Eyebrow className="-mt-3">{t("agriHome.directory.eyebrow")}</Eyebrow>
          {directory.length === 0 ? (
            <EmptyState
              icon="🏪"
              title={t("agriHome.directory.emptyTitle", { pincode })}
              description={t("agriHome.directory.emptyBody")}
            />
          ) : (
            <div className="grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
              {directory.map((card) => {
                const href = `/directory/businesses/${card.slug}?pin=${pincode}`;
                const rating = ratings[card.id];
                const km =
                  card.distance_m < UNLOCATABLE_M
                    ? `${(card.distance_m / 1000).toFixed(1)} km`
                    : null;
                return (
                  <div
                    key={card.id}
                    data-testid={`home-directory-${card.slug}`}
                    className="flex flex-col gap-1.5 rounded-card border border-cream-line bg-card p-4 transition-shadow hover:shadow-lift"
                  >
                    {card.verification_status === "verified" ? (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant="verified">{t("badges.verified")}</Badge>
                      </div>
                    ) : null}
                    <h3 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">
                      {card.name}
                    </h3>
                    <p className="flex flex-wrap items-center gap-1.5 text-[12.5px] text-muted">
                      {rating?.rating_avg ? (
                        <>
                          <RatingStars value={rating.rating_avg} />
                          <span>({rating.rating_count})</span>
                          {km ? <span aria-hidden="true">·</span> : null}
                        </>
                      ) : null}
                      {km ? <span>{km}</span> : null}
                    </p>
                    <div className="mt-1 flex gap-2">
                      <a
                        href={href}
                        className="flex min-h-[44px] flex-1 items-center justify-center rounded-btn bg-call text-[12.5px] font-bold text-white no-underline"
                      >
                        📞 {t("actions.call")}
                      </a>
                      <a
                        href={href}
                        className="flex min-h-[44px] flex-1 items-center justify-center rounded-btn border border-wa-line bg-wa-soft text-[12.5px] font-bold text-wa-deep no-underline"
                      >
                        {t("actions.whatsapp")}
                      </a>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Section>

        {/* §10a2 — how agri.in works (static i18n). */}
        <Section title={t("agriHome.how.title")}>
          <div className="grid gap-3 md:grid-cols-3">
            {(["s1", "s2", "s3"] as const).map((step, index) => (
              <div key={step} className="rounded-card border border-cream-line bg-card p-4 text-center">
                <span
                  aria-hidden="true"
                  className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-pill bg-brand-soft font-display text-base font-extrabold text-brand-deep"
                >
                  {index + 1}
                </span>
                <b className="block text-[13px] font-semibold text-ink">
                  {t(`agriHome.how.${step}.t`)}
                </b>
                <small className="text-[11px] text-muted">{t(`agriHome.how.${step}.d`)}</small>
              </div>
            ))}
          </div>
        </Section>

        {/* §10b equipment showcase: /catalog/verticals/{slug}/products has no
            agri schema yet → no products can exist → section ABSENT.
            §11 knowledge + news: content module (E6) is empty → ABSENT — no
            lorem articles, ever. */}

        {/* §11b/§11c — Q&A + events are Stage D surfaces: honest Soon cards
            (door to the /c/ landing), never fake threads or events. */}
        <Section title={t("agriHome.community.title")}>
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

        {/* §12 — Ask-AI band: ENTRY SURFACE ONLY (the assistant itself is
            A-U4, owner-gated safety sign-off). No fake input: one honest CTA
            to the /c/experts Soon landing, with the disclaimer copy shipping
            now per the build prompt. id="ask" anchors the bottom-nav mic. */}
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
              <p className="mt-0.5 text-[12px] text-brand-soft-2">{t("agriHome.ask.sub")}</p>
            </div>
            <a
              href="/c/experts"
              className="inline-flex min-h-[44px] items-center rounded-pill bg-accent px-[18px] text-[13.5px] font-bold text-accent-ink no-underline"
            >
              {t("agriHome.ask.cta")}
            </a>
          </div>
          <p className="mt-2.5 text-[10.5px] text-brand-soft-2">{t("agriHome.ask.note")}</p>
        </section>

        {/* §13 — helpline band from the human-verified E5 dataset; name,
            number, tel: link AND the source+date stamp all render from
            data/helplines.ts. */}
        <section
          aria-label={t("agriHome.helplines.title")}
          className="mt-5 rounded-band border border-accent bg-trust-bg px-[18px] py-4"
        >
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-1.5">
            <h2 className="font-display text-lg font-extrabold">
              📞 {t("agriHome.helplines.title")}
            </h2>
            <span className="text-[10.5px] text-muted">{t("agriHome.helplines.offline")}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {HELPLINES.map((helpline) => (
              <a
                key={helpline.key}
                href={helpline.telHref}
                className="inline-flex min-h-[44px] items-center gap-1.5 rounded-pill border border-cream-line bg-card px-3.5 text-[12px] text-ink no-underline hover:border-brand"
              >
                <b className="font-semibold text-brand-deep">
                  {t(`agriHome.helplines.${helpline.name}`)}
                </b>{" "}
                {helpline.number}
              </a>
            ))}
          </div>
          <p className="mt-2 text-[9.5px] text-muted">
            {t("agriHome.helplines.verifiedStamp", {
              sources: helplineSources,
              date: helplineStampDate,
            })}
          </p>
        </section>

        {/* §13b live activity feed: agri_live_feed flag is OFF and no feed
            endpoint exists → ABSENT (events are never fabricated). */}

        {/* §14 — stats band, REAL numbers only (never literals): the vertical
            count from /catalog/verticals and the review count summed from the
            D18 aggregates on this page. DECISION: the reference's "businesses
            listed" / "pincodes covered" cells are OMITTED — covers() returns
            no total and web-agri has no coverage feed, and a cell without an
            honest source is not rendered (milk's §16 rule). */}
        {verticals.length > 0 ? (
          <StatBand label={t("agriHome.stats.label")} data-testid="stats-band" className="mt-5">
            <StatCell
              first
              value={<CountUp end={verticals.length} />}
              label={t("agriHome.stats.verticals")}
            />
            {reviewCount > 0 ? (
              <StatCell value={<CountUp end={reviewCount} />} label={t("agriHome.stats.reviews")} />
            ) : null}
          </StatBand>
        ) : null}

        {/* §14b — trust pillars (static i18n) + the success story, which is
            marked ILLUSTRATIVE in copy and carries NO number chips in prod
            (nums omitted until a real consented story replaces it). */}
        <Section title={t("agriHome.pillars.title")} className="pb-0">
          <Eyebrow className="-mt-3">{t("agriHome.pillars.eyebrow")}</Eyebrow>
          <Reveal className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
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
          </Reveal>
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
            businesses on this page; zero reviews → section ABSENT. */}
        {reviews.length > 0 ? (
          <Section title={t("agriHome.reviews.title")}>
            <div className="grid gap-2.5 md:grid-cols-3">
              {reviews.slice(0, 3).map((review) => {
                const body = review.body[locale] ?? Object.values(review.body)[0] ?? "";
                return (
                  <ReviewCard
                    key={review.id}
                    data-testid="home-review"
                    stars={<RatingStars value={String(review.rating)} />}
                    body={body}
                    attribution={
                      <a
                        href={`/directory/businesses/${review.business.slug}`}
                        className="tap-target text-muted no-underline"
                      >
                        {review.business.name}
                      </a>
                    }
                  />
                );
              })}
            </div>
          </Section>
        ) : null}

        {/* §15b — earn AgriCoins. DECISION: the coins engine exposes no
            public rules endpoint (only authed /coins/balance·history·
            referral-code), so the cards carry i18n copy WITHOUT amounts —
            the coin glyph fills EarnCard's amount slot; real numbers arrive
            when a rules read exists. Never invent amounts. */}
        <Section title={t("agriHome.earn.title")} className="pb-0">
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

        {/* §16 popular searches: OMITTED this pass. The chips may only link
            routes that resolve, and no web-agri route accepts a search query
            today (/search absent, /directory has no index) — query-phrase
            chips pointing elsewhere would mislabel their target. The section
            returns with the search facade. */}

        {/* §17 — big CTA tiles. "Post my need" → /account/inquiries (the
            inquiries surface that exists today; web-agri has no post-need
            route). "List my business" → /business, the real console door. */}
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

        {/* §18 — mandi-alert opt-in: honest door to /notifications (no push
            machinery in web-agri yet — no permission prompt is faked). */}
        <div className="mt-5">
          <MandiAlertCard pincode={pincode} />
        </div>

        {/* §19 PWA band: SKIPPED — web-agri has no manifest/service worker
            (no public/ directory), so an install band would be a lie. It
            arrives with agri's PWA pass. */}

        {/* §20 — FAQ; the same strings are emitted as FAQPage JSON-LD above. */}
        <Section title={t("agriHome.faq.title")}>
          <div className="flex flex-col gap-2">
            {faq.map((item) => (
              <details key={item.q} className="rounded-btn border border-cream-line bg-card px-4">
                <summary className="cursor-pointer list-none py-3.5 text-[13px] font-semibold text-ink">
                  {item.q}
                </summary>
                <div className="pb-3.5 text-[12px] leading-relaxed text-sub">{item.a}</div>
              </details>
            ))}
          </div>
        </Section>

        {/* §20b — weekly digest, SOON state per the build prompt (no reader
            counts, no live subscription): the notify-me control is disabled
            until CP3 wires the real subscription on the Soon landing. */}
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
            organic · coins (→ /notifications, the coins surface milk also
            uses until a coins center exists). */}
        <Section title={t("agriHome.family.title")} className="pb-0">
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
