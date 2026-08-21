/**
 * The U2 console patterns, as shared components.
 *
 * A SIBLING catalog to `home-patterns.tsx`, not an extension of it: console
 * and consumer share tokens; they do not share shapes. The consumer catalog
 * holds read-side marketing surfaces; this one holds the write-side console —
 * forms, tables, state chips, empty panels, destructive-action confirms.
 * Stretching one file to hold both would blur the rule that makes the demo
 * verifiable: the kitchen sink and the product render the SAME code.
 *
 * Everything here is presentation only: no fetching, no locale routing, no
 * data shapes. The app passes strings and `ReactNode` slots; the catalog
 * passes literals. Links are slots (`ReactNode`) or class recipes
 * (`consoleNavLinkClass`), never `href` props, because the console routes
 * through Next's `Link` and the catalog uses plain anchors.
 */
import type { ReactNode } from "react";

import { Button } from "../components/button";
import { EmptyState } from "../components/empty-state";
import { cn } from "../lib/cn";

/* ── shell ─────────────────────────────────────────────────────────────── */

/**
 * The console frame: a horizontally scrollable pill row above the content
 * below `sm:` (design-system UX law #2 — nothing hidden behind a hamburger),
 * the classic w-48 sidebar from `sm:` up. One `<nav>`, responsive classes
 * only — the D26/M5 lesson, kept as the catalog shape so it cannot drift.
 */
export function ConsoleShell({
  navLabel,
  heading,
  brand,
  nav,
  footer,
  children,
  ...rest
}: {
  /** Accessible name for the nav landmark, e.g. "Business console". */
  navLabel: string;
  /** Sidebar heading (hidden below `lg:`, where the pill row speaks for itself). */
  heading: string;
  /** A-U7: the business switcher card above the nav (`ConsoleSidebarBrand`). */
  brand?: ReactNode;
  /** The module list — a `ConsoleNavList` of links. */
  nav: ReactNode;
  /** A-U7: the sidebar's foot note, desktop only. */
  footer?: ReactNode;
  children: ReactNode;
} & Omit<React.HTMLAttributes<HTMLDivElement>, "children">) {
  return (
    <div className="lg:grid lg:grid-cols-[218px_minmax(0,1fr)]" {...rest}>
      {/* A-U7 (A3 reference `.side`): a real white rail on the cream page from
          `lg:` up, and the SAME horizontally scrollable row below it — nothing
          hidden behind a hamburger (design-system UX law #2). `sticky top-0`
          rather than the reference's fixed 34px offset, because the console
          sits under the site header, whose height is not a constant. */}
      <nav
        aria-label={navLabel}
        className={cn(
          "flex gap-1.5 overflow-x-auto border-b border-cream-line bg-card px-3.5 py-2.5",
          "lg:sticky lg:top-0 lg:block lg:h-screen lg:gap-0 lg:overflow-y-auto lg:border-b-0 lg:border-r lg:px-3 lg:py-4",
        )}
      >
        <p className="sr-only">{heading}</p>
        {brand ? <div className="flex-none lg:mb-3.5">{brand}</div> : null}
        {nav}
        {footer ? (
          <div className="mt-3.5 hidden border-t border-cream-line pt-3 text-[10.5px] leading-relaxed text-muted lg:block">
            {footer}
          </div>
        ) : null}
      </nav>
      <div className="min-w-0 px-3.5 pb-10 pt-4 lg:px-6 lg:pt-5">{children}</div>
    </div>
  );
}

/**
 * A-U7 (A3 `.side .biz-sw`): the sidebar's business switcher.
 *
 * Presentation only — the caller supplies whatever control actually switches
 * business (a `<select>`, a link, or nothing at all when the account owns
 * one business and there is nothing to switch between).
 */
export function ConsoleSidebarBrand({
  icon,
  name,
  sub,
  control,
}: {
  icon: string;
  name: string;
  sub?: ReactNode;
  control?: ReactNode;
}) {
  return (
    <div className="flex min-w-[190px] items-center gap-2.5 rounded-btn border border-cream-line bg-cream px-2.5 py-2 lg:w-full">
      <span
        aria-hidden="true"
        className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-[9px] bg-brand-soft text-[15px]"
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <b className="block truncate text-xs font-medium leading-tight text-ink">{name}</b>
        {sub ? <small className="block truncate text-[9.5px] text-muted">{sub}</small> : null}
      </span>
      {control}
    </div>
  );
}

/**
 * Where the nav stops being a scrollable pill row and becomes a sidebar.
 *
 * Two shells sit on these shapes and they widen at different points: the
 * admin console (`AdminShell`) has always flipped at `sm:`, while A-U7's
 * business rail is 218px of real estate and only earns its place at `lg:`.
 * A prop rather than a template literal, because Tailwind only sees class
 * names it can read as literals — both branches are written out in full.
 */
export type ConsoleNavBreakpoint = "sm" | "lg";

export function ConsoleNavList({
  children,
  breakpoint = "sm",
}: {
  children: ReactNode;
  breakpoint?: ConsoleNavBreakpoint;
}) {
  return (
    <ul
      className={
        breakpoint === "lg"
          ? "flex gap-1.5 lg:block lg:space-y-0.5"
          : "flex gap-2 sm:block sm:space-y-1"
      }
    >
      {children}
    </ul>
  );
}

export function ConsoleNavItem({
  children,
  breakpoint = "sm",
}: {
  children: ReactNode;
  breakpoint?: ConsoleNavBreakpoint;
}) {
  return <li className={breakpoint === "lg" ? "flex-none lg:flex-auto" : "flex-none"}>{children}</li>;
}

/** A-U7 (A3 `.side nav a .ic` / `.n`): the icon and count slots inside a nav
 * link. Separate exports so the app's `<Link>` and the demo's `<a>` compose
 * the same row. The count is only ever a real number the caller was given. */
export function ConsoleNavIcon({ children }: { children: ReactNode }) {
  return (
    <span aria-hidden="true" className="w-5 flex-none text-center text-[15px]">
      {children}
    </span>
  );
}

export function ConsoleNavCount({ children }: { children: ReactNode }) {
  return (
    <span className="ml-auto rounded-pill bg-accent px-[7px] py-px text-[9px] font-bold text-accent-ink">
      {children}
    </span>
  );
}

/**
 * Class recipe for the nav link itself, shared by the app's `<Link>` and the
 * demo's plain `<a>`. Pill row below `sm:` (current = ink fill, mirroring the
 * campaign wizard's step pills); sidebar row from `sm:` (current = the
 * RadioCard "selected" convention, bg-brand-soft/text-brand-deep).
 */
export function consoleNavLinkClass(
  active: boolean,
  breakpoint: ConsoleNavBreakpoint = "sm",
): string {
  if (breakpoint === "lg") {
    // A-U7 (A3 `.side nav a`): an icon + label row, brand-soft when current.
    return cn(
      "flex min-h-[44px] items-center gap-2.5 whitespace-nowrap rounded-btn px-3.5 text-[12.5px] no-underline",
      "lg:min-h-[40px] lg:whitespace-normal lg:px-3",
      active
        ? "bg-brand-soft font-medium text-brand-deep"
        : "bg-cream text-sub lg:bg-transparent lg:hover:bg-cream",
    );
  }
  return cn(
    "flex min-h-[44px] items-center whitespace-nowrap rounded-pill px-4 text-[13px] font-semibold no-underline sm:block sm:min-h-0 sm:whitespace-normal sm:rounded-card sm:px-3 sm:py-2 sm:text-[14px]",
    active
      ? "bg-ink text-card sm:bg-brand-soft sm:text-brand-deep"
      : "bg-line text-ink sm:bg-transparent sm:font-normal sm:text-ink sm:hover:bg-line",
  );
}

/* ── page header ───────────────────────────────────────────────────────── */

/** The console page's h1 row: title left, one optional action right. */
export function ConsolePageHeader({
  title,
  sub,
  action,
  ...rest
}: {
  title: string;
  sub?: ReactNode;
  action?: ReactNode;
} & Omit<React.HTMLAttributes<HTMLElement>, "title">) {
  return (
    <header className="mb-4 flex flex-wrap items-start justify-between gap-2" {...rest}>
      <div className="min-w-0">
        <h1 className="font-display text-[20px] font-extrabold text-ink">{title}</h1>
        {sub ? <p className="mt-0.5 text-[13px] text-sub">{sub}</p> : null}
      </div>
      {action}
    </header>
  );
}

/* ── A-U7: the A3 console reference's shapes ───────────────────────────── */

/**
 * The A3 `.topbar`: eyebrow, title, sub-line, and a right-hand action group.
 *
 * A richer sibling of `ConsolePageHeader`, not a replacement — the older
 * shape is a plain h1 row and several console pages want exactly that.
 */
export function ConsoleTopbar({
  eyebrow,
  title,
  sub,
  actions,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-4 flex flex-wrap items-start gap-3">
      <div className="min-w-0 flex-1">
        {eyebrow ? (
          <p className="mb-1.5 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-coins-fg">
            <span aria-hidden="true" className="h-0.5 w-[22px] flex-none rounded-sm bg-accent" />
            {eyebrow}
          </p>
        ) : null}
        <h1 className="font-display text-xl font-semibold text-ink">{title}</h1>
        {sub ? <p className="mt-0.5 text-[11.5px] text-muted">{sub}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/** A-U7: the console button recipes (A3 `.btn-ghost` / `.btn-money`). The
 * shared `buttonVariants` are the 44px consumer set; the console runs a
 * denser 42px row, and the money pill has no consumer equivalent. */
export const consoleGhostButtonClass =
  "tap-target inline-flex min-h-[42px] items-center justify-center gap-1.5 rounded-btn border border-cream-line bg-card px-4 text-[13.5px] font-medium text-brand-deep no-underline disabled:opacity-60";

export const consoleMoneyButtonClass =
  "tap-target inline-flex min-h-[42px] items-center justify-center gap-1.5 rounded-pill bg-accent px-[17px] text-[13.5px] font-medium text-accent-ink no-underline disabled:opacity-60";

export const consolePrimaryButtonClass =
  "tap-target inline-flex min-h-[42px] items-center justify-center gap-1.5 rounded-btn bg-brand px-[17px] text-[13.5px] font-medium text-white no-underline disabled:opacity-60";

/** A-U7: KPI row (A3 `.kpis`). Four across on desktop, two on a phone. */
export function ConsoleKpiRow({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div role="group" aria-label={label} className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
      {children}
    </div>
  );
}

/**
 * A-U7: one KPI card (A3 `.kpi`).
 *
 * NO bar strip. The reference draws a 7-bar sparkline, and the analytics read
 * behind this console returns totals plus a by-pincode split — never a
 * per-day series. Bars would be decoration shaped like data, so the card
 * carries the number and the measured delta and stops there.
 */
export function ConsoleKpi({
  label,
  value,
  delta,
  deltaTone = "flat",
}: {
  label: string;
  value: string;
  /** e.g. "▲ 18% vs last wk". Omitted when there is nothing to compare to. */
  delta?: string;
  deltaTone?: "up" | "down" | "flat";
}) {
  return (
    <div className="rounded-card border border-cream-line bg-card px-[15px] py-[13px]">
      <small className="block text-[10px] font-medium uppercase tracking-[0.06em] text-muted">
        {label}
      </small>
      <b className="mt-0.5 block font-display text-2xl font-semibold leading-tight text-ink">
        {value}
      </b>
      {delta ? (
        <span
          className={cn(
            "mt-0.5 block text-[10.5px] font-medium",
            deltaTone === "up" && "text-up",
            deltaTone === "down" && "text-down",
            deltaTone === "flat" && "text-muted",
          )}
        >
          {delta}
        </span>
      ) : null}
    </div>
  );
}

/** A-U7: the A3 `.grid2` — main column plus a reference rail. */
export function ConsoleGrid2({ children }: { children: ReactNode }) {
  return <div className="mt-3 grid gap-3 lg:grid-cols-[1.6fr_1fr]">{children}</div>;
}

/** A-U7: a checklist row (A3 `.check`) — marker, label, optional right slot. */
export function ConsoleCheckRow({
  marker,
  done = false,
  children,
  right,
}: {
  /** Explicit marker wins; otherwise `done` picks ✅ / ○. */
  marker?: ReactNode;
  done?: boolean;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2.5 border-b border-cream-line py-[7px] text-xs text-ink last:border-b-0">
      <span aria-hidden="true" className={done ? "text-up" : "text-muted"}>
        {marker ?? (done ? "✅" : "○")}
      </span>
      <span className="min-w-0">{children}</span>
      {right ? <span className="ml-auto whitespace-nowrap text-[10.5px]">{right}</span> : null}
    </div>
  );
}

/** A-U7: the A3 `.prog` bar. `value` is a real percentage the caller
 * computed; there is no default, because a progress bar with an invented
 * number is the most confident lie a dashboard can tell. */
export function ConsoleProgress({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className="my-2 h-[7px] overflow-hidden rounded-pill bg-cream-deep"
    >
      <span
        className="block h-full rounded-pill bg-gradient-to-r from-brand to-accent"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/**
 * A-U7: one row of the leads/reviews inbox (A3 `.lead`).
 *
 * `tone="new"` is the reference's brand-bordered, tinted card. Actions are a
 * slot: this catalog never knows what a Call button does — on agri.in it runs
 * the D18 reveal, and that belongs to the app.
 */
export function ConsoleLeadRow({
  icon,
  title,
  meta,
  chip,
  actions,
  tone = "default",
}: {
  icon?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  chip?: ReactNode;
  actions?: ReactNode;
  tone?: "default" | "new";
}) {
  return (
    <div
      className={cn(
        "mb-2 flex flex-wrap items-start gap-2.5 rounded-btn border px-[13px] py-[11px] last:mb-0",
        tone === "new" ? "border-brand bg-cream" : "border-cream-line bg-card",
      )}
    >
      {icon ? (
        <span aria-hidden="true" className="text-lg leading-none">
          {icon}
        </span>
      ) : null}
      <div className="min-w-[200px] flex-1">
        <b className="block text-[12.5px] font-medium text-ink">{title}</b>
        {meta ? <span className="mt-px block text-[10.5px] text-muted">{meta}</span> : null}
      </div>
      {chip ? <span className="ml-auto">{chip}</span> : null}
      {actions ? <div className="mt-2 flex w-full gap-1.5">{actions}</div> : null}
    </div>
  );
}

/** A-U7: the small grey qualifier under a panel (A3 `.mini-note`). */
export function ConsoleMiniNote({ children }: { children: ReactNode }) {
  return <p className="mt-1.5 text-[10.5px] leading-relaxed text-muted">{children}</p>;
}

/* ── panel ─────────────────────────────────────────────────────────────── */

/**
 * The console's sectioning card. Pages are stacks of panels; an empty state
 * is the existing `EmptyState` primitive rendered as a panel's body — the
 * console adds no empty-state shape of its own.
 */
export function ConsolePanel({
  title,
  action,
  children,
  className,
  ...rest
}: {
  title?: string;
  /** One optional panel-level action, right of the title. */
  action?: ReactNode;
  children: ReactNode;
  className?: string;
} & Omit<React.HTMLAttributes<HTMLElement>, "title" | "className">) {
  return (
    <section
      className={cn("rounded-card border border-line bg-card p-4", className)}
      {...rest}
    >
      {title ? (
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="font-display text-[15px] font-extrabold text-ink">{title}</h2>
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/* ── dashboard stats ───────────────────────────────────────────────────── */

/** 2-up on mobile, n-up from `md`. Server-rendered finals, no count-up. */
export function ConsoleStatRow({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div role="group" aria-label={label} className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
      {children}
    </div>
  );
}

export function ConsoleStatTile({
  value,
  label,
  hint,
}: {
  value: string;
  label: string;
  /** Optional qualifier under the label, e.g. "last 30 days". */
  hint?: string;
}) {
  return (
    <div className="rounded-card border border-line bg-card p-3.5">
      <b className="block font-display text-[22px] font-extrabold leading-tight text-ink">
        {value}
      </b>
      <span className="mt-0.5 block text-[12px] font-semibold text-sub">{label}</span>
      {hint ? <span className="block text-[11px] text-muted">{hint}</span> : null}
    </div>
  );
}

/* ── module card ───────────────────────────────────────────────────────── */

/**
 * A dashboard entry tile for one console module. Rendered inside whatever
 * link element the caller supplies (same convention as `IconTile`), so the
 * tile never needs to know about routing.
 */
export function ConsoleModuleCard({
  icon,
  title,
  sub,
}: {
  icon: string;
  title: string;
  sub?: string;
}) {
  return (
    <span className="flex h-full items-center gap-3 rounded-card border border-line bg-card p-3.5 transition-shadow hover:shadow-lift">
      <span
        aria-hidden="true"
        className="flex h-11 w-11 flex-none items-center justify-center rounded-icon bg-brand-soft text-xl"
      >
        {icon}
      </span>
      <span className="min-w-0">
        <b className="block text-[13.5px] font-semibold text-ink">{title}</b>
        {sub ? <span className="block text-[11.5px] leading-snug text-sub">{sub}</span> : null}
      </span>
    </span>
  );
}

/* ── state chip ────────────────────────────────────────────────────────── */

export type ConsoleStateTone = "ok" | "pending" | "alert" | "neutral" | "info";

const STATE_TONES: Record<ConsoleStateTone, string> = {
  /** active / approved / verified */
  ok: "bg-verified-bg text-verified-fg",
  /** pending moderation / awaiting payment */
  pending: "bg-sponsored-bg text-sponsored-fg",
  /** suspended / rejected / expired — the palette's warm alert pair */
  alert: "border border-alert-line bg-alert-bg text-ink",
  /** draft / closed */
  neutral: "bg-ghost text-sub",
  /** tier / informational */
  info: "bg-brand-soft text-brand-deep",
};

/** Non-interactive status label. Tone maps to existing token pairs only. */
export function StateChip({
  tone,
  children,
  className,
  ...rest
}: {
  tone: ConsoleStateTone;
  children: ReactNode;
  className?: string;
} & Omit<React.HTMLAttributes<HTMLSpanElement>, "className">) {
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-pill px-2.5 py-0.5 text-[11px] font-bold",
        STATE_TONES[tone],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}

/* ── notice ────────────────────────────────────────────────────────────── */

/** Inline outcome banner for form saves — the ok/error pair the D26 console
 * pages each re-invented locally, canonicalized. */
export function ConsoleNotice({
  tone,
  children,
  ...rest
}: {
  tone: "ok" | "alert";
  children: ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="status"
      className={cn(
        "rounded-card p-3 text-[13px] font-semibold",
        tone === "ok"
          ? "bg-verified-bg text-verified-fg"
          : "border border-alert-line bg-alert-bg text-ink",
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

/* ── form field ────────────────────────────────────────────────────────── */

/** The console control recipe (inputs, selects, textareas). ≥44px tall. */
export const consoleControlClass =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";

/**
 * Label + control + optional hint/error wiring. The caller passes the control
 * and sets `id` on it; the field renders `<label htmlFor>` and, when `error`
 * is set, an error line with id `${id}-error` — point the control's
 * `aria-describedby` (and `aria-invalid`) at it.
 */
export function ConsoleField({
  id,
  label,
  hint,
  error,
  children,
  className,
}: {
  id: string;
  label: string;
  hint?: string | undefined;
  /** Validation message. Localized by the caller — error strings are the
   * usual place English survives a locale switch. */
  error?: string | undefined;
  children: ReactNode;
  className?: string | undefined;
}) {
  return (
    <div className={className}>
      <label htmlFor={id} className="block text-[13px] font-semibold text-ink">
        {label}
      </label>
      {children}
      {hint && !error ? <p className="mt-1 text-[11.5px] text-muted">{hint}</p> : null}
      {error ? (
        <p
          id={`${id}-error`}
          className="mt-1 rounded-btn border border-alert-line bg-alert-bg px-2.5 py-1.5 text-[12px] font-semibold text-ink"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

/* ── data table ────────────────────────────────────────────────────────── */

/**
 * The console data table's deliberate responsive treatment (NOT an overflow
 * box): a real `<table>` from `md:` up; below `md:` each row becomes a
 * bordered card and each cell a label/value line, with the header row hidden.
 * Explicit ARIA table roles are kept on every element because `display:block`
 * strips the implicit ones — without them the stacked view reads as loose
 * text to assistive tech.
 */
export function ConsoleTable({
  caption,
  head,
  children,
}: {
  /** Visually hidden table name for AT. */
  caption: string;
  /** One `ConsoleHeadCell` per column. */
  head: ReactNode;
  children: ReactNode;
}) {
  return (
    <table role="table" className="w-full border-collapse text-[13px] max-md:block">
      <caption className="sr-only">{caption}</caption>
      <thead role="rowgroup" className="max-md:hidden">
        <tr role="row" className="text-left">
          {head}
        </tr>
      </thead>
      <tbody role="rowgroup" className="max-md:block max-md:space-y-2.5">
        {children}
      </tbody>
    </table>
  );
}

export function ConsoleHeadCell({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <th
      role="columnheader"
      scope="col"
      className={cn(
        "border-b border-line pb-2 pr-3 text-[11px] font-extrabold uppercase tracking-[.06em] text-sub",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function ConsoleRow({
  children,
  className,
  ...rest
}: { children: ReactNode; className?: string } & Omit<
  React.HTMLAttributes<HTMLTableRowElement>,
  "className"
>) {
  return (
    <tr
      role="row"
      className={cn(
        "max-md:block max-md:space-y-1 max-md:rounded-card max-md:border max-md:border-line max-md:bg-card max-md:p-3",
        className,
      )}
      {...rest}
    >
      {children}
    </tr>
  );
}

export function ConsoleCell({
  label,
  children,
  className,
  ...rest
}: {
  /** Column name, repeated per cell for the stacked mobile view. */
  label: string;
  children: ReactNode;
  className?: string;
} & Omit<React.HTMLAttributes<HTMLTableCellElement>, "children" | "className">) {
  return (
    <td
      role="cell"
      className={cn(
        "border-b border-line py-2.5 pr-3 align-top text-ink max-md:flex max-md:items-baseline max-md:justify-between max-md:gap-3 max-md:border-0 max-md:p-0",
        className,
      )}
      {...rest}
    >
      <span aria-hidden="true" className="text-[11px] font-semibold text-sub md:hidden">
        {label}
      </span>
      <span className="max-md:text-right">{children}</span>
    </td>
  );
}

/* ── U3 · admin shell ──────────────────────────────────────────────────── */

/**
 * The admin console frame (U3). Same nav law as `ConsoleShell` — pill row
 * below `sm:`, sidebar from `sm:` up, one `<nav>`, responsive classes only —
 * but wider (`max-w-7xl`): operators want many table columns visible, not
 * consumer card rhythm.
 *
 * Contracts the caller owns:
 * - Links are slots; the ACTIVE link must carry `aria-current="page"` (the
 *   demo and web-admin both do; the class recipe stays `consoleNavLinkClass`).
 * - Role gating happens BEFORE render: the app filters its nav items against
 *   the server session's roles and passes only what the operator may see.
 *   The catalog never learns about roles — a non-admin session simply has no
 *   items to pass, so no admin nav renders.
 */
export function AdminShell({
  navLabel,
  heading,
  nav,
  aside,
  children,
  ...rest
}: {
  /** Accessible name for the nav landmark, e.g. "Admin console". */
  navLabel: string;
  /** Sidebar heading (hidden below `sm:`). */
  heading: string;
  /** The role-filtered module list — a `ConsoleNavList` of links. */
  nav: ReactNode;
  /** Optional sidebar footer, e.g. the signed-in-as line. Hidden below `sm:`. */
  aside?: ReactNode;
  children: ReactNode;
} & Omit<React.HTMLAttributes<HTMLDivElement>, "children">) {
  return (
    <div
      className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-4 py-5 sm:flex-row sm:gap-6"
      {...rest}
    >
      <nav
        aria-label={navLabel}
        className="flex gap-2 overflow-x-auto pb-1 sm:block sm:w-52 sm:shrink-0 sm:overflow-visible sm:pb-0"
      >
        <p className="hidden font-display text-[13px] font-extrabold uppercase tracking-wide text-sub sm:mb-3 sm:block">
          {heading}
        </p>
        {nav}
        {aside ? <div className="hidden sm:block sm:pt-6">{aside}</div> : null}
      </nav>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/* ── U3 · admin data table ─────────────────────────────────────────────── */

/** One column of an `AdminDataTable`. */
export interface AdminColumn<T> {
  /** Stable identity for React keys. */
  key: string;
  /** Column header; also the stacked-view label repeated per cell. */
  header: string;
  cell: (row: T) => ReactNode;
  /**
   * Hide the whole column (header, cells, stacked-view lines) below this
   * breakpoint — the deliberate responsive treatment; never an overflow box.
   */
  hideBelow?: "md" | "lg" | "xl";
  align?: "left" | "right";
}

/**
 * Full literals per breakpoint — Tailwind cannot see composed class names.
 * Each entry ALSO carries `max-md:hidden`: below `md:` the cell's stacked-view
 * `max-md:flex` would otherwise win the cascade over the wider `max-*:hidden`
 * (same specificity, later in the sheet); passing our own `max-md:` display
 * class makes tailwind-merge drop the flex and the column stays hidden.
 */
const HIDE_BELOW: Record<"md" | "lg" | "xl", string> = {
  md: "max-md:hidden",
  lg: "max-md:hidden max-lg:hidden",
  xl: "max-md:hidden max-xl:hidden",
};

/**
 * THE admin table (U3): every admin list surface renders through this one
 * primitive — typed columns, a toolbar slot, keyboard-reachable row open,
 * and its own loading/empty/error states, so no route file re-invents any
 * of it. Markup-wise it composes the U2 `ConsoleTable` family (real table
 * from `md:`, stacked label/value cards below, explicit ARIA roles).
 *
 * Pagination follows `Page[T]`: the caller hands the OPAQUE `nextCursor`
 * from the last page and an `onLoadMore`; a null cursor means the list is
 * complete and no control renders. The cursor is never parsed here.
 *
 * The empty state is SUCCESS, not error — an empty moderation queue means
 * the work is done. Callers write `empty` copy in that register.
 *
 * EN literal defaults ("Open", "Load more", "Loading") are deliberate: the
 * admin console is internal and single-language by owner decision (U3).
 */
export function AdminDataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  toolbar,
  loading = false,
  loadingLabel = "Loading",
  error,
  errorAction,
  empty,
  nextCursor = null,
  onLoadMore,
  loadingMore = false,
  loadMoreLabel = "Load more",
  onRowOpen,
  rowOpenLabel,
}: {
  /** Visually hidden table name for AT. */
  caption: string;
  columns: readonly AdminColumn<T>[];
  rows: readonly T[];
  rowKey: (row: T) => string;
  /** Filters/search row rendered above the table. */
  toolbar?: ReactNode;
  loading?: boolean;
  loadingLabel?: string;
  /** Request failure line; renders instead of rows. */
  error?: string;
  /** Optional retry control next to the error notice. */
  errorAction?: ReactNode;
  /** Empty-queue framing — write it as success ("Queue clear"), never error. */
  empty: { icon: string; title: ReactNode; description?: ReactNode };
  /** `Page[T].nextCursor`, opaque. Null = complete, no control renders. */
  nextCursor?: string | null;
  onLoadMore?: () => void;
  loadingMore?: boolean;
  loadMoreLabel?: string;
  /**
   * Row detail opener. Renders a real, focusable button per row (keyboard
   * reaches every row action); the whole row is a pointer-only enlarged hit
   * area for the same action.
   */
  onRowOpen?: (row: T) => void;
  /** Accessible per-row label for the open button, e.g. `Open ${row.name}`. */
  rowOpenLabel?: (row: T) => string;
}) {
  const openRow = onRowOpen
    ? (row: T) => (event: React.MouseEvent<HTMLTableRowElement>) => {
        // Clicks on real controls inside cells keep their own behaviour.
        const target = event.target as HTMLElement;
        if (target.closest("a,button,input,select,textarea,label")) return;
        onRowOpen(row);
      }
    : null;

  let body: ReactNode;
  if (loading) {
    body = (
      <div role="status" className="space-y-2 py-1">
        <span className="sr-only">{loadingLabel}</span>
        {[0, 1, 2].map((i) => (
          <div key={i} aria-hidden="true" className="h-9 animate-pulse rounded-btn bg-ghost" />
        ))}
      </div>
    );
  } else if (error) {
    body = (
      <div className="flex flex-col items-start gap-2">
        <ConsoleNotice tone="alert">{error}</ConsoleNotice>
        {errorAction}
      </div>
    );
  } else if (rows.length === 0) {
    body = (
      <EmptyState
        icon={empty.icon}
        title={empty.title}
        {...(empty.description !== undefined ? { description: empty.description } : {})}
        className="border-0 bg-transparent p-6"
      />
    );
  } else {
    body = (
      <ConsoleTable
        caption={caption}
        head={
          <>
            {columns.map((column) => (
              <ConsoleHeadCell
                key={column.key}
                className={cn(
                  column.hideBelow && HIDE_BELOW[column.hideBelow],
                  column.align === "right" && "text-right",
                )}
              >
                {column.header}
              </ConsoleHeadCell>
            ))}
            {onRowOpen ? (
              <ConsoleHeadCell className="w-px">
                <span className="sr-only">Open</span>
              </ConsoleHeadCell>
            ) : null}
          </>
        }
      >
        {rows.map((row) => (
          <ConsoleRow
            key={rowKey(row)}
            {...(openRow ? { onClick: openRow(row), className: "cursor-pointer hover:bg-ghost" } : {})}
          >
            {columns.map((column) => (
              <ConsoleCell
                key={column.key}
                label={column.header}
                className={cn(
                  column.hideBelow && HIDE_BELOW[column.hideBelow],
                  column.align === "right" && "md:text-right",
                )}
              >
                {column.cell(row)}
              </ConsoleCell>
            ))}
            {onRowOpen ? (
              <ConsoleCell label="" className="max-md:justify-end">
                <button
                  type="button"
                  onClick={() => onRowOpen(row)}
                  aria-label={rowOpenLabel ? rowOpenLabel(row) : undefined}
                  className="min-h-[44px] rounded-btn px-3 text-[12.5px] font-bold text-brand-deep hover:bg-brand-soft"
                >
                  Open
                </button>
              </ConsoleCell>
            ) : null}
          </ConsoleRow>
        ))}
      </ConsoleTable>
    );
  }

  return (
    <div>
      {toolbar ? <div className="mb-3 flex flex-wrap items-center gap-2">{toolbar}</div> : null}
      {body}
      {!loading && !error && rows.length > 0 && nextCursor !== null && onLoadMore ? (
        <div className="mt-3 flex justify-center">
          <Button
            variant="ghost"
            className="flex-none px-5"
            disabled={loadingMore}
            onClick={onLoadMore}
          >
            {loadingMore ? loadingLabel : loadMoreLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
