import {
  CountUp,
  CropChip,
  DeadlineItem,
  DeadlinesBar,
  EarnCard,
  Eyebrow,
  LiveDot,
  MandiCard,
  Reveal,
  SeasonCalendar,
  SeasonNote,
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
} from "@agri/ui";
import type { ReactNode } from "react";

/**
 * A-U1 — the A1 FINAL v4 shapes with the reference's sample data.
 *
 * This section IS the sanctioned home of that sample data (build prompt §3:
 * "that is where reference sample data lives, and nowhere else"). The
 * production home binds the same components to engines/flag stubs and
 * renders nothing when an engine has no data.
 */

function Label({ children }: { children: ReactNode }) {
  return (
    <p className="mb-2 mt-5 text-[11px] font-extrabold uppercase tracking-[.06em] text-sub">
      {children}
    </p>
  );
}

const waShare = (text: string) => `https://wa.me/?text=${encodeURIComponent(text)}`;

export function AU1AgriDemo() {
  return (
    <>
      <Label>
        Severe-weather alert strip — §2b; renders ONLY when an IMD alert is active (flag-gated
        until A-U2). severe-* tokens, full-bleed.
      </Label>
      <div className="-mx-4">
        <SevereAlertStrip action={<a href="#" className="no-underline">Details →</a>}>
          <b className="text-severe-ink">Heavy rain warning</b> — Coimbatore district · next 48
          hrs · கனமழை எச்சரிக்கை
        </SevereAlertStrip>
      </div>

      <Label>
        Today strip — §3, location-first lead (D52): weather · mandi · schemes · ask. The ask
        card is the band-gradient tone.
      </Label>
      <TodayStrip className="max-md:grid-cols-2 md:[grid-template-columns:1.1fr_1.1fr_1.1fr_1fr]">
        <TodayTile
          href="#"
          label="My weather · வானிலை"
          value={<>🌦️ 29°C</>}
          sub="Coimbatore · light rain from Thu"
          go="7-day forecast →"
        />
        <TodayTile
          href="#"
          label="My mandi · சந்தை"
          value={
            <>
              🍅 ₹28/kg <span className="text-[12px] font-medium text-up">▲ ₹4</span>
            </>
          }
          sub="Tomato · Coimbatore market · 6:00 AM"
          go="All 12 commodities →"
        />
        <TodayTile
          href="#"
          label="My schemes · திட்டங்கள்"
          value={<>🏛️ PM-Kisan</>}
          sub="18th instalment credited for 641001 region"
          go="Check your status →"
        />
        <TodayTile
          href="#"
          tone="ask"
          label="Ask agri.in"
          value={<>🎙️ Ask anything</>}
          sub="Crop, price, scheme — Tamil, English, हिन्दी"
          go="Speak or type →"
        />
      </TodayStrip>

      <Label>
        Mandi cards + sparklines — §7; eyebrow + live dot + source stamp render from the
        payload. Cards sit in a Reveal: sparklines draw on entry, render fully drawn under
        reduced motion / without JS. WhatsApp share chip = server-built wa.me link, 44px hit
        box.
      </Label>
      <Reveal>
        <Eyebrow>Market data · Agmarknet live</Eyebrow>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2.5">
          <h3 className="font-display text-lg font-semibold">Mandi prices · சந்தை விலை</h3>
          <span className="text-[10.5px] text-muted">
            <LiveDot />
            Agmarknet · updated today 6:00 AM
          </span>
        </div>
        <div className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
          <MandiCard
            emoji="🍅"
            name="Tomato"
            market="Coimbatore market"
            price="₹28/kg"
            change="▲ ₹4"
            tone="up"
            spark={[20, 21, 20, 22, 22, 24, 23, 26, 28]}
            range="30-day: ₹18–29 · modal ₹24 · arrivals 12,400 qtl"
            share={
              <ShareChip
                label="Share tomato price on WhatsApp"
                href={waShare("Tomato ₹28/kg (▲₹4) — Coimbatore market · 6:00 AM · Agmarknet via agri.in")}
              />
            }
          />
          <MandiCard
            emoji="🧅"
            name="Onion"
            market="Coimbatore market"
            price="₹26/kg"
            change="▼ ₹2"
            tone="down"
            spark={[32, 31, 31, 29, 30, 28, 28, 27, 26]}
            range="30-day: ₹24–34 · modal ₹29 · arrivals 8,150 qtl"
            share={
              <ShareChip
                label="Share onion price on WhatsApp"
                href={waShare("Onion ₹26/kg (▼₹2) — Coimbatore market · 6:00 AM · Agmarknet via agri.in")}
              />
            }
          />
          <MandiCard
            emoji="🌾"
            name="Paddy (common)"
            market="Coimbatore market"
            price="₹23/kg"
            change="—"
            tone="flat"
            spark={[23, 23, 22, 23, 23, 23, 22, 23, 23]}
            range="30-day: ₹22–24 · MSP ₹24.3"
          />
          <MandiCard
            emoji="🟡"
            name="Turmeric"
            market="Erode market"
            price="₹142/kg"
            change="▲ ₹6"
            tone="up"
            spark={[118, 122, 121, 128, 126, 132, 138, 139, 142]}
            range="30-day: ₹118–145 · export demand ↑"
          />
        </div>
      </Reveal>

      <Label>Kharif calendar — §7b; E5-shaped seasonal payload (TN west zone)</Label>
      <SeasonCalendar
        months={[
          { label: "Jun" },
          { label: "Jul", inSeason: true },
          { label: "Aug", inSeason: true, current: true },
          { label: "Sep", inSeason: true },
          { label: "Oct", inSeason: true },
          { label: "Nov" },
          { label: "Dec" },
          { label: "Jan" },
        ]}
      >
        <SeasonNote>🌱 Sowing window open now — TN west zone:</SeasonNote>
        <CropChip>🌾 Samba paddy · till 25 Aug</CropChip>
        <CropChip>🌽 Maize · till 30 Aug</CropChip>
        <CropChip>🥜 Groundnut (rainfed) · till 20 Aug</CropChip>
        <CropChip>🫘 Black gram · till 5 Sep</CropChip>
        <SeasonNote className="mt-2">🌾 Harvesting now:</SeasonNote>
        <CropChip harvest>🧅 Kharif onion · early lots</CropChip>
        <CropChip harvest>🍌 Banana · year-round</CropChip>
      </SeasonCalendar>

      <Label>
        Scheme deadlines bar — §9; incl. the PMFBY 72-hr intimation chip (wraps below md)
      </Label>
      <DeadlinesBar
        heading={<>⏰ Deadlines this month</>}
        action={<a href="#" className="no-underline">Set reminders 🔔</a>}
      >
        <DeadlineItem chip="20 AUG">
          <b className="font-medium text-ink">KCC saturation camp</b> · block offices
        </DeadlineItem>
        <DeadlineItem chip="31 AUG">
          <b className="font-medium text-ink">PMFBY Kharif enrolment</b> closes
        </DeadlineItem>
        <DeadlineItem chip="15 SEP">
          <b className="font-medium text-ink">Drone subsidy</b> FPO applications
        </DeadlineItem>
        <DeadlineItem chip="72 HRS">
          <b className="font-medium text-ink">PMFBY crop-loss intimation</b> · call 14447 within
          72 hrs of damage
        </DeadlineItem>
      </DeadlinesBar>

      <Label>Tip of the day — §8; gold tip strip, floating emoji (static under rm)</Label>
      <TipCard
        title="Tip of the day · இன்றைய குறிப்பு"
        sub="Rain coming Thursday — postpone urea top-dressing; applying before heavy rain loses up to 40% nitrogen to runoff."
        action={<a href="#" className="no-underline">More tips →</a>}
      />

      <Label>Trust pillars — §14b</Label>
      <Reveal className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
        <TrustPillar
          icon="🆓"
          tint="green"
          title="Free for farmers, always"
          sub="Search, prices, schemes, contacts — no charge, no commission on anything"
        />
        <TrustPillar
          icon="✅"
          tint="aqua"
          title="Verification can't be bought"
          sub='Documents checked by our team; paid placement is always labelled "Sponsored"'
        />
        <TrustPillar
          icon="📊"
          tint="blue"
          title="Data with sources & dates"
          sub="Every price stamped Agmarknet, every scheme verified against the official site"
        />
        <TrustPillar
          icon="🔒"
          tint="cream"
          title="Your data stays yours"
          sub="DPDP-compliant: consent-first contact reveal, export & delete anytime"
        />
      </Reveal>

      <Label>
        Success story — §14b; quote marked illustrative until a real consented story replaces
        it (or the number chips are omitted in prod — they are a prop, not baked in)
      </Label>
      <StoryCard
        quote='"Three years I sold tomato at whatever price the commission mandi agent said. Now I check agri.in before loading the tempo — last month alone the difference paid my drip loan EMI." (Illustrative)'
        who={
          <>
            <span
              aria-hidden="true"
              className="flex h-[34px] w-[34px] items-center justify-center rounded-full bg-accent font-semibold text-brand-deep"
            >
              M
            </span>
            <span>
              <b className="text-white">Murugesan P.</b> · 4-acre farmer, Annur · illustrative
              example
            </span>
          </>
        }
        nums={[
          { value: "₹2,340", label: "extra earned last month" },
          { value: "6:15 AM", label: "his daily price alert" },
          { value: "3", label: "vendors compared per sale" },
          { value: "0", label: "commission paid to anyone" },
        ]}
      />

      <Label>Earn AgriCoins — §15b; amounts come from the coins rules engine</Label>
      <div className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
        <EarnCard icon="⭐" title="Write a review" sub="after you contact a business" amount="+5" />
        <EarnCard icon="🎪" title="Attend a webinar" sub="check-in at live events" amount="+10" />
        <EarnCard icon="🤝" title="Refer a farmer" sub="when they verify their number" amount="+25" />
        <EarnCard icon="📅" title="Daily price check" sub="7-day streak bonus" amount="+15" />
      </div>

      <Label>
        Stats band with count-up — §14; server HTML carries the FINAL numbers (SEO/no-JS/rm),
        JS rewinds and eases up on scroll. Prod numbers come from APIs, never literals.
      </Label>
      <StatBand label="Agri.in in numbers">
        <StatCell first value={<CountUp end={36} />} label="verticals, one platform" />
        <StatCell value={<CountUp end={1450} />} label="businesses listed" />
        <StatCell value={<CountUp end={2300} />} label="pincodes covered" />
        <StatCell value={<CountUp end={96} />} label="% questions answered" />
      </StatBand>

      <Label>Eyebrow + wave divider — A1 chrome; the wave closes a brand band into cream</Label>
      <Eyebrow>Official portals · verified links · we never store your records</Eyebrow>
      <div className="relative overflow-hidden rounded-card [background-color:var(--brand-deep)] bg-cta-gradient p-8 text-white">
        <p className="text-[13px] text-brand-soft-2">
          Hero/band surface — the cream wave below is the WaveDivider composite.
        </p>
        <WaveDivider />
      </div>
    </>
  );
}
