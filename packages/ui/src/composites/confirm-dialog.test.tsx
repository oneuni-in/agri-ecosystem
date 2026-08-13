/**
 * ConfirmDialog is a client island; SSR renders the trigger only. The
 * reason-required contract (confirm disabled until a justification is typed,
 * `onConfirm(reason)` carries it to the mutation) is exercised end-to-end by
 * the Group B/C admin e2e — here we pin the closed-by-default shape, exactly
 * as confirm-action.test.tsx does for its U2 sibling.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Button } from "../components/button";
import { ConfirmDialog } from "./confirm-dialog";

describe("ConfirmDialog", () => {
  const html = renderToStaticMarkup(
    <ConfirmDialog
      trigger={<Button variant="ghost">Suspend business</Button>}
      title="Suspend this business?"
      description="It is hidden from consumer results immediately. Reinstating restores it."
      confirmLabel="Suspend"
      cancelLabel="Keep it live"
      reasonLabel="Reason"
      reasonHint="Recorded in the audit log with your name."
      onConfirm={() => {}}
    />,
  );

  it("renders the trigger, closed by default", () => {
    expect(html).toContain("Suspend business");
    expect(html).not.toContain("Keep it live"); // dialog content only mounts open
    expect(html).not.toContain("Recorded in the audit log");
  });
});
