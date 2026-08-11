"use client";

/**
 * AdCarousel (M2): the global sliding head banner. Native scroll-snap does
 * the swiping (no JS gesture lib); autoplay is a 6s interval that advances
 * scrollLeft - paused on touch/hover/hidden tab, and never started when
 * prefers-reduced-motion is set (DO NOT: autoplay without reduced-motion
 * respect). Slide 1 renders its image eager, the rest lazy (rural data).
 * Impressions are per-slide and viewport-gated via AdUnit/useImpression -
 * an off-screen slide never fires (NN2). Same CLS contract as AdSlot:
 * fixed-height reservation, fallback-or-collapse when empty.
 */
import { type ReactNode, useEffect, useRef, useState } from "react";

import { cn } from "../lib/cn";
import { pincodeFromCookieHeader } from "../lib/location";
import { parseServeResponse, type ServedAd, serveQuery } from "../lib/sponsored";

import { AdUnit } from "./ad-slot";

export const AD_CAROUSEL_MAX = 5;
export const AD_CAROUSEL_INTERVAL_MS = 6000;

/** Prev/next affordance (`.hero-nav`): a 32px disc, vertically centred,
 * hidden below 768px where the native swipe is the affordance.
 *
 * The 44px hit area (design-system.md §1.5) comes from a 44px transparent
 * button wrapping a 32px visual disc — deliberately NOT the `.tap-target`
 * utility, which sets `position: relative` and, being emitted after Tailwind's
 * core utilities, silently beats `absolute`. That dropped both arrows into
 * normal flow: they stacked under the carousel AND added their own 2x32px to
 * its height, so the reserved aspect-ratio box was 333px instead of 269px. */
function CarouselArrow({
  label,
  onClick,
  className,
  children,
}: {
  label: string;
  onClick: () => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={cn(
        "absolute top-1/2 flex h-11 w-11 -translate-y-1/2 items-center justify-center max-md:hidden",
        className,
      )}
    >
      {/* Solid ink disc, not the reference's translucent white: a creative is
          arbitrary artwork, and white-on-16%-white vanished completely over
          the light creatives this slot actually serves. */}
      <span
        aria-hidden="true"
        className="flex h-8 w-8 items-center justify-center rounded-pill bg-ink/70 text-base text-white"
      >
        {children}
      </span>
    </button>
  );
}

export function AdCarousel({
  slotKey,
  pincode,
  locale,
  endpoint = "/api/ads",
  heightClass,
  className,
  fallback,
  arrows,
  badgeClassName,
  sponsoredLabel,
  initialAds,
}: {
  slotKey: string;
  pincode?: string | null;
  locale?: string;
  endpoint?: string;
  heightClass: string;
  className?: string;
  fallback?: ReactNode;
  /** U1 §3 prev/next affordances. Passing the object enables them and forces
   * translated labels — there is no English default to leak. Like the dots,
   * they only render when there is more than one creative, so a single
   * creative collapses to a static banner with no dead controls. */
  arrows?: { prevLabel: string; nextLabel: string };
  /** Corner placement of the always-on "★ Sponsored" label (see `AdUnit`). */
  badgeClassName?: string;
  /** Translated wording for that label. */
  sponsoredLabel?: string;
  /**
   * Creatives already served on the SERVER. When supplied the client fetch is
   * skipped entirely and slide 1 ships in the SSR HTML — which is the whole
   * point: a client-fetched hero cannot start downloading its image until
   * hydration has run, and that was measured at 2372ms of LCP load delay.
   * Impressions are unaffected; they still fire from the viewport observer.
   */
  initialAds?: ServedAd[];
}) {
  // `initialAds` means "already resolved" - not a loading state, and not an
  // empty one either; an empty array from the server is a real "no fill".
  const [ads, setAds] = useState<ServedAd[] | null>(initialAds ?? null);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const pausedRef = useRef(false);
  const indexRef = useRef(0);
  const [dot, setDot] = useState(0);

  useEffect(() => {
    if (initialAds) return; // server already answered; never re-serve on mount
    let cancelled = false;
    const ctx = {
      pincode: pincode !== undefined ? pincode : pincodeFromCookieHeader(document.cookie),
      locale,
      count: AD_CAROUSEL_MAX,
    };
    fetch(`${endpoint}/serve?${serveQuery(slotKey, ctx)}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: unknown) => {
        if (cancelled) return;
        setAds(data === null ? [] : parseServeResponse(data).slice(0, AD_CAROUSEL_MAX));
      })
      .catch(() => {
        if (!cancelled) setAds([]);
      });
    return () => {
      cancelled = true;
    };
  }, [slotKey, pincode, locale, endpoint, initialAds]);

  const count = ads?.length ?? 0;
  useEffect(() => {
    if (count < 2) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => {
      if (pausedRef.current || document.hidden) return;
      const track = trackRef.current;
      if (!track) return;
      indexRef.current = (indexRef.current + 1) % count;
      track.scrollTo({ left: indexRef.current * track.clientWidth, behavior: "smooth" });
    }, AD_CAROUSEL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [count]);

  /** Manual advance. Wraps, so the arrows are never dead at either end.
   * Smooth scrolling is user-initiated here, but still skipped under
   * prefers-reduced-motion — the jump is instant instead. */
  function step(delta: number) {
    const track = trackRef.current;
    if (!track || count < 2) return;
    indexRef.current = (indexRef.current + delta + count) % count;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    track.scrollTo({
      left: indexRef.current * track.clientWidth,
      behavior: reduce ? "auto" : "smooth",
    });
  }

  if (ads !== null && count === 0 && !fallback) return null;
  return (
    <div
      className={cn(heightClass, "relative w-full", className)}
      data-testid={`ad-carousel-${slotKey}`}
    >
      {ads === null ? (
        <div
          className="h-full w-full animate-pulse rounded-card bg-ghost motion-reduce:animate-none"
          aria-hidden="true"
        />
      ) : count === 0 ? (
        fallback
      ) : (
        <>
          <div
            ref={trackRef}
            role="region"
            aria-label="Sponsored"
            onTouchStart={() => {
              pausedRef.current = true;
            }}
            onTouchEnd={() => {
              pausedRef.current = false;
            }}
            onMouseEnter={() => {
              pausedRef.current = true;
            }}
            onMouseLeave={() => {
              pausedRef.current = false;
            }}
            onScroll={(event) => {
              const el = event.currentTarget;
              const i = Math.round(el.scrollLeft / Math.max(el.clientWidth, 1));
              indexRef.current = i;
              setDot(i);
            }}
            className="flex h-full w-full snap-x snap-mandatory overflow-x-auto overscroll-x-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          >
            {ads.map((ad, i) => (
              <div key={ad.creative_id} className="h-full w-full flex-none snap-center">
                <AdUnit
                  ad={ad}
                  endpoint={endpoint}
                  eager={i === 0}
                  {...(badgeClassName ? { badgeClassName } : {})}
                  {...(sponsoredLabel ? { sponsoredLabel } : {})}
                />
              </div>
            ))}
          </div>
          {arrows && count > 1 ? (
            <>
              <CarouselArrow label={arrows.prevLabel} onClick={() => step(-1)} className="left-2">
                ‹
              </CarouselArrow>
              <CarouselArrow label={arrows.nextLabel} onClick={() => step(1)} className="right-2">
                ›
              </CarouselArrow>
            </>
          ) : null}
          {count > 1 ? (
            <div
              className="pointer-events-none absolute bottom-1 left-1/2 flex -translate-x-1/2 gap-1"
              aria-hidden="true"
            >
              {ads.map((ad, i) => (
                <span
                  key={ad.creative_id}
                  className={cn("h-1.5 w-1.5 rounded-pill", i === dot ? "bg-ink" : "bg-line")}
                />
              ))}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
