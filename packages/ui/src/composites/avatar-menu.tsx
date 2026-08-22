"use client";

import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * The header avatar, as a menu.
 *
 * Two things this fixes, both reported from the running site:
 *
 * 1. THE AVATAR WAS A LOGOUT BUTTON. Tapping your own face signed you out —
 *    with no confirmation, and with no other way to reach your account. The
 *    A1 reference labels this element "Account" (agri_home_desktop_v1.html,
 *    the guest-state note), which is what people expect it to be. Log out
 *    stays reachable, as an item inside the menu, where it takes a
 *    deliberate second tap.
 * 2. AN UPLOADED PHOTO NEVER SHOWED. The trigger rendered an initial and
 *    nothing else, so a profile photo was invisible everywhere except the
 *    page you uploaded it on.
 *
 * The photo is fetched by the browser from `photoSrc` — for agri.in that is
 * the app's own BFF proxy, which attaches the session bearer server-side.
 * The image is deliberately not a public URL (a face is not a product photo:
 * its visibility toggle has to govern the IMAGE, not merely whether a link
 * is rendered), so this cannot be a plain CDN `src` and must not become one.
 *
 * NO PHOTO IS THE NORMAL CASE: the endpoint 404s for anyone who has not
 * uploaded one, so the initial is the fallback, not an error state. That
 * check runs through a callback ref rather than `onError` alone — the same
 * pre-hydration trap the product thumbnails hit: the request can fail before
 * React attaches the handler, and then the handler never fires.
 */
export function AvatarMenu({
  initial,
  photoSrc,
  label,
  children,
  className,
}: {
  /** Shown when there is no photo, or the photo cannot be loaded. */
  initial: string;
  /** Owner-scoped image endpoint. Omit when the app has none. */
  photoSrc?: string | undefined;
  /** Accessible name for the trigger, e.g. "Account". */
  label: string;
  /** `AvatarMenuItem`s. */
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [photoFailed, setPhotoFailed] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  const close = useCallback((focusTrigger: boolean) => {
    setOpen(false);
    if (focusTrigger) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(true);
    };
    const onPointer = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) close(false);
    };
    document.addEventListener("keydown", onKey);
    // `pointerdown`, not `click`: a click that starts inside the menu and
    // ends outside it should not be treated as an outside dismissal.
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open, close]);

  /** Catches an image that already failed before hydration. */
  const markIfBroken = useCallback((img: HTMLImageElement | null) => {
    if (img && img.complete && img.naturalWidth === 0) setPhotoFailed(true);
  }, []);

  const showPhoto = Boolean(photoSrc) && !photoFailed;

  return (
    <div ref={wrapRef} className={cn("relative", className)}>
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((v) => !v)}
        className="tap-target flex h-[38px] w-[38px] items-center justify-center overflow-hidden rounded-full bg-card text-[15px] font-extrabold text-ink"
      >
        {showPhoto ? (
          // A plain <img>, like AdImage: this is an owner-scoped API response,
          // never a public asset next/image could optimise. (No eslint-disable
          // here — @agri/ui does not load the Next plugin, so a directive for
          // a rule that does not exist is itself an error.)
          <img
            ref={markIfBroken}
            src={photoSrc}
            alt=""
            className="h-full w-full object-cover"
            onError={() => setPhotoFailed(true)}
          />
        ) : (
          initial
        )}
      </button>

      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label={label}
          onClick={() => close(false)}
          className="absolute right-0 top-[calc(100%+6px)] z-50 min-w-[180px] overflow-hidden rounded-card border border-line bg-card py-1 shadow-lift"
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}

/** One row of an `AvatarMenu`. Renders an anchor when given `href`, so the
 * catalog never needs to know about routing. */
export function AvatarMenuItem({
  href,
  onSelect,
  icon,
  children,
}: {
  href?: string;
  onSelect?: () => void;
  icon?: ReactNode;
  children: ReactNode;
}) {
  const className =
    "flex min-h-[44px] w-full items-center gap-2.5 px-3.5 text-left text-[13px] font-semibold text-ink no-underline hover:bg-ghost";
  const body = (
    <>
      {icon ? (
        <span aria-hidden="true" className="w-5 flex-none text-center text-[15px]">
          {icon}
        </span>
      ) : null}
      {children}
    </>
  );
  if (href) {
    return (
      <a role="menuitem" href={href} className={className}>
        {body}
      </a>
    );
  }
  return (
    <button role="menuitem" type="button" onClick={onSelect} className={className}>
      {body}
    </button>
  );
}
