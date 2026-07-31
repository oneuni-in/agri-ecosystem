import { Badge } from "./badge";

/**
 * Atom (M2): the always-visible ad label (UX law 5). Thin alias over
 * <Badge variant="sponsored"> - that variant type-forbids children, so the
 * "★ Sponsored" text can never be overridden or omitted.
 */
export function SponsoredBadge({ className }: { className?: string }) {
  return <Badge variant="sponsored" {...(className ? { className } : {})} />;
}
