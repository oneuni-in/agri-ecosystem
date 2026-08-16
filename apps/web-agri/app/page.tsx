import type { MandiCommodity, TodayPayload, TranslatedText } from "@agri/types";
import {
  AdCarousel,
  Badge,
  BigCtaGrid,
  BigCtaTile,
  Card,
  CategoryGroup,
  CategoryTile,
  CropChip,
  DeadlineItem,
  DeadlinesBar,
  EarnCard,
  EcoPill,
  EcoStrip,
  EmptyState,
  Eyebrow,
  LiveDot,
  LOC_COOKIE,
  MandiCard,
  Marquee,
  RatingStars,
  ReviewCard,
  SeasonCalendar,
  SeasonNote,
  Section,
  SevereAlertStrip,
  ShareChip,
  StatBand,
  StatCell,
  StoryCard,
  TipCard,
  TodayStrip,
  TodayTile,
  TrustPillar,
  WaveDivider,
  Wrap,
} from "@agri/ui";
import { buildMetadata, canonicalUrl } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { cookies } from "next/headers";
import Link from "next/link";

import { HELPLINES } from "@/data/helplines";
import { SARKARI_LINKS } from "@/data/sarkari";
import { HOME_HERO_SLOT, serveAds } from "@/lib/ads";
import {
  fetchDirectoryRow,
  fetchReviewSignals,
  fetchToday,
  fetchVerticals,
  GROUP_LABEL_KEY,
  GROUP_STYLE,
  groupVerticals,
  resolveHomePincode,
  UNLOCATABLE_M,
} from "@/lib/home";

import { HeaderLocation } from "./header-location";
import { MandiAlertCard } from "./mandi-alert-card";

const SITE = "https://agri.in";

// Per-request: the page renders the VISITOR's pincode (their `agri_loc`
// cookie) — same contract as milk's U1 home.
/** The A1 stats format (thousands → Indian grouping + "+"), server-side —
 * the CountUp island's formatCount is client-module-bound, and the band now
 * renders static finals (motion deferred under the AG-A8 floor). */
function statValue(n: number): string {
  return n >= 1000 ? `${n.toLocaleString("en-IN")}+` : String(n);
}

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

/** TranslatedText → the visitor's locale, EN fallback (E5 rule). */
function pickText(locale: string, text: TranslatedText | null | undefined): string {
  if (!text) return "";
  return text[locale as keyof TranslatedText] ?? text.en;
}

/** Signed change → tone + the "▲ ₹4" / "▼ ₹2" / "—" text (A1 `.chg`). */
function priceChange(change: number): { tone: "up" | "down" | "flat"; text: string } {
  if (change > 0) return { tone: "up", text: `▲ ₹${change}` };
  if (change < 0) return { tone: "down", text: `▼ ₹${-change}` };
  return { tone: "flat", text: "—" };
}

const CHANGE_TEXT_CLASS = { up: "text-up", down: "text-down", flat: "text-muted" } as const;

const INR = new Intl.NumberFormat("en-IN");

/** §7 — the mandi-card WhatsApp share text, built SERVER-side from the
 * payload (name/price/change/market/as-of/source — never literals). */
function waShareHref(c: MandiCommodity, locale: string, today: TodayPayload): string {
  const text = `${pickText(locale, c.name)} ₹${c.price}/${c.unit} (${priceChange(c.change).text}) — ${c.market} · ${today.mandi.as_of} · ${today.mandi.source} via agri.in`;
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

/** §10c — the four calculator entry cards; hrefs anchor into /tools. */
const TOOL_CARDS = [
  { key: "emi", icon: "🚜", href: "/tools#emi" },
  { key: "seed", icon: "🌱", href: "/tools#seed-rate" },
  { key: "fert", icon: "🧪", href: "/tools#fertilizer" },
  { key: "spray", icon: "💧", href: "/tools#spray" },
] as const;

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

  // §10 rating meta + §15 strip come from the SAME D18 signals seam milk
  // proved (approved-only is the engine's own guarantee). The signals chain
  // starts the moment the directory read resolves and rides the SAME
  // Promise.all — a serial await here added its whole latency to first byte
  // (AG-A8 TTFB evidence).
  const directoryPromise = fetchDirectoryRow(pincode);
  const signalsPromise = directoryPromise.then((d) => fetchReviewSignals(d, 2));
  const [today, verticals, directory, heroAds, t, { ratings, reviews }] = await Promise.all([
    fetchToday(pincode),
    fetchVerticals(),
    directoryPromise,
    // Served on the SERVER: the hero is the LCP element, and a client fetch
    // delays its image until after hydration (milk's measured 2372ms lesson).
    serveAds(HOME_HERO_SLOT, { pincode, locale }, 5),
    getTranslations("ui"),
    signalsPromise,
  ]);

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
          flag off → `GET /market/today/{pincode}` 404s → fetchToday() is
          null → these sections are ABSENT from the DOM (assert node count,
          not visibility). Flag on: every value below renders FROM the
          payload — prices, stamps, sources, dates — never a literal. */}

      {/* §2b — severe-weather alert strip, full-bleed directly under the
          header: ONLY when the payload carries an active IMD alert for the
          visitor's district. "Details →" anchors the §8 weather section. */}
      {today?.severe_alert ? (
        <SevereAlertStrip
          data-testid="severe-alert-strip"
          action={
            <a href="#weather" className="text-severe-ink no-underline">
              {t("agriHome.today.details")}
            </a>
          }
        >
          <b className="text-severe-ink">{pickText(locale, today.severe_alert.headline)}</b> —{" "}
          {today.severe_alert.district} · {pickText(locale, today.severe_alert.window)}
        </SevereAlertStrip>
      ) : null}

      {/* §3 — TODAY strip, the FIRST section (location-first lead, D52):
          my weather · my mandi · my schemes · ask. ABOVE the fold — no
          Reveal, no content-visibility (the AG-A8 LCP lessons). */}
      {today ? (
        <Wrap>
          <section aria-label={t("agriHome.today.label")} data-testid="today-strip" className="mt-3.5">
            <TodayStrip className="max-md:grid-cols-2 md:[grid-template-columns:1.1fr_1.1fr_1.1fr_1fr]">
              {/* Contract v2: weather can be absent (upstream down, cold
                  cache). The tile omits itself; the rest of the strip —
                  mandi, schemes, ask — is unaffected. */}
              {today.weather ? (
                <TodayTile
                  href="#weather"
                  label={t("agriHome.today.weather")}
                  value={
                    <>
                      {today.weather.condition_icon} {today.weather.temp_c}°C
                    </>
                  }
                  sub={`${today.district ?? today.pincode} · ${pickText(locale, today.weather.condition)}`}
                  go={t("agriHome.today.weatherGo")}
                />
              ) : null}
              {today.mandi.commodities[0] ? (
                <TodayTile
                  href="#mandi"
                  label={t("agriHome.today.mandi")}
                  value={
                    <>
                      {today.mandi.commodities[0].emoji} ₹{today.mandi.commodities[0].price}/
                      {today.mandi.commodities[0].unit}{" "}
                      <span
                        className={`text-[12px] font-medium ${CHANGE_TEXT_CLASS[priceChange(today.mandi.commodities[0].change).tone]}`}
                      >
                        {priceChange(today.mandi.commodities[0].change).text}
                      </span>
                    </>
                  }
                  sub={`${pickText(locale, today.mandi.commodities[0].name)} · ${today.mandi.market} · ${today.mandi.as_of}`}
                  go={t("agriHome.today.mandiGo", { count: today.mandi.commodities.length })}
                />
              ) : null}
              {today.schemes.items[0] ? (
                <TodayTile
                  href="#schemes"
                  label={t("agriHome.today.schemes")}
                  value={<>🏛️ {pickText(locale, today.schemes.items[0].title)}</>}
                  sub={pickText(locale, today.schemes.items[0].body)}
                  go={`${pickText(locale, today.schemes.items[0].link_label)} →`}
                />
              ) : null}
              <TodayTile
                href="/c/experts"
                tone="ask"
                label={t("agriHome.today.ask")}
                value={<>🎙️ {t("agriHome.today.askValue")}</>}
                sub={t("agriHome.today.askSub")}
                go={t("agriHome.today.askGo")}
              />
            </TodayStrip>
          </section>
        </Wrap>
      ) : null}

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
              {/* A1 `.hero-ad h1` scale (clamp 21–32px): the house door is a real
                  hero banner, not a caption — and the page's largest text
                  block belongs at the top of the stream, not mid-page. */}
              <b className="max-w-[15em] px-5 text-center font-display text-[length:clamp(21px,3vw,32px)] font-semibold leading-[1.18]">
                {t("agriHome.hero.houseTitle")}
              </b>
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
          {/* A1's reveal/stagger/count-up motion is DEFERRED on the home:
              ~15 hydration islands walking a 6000px DOM were the measured
              anchor under the AG-A8 0.90 floor (Decision 3 outranks
              decorative motion; the milk StatBand precedent). The static
              state below IS the reference's reduced-motion fallback; /demo
              keeps the full motion spec. Recorded in polish-a1.md §0. */}
          <Eyebrow className="-mt-3">
            {/* Count comes from the registry read, never a literal:
                adding a vertical is a migration, and this line must
                follow it without an app-code change. */}
            {t("agriHome.categories.eyebrow", { count: verticals.length })}
          </Eyebrow>
          {groups.map((group) => {
            const style = GROUP_STYLE[group.key];
            return (
              <div key={group.key}>
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
                  {group.items.map((vertical) => {
                    const label = vertical.name[locale] ?? vertical.name["en"] ?? vertical.slug;
                    // UX law 1: EN + mother tongue on every tile. name.ta is
                    // the vernacular line; on /ta itself (where the label IS
                    // Tamil) the English name takes that slot instead of
                    // duplicating.
                    const vernacular =
                      locale === "ta" ? (vertical.name["en"] ?? "") : (vertical.name["ta"] ?? "");
                    return (
                      <div key={vertical.slug}>
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
              </div>
            );
          })}
          <p className="mt-2.5 text-[11.5px] text-muted">
            <b className="font-semibold text-brand-deep">{t("agriHome.soon")}</b>{" "}
            {t("agriHome.categories.note")}
          </p>
        </Section>

        {/* §6b — mandi ticker: every lane item renders from the payload
            (names, prices, changes), closed by the source + commodity count
            — also from the payload. Marquee handles reduced-motion. */}
        {today ? (
          <Marquee
            data-testid="mandi-ticker"
            label={t("agriHome.mandi.tickerLabel", { market: today.mandi.market })}
            className="mt-4"
          >
            <span className="pl-4">
              {today.mandi.market} · {today.mandi.as_of}
            </span>
            {today.mandi.commodities.map((c) => (
              <span key={c.slug}>
                {pickText(locale, c.name)}{" "}
                <b className="font-medium text-ink">
                  ₹{c.price}/{c.unit}{" "}
                  {c.change > 0 ? `▲${c.change}` : c.change < 0 ? `▼${-c.change}` : "—"}
                </b>
              </span>
            ))}
            <span>
              <b className="font-medium text-ink">
                {today.mandi.source} ·{" "}
                {t("agriHome.mandi.tickerCount", { count: today.mandi.commodities.length })}
              </b>{" "}
              ·
            </span>
          </Marquee>
        ) : null}

        {/* §7 — mandi price cards: first 8 commodities, tone from the sign
            of `change`, 30-day sparkline, range line and the WhatsApp share
            link ALL from the payload. The row stamp (source · updated as-of)
            is data; the LiveDot is the A1 freshness pulse. */}
        {today ? (
          <section
            id="mandi"
            aria-label={t("agriHome.mandi.title")}
            className="pb-2 pt-[22px] [content-visibility:auto] [contain-intrinsic-size:auto_600px]"
          >
            <Eyebrow>{t("agriHome.mandi.eyebrow", { source: today.mandi.source })}</Eyebrow>
            <div className="mb-3.5 flex flex-wrap items-baseline justify-between gap-2.5">
              <h2 className="font-display text-xl font-extrabold">{t("agriHome.mandi.title")}</h2>
              {/* A-U2 §2, honest degradation: with no ingested rows for
                  this area there is no as-of to stamp, so the strip says
                  so instead of rendering a dangling "updated". */}
              <span className="text-[10.5px] text-muted">
                {today.mandi.commodities.length > 0 ? (
                  <>
                    <LiveDot />
                    {t("agriHome.mandi.stamp", {
                      source: today.mandi.source,
                      asOf: today.mandi.as_of,
                    })}
                  </>
                ) : (
                  t("agriHome.mandi.empty")
                )}
              </span>
            </div>
            <div className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
              {today.mandi.commodities.slice(0, 8).map((c) => {
                const change = priceChange(c.change);
                const rangeParts = [
                  t("agriHome.mandi.range", { low: c.range_low, high: c.range_high }),
                  c.modal !== null ? t("agriHome.mandi.modal", { modal: c.modal }) : null,
                  c.arrivals_qtl !== null
                    ? t("agriHome.mandi.arrivals", { qtl: INR.format(c.arrivals_qtl) })
                    : null,
                  c.note ? pickText(locale, c.note) : null,
                ].filter(Boolean);
                return (
                  <MandiCard
                    key={c.slug}
                    data-testid="mandi-card"
                    emoji={c.emoji}
                    name={pickText(locale, c.name)}
                    market={c.market}
                    price={`₹${c.price}/${c.unit}`}
                    change={change.text}
                    tone={change.tone}
                    spark={[...c.series_30d]}
                    range={rangeParts.join(" · ")}
                    share={
                      <ShareChip
                        label={t("agriHome.mandi.share", { name: pickText(locale, c.name) })}
                        href={waShareHref(c, locale, today)}
                      />
                    }
                  />
                );
              })}
            </div>
          </section>
        ) : null}

        {/* §7b — kharif calendar: months rail + sowing/harvest chips from
            the payload's E5-shaped calendar block; zone in the eyebrow. */}
        {today ? (
          <section
            aria-label={t("agriHome.calendar.title")}
            className="pb-2 pt-[22px] [content-visibility:auto] [contain-intrinsic-size:auto_600px]"
          >
            <Eyebrow>
              {t("agriHome.calendar.eyebrow", { zone: pickText(locale, today.calendar.zone) })}
            </Eyebrow>
            <h2 className="mb-3.5 font-display text-xl font-extrabold">
              {t("agriHome.calendar.title")}
            </h2>
            <div>
              <SeasonCalendar
                months={today.calendar.months.map((m) => ({
                  label: m.label,
                  inSeason: m.in_season,
                  current: m.current,
                }))}
              >
                <SeasonNote>
                  🌱 {t("agriHome.calendar.sowing", { zone: pickText(locale, today.calendar.zone) })}
                </SeasonNote>
                {today.calendar.sowing.map((w) => (
                  <CropChip key={w.icon + pickText(locale, w.label)}>
                    {w.icon} {pickText(locale, w.label)}
                    {w.until ? ` · ${pickText(locale, w.until)}` : ""}
                  </CropChip>
                ))}
                <SeasonNote className="mt-2">🌾 {t("agriHome.calendar.harvesting")}</SeasonNote>
                {today.calendar.harvesting.map((w) => (
                  <CropChip harvest key={w.icon + pickText(locale, w.label)}>
                    {w.icon} {pickText(locale, w.label)}
                    {w.until ? ` · ${pickText(locale, w.until)}` : ""}
                  </CropChip>
                ))}
              </SeasonCalendar>
            </div>
          </section>
        ) : null}

        {/* §8 — weather: 7-day strip (first cell = today, brand-soft
            highlight), spray advisory, meta chips and the tip — all payload,
            incl. the source stamp. A1 grid: 2fr / 1.1fr from md.
            Contract v2: `today.weather` is nullable, so an Open-Meteo
            outage with a cold cache removes THIS section and nothing
            else — mandi, the calendar and schemes keep rendering from
            our own tables. */}
        {today?.weather ? (
          <section
            id="weather"
            aria-label={t("agriHome.weather.title")}
            className="pb-2 pt-[22px] [content-visibility:auto] [contain-intrinsic-size:auto_600px]"
          >
            <Eyebrow>{t("agriHome.weather.eyebrow")}</Eyebrow>
            <h2 className="mb-3.5 font-display text-xl font-extrabold">
              {t("agriHome.weather.title")}
            </h2>
            <div className="grid gap-2.5 md:[grid-template-columns:2fr_1.1fr]">
              <div
                aria-label={t("agriHome.weather.stripLabel")}
                className="flex gap-1.5 overflow-x-auto rounded-card border border-cream-line bg-card px-4 py-3.5"
              >
                {today.weather.days.map((day, index) => (
                  <div
                    key={pickText(locale, day.label)}
                    className={`min-w-[52px] flex-1 rounded-[10px] px-0.5 py-2 text-center ${
                      index === 0 ? "bg-brand-soft" : ""
                    }`}
                  >
                    <small className="block text-[10px] text-muted">
                      {pickText(locale, day.label)}
                    </small>
                    <span aria-hidden="true" className="my-1 block text-xl">
                      {day.icon}
                    </span>
                    <b className="text-[11.5px] font-medium">
                      {day.high_c}° / {day.low_c}°
                    </b>
                  </div>
                ))}
              </div>
              {today.weather.advisory ? (
                <div className="rounded-card border border-accent bg-trust-bg px-4 py-3.5">
                  <b className="mb-[3px] block text-[13px] font-medium text-ink">
                    🚿 {pickText(locale, today.weather.advisory.title)}
                  </b>
                  <p className="text-[11.5px] leading-[1.55] text-sub">
                    {pickText(locale, today.weather.advisory.body)}
                  </p>
                </div>
              ) : null}
              <div className="flex flex-wrap gap-x-4 gap-y-1.5 rounded-card border border-cream-line bg-card px-4 py-3 text-[11px] text-sub md:col-span-2">
                <span>
                  💧 {t("agriHome.weather.humidity")}{" "}
                  <b className="font-medium text-ink">{today.weather.humidity_pct}%</b>
                </span>
                <span>
                  🌬️ {t("agriHome.weather.wind")}{" "}
                  <b className="font-medium text-ink">
                    {today.weather.wind_kmh} km/h {today.weather.wind_dir}
                  </b>
                </span>
                {today.weather.rain_chance_pct !== null ? (
                  <span>
                    🌧️ {t("agriHome.weather.rain")}{" "}
                    <b className="font-medium text-ink">{today.weather.rain_chance_pct}%</b>
                  </span>
                ) : null}
                {today.weather.soil_temp_c !== null ? (
                  <span>
                    🌡️ {t("agriHome.weather.soil")}{" "}
                    <b className="font-medium text-ink">{today.weather.soil_temp_c}°C</b>
                  </span>
                ) : null}
                <span>🛰️ {t("agriHome.weather.source", { source: today.weather.source })}</span>
              </div>
            </div>
            {today.weather.tip ? (
              <TipCard
                className="mt-2.5"
                title={pickText(locale, today.weather.tip.title)}
                sub={pickText(locale, today.weather.tip.body)}
              />
            ) : null}
          </section>
        ) : null}

        {/* §9 — schemes spotlight + deadlines bar: level chips, bodies, the
            "verified against · date" stamp and every deadline chip render
            from the payload's E5-shaped schemes block. External links open
            the OFFICIAL portals. */}
        {today ? (
          <section
            id="schemes"
            aria-label={t("agriHome.schemes.title")}
            className="pb-2 pt-[22px] [content-visibility:auto] [contain-intrinsic-size:auto_600px]"
          >
            <Eyebrow>{t("agriHome.schemes.eyebrow")}</Eyebrow>
            <h2 className="mb-3.5 font-display text-xl font-extrabold">
              {t("agriHome.schemes.title")}
            </h2>
            <div className="grid gap-2.5 md:grid-cols-3">
              {today.schemes.items.slice(0, 3).map((scheme) => (
                <div
                  key={scheme.url}
                  data-testid="scheme-card"
                  className="rounded-card border border-cream-line bg-card px-4 py-3.5"
                >
                  <div className="mb-[7px] flex gap-1.5">
                    {scheme.level === "central" ? (
                      <span className="rounded-pill bg-brand-soft px-2 py-0.5 text-[9.5px] font-medium text-brand-deep">
                        {t("agriHome.schemes.central")}
                      </span>
                    ) : (
                      <span className="rounded-pill bg-sponsored-bg px-2 py-0.5 text-[9.5px] font-medium text-sponsored-fg">
                        {pickText(locale, scheme.state_label) || t("agriHome.schemes.state")}
                      </span>
                    )}
                  </div>
                  <b className="block text-[13.5px] font-medium text-ink">
                    {pickText(locale, scheme.title)}
                  </b>
                  <p className="mb-2 mt-1 text-[11.5px] leading-[1.55] text-sub">
                    {pickText(locale, scheme.body)}
                  </p>
                  <span className="block text-[9.5px] text-muted">
                    {t("agriHome.schemes.verifiedStamp", {
                      domain: scheme.verified_against,
                      date: scheme.verified_on,
                    })}
                  </span>
                  <a
                    href={scheme.url}
                    target="_blank"
                    rel="noopener"
                    className="tap-target mt-1.5 inline-block text-[11.5px] font-medium text-brand no-underline"
                  >
                    {pickText(locale, scheme.link_label)} →
                  </a>
                </div>
              ))}
            </div>
            {today.schemes.deadlines.length > 0 ? (
              <DeadlinesBar
                data-testid="deadlines-bar"
                className="mt-2.5"
                heading={<>⏰ {t("agriHome.schemes.deadlines")}</>}
                action={
                  <a href="/notifications" className="tap-target no-underline">
                    {t("agriHome.schemes.reminders")} 🔔
                  </a>
                }
              >
                {today.schemes.deadlines.map((deadline) => (
                  <DeadlineItem key={deadline.chip + pickText(locale, deadline.title)} chip={deadline.chip}>
                    <b className="font-medium text-ink">{pickText(locale, deadline.title)}</b>
                    {deadline.note ? <> · {pickText(locale, deadline.note)}</> : null}
                  </DeadlineItem>
                ))}
              </DeadlinesBar>
            ) : null}
          </section>
        ) : null}

        {/* §9b — sarkari services hub: REAL in this pass, flag-independent.
            Deep links to OFFICIAL portals only (data/sarkari.ts, checked by
            scripts/check-sarkari-links.mjs — AG-A11). We link, we never
            fetch or store anyone's records (DPDP). Domain + verified stamp
            render from the data file. */}
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
            nearest first, from the public covers() read. Organic only: milk
            injects sponsored listings via its M3.B slot, but no agri
            sponsored-listing slot is registered — nothing is injected until a
            real campaign can serve (honesty rule). Call/WhatsApp are doors to
            the profile page, where D18's capped, fail-closed contact-reveal
            flow lives — numbers are never in list payloads. */}
        <Section title={t("agriHome.directory.title")} className="pb-0 [content-visibility:auto] [contain-intrinsic-size:auto_600px]">
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
        <Section title={t("agriHome.how.title")} className="[content-visibility:auto] [contain-intrinsic-size:auto_600px]">
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

        {/* §10c — farm calculators entry (A1 .tools-grid): REAL doors into
            /tools, the client-side offline calculators the `farm-tools`
            registry vertical points at. */}
        <section
          aria-label={t("agriHome.toolsRow.title")}
          className="pb-2 pt-[22px] [content-visibility:auto] [contain-intrinsic-size:auto_600px]"
        >
          <Eyebrow>{t("agriHome.toolsRow.eyebrow")}</Eyebrow>
          <div className="mb-3.5 flex items-baseline justify-between gap-2.5">
            <h2 className="font-display text-xl font-extrabold">{t("agriHome.toolsRow.title")}</h2>
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
        <Section title={t("agriHome.community.title")} className="[content-visibility:auto] [contain-intrinsic-size:auto_600px]">
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
            <Link
              href="/c/experts"
              prefetch={false}
              className="inline-flex min-h-[44px] items-center rounded-pill bg-accent px-[18px] text-[13.5px] font-bold text-accent-ink no-underline"
            >
              {t("agriHome.ask.cta")}
            </Link>
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
              value={statValue(verticals.length)}
              label={t("agriHome.stats.verticals")}
            />
            {reviewCount > 0 ? (
              <StatCell value={statValue(reviewCount)} label={t("agriHome.stats.reviews")} />
            ) : null}
          </StatBand>
        ) : null}

        {/* §14b — trust pillars (static i18n) + the success story, which is
            marked ILLUSTRATIVE in copy and carries NO number chips in prod
            (nums omitted until a real consented story replaces it). */}
        <Section title={t("agriHome.pillars.title")} className="pb-0 [content-visibility:auto] [contain-intrinsic-size:auto_600px]">
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
            businesses on this page; zero reviews → section ABSENT. */}
        {reviews.length > 0 ? (
          <Section title={t("agriHome.reviews.title")} className="[content-visibility:auto] [contain-intrinsic-size:auto_600px]">
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
        <Section title={t("agriHome.earn.title")} className="pb-0 [content-visibility:auto] [contain-intrinsic-size:auto_600px]">
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
        <Section title={t("agriHome.faq.title")} className="[content-visibility:auto] [contain-intrinsic-size:auto_600px]">
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
        <Section title={t("agriHome.family.title")} className="pb-0 [content-visibility:auto] [contain-intrinsic-size:auto_600px]">
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
