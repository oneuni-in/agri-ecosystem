"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useState, type ReactNode } from "react";

import { Button } from "../components/button";

/**
 * The console's destructive-action confirm (U2). Client island.
 *
 * Two-step by design: the trigger opens a dialog that names the consequence;
 * nothing is mutated until the explicit confirm. The confirm button is
 * `variant="brand"` — the palette deliberately has no destructive red, and
 * the web-admin enforcement console set the convention (suspend/disable
 * confirm the same way). Removals behind this dialog are SOFT deletes on the
 * backend; the copy should say what actually happens ("hidden from public
 * results"), never promise a hard erase.
 *
 * `onConfirm` may be async: the dialog disables both buttons while it runs,
 * closes on success, and stays open (re-enabled) on failure so the caller's
 * error notice has a visible home.
 */
export function ConfirmAction({
  trigger,
  title,
  description,
  confirmLabel,
  cancelLabel,
  closeLabel = "Close",
  onConfirm,
}: {
  trigger: ReactNode;
  title: ReactNode;
  /** Names the consequence, e.g. "This hides the listing from buyers…". */
  description: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  closeLabel?: string;
  onConfirm: () => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const confirm = async () => {
    setBusy(true);
    try {
      await onConfirm();
      setOpen(false);
    } catch {
      // The caller surfaces the failure (notice/toast); the dialog just
      // returns control so the user can retry or cancel.
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={(next) => (busy ? undefined : setOpen(next))}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[90] bg-ink/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[95] w-[calc(100vw-32px)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-card border border-line bg-card p-5 shadow-lift">
          <div className="flex items-start justify-between gap-3">
            <Dialog.Title className="font-display text-xl font-extrabold">{title}</Dialog.Title>
            <Dialog.Close
              aria-label={closeLabel}
              disabled={busy}
              className="flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-btn bg-ghost text-base font-extrabold text-ink"
            >
              ✕
            </Dialog.Close>
          </div>
          <Dialog.Description className="mt-1 text-[13px] text-sub">
            {description}
          </Dialog.Description>
          <div className="mt-4 flex gap-2">
            <Dialog.Close asChild>
              <Button variant="ghost" disabled={busy}>
                {cancelLabel}
              </Button>
            </Dialog.Close>
            <Button variant="brand" disabled={busy} onClick={() => void confirm()}>
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
