/**
 * A-U1 — the agri.in A1 home patterns, as shared components.
 *
 * Same contract as home-patterns.tsx (the milk U1 file this sits beside):
 * presentation only — no fetching, no locale routing, no data shapes. The
 * app passes strings and ReactNode slots; the /demo kitchen sink passes the
 * A1 reference's sample literals, and NOWHERE else does sample data live
 * (build prompt §3, honesty rule).
 *
 * Visual truth: docs/design-reference/agri/agri_home_desktop_v1.html
 * (A1 FINAL v4). Section numbers in the comments are that file's.
 *
 * Motion: components that animate participate in the Reveal group
 * (`group-data-[in=…]/reveal:` variants) and every animated style carries a
 * motion-reduce override whose static state keeps the content fully visible
 * — sparklines render drawn, staggered tiles land at opacity 1 (the
 * reference's exact fallback behaviour).
 *
 * One-off colours in the reference map to existing tokens rather than
 * minting new ones (recorded in design-system.md §1.2b): eyebrow amber →
 * coins-fg · earn/tip golds → coins-fg/alert-line · deadline chip red pair
 * → severe-bg/down · crop harvest chip → sponsored badge pair. The
 * sanctioned NEW tokens (up/down/monsoon/severe-*) are §1.2b.
 */
import type { ReactNode } from "react";

import { cn } from "../lib/cn";
import { tintClass, type Tint } from "../components/category-tile";

/* ── A1 polish layer · section eyebrow ─────────────────────────────────── */

/** `.eyebrow`: 10px uppercase tracked label with the 22×2 accent dash. */
export function Eyebrow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mb-[5px] flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.14em] text-coins-fg",
        "before:h-0.5 before:w-[22px] before:rounded-sm before:bg-accent before:content-['']",
        className,
      )}
    >
      {children}
    </div>
  );
}

/* ── §2b · severe-weather alert strip ──────────────────────────────────── */

/**
 * Full-bleed strip under the header. Renders ONLY while an alert is active
 * for the user's district (and, until A-U2, only behind the `agri_today`
 * flag) — the strip itself has no opinion about when that is.
 */
export function SevereAlertStrip({
  icon = "⚠️",
  children,
  action,
  ...rest
}: {
  icon?: string;
  children: ReactNode;
  /** "Details →" link, right-aligned. */
  action?: ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className="border-b border-severe-border bg-severe-bg text-[12px] text-severe-ink"
      {...rest}
    >
      <div className="mx-auto flex max-w-[1140px] items-center gap-2 px-4 py-2">
        <span aria-hidden="true">{icon}</span>
        <span className="min-w-0 flex-1">{children}</span>
        {action ? (
          <span className="ml-auto whitespace-nowrap font-medium">
            {action}
          </span>
        ) : null}
      </div>
    </div>
  );
}

/* ── §7 · mandi card + sparkline ───────────────────────────────────────── */

export type PriceTone = "up" | "down" | "flat";

const chgText: Record<PriceTone, string> = {
  up: "text-up",
  down: "text-down",
  flat: "text-muted",
};

const sparkStroke: Record<PriceTone, string> = {
  up: "stroke-up",
  down: "stroke-down",
  flat: "stroke-muted",
};

/**
 * Maps a price series onto the reference's 110×26 polyline space (evenly
 * spaced x, y inverted, padded). A flat series draws the centre line.
 */
export function sparkPoints(
  values: number[],
  width = 110,
  height = 26,
  pad = 3,
): string {
  if (values.length === 0) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  return values
    .map((v, i) => {
      const x = Math.round(i * step * 10) / 10;
      const y =
        span === 0
          ? height / 2
          : Math.round(
              (pad + (1 - (v - min) / span) * (height - 2 * pad)) * 10,
            ) / 10;
      return `${x},${y}`;
    })
    .join(" ");
}

/**
 * `.spark`: 30-day sparkline. Inside a Reveal, the stroke draws itself on
 * entry (`animate-draw`); before that it is held un-drawn. Outside a Reveal
 * (server HTML, no JS) and under reduced motion it renders fully drawn —
 * the reference's own `stroke-dashoffset` fallback.
 */
export function Spark({
  values,
  tone = "flat",
  className,
}: {
  values: number[];
  tone?: PriceTone;
  className?: string;
}) {
  return (
    <svg
      className={cn("mt-[7px] w-full", className)}
      height={26}
      viewBox="0 0 110 26"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polyline
        fill="none"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={sparkPoints(values)}
        className={cn(
          sparkStroke[tone],
          "group-data-[in=false]/reveal:[stroke-dasharray:120] group-data-[in=false]/reveal:[stroke-dashoffset:120]",
          "group-data-[in=true]/reveal:[stroke-dasharray:120] group-data-[in=true]/reveal:animate-draw",
          "motion-reduce:!animate-none motion-reduce:![stroke-dasharray:none] motion-reduce:![stroke-dashoffset:0]",
        )}
      />
    </svg>
  );
}

/**
 * `.mcard .share` — the WhatsApp share chip, top-right of a mandi card.
 * An anchor to a share URL the caller builds server-side (wa.me text link),
 * so the card needs no client island. The visual chip is small but sits
 * inside a 44px hit box (§1.5 floor; `.tap-target` is barred here because
 * the chip is absolutely positioned).
 */
export function ShareChip({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={label}
      className="absolute right-0 top-0 flex h-11 w-11 items-start justify-end p-2.5 no-underline"
    >
      <span
        aria-hidden="true"
        className="rounded-lg border border-wa-line bg-wa-soft px-2 py-1 text-[11px] leading-none text-wa-deep"
      >
        📤
      </span>
    </a>
  );
}

/**
 * `.mcard`: commodity price card. Everything renders from the payload —
 * market names, as-of stamps and prices are NEVER hardcoded at a call site
 * (honesty rule; the /demo literals are the one sanctioned exception).
 */
export function MandiCard({
  emoji,
  name,
  market,
  price,
  change,
  tone = "flat",
  spark,
  range,
  share,
  className,
  ...rest
}: {
  emoji: string;
  name: string;
  market: string;
  /** Formatted price, e.g. "₹28/kg". */
  price: string;
  /** Formatted change, e.g. "▲ ₹4" / "▼ ₹2" / "—". */
  change: ReactNode;
  tone?: PriceTone;
  /** 30-day series, oldest first. */
  spark?: number[];
  /** "30-day: ₹18–29 · modal ₹24 · arrivals 12,400 qtl" */
  range?: ReactNode;
  /** A ShareChip, when the payload carries a share link. */
  share?: ReactNode;
  className?: string;
} & Omit<React.HTMLAttributes<HTMLDivElement>, "className">) {
  return (
    <div
      className={cn(
        "relative rounded-card border border-cream-line bg-card px-3.5 py-3",
        className,
      )}
      {...rest}
    >
      {share}
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className="text-[22px]">
          {emoji}
        </span>
        <span>
          <b className="block text-[13px] font-medium text-ink">{name}</b>
          <span className="block text-[10px] text-muted">{market}</span>
        </span>
      </div>
      <div className="mt-1.5 font-display text-[19px] font-semibold text-ink">
        {price}{" "}
        <span
          className={cn("font-body text-[11px] font-medium", chgText[tone])}
        >
          {change}
        </span>
      </div>
      {spark ? <Spark values={spark} tone={tone} /> : null}
      {range ? (
        <div className="mt-1 text-[9.5px] text-muted">{range}</div>
      ) : null}
    </div>
  );
}

/** `.live-dot`: mandi freshness pulse beside the source stamp. */
export function LiveDot({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "relative mr-[5px] inline-block h-2 w-2 rounded-full bg-up align-middle",
        "after:absolute after:-inset-1 after:rounded-full after:border-2 after:border-up after:opacity-60 after:content-['']",
        "motion-safe:after:animate-pulse2 motion-reduce:after:hidden",
        className,
      )}
    />
  );
}

/* ── §7b · crop calendar ───────────────────────────────────────────────── */

export type SeasonMonth = {
  label: string;
  /** Month is inside the season window (kharif underline). */
  inSeason?: boolean;
  /** The current month (solid brand). */
  current?: boolean;
};

/**
 * `.season`: months rail + crop-chip rows. The chips and row labels are
 * children (CropChip / SeasonNote) so the card renders exactly what the E5
 * payload contains.
 */
export function SeasonCalendar({
  months,
  children,
  className,
}: {
  months: SeasonMonth[];
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-card border border-cream-line bg-card px-[18px] py-4",
        className,
      )}
    >
      <div aria-hidden="true" className="mb-3 flex gap-1">
        {months.map((m) => (
          <span
            key={m.label}
            className={cn(
              "flex-1 rounded-lg py-1.5 text-center text-[10.5px] text-muted",
              m.inSeason && "[box-shadow:inset_0_-3px_0_var(--brand-soft-2)]",
              m.current && "bg-brand font-medium text-white",
            )}
          >
            {m.label}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

/** `.crop-chip`: sowing (brand-soft) or harvest (sponsored gold) chip. */
export function CropChip({
  harvest = false,
  children,
  className,
}: {
  harvest?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill px-[13px] py-1.5 text-[11.5px] font-medium",
        harvest
          ? "bg-sponsored-bg text-sponsored-fg"
          : "bg-brand-soft text-brand-deep",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** `.season .lbl`: full-width row label between chip groups. */
export function SeasonNote({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("mt-0.5 w-full text-[11px] text-muted", className)}>
      {children}
    </span>
  );
}

/* ── §9 · scheme deadlines bar ─────────────────────────────────────────── */

/** `.deadlines`: red heading + date-chip items + trailing action. */
export function DeadlinesBar({
  heading,
  action,
  children,
  className,
  ...rest
}: {
  heading: ReactNode;
  /** "Set reminders 🔔" link, pushed to the row end. */
  action?: ReactNode;
  children: ReactNode;
  className?: string;
} & Omit<React.HTMLAttributes<HTMLDivElement>, "className">) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-4 rounded-card border border-cream-line bg-card px-4 py-3",
        className,
      )}
      {...rest}
    >
      <span className="flex items-center gap-1.5 whitespace-nowrap text-[12px] font-semibold text-down">
        {heading}
      </span>
      {children}
      {action ? (
        <span className="ml-auto text-[11.5px] font-medium text-brand">
          {action}
        </span>
      ) : null}
    </div>
  );
}

/**
 * `.dl`: one deadline. Nowrap on desktop; wraps below `md` so the long
 * PMFBY 72-hr intimation chip never overflows (build prompt §W1/9).
 */
export function DeadlineItem({
  chip,
  children,
  className,
}: {
  /** The date chip, e.g. "31 AUG" or "72 HRS". */
  chip: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "flex items-center gap-1.5 whitespace-normal text-[11.5px] text-sub md:whitespace-nowrap",
        className,
      )}
    >
      {/* severe-ink, not --down: the down-orange measures 4.43:1 on
          severe-bg at this 10px size — just under the AA floor (axe). */}
      <span className="rounded-pill bg-severe-bg px-[9px] py-0.5 text-[10px] font-semibold text-severe-ink">
        {chip}
      </span>
      {children}
    </span>
  );
}

/* ── §14b · trust pillar ───────────────────────────────────────────────── */

/** `.pillar`: round tinted icon + bold line + sub. */
export function TrustPillar({
  icon,
  tint = "green",
  title,
  sub,
  className,
}: {
  icon: string;
  tint?: Tint;
  title: string;
  sub: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-[11px] rounded-card border border-cream-line bg-card px-4 py-3.5",
        "transition-[transform,box-shadow] duration-150 hover:-translate-y-0.5 hover:shadow-lift motion-reduce:transition-none motion-reduce:hover:translate-y-0",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "flex h-[34px] w-[34px] flex-none items-center justify-center rounded-full text-base",
          tintClass[tint],
        )}
      >
        {icon}
      </span>
      <span>
        <b className="block text-[12.5px] font-medium text-ink">{title}</b>
        <small className="mt-0.5 block text-[10.5px] leading-normal text-muted">
          {sub}
        </small>
      </span>
    </div>
  );
}

/* ── §14b · success story spotlight ────────────────────────────────────── */

/**
 * `.story`: gradient quote panel. `nums` is optional on purpose — until a
 * real consented story replaces the illustrative one, the honest options
 * are marking the quote as illustrative or omitting the number chips
 * (build prompt §W1/14b).
 */
export function StoryCard({
  quote,
  who,
  nums,
  className,
}: {
  quote: ReactNode;
  /** Attribution row: avatar + name + context, built by the caller. */
  who: ReactNode;
  nums?: { value: string; label: string }[];
  className?: string;
}) {
  return (
    <section
      className={cn(
        "relative grid items-center gap-5 overflow-hidden rounded-band [background-color:var(--brand-deep)] bg-cta-gradient p-6 text-white md:grid-cols-[1.6fr_1fr]",
        "before:absolute before:-top-3.5 before:left-3.5 before:font-display before:text-[110px] before:leading-none before:text-white/[.08] before:content-['❝']",
        className,
      )}
    >
      <div>
        <div className="font-display text-[length:clamp(15px,1.8vw,19px)] font-medium leading-normal">
          {quote}
        </div>
        <div className="mt-3 flex items-center gap-2 text-[12px] text-brand-soft-2">
          {who}
        </div>
      </div>
      {nums?.length ? (
        <div className="grid grid-cols-2 gap-2">
          {nums.map((n) => (
            <div
              key={n.label}
              className="rounded-xl border border-white/[.16] bg-white/10 px-3 py-2.5 text-center"
            >
              <b className="block font-display text-xl font-semibold text-coins-bg">
                {n.value}
              </b>
              <small className="text-[10px] text-brand-soft-2">{n.label}</small>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

/* ── §15b · earn AgriCoins card ────────────────────────────────────────── */

/** `.earn`: warm gold card — icon · action · condition · +amount. */
export function EarnCard({
  icon,
  title,
  sub,
  amount,
  className,
}: {
  icon: string;
  title: string;
  sub: string;
  /** "+5" — formatted by the caller from the coins rules engine. */
  amount: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2.5 rounded-card border border-alert-line bg-earn-gradient px-[15px] py-3",
        className,
      )}
    >
      <span aria-hidden="true" className="text-xl">
        {icon}
      </span>
      <span>
        <b className="block text-[12px] font-semibold text-coins-fg">{title}</b>
        <small className="text-[10px] text-coins-fg">{sub}</small>
      </span>
      <span className="ml-auto whitespace-nowrap font-display text-[15px] font-semibold text-coins-fg">
        {amount}
      </span>
    </div>
  );
}

/* ── §8 · tip of the day ───────────────────────────────────────────────── */

/** `.tip-card`: gold tip strip with floating emoji and a trailing action. */
export function TipCard({
  icon = "💡",
  title,
  sub,
  action,
  className,
}: {
  icon?: string;
  title: ReactNode;
  sub: ReactNode;
  /** "More tips →" pill. */
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-band border border-alert-line bg-tip-gradient px-4 py-3",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="text-[22px] motion-safe:animate-float"
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <b className="block text-[12.5px] font-medium text-coins-fg">{title}</b>
        <small className="text-[11px] text-coins-fg">{sub}</small>
      </span>
      {action ? (
        <span className="ml-auto whitespace-nowrap rounded-pill bg-card px-3 py-[5px] text-[11px] text-coins-fg">
          {action}
        </span>
      ) : null}
    </div>
  );
}

/* ── §4 · hero wave divider ────────────────────────────────────────────── */

/** `.hero-wave`: the cream wave that closes the hero ad into the page. */
export function WaveDivider({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={cn(
        "pointer-events-none absolute inset-x-0 -bottom-px h-[26px] w-full",
        className,
      )}
      viewBox="0 0 1440 26"
      preserveAspectRatio="none"
    >
      <path
        d="M0,26 L0,14 C240,2 480,24 720,14 C960,4 1200,22 1440,10 L1440,26 Z"
        className="fill-cream"
      />
    </svg>
  );
}

/* ── §11 · knowledge + news (E6 content engine) ────────────────────────── */

/**
 * `.kcard`: the knowledge tile — media band, category pill, title, meta.
 *
 * `duration` and `play` are OPTIONAL and independent of each other for a
 * reason. Video duration is curator-entered metadata (no keyless official
 * API reports it), so a real video can legitimately arrive without one.
 * The play affordance still renders — it is a video — and the duration
 * chip simply does not, rather than showing a placeholder time.
 */
export function KnowledgeCard({
  href,
  icon,
  tint,
  category,
  title,
  meta,
  duration,
  isVideo = false,
  className,
}: {
  href: string;
  /** Emoji stand-in for artwork, as the reference uses. */
  icon: string;
  tint?: Tint;
  /** The pill: "Guide · Kharif", "Advisory", "▶ Video · Water". */
  category: ReactNode;
  title: ReactNode;
  /** Attribution + read/watch time — built by the caller from data. */
  meta: ReactNode;
  /** "12:40". Omitted when unknown; never a placeholder. */
  duration?: string | null;
  isVideo?: boolean;
  className?: string;
}) {
  return (
    <a
      href={href}
      className={cn(
        "group/kcard block overflow-hidden rounded-card border border-cream-line bg-card no-underline",
        "transition-shadow hover:shadow-lift",
        className,
      )}
    >
      <div
        className={cn(
          "relative flex h-[74px] items-center justify-center text-[30px]",
          tint ? tintClass[tint] : "bg-brand-soft",
        )}
      >
        <span aria-hidden="true">{icon}</span>
        {isVideo ? (
          <span
            aria-hidden="true"
            className={cn(
              "absolute flex h-[34px] w-[34px] items-center justify-center rounded-full",
              "bg-ink/75 pl-[3px] text-[13px] text-white transition-colors",
              "group-hover/kcard:bg-brand",
            )}
          >
            ▶
          </span>
        ) : null}
        {duration ? (
          <span className="absolute bottom-1.5 right-[7px] rounded-[5px] bg-ink/75 px-1.5 py-px text-[9px] text-white">
            {duration}
          </span>
        ) : null}
      </div>
      <div className="px-[11px] py-[9px]">
        <span className="rounded-pill bg-brand-soft px-2 py-0.5 text-[9px] font-semibold text-brand-deep">
          {category}
        </span>
        <b className="my-[5px] mb-[3px] block text-xs font-medium leading-[1.35] text-ink">
          {title}
        </b>
        <div className="text-[10px] text-muted">{meta}</div>
      </div>
    </a>
  );
}

/**
 * `.news-list`: the headline rail beside the knowledge cards.
 *
 * Every row is a LINK OUT to the publisher, and `source` is required, not
 * optional: this component cannot render a headline that does not say
 * whose headline it is.
 */
export function NewsList({
  title,
  items,
  className,
}: {
  title: ReactNode;
  items: {
    id: string;
    href: string;
    headline: ReactNode;
    /** "The Hindu · 2 hrs ago" — publisher and age, always both. */
    source: ReactNode;
  }[];
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-card border border-cream-line bg-card px-3.5 py-3",
        className,
      )}
    >
      <h3 className="mb-2 font-display text-[13px] font-semibold text-ink">
        {title}
      </h3>
      {items.map((item) => (
        <a
          key={item.id}
          href={item.href}
          className="block border-t border-cream-line py-[7px] text-xs leading-[1.45] text-ink no-underline first-of-type:border-t-0 hover:text-brand-deep"
        >
          {item.headline}
          <small className="mt-0.5 block text-[10px] text-muted">
            {item.source}
          </small>
        </a>
      ))}
    </div>
  );
}
