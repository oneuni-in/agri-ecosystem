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

export function AdCarousel({
  slotKey,
  pincode,
  locale,
  endpoint = "/api/ads",
  heightClass,
  className,
  fallback,
}: {
  slotKey: string;
  pincode?: string | null;
  locale?: string;
  endpoint?: string;
  heightClass: string;
  className?: string;
  fallback?: ReactNode;
}) {
  const [ads, setAds] = useState<ServedAd[] | null>(null); // null = loading
  const trackRef = useRef<HTMLDivElement | null>(null);
  const pausedRef = useRef(false);
  const indexRef = useRef(0);
  const [dot, setDot] = useState(0);

  useEffect(() => {
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
  }, [slotKey, pincode, locale, endpoint]);

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
                <AdUnit ad={ad} endpoint={endpoint} eager={i === 0} />
              </div>
            ))}
          </div>
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
