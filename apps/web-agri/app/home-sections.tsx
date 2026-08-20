import type { MandiCommodity, TodayPayload, TranslatedText } from "@agri/types";
import {
  AdCarousel,
  Badge,
  buttonVariants,
  CategoryGroup,
  CategoryTile,
  cn,
  CropChip,
  DeadlineItem,
  DeadlinesBar,
  EmptyState,
  EarnCard,
  Eyebrow,
  KnowledgeCard,
  MandiCard,
  Marquee,
  NewsList,
  RatingStars,
  ReviewCard,
  SeasonCalendar,
  SeasonNote,
  Section,
  SevereAlertStrip,
  ShareChip,
  StatBand,
  StatCell,
  TipCard,
  TodayStrip,
  TodayTile,
  Wrap,
} from "@agri/ui";
import { getLocale, getTranslations } from "next-intl/server";

import { EARN_CARDS, fetchEarnRules } from "@/lib/coins";
import { istHourLabel, nextPullDay } from "@/lib/mandi";
import { formatDuration, pick as pickContent, type ContentKind } from "@/lib/content";
import { helplineStamp } from "@/lib/helplines";
import { HOME_HERO_SLOT } from "@/lib/ads";
import {
  directoryFor,
  helplinesForHome,
  heroAdsFor,
  knowledgeForHome,
  reviewSignalsFor,
  todayFor,
  verticalsForHome,
} from "@/lib/home-data";
import {
  GROUP_LABEL_KEY,
  GROUP_STYLE,
  groupVerticals,
  UNLOCATABLE_M,
} from "@/lib/home";

/**
 * A-U4 W0 — the home's data-bearing sections, one async component each.
 *
 * Before W0 all of this was inline in `page.tsx` behind a single
 * `Promise.all`, so the page emitted nothing until the slowest of eight reads
 * returned and the browser then had to lay out 1,066 elements before the hero
 * could paint. Each export below is now its own Suspense boundary in
 * `page.tsx`: the shell flushes immediately, and a slow section costs only
 * itself.
 *
 * They read through `lib/home-data.ts`, never the raw fetchers, because that
 * module's `cache()` wrappers are what stop independent boundaries turning
 * into duplicate HTTP calls — six of these components ask for the TODAY
 * payload and exactly one request leaves the server.
 *
 * The MARKUP is unchanged from A-U1/A-U3 and is meant to stay that way: W0 is
 * a delivery change, not a redesign, so a reviewer can diff these bodies
 * against the old `page.tsx` and find only the data source moved.
 */

/* ── shared formatters (moved verbatim from page.tsx) ─────────────────────── */

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

const CHANGE_TEXT_CLASS = {
  up: "text-up",
  down: "text-down",
  flat: "text-muted",
} as const;

const INR = new Intl.NumberFormat("en-IN");

/** §11 media stand-ins per content kind. Presentation, not data. */
const KNOWLEDGE_ICON: Record<ContentKind, string> = {
  article: "📰",
  video: "🎬",
  guide: "🌾",
  advisory: "🐛",
};

/** §7 — the mandi-card WhatsApp share text, built SERVER-side from the
 * payload (name/price/change/market/as-of/source — never literals). */
function waShareHref(c: MandiCommodity, locale: string, today: TodayPayload): string {
  const text = `${pickText(locale, c.name)} ₹${c.price}/${c.unit} (${priceChange(c.change).text}) — ${c.market} · ${today.mandi.as_of} · ${today.mandi.source} via agri.in`;
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}

/** The A1 stats format (thousands → Indian grouping + "+"), server-side. */
function statValue(n: number): string {
  return n >= 1000 ? `${n.toLocaleString("en-IN")}+` : String(n);
}

/* ── §2b + §3 · severe strip and the TODAY lead ───────────────────────────── */

/**
 * ABOVE THE FOLD. Streamed rather than awaited in the shell so the header,
 * hero and search band are not held behind the market read — the strip lands
 * in a reserved four-tile envelope (`TodayStripSkeleton`), so it costs no
 * layout shift.
 */
export async function TodayLead({ pincode }: { pincode: string }) {
  const [today, locale, t] = await Promise.all([
    todayFor(pincode),
    getLocale(),
    getTranslations("ui"),
  ]);
  if (!today) return null;

  return (
    <>
      {/* §2b — severe-weather alert strip: ONLY when the payload carries an
          active IMD alert for the visitor's district. */}
      {today.severe_alert ? (
        <SevereAlertStrip
          data-testid="severe-alert-strip"
          action={
            <a href="#weather" className="text-severe-ink no-underline">
              {t("agriHome.today.details")}
            </a>
          }
        >
          <b className="text-severe-ink">{pickText(locale, today.severe_alert.headline)}</b>{" "}
          — {today.severe_alert.district} · {pickText(locale, today.severe_alert.window)}
        </SevereAlertStrip>
      ) : null}

      {/* §3 — TODAY strip (location-first lead, D52): my weather · my mandi ·
          my schemes · ask. No Reveal, no content-visibility (AG-A8 LCP). */}
      <Wrap>
        <section
          aria-label={t("agriHome.today.label")}
          data-testid="today-strip"
          className="mt-3.5"
        >
          <TodayStrip className="max-md:grid-cols-2 md:[grid-template-columns:1.1fr_1.1fr_1.1fr_1fr]">
            {/* Contract v2: weather can be absent (upstream down, cold cache).
                The tile omits itself; the rest of the strip is unaffected. */}
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
    </>
  );
}

/* ── §4 · hero ad ─────────────────────────────────────────────────────────── */

/**
 * ABOVE THE FOLD, and the LCP element. The ad serve cannot be cached (D21
 * per-viewer frequency caps), so W0 streams it instead of blocking first byte
 * on it: the fallback below is the house door, rendered into the SAME
 * `aspect-[1600/420]` box the creative lands in, so loading, empty and full
 * all occupy identical space — zero CLS, which the 0.003 measurement confirms.
 */
export async function HeroAd({ pincode, house }: { pincode: string; house: HouseCopy }) {
  const [locale, t] = await Promise.all([getLocale(), getTranslations("ui")]);
  const heroAds = await heroAdsFor(pincode, locale);
  return (
    <AdCarousel
      slotKey={HOME_HERO_SLOT}
      initialAds={heroAds}
      heightClass="aspect-[1600/420]"
      badgeClassName="right-3 top-3"
      sponsoredLabel={t("badges.sponsored")}
      arrows={{ prevLabel: t("heroAd.prev"), nextLabel: t("heroAd.next") }}
      fallback={<HouseHero {...house} />}
    />
  );
}

export interface HouseCopy {
  title: string;
  cta: string;
}

/**
 * The house door — a first-party banner, not a served creative, so no badge
 * and no beacons (milk's HouseAdCard rule).
 *
 * It takes its copy as PROPS rather than awaiting `getTranslations` itself,
 * and that is load-bearing: a Suspense fallback must be synchronous, and this
 * component is the hero's fallback as well as its empty state. Lighthouse
 * measures the `<b>` below as the home's LCP element, so it has to be in the
 * FIRST flush — if the hero only appeared once the ad serve resolved, we would
 * have moved the largest paint behind a network call to make the page faster,
 * which is the opposite of the point. The shell resolves the two strings (no
 * network) and hands them down; the served creative later replaces this inside
 * the same reserved box.
 */
export function HouseHero({ title, cta }: HouseCopy) {
  return (
    <a
      href="/business"
      className="flex h-full w-full flex-col items-center justify-center gap-2 [background-color:var(--brand-deep)] bg-cta-gradient text-white no-underline"
    >
      {/* A1 `.hero-ad h1` scale (clamp 21–32px): the house door is a real hero
          banner, and the page's largest text block belongs at the top of the
          stream, not mid-page. */}
      <b className="max-w-[15em] px-5 text-center font-display text-[length:clamp(21px,3vw,32px)] font-semibold leading-[1.18]">
        {title}
      </b>
      <span className="rounded-pill bg-accent px-4 py-2 text-[13px] font-bold text-accent-ink">
        {cta}
      </span>
    </a>
  );
}

/** The hero's Suspense fallback: the house door in the SAME
 * `aspect-[1600/420]` box the creative lands in, so the swap costs no layout
 * shift and the LCP text paints in the first flush. */
export function HeroAdFallback({ house }: { house: HouseCopy }) {
  return (
    <div className="aspect-[1600/420] w-full">
      <HouseHero {...house} />
    </div>
  );
}

/* ── §6 · category grid ───────────────────────────────────────────────────── */

export async function CategoryGrid() {
  const [verticals, locale, t] = await Promise.all([
    verticalsForHome(),
    getLocale(),
    getTranslations("ui"),
  ]);
  const groups = groupVerticals(verticals);

  return (
    <Section title={t("agriHome.categories.title")} className="pb-0">
      {/* A1's reveal/stagger/count-up motion is DEFERRED on the home: ~15
          hydration islands walking a 6000px DOM were the measured anchor under
          the AG-A8 0.90 floor. The static state IS the reference's
          reduced-motion fallback; /demo keeps the full motion spec. */}
      <Eyebrow className="-mt-3">
        {/* Count comes from the registry read, never a literal. */}
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
                const label =
                  vertical.name[locale] ?? vertical.name["en"] ?? vertical.slug;
                // UX law 1: EN + mother tongue on every tile.
                const vernacular =
                  locale === "ta"
                    ? (vertical.name["en"] ?? "")
                    : (vertical.name["ta"] ?? "");
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
  );
}

/* ── §6b + §7 · mandi ticker and price cards ──────────────────────────────── */

export async function MandiBlock({ pincode }: { pincode: string }) {
  const [today, locale, t] = await Promise.all([
    todayFor(pincode),
    getLocale(),
    getTranslations("ui"),
  ]);
  if (!today) return null;

  // O1 (AG-A70): the once-a-day pull cadence, FROM the payload. Both the
  // ticker and the §7 stamp render it — the 60 s page cache does not make
  // a daily Agmarknet snapshot real-time, and the page must not imply it.
  const pullHour = istHourLabel(today.mandi.next_pull_hour_ist);

  return (
    <>
      {/* §6b — mandi ticker: every lane item renders from the payload. */}
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
          · {t("agriHome.mandi.tickerCadence", { hour: pullHour })} ·
        </span>
      </Marquee>

      {/* §7 — mandi price cards: first 8 commodities, tone from the sign of
          `change`, 30-day sparkline, range line and share link ALL from the
          payload. */}
      <section id="mandi" aria-label={t("agriHome.mandi.title")} className="pb-2 pt-[22px]">
        <Eyebrow>{t("agriHome.mandi.eyebrow", { source: today.mandi.source })}</Eyebrow>
        <div className="mb-3.5 flex flex-wrap items-baseline justify-between gap-2.5">
          <h2 className="font-display text-xl font-extrabold">{t("agriHome.mandi.title")}</h2>
          {/* A-U2 §2, honest degradation: with no ingested rows there is no
              as-of to stamp, so the strip says so.
              O1 (AG-A70): the stamp is readable, not a 10.5px whisper, and
              carries the daily cadence + next-update line. The LiveDot that
              used to pulse here is GONE — a live-dot over a once-daily
              dataset implies real-time, which is exactly what O1 forbids
              (weather keeps its fresher treatment elsewhere). */}
          {today.mandi.commodities.length > 0 ? (
            <div className="text-right" data-testid="mandi-stamp">
              <span className="block text-[12.5px] font-semibold text-ink">
                {t("agriHome.mandi.stamp", {
                  source: today.mandi.source,
                  asOf: today.mandi.as_of,
                })}
              </span>
              <span className="block text-[11.5px] text-muted">
                {t("agriHome.mandi.cadence", { hour: pullHour })} ·{" "}
                {t("agriHome.mandi.nextUpdate", {
                  hour: pullHour,
                  day: nextPullDay(today.mandi.next_pull_hour_ist),
                })}
              </span>
            </div>
          ) : (
            <span className="text-[10.5px] text-muted">{t("agriHome.mandi.empty")}</span>
          )}
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
                sparkDays={[...c.series_days]}
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
    </>
  );
}

/* ── §7b · kharif calendar ────────────────────────────────────────────────── */

export async function CalendarBlock({ pincode }: { pincode: string }) {
  const [today, locale, t] = await Promise.all([
    todayFor(pincode),
    getLocale(),
    getTranslations("ui"),
  ]);
  if (!today) return null;

  return (
    <section aria-label={t("agriHome.calendar.title")} className="pb-2 pt-[22px]">
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
  );
}

/* ── §8 · weather ─────────────────────────────────────────────────────────── */

export async function WeatherBlock({ pincode }: { pincode: string }) {
  const [today, locale, t] = await Promise.all([
    todayFor(pincode),
    getLocale(),
    getTranslations("ui"),
  ]);
  // Contract v2: `today.weather` is nullable, so an Open-Meteo outage with a
  // cold cache removes THIS section and nothing else.
  if (!today?.weather) return null;
  const weather = today.weather;

  return (
    <section id="weather" aria-label={t("agriHome.weather.title")} className="pb-2 pt-[22px]">
      <Eyebrow>{t("agriHome.weather.eyebrow")}</Eyebrow>
      <h2 className="mb-3.5 font-display text-xl font-extrabold">
        {t("agriHome.weather.title")}
      </h2>
      <div className="grid gap-2.5 md:[grid-template-columns:2fr_1.1fr]">
        <div
          aria-label={t("agriHome.weather.stripLabel")}
          className="flex gap-1.5 overflow-x-auto rounded-card border border-cream-line bg-card px-4 py-3.5"
        >
          {weather.days.map((day, index) => (
            <div
              key={pickText(locale, day.label)}
              className={`min-w-[52px] flex-1 rounded-[10px] px-0.5 py-2 text-center ${
                index === 0 ? "bg-brand-soft" : ""
              }`}
            >
              {/* --muted is 5.09:1 on white but ~4.47:1 on the today cell's
                  --brand-soft, which misses AA by a hair. Only cell 0 has that
                  background, so only cell 0 darkens. */}
              <small className={`block text-[10px] ${index === 0 ? "text-ink" : "text-muted"}`}>
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
        {weather.advisory ? (
          <div className="rounded-card border border-accent bg-trust-bg px-4 py-3.5">
            <b className="mb-[3px] block text-[13px] font-medium text-ink">
              🚿 {pickText(locale, weather.advisory.title)}
            </b>
            <p className="text-[11.5px] leading-[1.55] text-sub">
              {pickText(locale, weather.advisory.body)}
            </p>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-x-4 gap-y-1.5 rounded-card border border-cream-line bg-card px-4 py-3 text-[11px] text-sub md:col-span-2">
          <span>
            💧 {t("agriHome.weather.humidity")}{" "}
            <b className="font-medium text-ink">{weather.humidity_pct}%</b>
          </span>
          <span>
            🌬️ {t("agriHome.weather.wind")}{" "}
            <b className="font-medium text-ink">
              {weather.wind_kmh} km/h {weather.wind_dir}
            </b>
          </span>
          {weather.rain_chance_pct !== null ? (
            <span>
              🌧️ {t("agriHome.weather.rain")}{" "}
              <b className="font-medium text-ink">{weather.rain_chance_pct}%</b>
            </span>
          ) : null}
          {weather.soil_temp_c !== null ? (
            <span>
              🌡️ {t("agriHome.weather.soil")}{" "}
              <b className="font-medium text-ink">{weather.soil_temp_c}°C</b>
            </span>
          ) : null}
          <span>🛰️ {t("agriHome.weather.source", { source: weather.source })}</span>
        </div>
      </div>
      {weather.tip ? (
        <TipCard
          className="mt-2.5"
          title={pickText(locale, weather.tip.title)}
          sub={pickText(locale, weather.tip.body)}
        />
      ) : null}
    </section>
  );
}

/* ── §9 · schemes spotlight + deadlines ───────────────────────────────────── */

export async function SchemesBlock({ pincode }: { pincode: string }) {
  const [today, locale, t] = await Promise.all([
    todayFor(pincode),
    getLocale(),
    getTranslations("ui"),
  ]);
  if (!today) return null;

  return (
    <section id="schemes" aria-label={t("agriHome.schemes.title")} className="pb-2 pt-[22px]">
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
            <a
              href="/notifications"
              className="tap-target inline-flex min-h-[24px] items-center no-underline"
            >
              {t("agriHome.schemes.reminders")} 🔔
            </a>
          }
        >
          {today.schemes.deadlines.map((deadline) => (
            <DeadlineItem
              key={deadline.chip + pickText(locale, deadline.title)}
              chip={deadline.chip}
            >
              <b className="font-medium text-ink">{pickText(locale, deadline.title)}</b>
              {deadline.note ? <> · {pickText(locale, deadline.note)}</> : null}
            </DeadlineItem>
          ))}
        </DeadlinesBar>
      ) : null}
    </section>
  );
}

/* ── §10 · directory row ──────────────────────────────────────────────────── */

export async function DirectoryRow({ pincode }: { pincode: string }) {
  const [directory, { ratings }, t] = await Promise.all([
    directoryFor(pincode),
    reviewSignalsFor(pincode),
    getTranslations("ui"),
  ]);

  return (
    <Section title={t("agriHome.directory.title")} className="pb-0">
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
                {/* Call/WhatsApp are doors to the profile page, where D18's
                    capped, fail-closed contact-reveal flow lives — numbers are
                    never in list payloads. */}
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
  );
}

/* ── §11 · knowledge + news ───────────────────────────────────────────────── */

export async function KnowledgeBlock() {
  const [{ cards: knowledge, news }, locale, t] = await Promise.all([
    knowledgeForHome(),
    getLocale(),
    getTranslations("ui"),
  ]);
  // APPROVED items only — the backend gate means anything rendered here was
  // passed by a human. Nothing approved → the section is ABSENT.
  if (knowledge.length === 0 && news.length === 0) return null;

  const stamp = (item: { source_name: string; published_at: string }) =>
    t("agriHome.knowledge.sourceStamp", {
      source: item.source_name,
      date: new Date(item.published_at).toLocaleDateString(locale, {
        day: "numeric",
        month: "short",
      }),
    });

  return (
    <Section
      title={t("agriHome.knowledge.title")}
      see={t("agriHome.knowledge.all")}
      seeHref="/knowledge"
    >
      <Eyebrow className="-mt-3">{t("agriHome.knowledge.eyebrow")}</Eyebrow>
      <div className="grid gap-3 lg:grid-cols-[2fr_1.2fr]">
        {knowledge.length > 0 ? (
          <div className="grid content-start gap-2.5 max-md:grid-cols-1 md:grid-cols-3">
            {knowledge.map((item) => (
              <KnowledgeCard
                key={item.id}
                href={`/knowledge/${item.slug}`}
                icon={KNOWLEDGE_ICON[item.kind]}
                isVideo={item.kind === "video"}
                // Under the section h2, so h3 here — the same level NewsList
                // uses beside it (the AG-A34 heading-order lesson).
                titleAs="h3"
                duration={formatDuration(item.duration_seconds)}
                category={
                  item.kind === "video"
                    ? `▶ ${t(`knowledge.kinds.${item.kind}`)}`
                    : t(`knowledge.kinds.${item.kind}`)
                }
                title={pickContent(locale, item.title)}
                meta={stamp(item)}
              />
            ))}
          </div>
        ) : null}
        {news.length > 0 ? (
          <NewsList
            title={`📰 ${t("agriHome.knowledge.newsTitle")}`}
            items={news.map((item) => ({
              id: item.id,
              href: `/knowledge/${item.slug}`,
              headline: pickContent(locale, item.title),
              source: stamp(item),
            }))}
          />
        ) : null}
      </div>
    </Section>
  );
}

/* ── §13 · helpline band ──────────────────────────────────────────────────── */

export async function HelplineBand() {
  const [helplines, locale, t] = await Promise.all([
    helplinesForHome(),
    getLocale(),
    getTranslations("ui"),
  ]);
  // Band absent when the dataset is empty: a helpline band with no numbers
  // helps nobody, and a wrong number is worse than none.
  if (helplines.length === 0) return null;

  // The stamp claims something about the WHOLE band, so it carries the OLDEST
  // verification in it.
  const { sources, date } = helplineStamp(helplines);

  return (
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
        {helplines.map((helpline) => (
          <a
            key={helpline.slug}
            href={`tel:${helpline.dial}`}
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-pill border border-cream-line bg-card px-3.5 text-[12px] text-ink no-underline hover:border-brand"
          >
            <b className="font-semibold text-brand-deep">
              {pickContent(locale, helpline.name)}
            </b>{" "}
            {helpline.number}
          </a>
        ))}
      </div>
      <p className="mt-2 text-[9.5px] text-muted">
        {t("agriHome.helplines.verifiedStamp", { sources, date })}
      </p>
    </section>
  );
}

/* ── §14 · stats band ─────────────────────────────────────────────────────── */

/**
 * REAL numbers only (never literals): the vertical count from the registry and
 * the review count summed from the D18 aggregates. The reference's "businesses
 * listed" / "pincodes covered" cells stay OMITTED — covers() returns no total,
 * and a cell without an honest source is not rendered (milk's §16 rule).
 */
export async function StatsBandSection({ pincode }: { pincode: string }) {
  const [verticals, { ratings }, t] = await Promise.all([
    verticalsForHome(),
    reviewSignalsFor(pincode),
    getTranslations("ui"),
  ]);
  if (verticals.length === 0) return null;
  const reviewCount = Object.values(ratings).reduce((sum, r) => sum + r.rating_count, 0);

  return (
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
  );
}

/* ── §15 · reviews strip ──────────────────────────────────────────────────── */

/** Approved-only D18 rows composed from the businesses on this page.
 *
 * Zero reviews → EMPTY-BUT-HONEST (owner direction 2026-08-20, AG-A68), no
 * longer ABSENT: the heading stays, with the moderation note, a coins
 * nudge and a real door into writing one (reviews attach to directory
 * businesses — D18 — so the door is /directory, where the visitor picks
 * the business to review). The reference mockup's three sample quotes are
 * illustrative copy and are NEVER rendered; the coin amount comes from the
 * same rules engine as §15b, and a missing/inactive `review_approved` rule
 * renders the nudge and CTA WITHOUT an amount (the standing A-U1 rule —
 * never a literal 5). */
export async function ReviewsStrip({ pincode }: { pincode: string }) {
  const [{ reviews }, locale, t] = await Promise.all([
    reviewSignalsFor(pincode),
    getLocale(),
    getTranslations("ui"),
  ]);

  if (reviews.length === 0) {
    const rules = await fetchEarnRules();
    const amount = rules["review_approved"]?.amount;
    return (
      <Section title={t("agriHome.reviews.title")}>
        <div
          data-testid="reviews-empty"
          className="rounded-card border border-cream-line bg-card p-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-2.5">
            <p className="m-0 max-w-[58ch] text-[12.5px] leading-[1.55] text-sub">
              {t("agriHome.reviews.emptyNote")}
            </p>
            <span className="rounded-pill bg-coins-bg px-3 py-1.5 text-[11px] font-bold text-coins-fg">
              {amount !== undefined
                ? t("agriHome.reviews.coinsNudge", { amount })
                : t("agriHome.reviews.coinsNudgeNoAmount")}
            </span>
          </div>
          <a
            href="/directory"
            className={cn(
              buttonVariants({ variant: "ghost" }),
              "mt-3 inline-flex flex-none px-4 text-[12.5px] no-underline",
            )}
          >
            {amount !== undefined
              ? t("agriHome.reviews.cta", { amount })
              : t("agriHome.reviews.ctaNoAmount")}
          </a>
        </div>
      </Section>
    );
  }

  return (
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
  );
}


/* ── §15b · earn AgriCoins ────────────────────────────────────────────────── */

/**
 * The A1 earn cards, rendering REAL amounts from the rules engine.
 *
 * A-U1 shipped these with a coin glyph in the amount slot and an explicit
 * note: the coins engine exposed no public rules read, and inventing figures
 * was refused. A-U4 W2 added `GET /coins/rules`, so the number beside each
 * card is now the amount that rule actually pays.
 *
 * Two honesty rules survive into the rendering:
 *  - a card whose rule is missing or inactive shows NO amount rather than a
 *    guess, which is the A-U1 rule unchanged;
 *  - the webinar card has no rule at all (events are Stage D) and carries
 *    the Soon treatment instead of a number — see EARN_CARDS.
 */
export async function EarnCoins() {
  const [rules, t] = await Promise.all([fetchEarnRules(), getTranslations("ui")]);

  return (
    <Section title={t("agriHome.earn.title")} className="pb-0">
      <Eyebrow className="-mt-3">{t("agriHome.earn.eyebrow")}</Eyebrow>
      <div className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
        {EARN_CARDS.map((card) => {
          const rule = card.code ? rules[card.code] : undefined;
          return (
            <EarnCard
              key={card.key}
              icon={card.icon}
              title={t(`agriHome.earn.${card.key}t`)}
              sub={t(`agriHome.earn.${card.key}d`)}
              // No rule -> no number. Never a placeholder that reads like one.
              amount={rule ? `+${rule.amount}` : t("agriHome.soon")}
            />
          );
        })}
      </div>
    </Section>
  );
}
