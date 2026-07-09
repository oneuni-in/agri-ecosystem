"use client";

import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * Client island. Fade-only entrance (reduced-motion safe); anatomy follows
 * the base card tokens (§1.4).
 */
export function Modal({
  trigger,
  title,
  description,
  children,
  closeLabel = "Close",
  className,
}: {
  trigger: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  closeLabel?: string;
  className?: string;
}) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[90] bg-ink/50" />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-[95] w-[calc(100vw-32px)] max-w-lg -translate-x-1/2 -translate-y-1/2",
            "rounded-card border border-line bg-card p-5 shadow-lift",
            className,
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <Dialog.Title className="font-display text-xl font-extrabold">{title}</Dialog.Title>
            <Dialog.Close
              aria-label={closeLabel}
              className="flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-btn bg-ghost text-base font-extrabold text-ink"
            >
              ✕
            </Dialog.Close>
          </div>
          {description ? (
            <Dialog.Description className="mt-1 text-[13px] text-sub">
              {description}
            </Dialog.Description>
          ) : null}
          {children ? <div className="mt-4">{children}</div> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
