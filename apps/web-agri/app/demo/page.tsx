import type { SiteTheme } from "@agri/types";
import {
  Avatar,
  Badge,
  BigCtaGrid,
  BigCtaTile,
  BottomNav,
  Button,
  CallButton,
  Card,
  CardsRow,
  CategoryBar,
  CategoryBarLink,
  CategoryGroup,
  CategoryTile,
  CertBar,
  CertCard,
  CoinsPill,
  ConsoleCell,
  ConsoleField,
  ConsoleHeadCell,
  ConsoleModuleCard,
  ConsoleNavItem,
  ConsoleNavList,
  ConsoleNotice,
  ConsolePageHeader,
  ConsolePanel,
  ConsoleRow,
  ConsoleShell,
  ConsoleStatRow,
  ConsoleStatTile,
  ConsoleTable,
  consoleControlClass,
  consoleNavLinkClass,
  EcoPill,
  EcoStrip,
  EmptyState,
  GpsPill,
  HeaderStack,
  HelplineBand,
  IconTile,
  LangSwitcher,
  ListingCard,
  LocationPill,
  Marquee,
  Modal,
  NeedStrip,
  NotificationBell,
  PincodeHero,
  PincodeInput,
  PriceUnit,
  ProductCard,
  ProductGrid,
  ProfileNudge,
  RatingStars,
  ReviewCard,
  SearchBand,
  SearchBar,
  Section,
  Skeleton,
  SponsoredBadge,
  StateChip,
  StatBand,
  StatCell,
  TodayCard,
  TodayStrip,
  TypeFilter,
  TypeFilterRow,
  UtilityLink,
  UtilityStrip,
  VendorCard,
  WhatsAppButton,
  Wrap,
  cn,
} from "@agri/ui";
import { locales, type Locale } from "@agri/ui/i18n";
import { breadcrumbJsonLd, buildMetadata, canonicalUrl, JsonLd } from "@agri/ui/seo";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { NotificationsPanelDemo } from "./notifications-panel-demo";
import { ToastDemo } from "./toast-demo";
import { U1BandsDemo } from "./u1-bands-demo";
import { U2ConfirmDemo } from "./u2-confirm-demo";

export const metadata: Metadata = buildMetadata({
  title: "Design system demo — D02",
  description: "All 18 components and composite patterns, per theme and locale.",
  canonical: canonicalUrl("https://agri.in", "/demo"),
  noIndex: true,
});

const THEMES = ["agri", "milk", "organic"] as const;
type ThemeKey = (typeof THEMES)[number];

function isThemeKey(value: unknown): value is ThemeKey {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value);
}

function Label({ children }: { children: ReactNode }) {
  return (
    <p className="mb-2 mt-5 text-[11px] font-extrabold uppercase tracking-[.06em] text-sub">
      {children}
    </p>
  );
}

export default async function DemoPage({
  searchParams,
}: {
  searchParams: Promise<{ theme?: string | string[] }>;
}) {
  const params = await searchParams;
  const theme: ThemeKey = isThemeKey(params.theme) ? params.theme : "agri";
  const dataTheme: SiteTheme = `theme-${theme}`;
  // Vernacular line stays the mother tongue even when the UI locale is EN
  // (mockup convention); ta/hi rows below prove locale switching.
  const [tEn, tTa, tHi] = await Promise.all([
    getTranslations({ locale: "en", namespace: "ui" }),
    getTranslations({ locale: "ta", namespace: "ui" }),
    getTranslations({ locale: "hi", namespace: "ui" }),
  ]);
  const t = { en: tEn, ta: tTa, hi: tHi } as const;

  return (
    <div data-theme={dataTheme}>
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Home", url: "https://agri.in" },
          { name: "Design demo", url: "https://agri.in/demo" },
        ])}
      />

      {/* theme switcher — server-rendered links, keyboard operable */}
      <div className="sticky top-0 z-[70] flex items-center gap-2 overflow-x-auto bg-ink px-3.5 py-2.5">
        <span className="mr-1 whitespace-nowrap text-[11px] font-bold uppercase tracking-[.1em] text-line">
          Theme
        </span>
        {THEMES.map((key) => (
          <a
            key={key}
            href={`/demo?theme=${key}`}
            aria-current={key === theme ? "page" : undefined}
            className={cn(
              "whitespace-nowrap rounded-pill border-[1.5px] border-sub px-[18px] py-[9px] text-sm font-bold no-underline",
              key === theme ? "border-card bg-card text-ink" : "text-line",
            )}
          >
            {key === "agri" ? "🌾 agri.in" : key === "milk" ? "🥛 milk.in" : "🌿 organicstore.in"}
          </a>
        ))}
      </div>

      <main>
      {/* ═══ composite: utility-strip (U1 §1) ═══ */}
      <UtilityStrip
        tagline="Every milk near you · பால் · दूध"
        links={
          <>
            <UtilityLink href="#">List your business</UtilityLink>
            <UtilityLink href="#">Advertise</UtilityLink>
          </>
        }
        hotline="Post need on WhatsApp: 96000-00000"
      />

      {/* ═══ composite: header stack + searchband ═══ */}
      <HeaderStack
        logo="agri.in"
        tagline="All of agriculture · வேளாண்மை · कृषि"
        location={
          <LocationPill>
            📍 <span className="max-sm:hidden">Coimbatore · 641001</span> ▾
          </LocationPill>
        }
        right={
          <>
            <LangSwitcher label={t.en("lang.label")} />
            <CoinsPill amount="1,240" />
            <Avatar initial="A" aria-label="Profile: @arun" />
          </>
        }
      >
        <SearchBand>
          <SearchBar
            placeholder={t.en("search.placeholder")}
            aria-label={t.en("search.inputLabel")}
            micLabel={t.en("search.micLabel")}
            camLabel={t.en("search.camLabel")}
            showCam
            hint={
              <>
                🎤 Press the mic and <b>speak in Tamil, Hindi or English</b> — no typing needed
              </>
            }
          />
        </SearchBand>
      </HeaderStack>

      <Wrap>
        {/* ═══ composite: today strip ═══ */}
        <Section title="Today · இன்று · आज">
          <TodayStrip>
            <TodayCard
              label="🌤️ Weather · 641001"
              value="31° · Light rain 4pm"
              sub="Good day for spraying till noon"
            />
            <TodayCard
              label="🏪 Mandi · Coimbatore"
              value="Tomato ₹2,340/q ▲6%"
              sub="Coconut ₹11,800 ▼2% · tap for all"
            />
            <TodayCard
              alert
              label="🔔 Your alert"
              value="PM-Kisan installment"
              sub="eKYC deadline in 5 days → check now"
            />
          </TodayStrip>
        </Section>

        {/* ═══ composite: category groups ═══ */}
        <Section title="Everything in one place" see="All 34 categories →" seeHref="#">
          <CategoryGroup label="Buy inputs & machines · உள்ளீடுகள் · सामग्री">
            <CategoryTile href="#" tint="green" icon="🌱" label="Seeds" vernacular="விதைகள்" />
            <CategoryTile href="#" tint="sand" icon="🧪" label="Fertilizers" vernacular="உரங்கள்" />
            <CategoryTile href="#" tint="blush" icon="🛡️" label="Crop protection" vernacular="पौध सुरक्षा" />
            <CategoryTile href="#" tint="peach" icon="🚜" label="Tractors" vernacular="டிராக்டர்" />
            <CategoryTile href="#" tint="bluegray" icon="⚙️" label="Machinery" vernacular="மெஷின்" />
            <CategoryTile href="#" tint="aqua" icon="💧" label="Drip & irrigation" vernacular="சொட்டு நீர்" />
            <CategoryTile href="#" tint="cream" icon="☀️" label="Solar & pumps" vernacular="சோலார்" />
            <CategoryTile href="#" tint="lilac" icon="🛸" label="Drones" vernacular="ड्रोन" />
          </CategoryGroup>
          <CategoryGroup label="Money & support · பணம் · पैसा">
            <CategoryTile href="#" tint="green" icon="🏦" label="Agri loans" vernacular="கடன்" />
            <CategoryTile href="#" tint="blue" icon="☔" label="Crop insurance" vernacular="காப்பீடு" />
            <CategoryTile href="#" tint="gold" icon="🏛️" label="Govt schemes" vernacular="திட்டங்கள்" />
            <CategoryTile href="#" tint="violet" icon="🤝" label="FPO" vernacular="एफपीओ" />
            <CategoryTile href="#" tint="aqua" icon="🌍" label="Carbon credits" vernacular="கார்பன்" />
          </CategoryGroup>
        </Section>

        {/* ═══ composite: helpline band ═══ */}
        <HelplineBand
          icon="📞"
          title="Kisan Call Centre — free help in Tamil"
          sub="உழவர் உதவி எண் · किसान हेल्पलाइन · 6 AM – 10 PM · toll free"
          callLabel="Call 1800-180-1551"
          callHref="tel:18001801551"
        />

        {/* ═══ composite: listing cards ═══ */}
        <Section title="Popular near Coimbatore">
          <CardsRow>
            <ListingCard
              badge={<Badge variant="sponsored" />}
              tint="peach"
              icon="🚜"
              title="Mahindra 575 DI · 45 HP"
              meta="₹6.4L onwards · Compare 4 similar"
              actions={
                <>
                  <Button variant="ghost">{t.en("actions.compare")}</Button>
                  <CallButton label="Dealer" href="tel:1800000000" />
                </>
              }
            />
            <ListingCard
              badge={<Badge variant="verified">{t.en("badges.verified")}</Badge>}
              tint="sand"
              icon="🔬"
              title="AgriSoil Lab, Peelamedu"
              meta={
                <>
                  <RatingStars value="4.6" /> · 2.1 km · Report in 3 days
                </>
              }
              actions={
                <>
                  <Button variant="ghost">Book pickup</Button>
                  <CallButton label={t.en("actions.call")} href="tel:1800000000" />
                </>
              }
            />
            <ListingCard
              badge={<Badge variant="verified">✔ Verified vendor</Badge>}
              tint="blue"
              icon="🐄"
              title="Murugan Dairy Farm"
              meta={
                <>
                  <RatingStars value="4.7" /> (214) · 1.2 km · Fresh cow &amp; A2
                </>
              }
              priceTag={
                <>
                  ₹55/L <PriceUnit>cow</PriceUnit> · ₹110/L <PriceUnit>A2</PriceUnit>
                </>
              }
              extraMeta="🕔 Delivers 5:30–7:30 AM · covers 641001, 641002, 641004"
              actions={
                <>
                  <CallButton label={t.en("actions.call")} href="tel:1800000000" />
                  <WhatsAppButton label={t.en("actions.whatsapp")} href="https://wa.me/910000000000" />
                </>
              }
            />
          </CardsRow>
        </Section>

        {/* ═══ composite: pincode hero (milk pattern) on header gradient ═══ */}
        <Section title="Pincode hero · milk.in pattern">
          <div className="overflow-hidden rounded-band bg-header-gradient">
            <PincodeHero
              title={t.en("pincode.title")}
              subtitle={t.en("pincode.subtitle")}
            >
              <PincodeInput
                defaultValue="641001"
                aria-label={t.en("pincode.inputLabel")}
                findLabel={t.en("pincode.find")}
              />
              <GpsPill>{t.en("pincode.gps")} · என் இடம்</GpsPill>
            </PincodeHero>
          </div>
        </Section>

        {/* ═══ composite: header — flat/nowrap variant (U1 §2) ═══
            No search input: on milk.in search lives in the band below, and
            the brand lockup is two lines with their own line-heights so the
            Tamil/Devanagari tagline cannot collide with the logo. */}
        <Section title="Header · milk.in pattern (flat, no search)">
          <div className="overflow-hidden rounded-band">
            <HeaderStack
              flat
              nowrap
              logo="milk.in"
              tagline="பால் · दूध · every milk near you"
              location={
                <LocationPill>
                  📍 <span className="max-sm:hidden">Coimbatore · 641001</span> ▾
                </LocationPill>
              }
              right={
                <>
                  <LangSwitcher label={t.en("lang.label")} />
                  <CoinsPill amount="1,240" />
                  <Avatar initial="A" aria-label="Profile: @arun" />
                </>
              }
            />
          </div>
        </Section>

        {/* ═══ composite: pincode band — banded variant (U1 §4) ═══ */}
        <Section title="Search band · milk.in pattern (banded)">
          <PincodeHero
            banded
            title={t.en("pincode.title")}
            subtitle={t.en("pincode.subtitle")}
          >
            <PincodeInput
              defaultValue="641001"
              aria-label={t.en("pincode.inputLabel")}
              findLabel={t.en("pincode.find")}
              mic={
                <button
                  type="button"
                  aria-label={t.en("search.micLabel")}
                  className="tap-target px-1 text-[17px] text-brand"
                >
                  <span aria-hidden="true">🎙️</span>
                </button>
              }
            />
            <GpsPill>{t.en("pincode.gps")} · என் இடம்</GpsPill>
          </PincodeHero>
        </Section>

        {/* ═══ composite: category-bar (U1 §5) ═══
            The overflow rule is the binding part: nowrap, horizontal scroll,
            hidden scrollbar, edge fade, and the two attribute filters pinned
            right on desktop / absent below 1024px. Resize to check. */}
        <Section title="Category bar · milk.in pattern">
          <CategoryBar
            label="Dairy categories"
            filters={
              <>
                <CategoryBarLink href="#">🚚 Home delivery</CategoryBarLink>
                <CategoryBarLink href="#">🌿 Organic</CategoryBarLink>
              </>
            }
          >
            <CategoryBarLink href="#" active>
              All milk
            </CategoryBarLink>
            {["Ghee", "Paneer", "Curd", "Yogurt", "Buttermilk", "Cheese", "Butter", "Milk powder"].map(
              (label) => (
                <CategoryBarLink key={label} href="#">
                  {label}
                </CategoryBarLink>
              ),
            )}
          </CategoryBar>
        </Section>

        {/* ═══ composite: type filter row ═══ */}
        <Section title="Type filters · milk.in pattern">
          <TypeFilterRow label="Milk type">
            <TypeFilter active icon="🥛" label="All" vernacular="எல்லாம்" />
            <TypeFilter icon="🐄" label="Cow" vernacular="பசு" />
            <TypeFilter icon="🐃" label="Buffalo" vernacular="எருமை" />
            <TypeFilter icon="✨" label="A2 milk" />
            <TypeFilter icon="🌿" label="Organic" />
            <TypeFilter icon="🧈" label="Curd & ghee" vernacular="தயிர் நெய்" />
            <TypeFilter icon="🏠" label="Home delivery" vernacular="டெலிவரி" />
          </TypeFilterRow>
        </Section>

        {/* ═══ composite: cert bar + product grid (organic patterns) ═══ */}
        <Section title="How to know it's really organic">
          <CertBar>
            <CertCard icon="🇮🇳" title="India Organic (NPOP)" sub="Govt of India certified" />
            <CertCard icon="🤝" title="PGS-India Green" sub="Farmer-group certified" />
            <CertCard icon="🌎" title="USDA Organic" sub="For export-grade products" />
            <CertCard
              gold
              icon="✔️"
              title="We verify every certificate"
              sub="Document checked before badge is shown"
            />
          </CertBar>
        </Section>
        <Section title="Certified products" see="See all →" seeHref="#">
          <ProductGrid>
            <ProductCard
              tint="sage"
              image="🍚"
              cert={<Badge variant="cert">🇮🇳 NPOP ✔</Badge>}
              title="Mapillai Samba Rice 5kg"
              brandLine={
                <>
                  Kovai Naturals · <RatingStars value="4.8" className="text-[11.5px]" />
                </>
              }
              cta={t.en("product.whereToBuy")}
            />
            <ProductCard
              tint="sand"
              image="🫒"
              cert={<Badge variant="cert">🇮🇳 NPOP ✔</Badge>}
              title="Cold-pressed Groundnut Oil 1L"
              brandLine={
                <>
                  Terra Organics · <RatingStars value="4.6" className="text-[11.5px]" />
                </>
              }
              cta={t.en("product.whereToBuy")}
            />
            <ProductCard
              tint="cream"
              image="🍯"
              cert={<Badge variant="cert">🤝 PGS ✔</Badge>}
              title="Wild Forest Honey 500g"
              brandLine={
                <>
                  Nilgiri Bee Farms · <RatingStars value="4.7" className="text-[11.5px]" />
                </>
              }
              cta={t.en("product.whereToBuy")}
            />
            <ProductCard
              tint="blush"
              image="🌶️"
              cert={<Badge variant="cert">🌎 USDA ✔</Badge>}
              title="Turmeric Powder 250g"
              brandLine={
                <>
                  Erode Organics · <RatingStars value="4.9" className="text-[11.5px]" />
                </>
              }
              cta={t.en("product.whereToBuy")}
            />
          </ProductGrid>
        </Section>

        {/* ═══ composite: big CTA tiles + eco strip ═══ */}
        <Section title="Big CTA tiles">
          <BigCtaGrid>
            <BigCtaTile
              href="#"
              icon="📝"
              title="Need daily milk? Tell us once."
              sub={'"1 litre cow milk, every morning, 641001" — nearby vendors will contact YOU. Speak it 🎤 or type it.'}
              cta="Post my need · தேவையை சொல்லுங்கள்"
            />
            <BigCtaTile
              href="#"
              gradient="gold"
              icon="👨‍🌾"
              title="Organic farmer or brand?"
              sub="List your products free. Upload your certificate — we verify it and buyers find you."
              cta="List my products"
            />
          </BigCtaGrid>
        </Section>
        <Section title="Our family · one login works everywhere">
          <EcoStrip>
            <EcoPill href="#" gradient="milk" title="🥛 milk.in" sub="All milk options in your pincode" />
            <EcoPill href="#" gradient="organic" title="🌿 organicstore.in" sub="Certified organic brands & products" />
            <EcoPill href="#" gradient="coins" title="🪙 AgriCoins" sub="Your rewards: 1,240 coins" />
          </EcoStrip>
        </Section>

        {/* ═══ composite: profile nudge (D11) ═══ */}
        <Section title="Profile nudge (D11)">
          <ProfileNudge
            score={60}
            href="#"
            title={t.en("profileNudge.title", { score: 60 })}
            cta={t.en("profileNudge.cta")}
            className="max-w-[420px]"
          />
        </Section>

        {/* ═══ notification center (D12) ═══ */}
        <Section title="Notifications (D12)">
          <Label>Bell — HeaderStack right slot</Label>
          <div className="overflow-hidden rounded-band bg-header-gradient p-4">
            <div className="flex items-center gap-3">
              <NotificationBell label={t.en("notifications.bell")} unread={0} />
              <NotificationBell label={t.en("notifications.bell")} unread={3} />
              <NotificationBell label={t.en("notifications.bell")} unread={120} />
            </div>
          </div>
          <Label>Panel</Label>
          <div className="max-w-[560px]">
            <NotificationsPanelDemo
              strings={{
                title: t.en("notifications.title"),
                empty: t.en("notifications.empty"),
                markAllRead: t.en("notifications.markAllRead"),
                markRead: t.en("notifications.markRead"),
                loadMore: t.en("notifications.loadMore"),
              }}
            />
          </div>
        </Section>

        {/* ═══ remaining primitives ═══ */}
        <Section title="Primitives">
          <Label>Buttons</Label>
          <div className="flex max-w-[560px] gap-2">
            <CallButton label={t.en("actions.call")} href="tel:1800000000" />
            <WhatsAppButton label={t.en("actions.whatsapp")} href="https://wa.me/910000000000" />
            <Button variant="ghost">How to apply · எப்படி</Button>
            <Button variant="brand">{t.en("pincode.find")}</Button>
          </div>
          <Label>Badges &amp; rating</Label>
          <div className="flex items-center gap-2">
            <Badge variant="verified">{t.en("badges.verified")}</Badge>
            <Badge variant="sponsored" />
            <Badge variant="cert">🇮🇳 NPOP ✔</Badge>
            <RatingStars value="4.7" />
          </div>
          <Label>Card (hover lift)</Label>
          <Card hover className="max-w-[320px] p-4">
            <b className="text-[15.5px]">White card · 1px line border</b>
            <p className="text-[12.5px] text-sub">No shadow at rest; lifts −2px on hover.</p>
          </Card>
          <Label>Skeleton — reserves exact final dimensions (CLS 0)</Label>
          <div className="flex max-w-[560px] flex-col gap-2">
            <Skeleton width="100%" height="56px" />
            <div className="flex gap-2">
              <Skeleton width="56px" height="56px" className="rounded-icon" />
              <Skeleton width="calc(100% - 64px)" height="56px" />
            </div>
          </div>
          <Label>Empty state</Label>
          <EmptyState
            className="max-w-[420px]"
            icon="🔍"
            title="No sellers in 641001 yet"
            description="Try a nearby pincode, or post your need and vendors will contact you."
            action={<Button variant="brand">Post my need</Button>}
          />
          <Label>Modal &amp; toast (client islands)</Label>
          <div className="flex max-w-[440px] gap-2">
            <Modal
              trigger={<Button variant="ghost" className="max-w-[220px]">Open modal</Button>}
              title="Check my eligibility"
              description="90% subsidy — drip irrigation (TN) · Deadline Aug 15"
            >
              <div className="flex gap-2">
                <CallButton label={t.en("actions.call")} href="tel:18001801551" />
                <Button variant="ghost">See documents</Button>
              </div>
            </Modal>
            <ToastDemo />
          </div>
        </Section>

        {/* ═══ U1 home patterns ═══
            Every pattern the Milk.in home introduced, as the SAME @agri/ui
            component the page renders — not a copy of its markup. U1's rule
            is "demo and product may never disagree", and the only way to
            guarantee that is to make them the same code. Best viewed with
            ?theme=milk, which is where these were designed. */}
        <Section title="U1 · home patterns (milk)">
          <Label>Need strip — §2b, full-bleed under the header (D25 active need)</Label>
          <div className="-mx-4">
            <NeedStrip
              icon="🥛"
              action={<a href="#" className="no-underline">View →</a>}
            >
              Your need: <b className="text-ink">2L · Cow milk · daily</b> —{" "}
              <b className="text-ink">2 vendors responded</b>
            </NeedStrip>
          </div>

          <Label>Marquee — §5b price ticker; pauses on hover, static under reduced motion</Label>
          <Marquee label="Today's milk prices in 641001">
            <span>Today in 641001</span>
            <span>
              Cow <b className="font-medium text-ink">₹52–58/L</b>
            </span>
            <span>
              Buffalo <b className="font-medium text-ink">₹68–74/L</b>
            </span>
            <span>
              A2 <b className="font-medium text-ink">₹105–120/L</b>
            </span>
            <span>
              <b className="font-medium text-ink">18 sellers in 641001</b>
            </span>
          </Marquee>

          <Label>Stat band — §8b; server-rendered finals, no count-up animation</Label>
          <StatBand label="Marketplace at a glance">
            <StatCell first value="126" label="Verified vendors" />
            <StatCell value="1,204" label="Pincodes covered" />
            <StatCell value="18" label="Sellers near you" />
            <StatCell value="341" label="Reviews" />
          </StatBand>

          <Label>Vendor card — §8/§24; every slot is a different backend</Label>
          <div className="grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
            <VendorCard
              name="Sakthi Dairy Farm"
              badges={
                <>
                  <Badge variant="verified">Verified</Badge>
                  <Badge variant="cert">Recommended</Badge>
                </>
              }
              meta={
                <>
                  <RatingStars value="4.6" />
                  <span>(23)</span>
                  <span aria-hidden="true">·</span>
                  <span>1.4 km</span>
                </>
              }
              prices={
                <>
                  <b className="font-semibold">₹55/L</b> <span className="text-muted">Cow</span>
                  <span aria-hidden="true"> · </span>
                  <b className="font-semibold">₹110/L</b> <span className="text-muted">A2</span>
                </>
              }
              actions={
                <>
                  <CallButton label={t.en("actions.call")} href="tel:18001801551" />
                  <WhatsAppButton label={t.en("actions.whatsapp")} href="#" />
                </>
              }
            />
            {/* A paid card is the same grid cell with a 2px golden border —
                placement and caps are M3's, never the card's. */}
            <VendorCard
              className="border-2 border-ad-border"
              name="Aavin Milk Booth"
              badges={<SponsoredBadge label="★ Sponsored" />}
              meta={<span>0.8 km</span>}
              actions={<CallButton label={t.en("actions.call")} href="tel:18001801551" />}
            />
            {/* U1b: a search hit is the SAME shell, link-wrapped and
                action-less (the whole card is the link — a Call row inside it
                would be a nested control), with the kind pill in the badge
                row and the description in the `body` slot. */}
            <a href="#" className="block no-underline">
              <VendorCard
                className="h-full"
                name="Fresh paneer 200g"
                badges={
                  <span className="rounded-pill bg-ghost px-[9px] py-[3px] text-[11px] font-extrabold text-sub">
                    Product
                  </span>
                }
                meta={
                  <>
                    <span>Sakthi Dairy Farm</span>
                    <span>Coimbatore, Tamil Nadu</span>
                  </>
                }
                body={<span className="line-clamp-2">Soft paneer made fresh every morning.</span>}
                prices={<b className="font-semibold">₹90</b>}
              />
            </a>
          </div>

          <Label>Review card — §8d; approved reviews only, body is locale-keyed</Label>
          <div className="grid gap-2.5 md:grid-cols-3">
            <ReviewCard
              stars={<RatingStars value="5" />}
              body="Fresh milk every morning at 6am, never missed a day."
              attribution="Sakthi Dairy Farm"
            />
            <ReviewCard
              stars={<RatingStars value="4" />}
              body="தினமும் காலையில் நல்ல பால். விலையும் நியாயம்."
              attribution="Anbu Milk Supply"
            />
          </div>

          <Label>Icon tile — §8g service tile (stack) and §8f brand card (row)</Label>
          <div className="flex gap-2.5 overflow-x-auto pb-1">
            {[
              { icon: "🐄", title: t.en("categories.vet") },
              { icon: "🌾", title: "Cattle feed" },
              { icon: "🏭", title: "Dairy farms" },
              { icon: "🤝", title: "Cooperatives" },
            ].map((tile) => (
              <a
                key={tile.title}
                href="#"
                className="w-[118px] flex-none rounded-card border border-cream-line bg-card px-2 py-3.5 text-center no-underline"
              >
                <IconTile icon={tile.icon} title={tile.title} />
              </a>
            ))}
          </div>
          <div className="mt-2.5 grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
            <a href="#" className="rounded-card border border-cream-line bg-card p-3.5 no-underline">
              <IconTile
                variant="row"
                icon="🥛"
                title="Aavin"
                sub="Cow ₹48/L · Buffalo ₹62/L"
                footer="Nearest shops →"
              />
            </a>
          </div>

          <Label>Opt-in bands — §10a price alerts, §10b app install (both dismissible)</Label>
          <U1BandsDemo />
        </Section>

        {/* ═══ U2 console patterns ═══
            The write-side sibling catalog (console-patterns.tsx). Same rule
            as U1: the vendor console renders these SAME components — forms,
            tables, state chips, empty panels, destructive confirms — never a
            copy of their markup. */}
        <Section title="U2 · console patterns (vendor console)">
          <Label>Shell + nav — pill row below sm, w-48 sidebar from sm (one nav, responsive classes only)</Label>
          <div className="overflow-hidden rounded-card border border-line bg-page-bg">
            <ConsoleShell
              navLabel="Business console (demo)"
              heading="Business console"
              nav={
                <ConsoleNavList>
                  {[
                    { title: "Dashboard", active: true },
                    { title: "Lead inbox", active: false },
                    { title: "Listings", active: false },
                    { title: "Products", active: false },
                  ].map((entry) => (
                    <ConsoleNavItem key={entry.title}>
                      <a href="#" className={consoleNavLinkClass(entry.active)}>
                        {entry.title}
                      </a>
                    </ConsoleNavItem>
                  ))}
                </ConsoleNavList>
              }
            >
              <ConsolePageHeader
                title="Dashboard"
                sub="Sakthi Dairy Farm · 641001"
                action={<StateChip tone="info">Premium</StateChip>}
              />
              <ConsoleStatRow label="Last 30 days">
                <ConsoleStatTile value="124" label="Profile views" hint="last 30 days" />
                <ConsoleStatTile value="9" label="Phone reveals" hint="last 30 days" />
                <ConsoleStatTile value="3" label="Open leads" />
                <ConsoleStatTile value="4.6" label="Rating" hint="23 reviews" />
              </ConsoleStatRow>
            </ConsoleShell>
          </div>

          <Label>Module cards — dashboard entries, rendered inside the caller's link</Label>
          <div className="grid gap-2.5 md:grid-cols-2 lg:grid-cols-3">
            <a href="#" className="no-underline">
              <ConsoleModuleCard icon="📥" title="Lead inbox" sub="2 leads waiting" />
            </a>
            <a href="#" className="no-underline">
              <ConsoleModuleCard icon="🏪" title="Listings" sub="Business profile & coverage" />
            </a>
            <a href="#" className="no-underline">
              <ConsoleModuleCard icon="🥛" title="Products" sub="Prices buyers see" />
            </a>
          </div>

          <Label>State chips — every lifecycle state, token pairs only</Label>
          <div className="flex flex-wrap gap-2">
            <StateChip tone="ok">Active</StateChip>
            <StateChip tone="pending">Pending review</StateChip>
            <StateChip tone="alert">Suspended</StateChip>
            <StateChip tone="neutral">Draft</StateChip>
            <StateChip tone="info">Premium</StateChip>
          </div>

          <Label>Form fields — label/control/hint wiring; the error state carries id=&quot;…-error&quot;</Label>
          <ConsolePanel className="max-w-[480px]">
            <div className="flex flex-col gap-3">
              <ConsoleField id="demo-biz-name" label="Business name" hint="Shown on your public page">
                <input
                  id="demo-biz-name"
                  className={consoleControlClass}
                  defaultValue="Sakthi Dairy Farm"
                />
              </ConsoleField>
              <ConsoleField id="demo-pincode" label="Primary pincode" error="Enter a 6-digit pincode">
                <input
                  id="demo-pincode"
                  className={consoleControlClass}
                  defaultValue="6410"
                  aria-invalid="true"
                  aria-describedby="demo-pincode-error"
                />
              </ConsoleField>
              <ConsoleField id="demo-type" label="Business type">
                <select id="demo-type" className={consoleControlClass} defaultValue="vendor">
                  <option value="vendor">Vendor</option>
                  <option value="shop">Shop</option>
                  <option value="farm">Farm</option>
                </select>
              </ConsoleField>
            </div>
          </ConsolePanel>

          <Label>Data table — real table from md, stacked label/value cards below (never an overflow box)</Label>
          <ConsolePanel>
            <ConsoleTable
              caption="Your product listings"
              head={
                <>
                  <ConsoleHeadCell>Product</ConsoleHeadCell>
                  <ConsoleHeadCell>Price</ConsoleHeadCell>
                  <ConsoleHeadCell>Status</ConsoleHeadCell>
                </>
              }
            >
              <ConsoleRow>
                <ConsoleCell label="Product">Cow milk</ConsoleCell>
                <ConsoleCell label="Price">₹55/L</ConsoleCell>
                <ConsoleCell label="Status">
                  <StateChip tone="ok">Active</StateChip>
                </ConsoleCell>
              </ConsoleRow>
              <ConsoleRow>
                <ConsoleCell label="Product">A2 milk</ConsoleCell>
                <ConsoleCell label="Price">₹110/L</ConsoleCell>
                <ConsoleCell label="Status">
                  <StateChip tone="pending">Pending review</StateChip>
                </ConsoleCell>
              </ConsoleRow>
              <ConsoleRow>
                <ConsoleCell label="Product">Paneer 200g</ConsoleCell>
                <ConsoleCell label="Price">₹90</ConsoleCell>
                <ConsoleCell label="Status">
                  <StateChip tone="neutral">Draft</StateChip>
                </ConsoleCell>
              </ConsoleRow>
            </ConsoleTable>
          </ConsolePanel>

          <Label>Empty panel — the existing EmptyState primitive as a panel body (no new shape)</Label>
          <ConsolePanel title="Lead inbox" className="max-w-[480px]">
            <EmptyState
              icon="📥"
              title="No leads yet."
              description="Buyers who post a need in your coverage area appear here."
            />
          </ConsolePanel>

          <Label>Notices — inline save outcomes (ok / alert)</Label>
          <div className="flex max-w-[480px] flex-col gap-2">
            <ConsoleNotice tone="ok">Coverage saved.</ConsoleNotice>
            <ConsoleNotice tone="alert">Could not save — pincode 999999 is not serviceable.</ConsoleNotice>
          </div>

          <Label>Destructive confirm — two-step, names the consequence, soft-delete honest copy</Label>
          <U2ConfirmDemo />
        </Section>

        {/* ═══ locale matrix — icon + EN + vernacular in all 3 locales ═══ */}
        {locales.map((locale: Locale) => (
          <Section key={locale} title={`Locale · ${locale.toUpperCase()}`}>
            <CategoryGroup label={`${t[locale]("today.title")} · ${t[locale]("nav.categories")}`}>
              <CategoryTile href="#" tint="green" icon="🌱" label={t.en("categories.seeds")} vernacular={locale === "en" ? tTa("categories.seeds") : t[locale]("categories.seeds")} />
              <CategoryTile href="#" tint="peach" icon="🚜" label={t.en("categories.tractors")} vernacular={locale === "en" ? tTa("categories.tractors") : t[locale]("categories.tractors")} />
              <CategoryTile href="#" tint="green" icon="🏦" label={t.en("categories.loans")} vernacular={locale === "en" ? tTa("categories.loans") : t[locale]("categories.loans")} />
              <CategoryTile href="#" tint="gold" icon="📈" label={t.en("categories.mandi")} vernacular={locale === "en" ? tTa("categories.mandi") : t[locale]("categories.mandi")} />
              <CategoryTile href="#" tint="blush" icon="🐄" label={t.en("categories.vet")} vernacular={locale === "en" ? tTa("categories.vet") : t[locale]("categories.vet")} />
            </CategoryGroup>
            <div className="mt-3 flex max-w-[560px] gap-2">
              <Button variant="brand">{t[locale]("pincode.find")}</Button>
              <Button variant="ghost">{t[locale]("nav.askAi")}</Button>
              <CallButton label={t[locale]("actions.call")} href="tel:18001801551" />
            </div>
          </Section>
        ))}
        <div className="h-8" />
      </Wrap>
      </main>

      {/* ═══ composite: bottom nav (sticky) ═══ */}
      <BottomNav
        items={[
          { icon: "🏠", label: t.en("nav.home"), href: "#", active: true },
          { icon: "🗂️", label: t.en("nav.categories"), href: "#" },
          { icon: "🎤", label: t.en("nav.askAi"), href: "#", ai: true },
          { icon: "🔔", label: t.en("nav.alerts"), href: "#" },
          { icon: "👤", label: t.en("nav.profile"), href: "#" },
        ]}
      />
    </div>
  );
}
