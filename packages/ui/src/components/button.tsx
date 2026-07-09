import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "../lib/cn";

/**
 * Mockup `.abtn` recipes (design-system.md §2). All variants ≥44px tall,
 * flex-1 so action rows split evenly, 800 weight.
 */
export const buttonVariants = cva(
  "inline-flex min-h-[44px] flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-btn px-2 py-3 text-sm font-extrabold transition-[transform,box-shadow] duration-150 motion-reduce:transition-none",
  {
    variants: {
      variant: {
        call: "bg-call text-white",
        wa: "border-[1.5px] border-wa-line bg-wa-soft text-wa-deep",
        ghost: "bg-ghost text-ink",
        brand: "bg-brand text-white",
      },
    },
    defaultVariants: { variant: "ghost" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={cn(buttonVariants({ variant }), className)} {...props} />;
}

interface ActionButtonProps {
  label: string;
  /** `tel:` / `https://wa.me/...` — renders an anchor when given. */
  href?: string;
  className?: string;
}

/** Call leads every vendor card — forms never do (UX law 4). Emoji-prefixed. */
export function CallButton({ label, href, className }: ActionButtonProps) {
  if (href) {
    return (
      <a href={href} className={cn(buttonVariants({ variant: "call" }), "no-underline", className)}>
        📞 {label}
      </a>
    );
  }
  return <Button variant="call" className={className}>📞 {label}</Button>;
}

export function WhatsAppButton({ label, href, className }: ActionButtonProps) {
  if (href) {
    return (
      <a href={href} className={cn(buttonVariants({ variant: "wa" }), "no-underline", className)}>
        {label}
      </a>
    );
  }
  return <Button variant="wa" className={className}>{label}</Button>;
}
