/**
 * ProfileNudge (D11.E): "Complete your profile — 60%" strip any app can embed.
 * Presentational + server-safe: the app supplies translated title/cta (with
 * the score already interpolated) and the link into id.agri.in's /account.
 * Renders nothing once the profile is complete.
 */
import type { JSX } from "react";

import { cn } from "../lib/cn";
import { buttonVariants } from "./button";
import { Card } from "./card";

export function clampScore(score: number): number {
  return Math.min(100, Math.max(0, Math.round(score)));
}

export interface ProfileNudgeProps {
  score: number;
  href: string;
  title: string;
  cta: string;
  className?: string;
}

export function ProfileNudge({
  score,
  href,
  title,
  cta,
  className,
}: ProfileNudgeProps): JSX.Element | null {
  const clamped = clampScore(score);
  if (clamped >= 100) return null;
  return (
    <Card className={cn("flex items-center gap-4 p-4", className)}>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-ink">{title}</p>
        <div
          className="mt-2 h-2 rounded-pill bg-line"
          role="progressbar"
          aria-valuenow={clamped}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={title}
        >
          <div className="h-2 rounded-pill bg-brand" style={{ width: `${clamped}%` }} />
        </div>
      </div>
      <a href={href} className={cn(buttonVariants({ variant: "brand" }), "shrink-0")}>
        {cta}
      </a>
    </Card>
  );
}
