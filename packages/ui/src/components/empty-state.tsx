import type { ReactNode } from "react";

import { cn } from "../lib/cn";

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-2 rounded-card border border-line bg-card p-8 text-center",
        className,
      )}
    >
      <span className="text-[44px] leading-none" aria-hidden="true">
        {icon}
      </span>
      <p className="text-[15.5px] font-extrabold">{title}</p>
      {description ? <p className="text-[12.5px] text-sub">{description}</p> : null}
      {action ? <div className="mt-2 flex w-full max-w-[280px]">{action}</div> : null}
    </div>
  );
}
