import { cn } from "../lib/cn";
import { isSafeMediaUrl } from "../lib/sponsored";

/**
 * Atom (M2): the ONLY way ad media reaches a page - a plain sanitized <img>,
 * never HTML/script creatives (v1 contract). Unsafe URLs render nothing.
 * `eager` is for carousel slide 1 only (rural data reality: everything else
 * stays lazy).
 */
export function AdImage({
  src,
  alt,
  eager = false,
  className,
}: {
  src: string;
  alt: string;
  eager?: boolean;
  className?: string;
}) {
  if (!isSafeMediaUrl(src)) return null;
  return (
    <img
      src={src}
      alt={alt}
      loading={eager ? "eager" : "lazy"}
      // The eager slide is the hero, i.e. the LCP element. Without an explicit
      // high priority the preload scanner still queues it behind the page's
      // other subresources (Lighthouse: prioritize-lcp-image, 466ms).
      {...(eager ? { fetchPriority: "high" as const } : {})}
      decoding="async"
      draggable={false}
      className={cn("h-full w-full object-cover", className)}
    />
  );
}
