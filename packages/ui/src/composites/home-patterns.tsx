/**
 * The U1 home patterns, as shared components.
 *
 * These live here rather than inside web-milk for one reason: U1's rule is
 * "every new pattern lands in the kitchen sink FIRST as a named section —
 * demo and product may never disagree". A pattern that exists only in the app
 * cannot be shown in the catalog without copying its markup, and a copy is a
 * disagreement waiting to happen. Everything here is presentation only: no
 * fetching, no locale routing, no data shapes. The app passes strings and
 * `ReactNode` slots; the catalog passes literals.
 *
 * Links are slots (`ReactNode`), never `href` props, because web-milk routes
 * through next-intl's locale-aware `Link` and the catalog uses plain anchors.
 */
import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/* ── §5b · marquee ─────────────────────────────────────────────────────── */

/**
 * Shell + ink per tone. The ink lives on the inner track, which callers cannot
 * reach through `className`, so a tone has to be a prop rather than a class
 * the app tacks on — otherwise the background changes and the text does not.
 *
 * `gold` reuses the golden family already carrying paid and coins surfaces
 * rather than introducing a colour: `tint-gold` behind `accent-ink`, bordered
 * with `certgold-line`. That ink-on-tint pairing measures about 11:1, so it
 * clears AA with room to spare at this 12px size.
 */
const MARQUEE_TONES = {
  brand: { shell: "border-brand-soft-2 bg-brand-soft", ink: "text-brand-deep" },
  gold: { shell: "border-certgold-line bg-tint-gold", ink: "text-accent-ink" },
} as const;

/**
 * A seamless horizontal marquee. Renders its children TWICE and translates the
 * track by -50%, so the second copy arrives exactly as the first leaves; the
 * duplicate is `aria-hidden` so assistive tech reads the content once.
 *
 * Motion is CSS only (`animation-ticker` in the preset) and pauses on hover.
 * Under `prefers-reduced-motion` the animation is removed entirely and the
 * strip degrades to a static row — no JS, no media-query listener.
 */
export function Marquee({
  children,
  label,
  className,
  tone = "brand",
  ...rest
}: {
  children: ReactNode;
  /** Accessible name for the strip, e.g. "Today's milk prices in 641001". */
  label: string;
  className?: string;
  /** Colour family. `brand` is the default; `gold` marks the live strip. */
  tone?: keyof typeof MARQUEE_TONES;
} & Omit<React.HTMLAttributes<HTMLDivElement>, "children" | "className">) {
  const palette = MARQUEE_TONES[tone];
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-pill border",
        palette.shell,
        className,
      )}
      aria-label={label}
      {...rest}
    >
      <div
        className={cn(
          "flex w-max animate-ticker gap-[34px] whitespace-nowrap py-2 text-[12px] hover:[animation-play-state:paused] motion-reduce:[animation:none]",
          palette.ink,
        )}
      >
        {children}
        <span aria-hidden="true" className="contents">
          {children}
        </span>
      </div>
    </div>
  );
}

/* ── §8b · stats band ──────────────────────────────────────────────────── */

/**
 * Equal-width stat cells, 2-up on mobile and n-up from `md`. Deliberately no
 * count-up animation: the reference animates from 0 on scroll, which needs a
 * client island and repaints text mid-scroll for a number that is already
 * final when the HTML is sent.
 */
export function StatBand({
  children,
  label,
  className,
  ...rest
}: {
  children: ReactNode;
  label: string;
  className?: string;
} & Omit<React.HTMLAttributes<HTMLElement>, "children" | "className">) {
  return (
    <section
      aria-label={label}
      // Solid `bg-cert-bg`, not the softer `bg-cert-bg/40` this started as. An
      // alpha background is not resolvable by contrast tooling: WebKit hands
      // axe the alpha value and it falls back to an unrelated ancestor,
      // reporting the 6.8:1 cert-fg pairing as 1.56:1. The tint is a token
      // either way.
      className={cn("flex flex-wrap rounded-card border border-cert-bg bg-cert-bg", className)}
      {...rest}
    >
      {children}
    </section>
  );
}

export function StatCell({
  value,
  label,
  first = false,
}: {
  /** A string for a static band; agri's A-U1 band passes a `<CountUp>`. */
  value: ReactNode;
  label: string;
  /** Suppresses the divider. The caller knows the index; the cell does not. */
  first?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex-1 basis-1/2 px-2 py-4 text-center md:basis-0",
        first ? "" : "md:border-l md:border-cream-line",
      )}
    >
      <b className="block font-display text-2xl font-extrabold text-cert-fg">{value}</b>
      <small className="text-[11px] text-sub">{label}</small>
    </div>
  );
}

/* ── §2b · need strip ──────────────────────────────────────────────────── */

/**
 * Full-bleed status strip directly under the header. Used for the D25
 * active-need line; the strip has no opinion about what the status is, only
 * that it is one line with an action at the end.
 */
export function NeedStrip({
  icon,
  children,
  action,
  ...rest
}: {
  icon: string;
  children: ReactNode;
  action: ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className="border-b border-brand-soft-2 bg-brand-soft text-[12px] text-brand-deep"
      {...rest}
    >
      <div className="mx-auto flex max-w-[1140px] items-center gap-2 px-4 py-2">
        <span aria-hidden="true">{icon}</span>
        <span className="min-w-0 flex-1 truncate">{children}</span>
        <span className="ml-auto whitespace-nowrap font-medium text-brand">{action}</span>
      </div>
    </div>
  );
}

/* ── §10a · alert card ─────────────────────────────────────────────────── */

/** A single-line opt-in card: icon, title, sub, one action, one dismiss. */
export function AlertCard({
  icon,
  title,
  sub,
  action,
  dismissLabel,
  onDismiss,
  ...rest
}: {
  icon: string;
  title: string;
  sub: string;
  action: ReactNode;
  dismissLabel: string;
  onDismiss: () => void;
} & Omit<React.HTMLAttributes<HTMLElement>, "title">) {
  return (
    <section
      className="flex items-center gap-3 rounded-card border border-cream-line bg-card px-4 py-3.5"
      {...rest}
    >
      <span aria-hidden="true" className="text-2xl">
        {icon}
      </span>
      <span className="flex-1">
        <b className="block text-[13px] font-medium text-ink">{title}</b>
        <small className="text-[11px] text-muted">{sub}</small>
      </span>
      {action}
      <button type="button" aria-label={dismissLabel} onClick={onDismiss} className="tap-target text-muted">
        ✕
      </button>
    </section>
  );
}

/* ── §10b · app band ───────────────────────────────────────────────────── */

/** The dark gradient install band. Stacks below `md`, where the reference
 * drops the spacer and lets the button sit under the copy. */
export function AppBand({
  icon,
  title,
  sub,
  action,
  dismissLabel,
  onDismiss,
  ...rest
}: {
  icon: string;
  title: string;
  sub: string;
  /** Absent on iOS Safari, which never fires `beforeinstallprompt` — there the
   * `sub` carries the Add-to-Home-Screen instruction instead. */
  action?: ReactNode;
  dismissLabel: string;
  onDismiss: () => void;
} & Omit<React.HTMLAttributes<HTMLElement>, "title">) {
  return (
    <section
      // A solid background-color UNDER the gradient, not instead of it. axe
      // cannot see through a `background-image` gradient, so it computes the
      // band's copy against the page's cream and reports 1.5:1 for a pairing
      // that actually measures 5.7:1. Painting the gradient's dark end as the
      // element's background-color gives the tooling something true to read,
      // and is invisible: the gradient covers it. Written as an arbitrary
      // property because `cn()` runs tailwind-merge, which cannot tell that
      // `bg-cta-gradient` is an image — it classes both as background-color
      // and silently DROPS `bg-brand-deep` (verified).
      className="flex flex-col items-start gap-4 rounded-card [background-color:var(--brand-deep)] bg-cta-gradient p-5 text-white md:flex-row md:items-center"
      {...rest}
    >
      <span aria-hidden="true" className="text-[34px]">
        {icon}
      </span>
      <div className="flex-1">
        <b className="block font-display text-[17px] font-semibold">{title}</b>
        <p className="mt-1 text-[12px] text-brand-soft-2">{sub}</p>
      </div>
      {action}
      <button
        type="button"
        aria-label={dismissLabel}
        onClick={onDismiss}
        className="tap-target text-brand-soft-2"
      >
        ✕
      </button>
    </section>
  );
}

/* ── §8d · review card ─────────────────────────────────────────────────── */

/** One approved review: stars, body, and an attribution slot (a link to the
 * business in the app, plain text in the catalog). */
export function ReviewCard({
  stars,
  body,
  attribution,
  ...rest
}: {
  stars: ReactNode;
  body: string;
  attribution: ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className="rounded-card border border-cream-line bg-card p-3.5" {...rest}>
      {stars}
      <p className="my-2 text-[12px] leading-relaxed text-ink">{body}</p>
      <span className="text-[11px] text-muted">{attribution}</span>
    </div>
  );
}

/* ── §8f/§8g · icon tile ───────────────────────────────────────────────── */

/**
 * Icon disc + title, with two shapes:
 *   `stack` — the §8g service tile: fixed width, centred, horizontally scrolled
 *   `row`   — the §8f brand card: icon beside the copy, optional footer button
 *
 * Rendered inside whatever link element the caller supplies, so the tile never
 * needs to know about locale-prefixed routing.
 */
export function IconTile({
  icon,
  title,
  sub,
  footer,
  variant = "stack",
}: {
  icon: string;
  title: string;
  sub?: ReactNode;
  footer?: ReactNode;
  variant?: "stack" | "row";
}) {
  if (variant === "stack") {
    return (
      <>
        <span
          aria-hidden="true"
          className="mx-auto mb-1.5 flex h-11 w-11 items-center justify-center rounded-icon bg-brand-soft text-[22px]"
        >
          {icon}
        </span>
        <b className="block text-[11.5px] font-semibold text-ink">{title}</b>
      </>
    );
  }
  return (
    <>
      <span className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="flex h-11 w-11 flex-none items-center justify-center rounded-icon bg-brand-soft text-xl"
        >
          {icon}
        </span>
        <span>
          <b className="block text-[13.5px] font-semibold text-ink">{title}</b>
          <span className="block text-[11px] leading-relaxed text-sub">{sub}</span>
        </span>
      </span>
      {footer ? (
        <span className="mt-2.5 block rounded-btn border border-cream-line bg-cream-deep py-2 text-center text-[12px] font-semibold text-ink">
          {footer}
        </span>
      ) : null}
    </>
  );
}

/* ── §8/§24 · vendor card ──────────────────────────────────────────────── */

/**
 * The rich vendor card shell. Slot-based on purpose: the badges, the rating
 * stars, the per-type price line and the two action buttons are all built by
 * the caller, because each is bound to a different backend (D18 aggregates,
 * M3.C recommendations, the product listings, the D18 reveal gate). What is
 * shared — and what drifts if it is copied — is the frame: spacing, the
 * heading size, the meta row, the 40px action pair.
 */
export function VendorCard({
  badges,
  name,
  meta,
  body,
  prices,
  actions,
  className,
  ...rest
}: {
  badges?: ReactNode;
  name: string;
  meta?: ReactNode;
  /** Free descriptive line (e.g. a search hit's description) — clamped by the
   * caller if needed; sits between the meta row and the price line. */
  body?: ReactNode;
  prices?: ReactNode;
  /** Optional: an action-less card (a search hit wrapped in its own link)
   * simply omits the row rather than rendering an empty 44px band. */
  actions?: ReactNode;
  className?: string;
} & Omit<React.HTMLAttributes<HTMLDivElement>, "className">) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 rounded-card border border-cream-line bg-card p-4 transition-shadow hover:shadow-lift",
        className,
      )}
      {...rest}
    >
      {badges ? <div className="flex flex-wrap items-center gap-1.5">{badges}</div> : null}
      <h3 className="text-[15.5px] font-extrabold leading-[1.3] text-ink">{name}</h3>
      {meta ? (
        <p className="flex flex-wrap items-center gap-1.5 text-[12.5px] text-muted">{meta}</p>
      ) : null}
      {body ? <p className="text-[13px] leading-relaxed text-sub">{body}</p> : null}
      {prices ? <p className="text-[13px] text-ink">{prices}</p> : null}
      {actions ? <div className="mt-1 flex gap-2">{actions}</div> : null}
    </div>
  );
}
