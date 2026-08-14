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
      setState("in");
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setState("in");
          io.disconnect();
        }
      },
      { threshold: 0.25 },
    );
    setState("pending");
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
