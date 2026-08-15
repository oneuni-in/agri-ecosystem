"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A-U1 stats-band count format, exact from the A1 reference script:
 * thousands get Indian grouping and a trailing "+", small numbers render
 * bare (the "%"/unit suffix lives in the cell label, not here).
 */
export function formatCount(n: number): string {
  return n >= 1000 ? `${n.toLocaleString("en-IN")}+` : String(n);
}

/**
 * A-U1 — count-up stat value (A1 `[data-count]`). Server HTML carries the
 * FINAL number: a no-JS reader, a crawler and anyone with
 * `prefers-reduced-motion` sees the real value with zero script. With JS and
 * motion allowed, the value rewinds to 0 on mount and eases up (900ms,
 * cubic ease-out — the reference's curve) when the cell scrolls into view.
 *
 * The number itself must come from an API at the call site — never a
 * literal (build prompt §W1/14: "numbers from APIs, not literals").
 */
export function CountUp({ end, format = formatCount }: { end: number; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [text, setText] = useState(() => format(end));

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (
      matchMedia("(prefers-reduced-motion: reduce)").matches ||
      typeof IntersectionObserver === "undefined"
    ) {
      setText(format(end));
      return;
    }
    let raf = 0;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        io.disconnect();
        const t0 = performance.now();
        const dur = 900;
        const tick = (t: number) => {
          const p = Math.min((t - t0) / dur, 1);
          setText(format(Math.round(end * (1 - Math.pow(1 - p, 3)))));
          if (p < 1) raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      },
      { threshold: 0.25 },
    );
    setText(format(0));
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
    // Re-running on `end` keeps a late-arriving API value honest.
  }, [end, format]);

  return <span ref={ref}>{text}</span>;
}
