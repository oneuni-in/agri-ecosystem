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
  nav,
  children,
  ...rest
}: {
  /** Accessible name for the nav landmark, e.g. "Business console". */
  navLabel: string;
  /** Sidebar heading (hidden below `sm:`, where the pill row speaks for itself). */
  heading: string;
  /** The module list — a `ConsoleNavList` of links. */
  nav: ReactNode;
  children: ReactNode;
} & Omit<React.HTMLAttributes<HTMLDivElement>, "children">) {
  return (
    <div
      className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-6 sm:flex-row sm:gap-6"
      {...rest}
    >
      <nav
        aria-label={navLabel}
        className="flex gap-2 overflow-x-auto pb-1 sm:block sm:w-48 sm:shrink-0 sm:overflow-visible sm:pb-0"
      >
        <p className="hidden font-display text-[13px] font-extrabold uppercase tracking-wide text-sub sm:mb-3 sm:block">
          {heading}
        </p>
        {nav}
      </nav>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

export function ConsoleNavList({ children }: { children: ReactNode }) {
  return <ul className="flex gap-2 sm:block sm:space-y-1">{children}</ul>;
}

export function ConsoleNavItem({ children }: { children: ReactNode }) {
  return <li className="flex-none">{children}</li>;
}

/**
 * Class recipe for the nav link itself, shared by the app's `<Link>` and the
 * demo's plain `<a>`. Pill row below `sm:` (current = ink fill, mirroring the
 * campaign wizard's step pills); sidebar row from `sm:` (current = the
 * RadioCard "selected" convention, bg-brand-soft/text-brand-deep).
 */
export function consoleNavLinkClass(active: boolean): string {
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
  hint?: string;
  /** Validation message. Localized by the caller — error strings are the
   * usual place English survives a locale switch. */
  error?: string;
  children: ReactNode;
  className?: string;
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

export function ConsoleHeadCell({ children }: { children: ReactNode }) {
  return (
    <th
      role="columnheader"
      scope="col"
      className="border-b border-line pb-2 pr-3 text-[11px] font-extrabold uppercase tracking-[.06em] text-sub"
    >
      {children}
    </th>
  );
}

export function ConsoleRow({ children, ...rest }: { children: ReactNode } & React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      role="row"
      className="max-md:block max-md:space-y-1 max-md:rounded-card max-md:border max-md:border-line max-md:bg-card max-md:p-3"
      {...rest}
    >
      {children}
    </tr>
  );
}

export function ConsoleCell({
  label,
  children,
  ...rest
}: {
  /** Column name, repeated per cell for the stacked mobile view. */
  label: string;
  children: ReactNode;
} & Omit<React.HTMLAttributes<HTMLTableCellElement>, "children">) {
  return (
    <td
      role="cell"
      className="border-b border-line py-2.5 pr-3 align-top text-ink max-md:flex max-md:items-baseline max-md:justify-between max-md:gap-3 max-md:border-0 max-md:p-0"
      {...rest}
    >
      <span aria-hidden="true" className="text-[11px] font-semibold text-sub md:hidden">
        {label}
      </span>
      <span className="max-md:text-right">{children}</span>
    </td>
  );
}
