"use client";

import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * The admin row-detail panel (U3): a right-side sheet the console opens from
 * `AdminDataTable`'s row-open action. CONTROLLED by design — the opener is a
 * table row elsewhere in the tree, so the caller owns `open`/`onOpenChange`
 * (unlike the self-contained `Modal`/`ConfirmDialog` trigger pattern).
 *
 * Client island. No entrance animation (the Modal precedent — reduced-motion
 * safe by having no motion to reduce). Radix gives focus trap, Escape close,
 * and overlay dismiss.
 */
export function DetailDrawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  closeLabel = "Close",
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  closeLabel?: string;
  className?: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[90] bg-ink/50" />
        <Dialog.Content
          className={cn(
            "fixed inset-y-0 right-0 z-[95] w-full max-w-md overflow-y-auto border-l border-line bg-card p-5 shadow-lift",
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
          <div className="mt-4">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
