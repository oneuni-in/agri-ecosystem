"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * A-U1 — scroll reveal (A1 `.reveal`). Progressive enhancement in three
 * states, carried on `data-in` so descendants can join in with
 * `group-data-[in=…]/reveal:` variants (the sparkline draw, tile pop-in):
 *
 *   (no attr)        server HTML / no JS — fully visible, no motion. A guest
 *                    on a 2G connection never gets a blank section.
 *   data-in="false"  mounted, below the fold, motion allowed — hidden,
 *                    waiting on the IntersectionObserver.
 *   data-in="true"   intersected — fades/slides in once, then unobserves.
 *
 * `prefers-reduced-motion` short-circuits to "true" on mount (the reference
 * does exactly this) and the pending state additionally carries
 * `motion-reduce:` overrides, so content stays visible even if the media
 * query flips mid-session.
 */
export function Reveal({
  children,
  className,
  ...rest
}: {
  children: ReactNode;
  className?: string;
} & React.HTMLAttributes<HTMLDivElement>) {
  const ref = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"ssr" | "pending" | "in">("ssr");

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (
      matchMedia("(prefers-reduced-motion: reduce)").matches ||
      typeof IntersectionObserver === "undefined"
    ) {
      return; // stay "ssr": content painted, no motion
    }
    // Three rounds of AG-A8 CI evidence shaped this effect:
    // 1. Content in the first viewport must stay in "ssr" — not even a
    //    state flip. Hiding it repainted the largest above-fold text after
    //    hydration (LCP 2.4s→4.1s), and flipping straight to "in" re-
    //    rendered with transition/transform classes, layer-izing and
    //    repainting the subtree (LCP 4.4s).
    // 2. The visibility check must come from the observer's FIRST callback,
    //    not getBoundingClientRect(): a dozen instances interleaving rect
    //    reads with setState writes forced a layout each (~1s of observed
    //    Style & Layout that lantern simulated into ~2s of LCP delay). The
    //    observer delivers geometry async with zero forced layouts, and
    //    React batches every same-tick "pending" flip into one commit.
    let sawInitial = false;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!sawInitial) {
            sawInitial = true;
            const viewportBottom = e.rootBounds ? e.rootBounds.bottom : window.innerHeight;
            if (e.isIntersecting || e.boundingClientRect.top < viewportBottom) {
              io.disconnect(); // landed-on content never animates
              return;
            }
            setState("pending");
          } else if (e.isIntersecting) {
            io.disconnect();
            setState("in");
          }
        }
      },
      { threshold: 0.25 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      data-in={state === "ssr" ? undefined : state === "in"}
      className={cn(
        "group/reveal",
        state === "pending" &&
          "translate-y-3.5 opacity-0 motion-reduce:translate-y-0 motion-reduce:opacity-100",
        state === "in" &&
          "translate-y-0 opacity-100 transition-[opacity,transform] duration-500 ease-out",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}
