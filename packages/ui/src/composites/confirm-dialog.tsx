"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useId, useState, type ReactNode } from "react";

import { Button } from "../components/button";
import { ConsoleField, consoleControlClass } from "./console-patterns";

/**
 * The ADMIN destructive-action confirm (U3) — `ConfirmAction`'s sibling with
 * one non-negotiable addition: the justification is captured INSIDE the
 * confirm step (U3 audit rule 3), never in a follow-up, otherwise the audit
 * log fills with blanks. Confirm stays disabled until a reason is typed, and
 * `onConfirm` receives the trimmed reason to send with the mutation so the
 * audit row commits with it.
 *
 * Everything else keeps the U2 contract: two-step, the description names the
 * consequence in soft-delete-honest copy, `variant="brand"` confirm (the
 * palette deliberately has no destructive red), busy-disabled buttons, close
 * on success, stay open on failure so the caller's error notice has a home.
 */
export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel,
  cancelLabel,
  closeLabel = "Close",
  reasonLabel = "Reason",
  reasonHint,
  onConfirm,
}: {
  trigger: ReactNode;
  title: ReactNode;
  /** Names the consequence, e.g. "Hidden from consumer results immediately". */
  description: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  closeLabel?: string;
  reasonLabel?: string;
  /** e.g. "Recorded in the audit log with your name." */
  reasonHint?: string;
  /** Receives the trimmed justification; send it with the mutation. */
  onConfirm: (reason: string) => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const reasonId = useId();
  const ready = reason.trim().length > 0;

  const confirm = async () => {
    setBusy(true);
    try {
      await onConfirm(reason.trim());
      setOpen(false);
      setReason("");
    } catch {
      // The caller surfaces the failure; the dialog keeps the typed reason
      // so a retry does not start from a blank.
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (busy) return;
        setOpen(next);
        if (!next) setReason("");
      }}
    >
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
          <div className="mt-4">
            <ConsoleField id={reasonId} label={reasonLabel} hint={reasonHint}>
              <textarea
                id={reasonId}
                rows={3}
                value={reason}
                disabled={busy}
                onChange={(event) => setReason(event.target.value)}
                className={consoleControlClass}
              />
            </ConsoleField>
          </div>
          <div className="mt-4 flex gap-2">
            <Dialog.Close asChild>
              <Button variant="ghost" disabled={busy}>
                {cancelLabel}
              </Button>
            </Dialog.Close>
            <Button variant="brand" disabled={busy || !ready} onClick={() => void confirm()}>
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
