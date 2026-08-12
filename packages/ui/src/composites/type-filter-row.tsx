import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "../lib/cn";

/** Horizontally scrollable filter row (`.typefilters`), milk.in pattern. */
export function TypeFilterRow({
  children,
  label,
  className,
  ...rest
}: {
  children: ReactNode;
  /** Accessible group label, e.g. "Milk type". */
  label: string;
  className?: string;
} & Omit<React.HTMLAttributes<HTMLDivElement>, "children" | "className">) {
  return (
    <div
      role="group"
      aria-label={label}
      className={cn("flex gap-[9px] overflow-x-auto pb-1 pt-3.5", className)}
      {...rest}
    >
      {children}
    </div>
  );
}

/** 86px-min chip (`.tf`); active = brand border + brand-soft bg. */
export function TypeFilter({
  icon,
  label,
  vernacular,
  active = false,
  className,
  ...props
}: {
  icon: ReactNode;
  label: ReactNode;
  vernacular?: ReactNode;
  active?: boolean;
  className?: string;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className">) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        "flex min-w-[86px] shrink-0 flex-col items-center gap-[3px] rounded-card border-2 border-line bg-card px-3.5 py-2.5 text-ink",
        active && "border-brand bg-brand-soft",
        className,
      )}
      {...props}
    >
      <span aria-hidden="true" className="text-[26px] leading-none">
        {icon}
      </span>
      <b className="text-xs">
        {label}
        {vernacular ? <span className="vern">{vernacular}</span> : null}
      </b>
    </button>
  );
}
