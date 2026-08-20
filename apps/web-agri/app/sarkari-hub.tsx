"use client";

/**
 * A-U4b O2 (AG-A61) — sarkari cards + detail dialog island.
 *
 * The owner's rule: leaving agri.in must be a DELIBERATE second click. Each
 * card stays a REAL `<a href>` to the official portal — crawlable, and the
 * no-JS path is exactly the old behaviour (new tab, official site). With JS,
 * a plain left-click is intercepted (`shouldInterceptClick`) and opens a
 * native `<dialog>` describing the scheme — what it is, who is eligible,
 * documents needed — stamped with its official source + the date the copy
 * was checked, and a prominent "open the portal" link at the bottom.
 * Modified clicks (ctrl/cmd/shift/middle) are NOT intercepted, so
 * open-in-new-tab keeps its browser meaning.
 *
 * Dialog mechanism: the shared @agri/ui `Modal` (Radix — the location-pill
 * dialog) is trigger-owned and uncontrolled, and Radix's composed click
 * handler skips itself once `defaultPrevented` is set — the very thing an
 * anchor intercept must set. A native `<dialog>` + `showModal()` gives the
 * same a11y contract without that conflict: top-layer focus trap, Escape
 * closes (cancel→close), implicit `role=dialog`/`aria-modal`. Focus returns
 * to the clicked card explicitly on close — Safari doesn't focus clicked
 * links, so the browser's own restore could land on `<body>`.
 *
 * All strings arrive as props, resolved server-side (the LiveLocationPill
 * strings-prop precedent) — no next-intl namespace ships to the client and
 * the island stays small. DPDP: the dialog is descriptive words only; this
 * island fetches and stores nothing.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { shouldInterceptClick } from "@/lib/sarkari";

export interface SarkariCard {
  key: string;
  url: string;
  domain: string;
  verified_on: string;
  icon: string;
  title: string;
  sub: string;
  /** Detail copy, already resolved to the request locale. */
  what: string;
  eligibility: string;
  documents: string;
  /** "Source: {domain} · ✓ {date}" — interpolated server-side. */
  sourceLine: string;
  /** "Open {domain} ↗" — interpolated server-side. */
  goLabel: string;
}

export interface SarkariHubLabels {
  what: string;
  eligibility: string;
  documents: string;
  close: string;
  /** The we-never-store-your-records line (DPDP), shown in the dialog. */
  dpdp: string;
}

export function SarkariHub({
  cards,
  labels,
}: {
  cards: SarkariCard[];
  labels: SarkariHubLabels;
}) {
  const [active, setActive] = useState<SarkariCard | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const openerRef = useRef<HTMLAnchorElement | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (active && dialog && !dialog.open) dialog.showModal();
  }, [active]);

  const close = useCallback(() => dialogRef.current?.close(), []);

  // Fires for every way the dialog shuts (✕, Escape, backdrop, the go-link).
  const onDialogClose = useCallback(() => {
    setActive(null);
    openerRef.current?.focus();
    openerRef.current = null;
  }, []);

  return (
    <>
      <div className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-3">
        {cards.map((card) => (
          <a
            key={card.key}
            data-testid="sarkari-link"
            href={card.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(event) => {
              if (!shouldInterceptClick(event)) return;
              event.preventDefault();
              openerRef.current = event.currentTarget;
              setActive(card);
            }}
            className="flex items-start gap-[11px] rounded-card border border-cream-line bg-card px-3.5 py-3 no-underline transition-[transform,box-shadow] duration-150 hover:-translate-y-0.5 hover:shadow-lift motion-reduce:transition-none motion-reduce:hover:translate-y-0"
          >
            <span
              aria-hidden="true"
              className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-[10px] bg-brand-soft text-base"
            >
              {card.icon}
            </span>
            <span className="min-w-0">
              <b className="block text-[12.5px] font-medium text-ink">{card.title}</b>
              <small className="mt-px block text-[10px] leading-normal text-muted">
                {card.sub}
              </small>
              <span className="mt-[3px] inline-block text-[9.5px] font-medium text-brand">
                {card.domain} ↗ · ✓ {card.verified_on}
              </span>
            </span>
          </a>
        ))}
      </div>

      <dialog
        ref={dialogRef}
        data-testid="sarkari-dialog"
        aria-labelledby="sarkari-dialog-title"
        onClose={onDialogClose}
        onClick={(event) => {
          // The panel itself has p-0 and a padded inner div, so a click whose
          // target is the <dialog> element can only be on the backdrop.
          if (event.target === dialogRef.current) close();
        }}
        className="m-auto max-h-[85dvh] w-[calc(100vw-32px)] max-w-lg overflow-y-auto rounded-card border border-cream-line bg-card p-0 text-ink shadow-lift [&::backdrop]:bg-ink/50"
      >
        {active ? (
          <div className="p-5">
            <div className="flex items-start justify-between gap-3">
              <h3
                id="sarkari-dialog-title"
                className="font-display text-lg font-extrabold leading-snug"
              >
                <span aria-hidden="true" className="mr-1.5">
                  {active.icon}
                </span>
                {active.title}
              </h3>
              <button
                type="button"
                onClick={close}
                aria-label={labels.close}
                data-testid="sarkari-dialog-close"
                className="flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-btn bg-ghost text-base font-extrabold text-ink"
              >
                ✕
              </button>
            </div>

            <dl className="mt-3 grid gap-3">
              {(
                [
                  [labels.what, active.what],
                  [labels.eligibility, active.eligibility],
                  [labels.documents, active.documents],
                ] as const
              ).map(([term, copy]) => (
                <div key={term}>
                  <dt className="text-[10.5px] font-bold uppercase tracking-wide text-muted">
                    {term}
                  </dt>
                  <dd className="mt-1 text-[13px] leading-relaxed text-ink">{copy}</dd>
                </div>
              ))}
            </dl>

            <p className="mt-3.5 text-[10.5px] font-medium text-brand">{active.sourceLine}</p>
            <p className="mt-1 text-[10.5px] leading-normal text-muted">{labels.dpdp}</p>

            <a
              data-testid="sarkari-dialog-go"
              href={active.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={close}
              className="tap-target mt-4 flex min-h-[44px] items-center justify-center rounded-btn bg-brand px-4 text-center text-[13px] font-bold text-white no-underline"
            >
              {active.goLabel}
            </a>
          </div>
        ) : null}
      </dialog>
    </>
  );
}
