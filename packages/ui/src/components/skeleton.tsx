import { cn } from "../lib/cn";

/**
 * Placeholder that reserves the exact final dimensions — CLS must stay 0,
 * so width/height are required, not optional.
 */
export function Skeleton({
  width,
  height,
  className,
}: {
  width: string;
  height: string;
  className?: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-card bg-line motion-reduce:animate-none", className)}
      style={{ width, height }}
    />
  );
}
