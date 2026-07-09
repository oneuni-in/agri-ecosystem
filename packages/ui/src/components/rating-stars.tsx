import { cn } from "../lib/cn";

/** `★ 4.7` — number-first textual pattern, never icon rows (design-system.md §2). */
export function RatingStars({ value, className }: { value: number | string; className?: string }) {
  return <span className={cn("text-[13px] font-extrabold text-rating", className)}>★ {value}</span>;
}
