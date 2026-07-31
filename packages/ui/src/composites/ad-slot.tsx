"use client";

/**
 * AdSlot (M2): the one ad primitive. Vertical-agnostic - a slot key + context
 * in, an approved creative out. Contracts (SPEC M2 non-negotiables):
 * - renders ONLY what /ads/serve returns (the backend serves approved-only;
 *   the parse layer additionally drops anything unlabeled - NN1 defense in
 *   depth)
 * - reserved fixed-height box while loading; empty -> fallback or collapse
 *   (NN3: CLS 0 empty/loading/full)
 * - impression beacon fires at >=50% viewport visibility, once, NEVER on
 *   mount (NN2); click beacon on click; both land in the D21 partitioned
 *   tracking tables (server dedupes per viewer/placement, 60s window)
 * - sendBeacon with keepalive-fetch fallback (view-beacon.tsx precedent)
 */
import { type ReactNode, useEffect, useRef, useState } from "react";

import { AdImage } from "../components/ad-image";
import { SponsoredBadge } from "../components/sponsored-badge";
import { cn } from "../lib/cn";
import { pincodeFromCookieHeader } from "../lib/location";
import {
  type AdServeContext,
  parseServeResponse,
  type ServedAd,
  serveQuery,
} from "../lib/sponsored";

export function sendAdBeacon(url: string, ad: ServedAd): void {
  const body = JSON.stringify({
    placement_id: ad.placement_id,
    creative_id: ad.creative_id,
    slot_key: ad.slot_key,
  });
  try {
    if (navigator.sendBeacon?.(url, new Blob([body], { type: "application/json" }))) return;
  } catch {
    /* fall through to fetch */
  }
  fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => undefined);
}

/** Impression ref: fires once when >=50% of the element is in the viewport.
 * No IntersectionObserver (very old browsers) -> no impression at all;
 * firing blind on mount is the one thing this must never do (NN2). */
export function useImpression(ad: ServedAd | null, endpoint: string) {
  const ref = useRef<HTMLAnchorElement | null>(null);
  // Keyed on the ad object, not a boolean: React StrictMode re-runs effects
  // (unmount/remount) in dev, and a boolean reset there double-fired the
  // beacon for the SAME ad. A new ad object still gets a fresh lifecycle.
  const fired = useRef<ServedAd | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!ad || !el || fired.current === ad) return;
    if (typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => {
        if (fired.current === ad) return;
        if (entries.some((entry) => entry.isIntersecting)) {
          fired.current = ad;
          sendAdBeacon(`${endpoint}/impressions`, ad);
          io.disconnect();
        }
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ad, endpoint]);
  return ref;
}

function sameOrigin(url: string): boolean {
  try {
    return new URL(url).origin === window.location.origin;
  } catch {
    return false;
  }
}

/** One rendered creative: image variant when media exists, copy-only house
 * card otherwise. Plain text rendering everywhere (React escaping - never
 * dangerouslySetInnerHTML). */
export function AdUnit({
  ad,
  endpoint,
  eager = false,
}: {
  ad: ServedAd;
  endpoint: string;
  eager?: boolean;
}) {
  const ref = useImpression(ad, endpoint);
  const external = typeof window !== "undefined" && !sameOrigin(ad.target_url);
  return (
    <a
      ref={ref}
      href={ad.target_url}
      {...(external
        ? { target: "_blank", rel: "noopener nofollow sponsored" }
        : { rel: "nofollow sponsored" })}
      onClick={() => sendAdBeacon(`${endpoint}/clicks`, ad)}
      className="relative block h-full w-full overflow-hidden rounded-card no-underline"
      data-testid={`ad-unit-${ad.slot_key}`}
    >
      {ad.media_urls[0] ? (
        <AdImage src={ad.media_urls[0]} alt={ad.title} eager={eager} />
      ) : (
        <span className="flex h-full w-full flex-col items-center justify-center gap-0.5 rounded-card border border-line bg-brand-soft px-4 text-center">
          <span className="text-[14px] font-extrabold leading-tight text-ink">{ad.title}</span>
          {ad.body ? (
            <span className="line-clamp-1 text-[12px] leading-tight text-sub">{ad.body}</span>
          ) : null}
        </span>
      )}
      <SponsoredBadge className="absolute left-2 top-2" />
    </a>
  );
}

export function AdSlot({
  slotKey,
  category,
  pincode,
  locale,
  endpoint = "/api/ads",
  heightClass,
  className,
  fallback,
}: {
  slotKey: string;
  category?: string;
  /** Explicit pincode context; omit to read the agri_loc cookie client-side
   * (undefined = cookie, null = deliberately no pincode). */
  pincode?: string | null;
  locale?: string;
  endpoint?: string;
  /** Fixed-height tailwind class(es), e.g. "h-[72px] sm:h-[90px]" — the CLS
   * reservation. Required so a slot can never be mounted without one. */
  heightClass: string;
  className?: string;
  /** Rendered when the engine returns nothing (flag off, no fill, blocked).
   * Omit to collapse the slot entirely. */
  fallback?: ReactNode;
}) {
  const [ad, setAd] = useState<ServedAd | null>(null);
  const [state, setState] = useState<"loading" | "empty" | "ready">("loading");
  useEffect(() => {
    let cancelled = false;
    const ctx: AdServeContext = {
      pincode: pincode !== undefined ? pincode : pincodeFromCookieHeader(document.cookie),
      category,
      locale,
    };
    fetch(`${endpoint}/serve?${serveQuery(slotKey, ctx)}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: unknown) => {
        if (cancelled) return;
        const ads = data === null ? [] : parseServeResponse(data);
        if (ads[0]) {
          setAd(ads[0]);
          setState("ready");
        } else {
          setState("empty");
        }
      })
      .catch(() => {
        if (!cancelled) setState("empty");
      });
    return () => {
      cancelled = true;
    };
  }, [slotKey, category, pincode, locale, endpoint]);

  if (state === "empty" && !fallback) return null;
  return (
    <div className={cn(heightClass, "w-full", className)} data-testid={`ad-slot-${slotKey}`}>
      {state === "ready" && ad ? (
        <AdUnit ad={ad} endpoint={endpoint} />
      ) : state === "empty" ? (
        fallback
      ) : (
        <div
          className="h-full w-full animate-pulse rounded-card bg-ghost motion-reduce:animate-none"
          aria-hidden="true"
        />
      )}
    </div>
  );
}
