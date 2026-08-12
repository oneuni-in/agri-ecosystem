"use client";

/** Kitchen-sink host for the U2 destructive-action confirm: the demo page is
 * a Server Component and `onConfirm` is a function, so the island mounts
 * here. Same pattern as U1BandsDemo. */
import { Button, ConfirmAction, ConsoleNotice } from "@agri/ui";
import { useState } from "react";

export function U2ConfirmDemo() {
  const [outcome, setOutcome] = useState<string | null>(null);

  return (
    <div className="flex max-w-[440px] flex-col gap-2">
      <div className="flex gap-2">
        <ConfirmAction
          trigger={<Button variant="ghost">Delete listing</Button>}
          title="Delete this listing?"
          description="It disappears from public results immediately. Our team can restore it if you change your mind."
          confirmLabel="Delete listing"
          cancelLabel="Keep it"
          onConfirm={() => setOutcome("Deleted (soft) — restorable by support.")}
        />
      </div>
      {outcome ? <ConsoleNotice tone="ok">{outcome}</ConsoleNotice> : null}
    </div>
  );
}
